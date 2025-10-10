/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * NXP Simulated Temperature Sensor Driver
 * 
 * This driver simulates a hardware temperature sensor using a platform driver
 * approach. It provides:
 * - Character device interface for reading temperature samples
 * - poll/epoll support for event-driven reading
 * - sysfs interface for configuration
 * - ioctl interface for batch operations
 * - Device Tree binding support
 * 
 * Copyright (c) 2025 Armando Mares
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/of_device.h>
#include <linux/miscdevice.h>
#include <linux/atomic.h>
#include <linux/fs.h>
#include <linux/random.h>
#include <linux/ktime.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/poll.h>
#include <linux/hrtimer.h>
#include <linux/workqueue.h>
#include <linux/jiffies.h>
#include <linux/kfifo.h>
#include <linux/wait.h>

#include "nxp_simtemp.h"
#include "nxp_simtemp_ioctl.h"

MODULE_AUTHOR("Armando Mares");
MODULE_DESCRIPTION("NXP Simulated Temperature Sensor Driver");
MODULE_LICENSE("GPL v2");
MODULE_VERSION("1.0.0");

/* Global variables */
static struct simtemp_device *g_simtemp_dev = NULL;


static s32 simtemp_get_base_temperature(struct simtemp_device *simtemp)
{
	static int counter = 0;
	int temp;

	int angle = (counter * 300) % 6280;
	int sine_approx;

	switch (simtemp->mode) {
	case SIMTEMP_MODE_NORMAL:

		if (angle < 1570)
			sine_approx = (angle * 1000) / 1570;
		else if (angle < 4710)
			sine_approx = 1000 - ((angle - 1570) * 1000) / 1570;
		else
			sine_approx = -((angle - 4710) * 1000) / 1570;

		temp = SIMTEMP_BASE_TEMP_MC + (10000 * sine_approx) / 1000;
		break;

	case SIMTEMP_MODE_NOISY:
		{
			int noise;
			get_random_bytes(&noise, sizeof(noise));
			noise = noise % SIMTEMP_NOISE_RANGE_MC; 
		
			if (angle < 1570)
				sine_approx = (angle * 1000) / 1570;
			else if (angle < 4710)
				sine_approx = 1000 - ((angle - 1570) * 1000) / 1570;
			else
				sine_approx = -((angle - 4710) * 1000) / 1570;

			temp = SIMTEMP_BASE_TEMP_MC + (SIMTEMP_TEMP_RANGE_MC * sine_approx) / 1000;
			temp += noise; 
		}
		break;

	case SIMTEMP_MODE_RAMP:
	{
		int k = counter % 200;
		int up = (k <= 100);
		int frac = k % 100;
		int ramp = up ? (frac * SIMTEMP_TEMP_RANGE_MC / 100)
			      : ((200 - k) * SIMTEMP_TEMP_RANGE_MC / 100);
		temp = SIMTEMP_BASE_TEMP_MC + ramp;
		break;
	}

	default:
		temp = 0; 
		break;
	}
	counter++;
	return temp;
}

int simtemp_generate_sample(struct simtemp_device *simtemp)
{
	struct simtemp_sample sample;
	unsigned long flags;
	bool threshold_event = false;
	int ret;
	
	if (!simtemp->enabled)
		return 0;
	
	sample.timestamp_ns = ktime_get_ns();
	sample.temp_mC = simtemp_get_base_temperature(simtemp);
	sample.flags = SIMTEMP_FLAG_NEW_SAMPLE;
	
	if ((simtemp->last_temp_mC < simtemp->threshold_mC && 
	     sample.temp_mC >= simtemp->threshold_mC) ||
	    (simtemp->last_temp_mC >= simtemp->threshold_mC && 
	     sample.temp_mC < simtemp->threshold_mC)) {
		sample.flags |= SIMTEMP_FLAG_THRESHOLD_CROSSED;
		threshold_event = true;
		simtemp->stats.alerts++;
	}
	
	simtemp->last_temp_mC = sample.temp_mC;
	
	spin_lock_irqsave(&simtemp->buffer_lock, flags);
	ret = kfifo_put(&simtemp->sample_buffer, sample);
	spin_unlock_irqrestore(&simtemp->buffer_lock, flags);
	
	if (!ret) {
		simtemp->stats.last_error = -EOVERFLOW;
		simtemp_warn(simtemp, "Sample buffer overflow\n");
	} else {
		simtemp->stats.updates++;
	}
	
	wake_up_interruptible(&simtemp->wait_queue);
	
	simtemp_dbg(simtemp, "Generated sample: temp=%d.%03d°C, flags=0x%x\n",
		    sample.temp_mC / 1000, abs(sample.temp_mC % 1000), sample.flags);
	
	return 0;
}

void simtemp_sample_work(struct work_struct *work)
{
	struct simtemp_device *simtemp = container_of(work, struct simtemp_device, sample_work);
	simtemp_generate_sample(simtemp);
}

enum hrtimer_restart simtemp_timer_callback(struct hrtimer *timer)
{
	struct simtemp_device *simtemp = container_of(timer, struct simtemp_device, timer);

	schedule_work(&simtemp->sample_work);

	if (simtemp->enabled) {
		hrtimer_forward_now(timer, ms_to_ktime(simtemp->sampling_ms));
		return HRTIMER_RESTART;
	}
	
	return HRTIMER_NORESTART;
}

static int simtemp_open(struct inode *inode, struct file *file)
{
	struct simtemp_device *simtemp = container_of(file->private_data, struct simtemp_device, misc_dev);
	
	if (atomic_inc_return(&simtemp->open_count) == 1) {
		simtemp_info(simtemp, "Device opened\n");
	}
	
	file->private_data = simtemp;
	return 0;
}

static int simtemp_release(struct inode *inode, struct file *file)
{
	struct simtemp_device *simtemp = file->private_data;
	
	if (atomic_dec_return(&simtemp->open_count) == 0) {
		simtemp_info(simtemp, "Device closed\n");
	}
	
	return 0;
}

static __poll_t simtemp_poll(struct file *file, struct poll_table_struct *wait)
{
	struct simtemp_device *simtemp = file->private_data;
	__poll_t mask = 0;
	
	simtemp->stats.poll_calls++;
	
	poll_wait(file, &simtemp->wait_queue, wait);
	
	if (!kfifo_is_empty(&simtemp->sample_buffer))
		mask |= EPOLLIN | EPOLLRDNORM;
	
	return mask;
}


static ssize_t simtemp_read(struct file *file, char __user *buf, size_t count, loff_t *ppos)
{
	struct simtemp_device *simtemp = file->private_data;
	struct simtemp_sample sample;
	unsigned long flags;
	int ret;
	
	simtemp->stats.read_calls++;
	
	if (count < sizeof(struct simtemp_sample))
		return -EINVAL;
	
	if (kfifo_is_empty(&simtemp->sample_buffer)) {
		if (file->f_flags & O_NONBLOCK)
			return -EAGAIN;
		
		ret = wait_event_interruptible(simtemp->wait_queue,
					       !kfifo_is_empty(&simtemp->sample_buffer));
		if (ret)
			return ret;
	}
	
	spin_lock_irqsave(&simtemp->buffer_lock, flags);
	ret = kfifo_get(&simtemp->sample_buffer, &sample);
	spin_unlock_irqrestore(&simtemp->buffer_lock, flags);
	
	if (!ret)
		return -EAGAIN;
	
	if (copy_to_user(buf, &sample, sizeof(sample)))
		return -EFAULT;
	
	return sizeof(struct simtemp_sample);
}

static long simtemp_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct simtemp_device *simtemp = file->private_data;
	struct simtemp_config config;
	struct simtemp_ioctl_stats stats;
	int ret = 0;
	
	if (_IOC_TYPE(cmd) != SIMTEMP_IOC_MAGIC)
		return -ENOTTY;
	if (_IOC_NR(cmd) > SIMTEMP_IOC_MAXNR)
		return -ENOTTY;
	
	switch (cmd) {
	case SIMTEMP_IOC_GET_CONFIG:
		config.sampling_ms = simtemp->sampling_ms;
		config.threshold_mC = simtemp->threshold_mC;
		config.mode = simtemp->mode;
		config.flags = 0;

		if (copy_to_user((void __user *)arg, &config, sizeof(config))) {
			ret = -EFAULT;
		}
		break;
		
	case SIMTEMP_IOC_SET_CONFIG:
		if (copy_from_user(&config, (void __user *)arg, sizeof(config))) {
			ret = -EFAULT;
			break;
		}
		
		if (config.sampling_ms < SIMTEMP_MIN_SAMPLING_MS ||
		    config.sampling_ms > SIMTEMP_MAX_SAMPLING_MS ||
		    config.mode >= SIMTEMP_MODE_MAX) {
			ret = -EINVAL;
			break;
		}
		
		simtemp->sampling_ms = config.sampling_ms;
		simtemp->threshold_mC = config.threshold_mC;
		simtemp->mode = config.mode;
		break;
		
	case SIMTEMP_IOC_GET_STATS:
		stats.updates = simtemp->stats.updates;
		stats.alerts = simtemp->stats.alerts;
		stats.read_calls = simtemp->stats.read_calls;
		stats.poll_calls = simtemp->stats.poll_calls;
		stats.last_error = simtemp->stats.last_error;
		stats.buffer_usage = (kfifo_len(&simtemp->sample_buffer) * 100) / SIMTEMP_BUFFER_SIZE;
		
		if (copy_to_user((void __user *)arg, &stats, sizeof(stats)))
			ret = -EFAULT;
		break;
		
	case SIMTEMP_IOC_RESET_STATS:
		memset(&simtemp->stats, 0, sizeof(simtemp->stats));
		break;
		
	case SIMTEMP_IOC_ENABLE:
		if (!simtemp->enabled) {
			simtemp->enabled = true;
			hrtimer_start(&simtemp->timer, ms_to_ktime(simtemp->sampling_ms), HRTIMER_MODE_REL);
		}
		break;
		
	case SIMTEMP_IOC_DISABLE:
		simtemp->enabled = false;
		hrtimer_cancel(&simtemp->timer);
		break;
		
	case SIMTEMP_IOC_FLUSH_BUFFER:
		kfifo_reset(&simtemp->sample_buffer);
		break;
		
	default:
		ret = -ENOTTY;
		break;
	}
	
	return ret;
}

static const struct file_operations simtemp_fops = {
	.owner = THIS_MODULE,
	.open = simtemp_open,
	.release = simtemp_release,
	.read = simtemp_read,
	.poll = simtemp_poll,
	.unlocked_ioctl = simtemp_ioctl,
	.llseek = noop_llseek,
};

static ssize_t sampling_ms_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	struct simtemp_device *simtemp = dev_get_drvdata(dev);
	return sprintf(buf, "%u\n", simtemp->sampling_ms);
}

static ssize_t threshold_mC_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	struct simtemp_device *simtemp = dev_get_drvdata(dev);
	return sprintf(buf, "%d\n", simtemp->threshold_mC);
}

static ssize_t mode_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	struct simtemp_device *simtemp = dev_get_drvdata(dev);
	const char *mode_names[] = {"normal", "noisy", "ramp"};
	
	if (simtemp->mode >= ARRAY_SIZE(mode_names))
		return sprintf(buf, "unknown\n");
	
	return sprintf(buf, "%s\n", mode_names[simtemp->mode]);
}

static ssize_t stats_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	struct simtemp_device *simtemp = dev_get_drvdata(dev);
	return sprintf(buf, "updates: %lu\nalerts: %lu\nread_calls: %lu\npoll_calls: %lu\nlast_error: %d\nbuffer_usage: %u%%\n",
		       simtemp->stats.updates, simtemp->stats.alerts,
		       simtemp->stats.read_calls, simtemp->stats.poll_calls,
		       simtemp->stats.last_error,
		       (kfifo_len(&simtemp->sample_buffer) * 100) / SIMTEMP_BUFFER_SIZE);
}
static DEVICE_ATTR_RO(stats);

static ssize_t enabled_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	struct simtemp_device *simtemp = dev_get_drvdata(dev);
	return sprintf(buf, "%d\n", simtemp->enabled ? 1 : 0);
}

static ssize_t sampling_ms_store(struct device *dev, struct device_attribute *attr,
				 const char *buf, size_t count)
{
	struct simtemp_device *simtemp = dev_get_drvdata(dev);
	unsigned int val;
	int ret;
	
	ret = kstrtouint(buf, 10, &val);
	if (ret)
		return ret;
	
	if (val < SIMTEMP_MIN_SAMPLING_MS || val > SIMTEMP_MAX_SAMPLING_MS)
		return -EINVAL;
	
	mutex_lock(&simtemp->config_lock);
	simtemp->sampling_ms = val;
	mutex_unlock(&simtemp->config_lock);
	
	return count;
}
static DEVICE_ATTR_RW(sampling_ms);

static ssize_t threshold_mC_store(struct device *dev, struct device_attribute *attr,
				  const char *buf, size_t count)
{
	struct simtemp_device *simtemp = dev_get_drvdata(dev);
	int val;
	int ret;
	
	ret = kstrtoint(buf, 10, &val);
	if (ret)
		return ret;
	
	mutex_lock(&simtemp->config_lock);
	simtemp->threshold_mC = val;
	mutex_unlock(&simtemp->config_lock);
	
	return count;
}
static DEVICE_ATTR_RW(threshold_mC);

static ssize_t mode_store(struct device *dev, struct device_attribute *attr,
			 const char *buf, size_t count)
{
	struct simtemp_device *simtemp = dev_get_drvdata(dev);
	enum simtemp_mode mode;
	
	if (sysfs_streq(buf, "normal"))
		mode = SIMTEMP_MODE_NORMAL;
	else if (sysfs_streq(buf, "noisy"))
		mode = SIMTEMP_MODE_NOISY;
	else if (sysfs_streq(buf, "ramp"))
		mode = SIMTEMP_MODE_RAMP;
	else
		return -EINVAL;
	
	mutex_lock(&simtemp->config_lock);
	simtemp->mode = mode;
	mutex_unlock(&simtemp->config_lock);
	
	return count;
}
static DEVICE_ATTR_RW(mode);

static ssize_t enabled_store(struct device *dev, struct device_attribute *attr,
			    const char *buf, size_t count)
{
	struct simtemp_device *simtemp = dev_get_drvdata(dev);
	bool val;
	int ret;
	
	ret = kstrtobool(buf, &val);
	if (ret)
		return ret;
	
	mutex_lock(&simtemp->config_lock);
	if (val && !simtemp->enabled) {
		simtemp->enabled = true;
		hrtimer_start(&simtemp->timer, ms_to_ktime(simtemp->sampling_ms), HRTIMER_MODE_REL);
	} else if (!val && simtemp->enabled) {
		simtemp->enabled = false;
		hrtimer_cancel(&simtemp->timer);
	}
	mutex_unlock(&simtemp->config_lock);
	
	return count;
}
static DEVICE_ATTR_RW(enabled);

static struct attribute *simtemp_attrs[] = {
	&dev_attr_sampling_ms.attr,
	&dev_attr_threshold_mC.attr,
	&dev_attr_mode.attr,
	&dev_attr_stats.attr,
	&dev_attr_enabled.attr,
	NULL,
};

static const struct attribute_group simtemp_attr_group = {
	.attrs = simtemp_attrs,
};

int simtemp_sysfs_init(struct simtemp_device *simtemp)
{
	return sysfs_create_group(&simtemp->misc_dev.this_device->kobj, &simtemp_attr_group);
}

void simtemp_sysfs_cleanup(struct simtemp_device *simtemp)
{
	sysfs_remove_group(&simtemp->misc_dev.this_device->kobj, &simtemp_attr_group);
}

static int simtemp_parse_dt(struct simtemp_device *simtemp, struct device_node *np)
{
	int ret;
	
	ret = of_property_read_u32(np, "sampling-ms", &simtemp->dt_sampling_ms);
	if (ret) {
		simtemp->dt_sampling_ms = SIMTEMP_DEFAULT_SAMPLING_MS;
		simtemp_info(simtemp, "Using default sampling period: %u ms\n", 
			     simtemp->dt_sampling_ms);
	}
	
	ret = of_property_read_s32(np, "threshold-mC", &simtemp->dt_threshold_mC);
	if (ret) {
		simtemp->dt_threshold_mC = SIMTEMP_DEFAULT_THRESHOLD_MC;
		simtemp_info(simtemp, "Using default threshold: %d mC\n", 
			     simtemp->dt_threshold_mC);
	}
	
	simtemp_info(simtemp, "DT config: sampling=%u ms, threshold=%d mC\n",
		     simtemp->dt_sampling_ms, simtemp->dt_threshold_mC);
	
	return 0;
}

static int simtemp_probe(struct platform_device *pdev)
{
	struct simtemp_device *simtemp;
	struct device_node *np = pdev->dev.of_node;
	int ret;
	
	simtemp = devm_kzalloc(&pdev->dev, sizeof(*simtemp), GFP_KERNEL);
	if (!simtemp)
		return -ENOMEM;
	
	simtemp->pdev = pdev;
	simtemp->dev = &pdev->dev;
	platform_set_drvdata(pdev, simtemp);
	
	if (np) {
		ret = simtemp_parse_dt(simtemp, np);
		if (ret)
			return ret;
	} else {
		simtemp->dt_sampling_ms = SIMTEMP_DEFAULT_SAMPLING_MS;
		simtemp->dt_threshold_mC = SIMTEMP_DEFAULT_THRESHOLD_MC;
	}
	
	simtemp->sampling_ms = simtemp->dt_sampling_ms;
	simtemp->threshold_mC = simtemp->dt_threshold_mC;
	simtemp->mode = SIMTEMP_MODE_NORMAL;
	simtemp->enabled = false;
	simtemp->last_temp_mC = SIMTEMP_BASE_TEMP_MC;
	
	mutex_init(&simtemp->config_lock);
	spin_lock_init(&simtemp->buffer_lock);
	init_waitqueue_head(&simtemp->wait_queue);
	atomic_set(&simtemp->open_count, 0);
	
	INIT_KFIFO(simtemp->sample_buffer);
	
	hrtimer_init(&simtemp->timer, CLOCK_MONOTONIC, HRTIMER_MODE_REL);
	simtemp->timer.function = simtemp_timer_callback;
	INIT_WORK(&simtemp->sample_work, simtemp_sample_work);
	
	simtemp->misc_dev.minor = MISC_DYNAMIC_MINOR;
	simtemp->misc_dev.name = "simtemp";
	simtemp->misc_dev.fops = &simtemp_fops;
	simtemp->misc_dev.parent = &pdev->dev;
	
	ret = misc_register(&simtemp->misc_dev);
	if (ret) {
		dev_err(&pdev->dev, "Failed to register misc device: %d\n", ret);
		return ret;
	}
	
	ret = simtemp_sysfs_init(simtemp);
	if (ret) {
		dev_err(&pdev->dev, "Failed to create sysfs attributes: %d\n", ret);
		misc_deregister(&simtemp->misc_dev);
		return ret;
	}
	
	g_simtemp_dev = simtemp;
	
	dev_info(&pdev->dev, "NXP simtemp driver probed successfully\n");
	
	return 0;
}

static void simtemp_remove(struct platform_device *pdev)
{
	struct simtemp_device *simtemp = platform_get_drvdata(pdev);
	
	mutex_lock(&simtemp->config_lock);
	simtemp->enabled = false;
	mutex_unlock(&simtemp->config_lock);
	
	hrtimer_cancel(&simtemp->timer);
	cancel_work_sync(&simtemp->sample_work);
	
	wake_up_interruptible_all(&simtemp->wait_queue);
	
	simtemp_sysfs_cleanup(simtemp);
	
	misc_deregister(&simtemp->misc_dev);
	
	g_simtemp_dev = NULL;
	
	dev_info(&pdev->dev, "NXP simtemp driver removed\n");
}

static const struct of_device_id simtemp_of_match[] = {
	{ .compatible = "nxp,simtemp" },
	{ }
};
MODULE_DEVICE_TABLE(of, simtemp_of_match);

static struct platform_driver simtemp_driver = {
	.probe = simtemp_probe,
	.remove = simtemp_remove,
	.driver = {
		.name = "nxp-simtemp",
		.of_match_table = simtemp_of_match,
	},
};

static struct platform_device *simtemp_pdev = NULL;

static void simtemp_device_release(struct device *dev)
{
	/* Nothing to do */
}

static int __init simtemp_init(void)
{
	int ret;

	pr_info("NXP Simulated Temperature Sensor Driver Initializing\n");
	
	ret = platform_driver_register(&simtemp_driver);
	if (ret) {
		pr_err("nxp-simtemp: Failed to register platform driver: %d\n", ret);
		return ret;
	}
	
	simtemp_pdev = platform_device_alloc("nxp-simtemp", -1);
	if (!simtemp_pdev) {
		platform_driver_unregister(&simtemp_driver);
		return -ENOMEM;
	}
	
	simtemp_pdev->dev.release = simtemp_device_release;
	
	ret = platform_device_add(simtemp_pdev);
	if (ret) {
		platform_device_put(simtemp_pdev);
		platform_driver_unregister(&simtemp_driver);
		return ret;
	}
	
	pr_info("nxp-simtemp: Module loaded successfully\n");
	return 0;
}

static void __exit simtemp_exit(void)
{
	if (simtemp_pdev)
		platform_device_unregister(simtemp_pdev);
	
	platform_driver_unregister(&simtemp_driver);
	
	pr_info("nxp-simtemp: Module unloaded\n");
}

module_init(simtemp_init);
module_exit(simtemp_exit);
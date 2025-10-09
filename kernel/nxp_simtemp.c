#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/atomic.h>
#include <linux/fs.h>
#include <linux/random.h>
#include <linux/ktime.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/poll.h>

#include "nxp_simtemp.h"
#include "nxp_simtemp_ioctl.h"

MODULE_AUTHOR("Armando Mares");
MODULE_DESCRIPTION("NXP Simulated Temperature Sensor Driver");
MODULE_LICENSE("GPL v2");
MODULE_VERSION("1.0.0");


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

static int simtemp_probe(struct platform_device *pdev)
{
	struct simtemp_device *simtemp;

	simtemp->mode = SIMTEMP_MODE_NORMAL;
	simtemp->enabled = false;
	simtemp->last_temp_mC = SIMTEMP_BASE_TEMP_MC;
	
	mutex_init(&simtemp->config_lock);
	spin_lock_init(&simtemp->buffer_lock);
	init_waitqueue_head(&simtemp->wait_queue);
	atomic_set(&simtemp->open_count, 0);
	
	INIT_KFIFO(simtemp->sample_buffer);

	
	dev_info(&pdev->dev, "NXP simtemp driver probed successfully\n");
	
	return 0;
}

static struct platform_driver simtemp_driver = {
	.probe = simtemp_probe,
	.remove = simtemp_remove,
	.driver = {
		.name = "nxp-simtemp",
		.of_match_table = simtemp_of_match,
	},
};

static int __init simtemp_init(void)
{
	pr_info("NXP Simulated Temperature Sensor Driver Initializing\n");

	pr_info("nxp-simtemp: Module loaded successfully\n");
	return 0;
}


static void __exit simtemp_exit(void)
{
	pr_info("nxp-simtemp: Module unloaded\n");
}

module_init(simtemp_init);
module_exit(simtemp_exit);
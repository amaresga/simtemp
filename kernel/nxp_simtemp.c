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

#include "nxp_simtemp.h"

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
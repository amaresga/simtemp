#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>


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


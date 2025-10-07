#ifndef _NXP_SIMTEMP_H_
#define _NXP_SIMTEMP_H_

#include <linux/types.h>
#include <linux/device.h>

struct simtemp_sample {
	__u64 timestamp_ns;	/* monotonic timestamp */
	__s32 temp_mC;		/* milli-degree Celsius (e.g., 44123 = 44.123 °C) */
	__u32 flags;		/* bit0=NEW_SAMPLE, bit1=THRESHOLD_CROSSED */
} __attribute__((packed));

struct simtemp_device {

	unsigned int sampling_ms;
	s32 threshold_mC;
	enum simtemp_mode mode;

};
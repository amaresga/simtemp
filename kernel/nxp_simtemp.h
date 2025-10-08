#ifndef _NXP_SIMTEMP_H_
#define _NXP_SIMTEMP_H_

#include <linux/types.h>
#include <linux/device.h>

#include <linux/mutex.h>
#include <linux/spinlock.h>

struct simtemp_sample {
	__u64 timestamp_ns;	/* monotonic timestamp */
	__s32 temp_mC;		/* milli-degree Celsius (e.g., 44123 = 44.123 °C) */
	__u32 flags;		/* bit0=NEW_SAMPLE, bit1=THRESHOLD_CROSSED */
} __attribute__((packed));

#define SIMTEMP_BUFFER_SIZE	64

struct simtemp_device {

	unsigned int sampling_ms;
	s32 threshold_mC;
	enum simtemp_mode mode;

    s32 last_temp_mC;
    bool enabled;
	bool threshold_crossed;
    
    struct simtemp_stats stats;

	DECLARE_KFIFO(sample_buffer, struct simtemp_sample, SIMTEMP_BUFFER_SIZE);
	spinlock_t buffer_lock;

	wait_queue_head_t wait_queue;
};

struct simtemp_stats {
	unsigned long updates;
	unsigned long alerts;
	unsigned long read_calls;
	unsigned long poll_calls;
	int last_error;
};
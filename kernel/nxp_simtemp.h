/* SPDX-License-Identifier: GPL-2.0-only */

/* NXP Simulated Temperature Sensor Driver */

/* Copyright (c) 2025 Armando Mares */

#ifndef _NXP_SIMTEMP_H_
#define _NXP_SIMTEMP_H_

#include <linux/types.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>
#include <linux/kfifo.h>
#include <linux/wait.h>
#include <linux/atomic.h>
#include <linux/miscdevice.h>
#include <linux/platform_device.h>
#include <linux/hrtimer.h>
#include <linux/workqueue.h>

struct simtemp_device;

struct simtemp_sample {
	__u64 timestamp_ns; /* monotonic timestamp */
	__s32 temp_mC; /* milli-degree Celsius (e.g., 44123 = 44.123 °C) */
	__u32 flags; /* bit0=NEW_SAMPLE, bit1=THRESHOLD_CROSSED */
} __packed;

/* Flag definitions */
#define SIMTEMP_FLAG_NEW_SAMPLE BIT(0)
#define SIMTEMP_FLAG_THRESHOLD_CROSSED BIT(1)

/* Buffer size */
#define SIMTEMP_BUFFER_SIZE 64

enum simtemp_mode {
	SIMTEMP_MODE_NORMAL = 0,
	SIMTEMP_MODE_NOISY,
	SIMTEMP_MODE_RAMP,
	SIMTEMP_MODE_MAX
};

struct simtemp_stats {
	unsigned long updates;
	unsigned long alerts;
	unsigned long read_calls;
	unsigned long poll_calls;
	int last_error;
};

/* Main device structure */
struct simtemp_device {
	struct platform_device *pdev;
	struct miscdevice misc_dev;
	struct device *dev;

	struct hrtimer timer;
	struct work_struct sample_work;

	unsigned int sampling_ms;
	s32 threshold_mC;
	enum simtemp_mode mode;

	u32 dt_sampling_ms;
	s32 dt_threshold_mC;

	s32 last_temp_mC;
	bool enabled;
	bool threshold_crossed;

	struct simtemp_stats stats;

	DECLARE_KFIFO(sample_buffer, struct simtemp_sample,
		      SIMTEMP_BUFFER_SIZE);
	spinlock_t buffer_lock;

	wait_queue_head_t wait_queue;

	struct mutex config_lock;
	atomic_t open_count;
};

#define SIMTEMP_DEFAULT_SAMPLING_MS 100
#define SIMTEMP_DEFAULT_THRESHOLD_MC 45000 /* 45.0 °C */
#define SIMTEMP_MIN_SAMPLING_MS 1
#define SIMTEMP_MAX_SAMPLING_MS 10000

#define SIMTEMP_BASE_TEMP_MC 25000 /* 25.0 °C */
#define SIMTEMP_TEMP_RANGE_MC 30000 /* ±30.0 °C */
#define SIMTEMP_NOISE_RANGE_MC 2000 /* ±2.0 °C */

int simtemp_generate_sample(struct simtemp_device *simtemp);
int simtemp_sysfs_init(struct simtemp_device *simtemp);
void simtemp_sysfs_cleanup(struct simtemp_device *simtemp);
enum hrtimer_restart simtemp_timer_callback(struct hrtimer *timer);
void simtemp_sample_work(struct work_struct *work);

#define simtemp_err(simtemp, fmt, args...) dev_err((simtemp)->dev, fmt, ##args)

#define simtemp_warn(simtemp, fmt, args...) \
	dev_warn((simtemp)->dev, fmt, ##args)

#define simtemp_info(simtemp, fmt, args...) \
	dev_info((simtemp)->dev, fmt, ##args)

#define simtemp_dbg(simtemp, fmt, args...) dev_dbg((simtemp)->dev, fmt, ##args)

#endif /* _NXP_SIMTEMP_H_ */

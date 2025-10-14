/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * NXP Simulated Temperature Sensor Driver - IOCTL Interface
 *
 * Copyright (c) 2025 Armando Mares
 */

#ifndef _NXP_SIMTEMP_IOCTL_H_
#define _NXP_SIMTEMP_IOCTL_H_

#include <linux/ioctl.h>
#include <linux/types.h>

#define SIMTEMP_IOC_MAGIC 'S'

struct simtemp_config {
	__u32 sampling_ms;
	__s32 threshold_mC;
	__u32 mode;
	__u32 flags; /* Reserved for future use */
};

struct simtemp_ioctl_stats {
	__u64 updates;
	__u64 alerts;
	__u64 read_calls;
	__u64 poll_calls;
	__s32 last_error;
	__u32 buffer_usage;
};

#define SIMTEMP_IOC_MAXNR 7

#define SIMTEMP_MODE_NORMAL_IOCTL 0
#define SIMTEMP_MODE_NOISY_IOCTL 1
#define SIMTEMP_MODE_RAMP_IOCTL 2

#define SIMTEMP_IOC_GET_CONFIG _IOR(SIMTEMP_IOC_MAGIC, 1, struct simtemp_config)
#define SIMTEMP_IOC_SET_CONFIG _IOW(SIMTEMP_IOC_MAGIC, 2, struct simtemp_config)
#define SIMTEMP_IOC_GET_STATS \
	_IOR(SIMTEMP_IOC_MAGIC, 3, struct simtemp_ioctl_stats)
#define SIMTEMP_IOC_RESET_STATS _IO(SIMTEMP_IOC_MAGIC, 4)
#define SIMTEMP_IOC_ENABLE _IO(SIMTEMP_IOC_MAGIC, 5)
#define SIMTEMP_IOC_DISABLE _IO(SIMTEMP_IOC_MAGIC, 6)
#define SIMTEMP_IOC_FLUSH_BUFFER _IO(SIMTEMP_IOC_MAGIC, 7)

#endif /* _NXP_SIMTEMP_IOCTL_H_ */

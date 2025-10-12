#!/usr/bin/env python3
"""
NXP Simulated Temperature Sensor CLI Application

This application provides command-line interface to interact with the
nxp_simtemp kernel module. It can configure the device, read temperature
samples, and perform test operations.

Copyright (c) 2025 Armando Mares
"""

import sys
import os
import struct
import select
import time
import argparse
import signal
from datetime import datetime
from typing import Optional, Tuple
import fcntl

import ctypes
from ctypes import c_uint32, c_int32, c_uint64, Structure, sizeof

SIMTEMP_IOC_MAGIC = ord('S')
SIMTEMP_FLAG_NEW_SAMPLE = 1 << 0
SIMTEMP_FLAG_THRESHOLD_CROSSED = 1 << 1

def _IOC(dir, type, nr, size):
    return (dir << 30) | (type << 8) | (nr << 0) | (size << 16)

def _IOR(type, nr, size):
    return _IOC(2, type, nr, size)

def _IOW(type, nr, size):
    return _IOC(1, type, nr, size)

def _IO(type, nr):
    return _IOC(0, type, nr, 0)

SIMTEMP_MODE_NORMAL = 0
SIMTEMP_MODE_NOISY  = 1
SIMTEMP_MODE_RAMP   = 2

MODE_NAMES = {
    SIMTEMP_MODE_NORMAL: "normal",
    SIMTEMP_MODE_NOISY: "noisy",
    SIMTEMP_MODE_RAMP: "ramp"
}

class SimtempDevice:
    """Interface to the simtemp device"""
    
    def __init__(self, device_path="/dev/simtemp"):
        self.device_path = device_path
        self.fd = None
        self.sysfs_base = self._find_sysfs_path()
    
    def _find_sysfs_path(self):
        """Find the sysfs path for the simtemp device"""
        # Try common locations
        possible_paths = [
            "/sys/class/misc/simtemp",
            "/sys/devices/platform/nxp-simtemp/misc/simtemp",
            "/sys/devices/platform/nxp-simtemp.-1/misc/simtemp"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # If not found, return a default and let individual operations fail gracefully
        return "/sys/class/misc/simtemp"
    
    def open(self):
        """Open the device"""
        try:
            self.fd = os.open(self.device_path, os.O_RDONLY | os.O_NONBLOCK)
            return True
        except OSError as e:
            print(f"Error opening device {self.device_path}: {e}")
            return False
    
    def close(self):
        """Close the device"""
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
    
    def read_sample(self, timeout=None) -> Optional[Tuple[datetime, float, int]]:
        """Read a temperature sample from the device"""
        if self.fd is None:
            return None
        
        try:
            if timeout is not None:
                # Use select to wait for data with timeout
                ready, _, _ = select.select([self.fd], [], [], timeout)
                if not ready:
                    return None
            
            # Read the sample structure
            data = os.read(self.fd, sizeof(SimtempSample))
            if len(data) != sizeof(SimtempSample):
                return None
            
            # Unpack the data
            sample = SimtempSample.from_buffer_copy(data)
            
            # Convert timestamp to datetime
            timestamp = datetime.fromtimestamp(sample.timestamp_ns / 1e9)
            
            # Convert temperature to Celsius
            temp_c = sample.temp_mC / 1000.0
            
            return timestamp, temp_c, sample.flags
            
        except OSError:
            return None
    
    def set_sysfs_value(self, attribute, value):
        """Set a sysfs attribute value"""
        try:
            path = os.path.join(self.sysfs_base, attribute)
            with open(path, 'w') as f:
                f.write(str(value))
            return True
        except (OSError, IOError) as e:
            print(f"Error setting {attribute}: {e}")
            return False
    
    def get_sysfs_value(self, attribute):
        """Get a sysfs attribute value"""
        try:
            path = os.path.join(self.sysfs_base, attribute)
            with open(path, 'r') as f:
                return f.read().strip()
        except (OSError, IOError) as e:
            print(f"Error reading {attribute}: {e}")
            return None
    
    def set_sampling_period(self, period_ms):
        """Set sampling period via sysfs"""
        return self.set_sysfs_value("sampling_ms", period_ms)
    
    def set_threshold(self, threshold_mc):
        """Set temperature threshold via sysfs"""
        return self.set_sysfs_value("threshold_mC", threshold_mc)
    
    def set_mode(self, mode):
        """Set simulation mode via sysfs"""
        return self.set_sysfs_value("mode", mode)
    
    def enable_device(self):
        """Enable the device via sysfs"""
        return self.set_sysfs_value("enabled", "1")
    
    def disable_device(self):
        """Disable the device via sysfs"""
        return self.set_sysfs_value("enabled", "0")
    
    def get_stats(self):
        """Get device statistics via sysfs"""
        stats_str = self.get_sysfs_value("stats")
        if stats_str is None:
            return None
        
        # Parse the stats string
        stats = {}
        for line in stats_str.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                if value.endswith('%'):
                    value = value[:-1]
                try:
                    stats[key] = int(value)
                except ValueError:
                    stats[key] = value
        
        return stats
    
    def ioctl_set_config(self, sampling_ms, threshold_mc, mode):
        """Set configuration via ioctl"""
        if self.fd is None:
            return False
        
        try:
            config = SimtempConfig()
            config.sampling_ms = sampling_ms
            config.threshold_mC = threshold_mc
            config.mode = mode
            config.flags = 0
            
            fcntl.ioctl(self.fd, SIMTEMP_IOC_SET_CONFIG, config)
            return True
        except OSError as e:
            print(f"IOCTL set config error: {e}")
            return False
    
    def ioctl_get_config(self):
        """Get configuration via ioctl"""
        if self.fd is None:
            return None
        
        try:
            config = SimtempConfig()
            fcntl.ioctl(self.fd, SIMTEMP_IOC_GET_CONFIG, config)
            return {
                'sampling_ms': config.sampling_ms,
                'threshold_mC': config.threshold_mC,
                'mode': config.mode
            }
        except OSError as e:
            print(f"IOCTL get config error: {e}")
            return None
        
def format_sample(timestamp, temp_c, flags):
    """Format a temperature sample for display"""
    alert = 1 if flags & SIMTEMP_FLAG_THRESHOLD_CROSSED else 0
    return f"{timestamp.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z temp={temp_c:.1f}C alert={alert}"

def monitor_temperature(device, duration=None, max_samples=None):
    """Monitor temperature readings"""
    print("Monitoring temperature... (Ctrl+C to stop)")
    print("Timestamp                    Temperature  Alert")
    print("-" * 50)
    
    sample_count = 0
    start_time = time.time()
    
    try:
        while True:
            # Check time limit
            if duration is not None and (time.time() - start_time) >= duration:
                break
            
            # Check sample count limit
            if max_samples is not None and sample_count >= max_samples:
                break
            
            # Read sample with timeout
            result = device.read_sample(timeout=1.0)
            if result is None:
                continue
            
            timestamp, temp_c, flags = result
            print(format_sample(timestamp, temp_c, flags))
            sample_count += 1
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
    
    return sample_count

def test_threshold_alert(device, test_threshold=None):
    """Test threshold alert functionality"""
    print("Testing threshold alert functionality...")
    
    # Get current configuration
    current_sampling = device.get_sysfs_value("sampling_ms")
    current_threshold = device.get_sysfs_value("threshold_mC")
    current_mode = device.get_sysfs_value("mode")
    
    if current_sampling is None:
        print("Failed to read current configuration")
        return False
    
    try:
        # Set test configuration
        if test_threshold is None:
            # Set threshold slightly below expected range to trigger alert
            test_threshold = 30000  # 30°C
        
        print(f"Setting test threshold to {test_threshold/1000:.1f}°C")
        device.set_threshold(test_threshold)
        device.set_sampling_period(50)  # Fast sampling for quick test
        device.set_mode("normal")
        device.enable_device()
        
        # Wait for samples and alert
        alert_detected = False
        sample_count = 0
        max_samples = 20  # Wait for up to 20 samples (1 second at 50ms)
        
        print("Waiting for threshold crossing...")
        
        while sample_count < max_samples and not alert_detected:
            result = device.read_sample(timeout=0.1)
            if result is None:
                continue
            
            timestamp, temp_c, flags = result
            sample_count += 1
            
            if flags & SIMTEMP_FLAG_THRESHOLD_CROSSED:
                print(f"✓ Alert detected! Temperature: {temp_c:.1f}°C")
                alert_detected = True
                break
            
            print(f"Sample {sample_count}: {temp_c:.1f}°C (threshold: {test_threshold/1000:.1f}°C)")
        
        # Restore original configuration
        device.set_threshold(current_threshold)
        device.set_sampling_period(current_sampling)
        device.set_mode(current_mode)
        
        if alert_detected:
            print("✓ Test PASSED: Threshold alert working correctly")
            return True
        else:
            print("✗ Test FAILED: No threshold alert detected")
            return False
            
    except Exception as e:
        print(f"✗ Test FAILED: Exception occurred: {e}")
        return False
    
def main():
    print("Simtemp CLI started.")
    # TODO: Implement CLI logic here

if __name__ == "__main__":
    sys.exit(main())

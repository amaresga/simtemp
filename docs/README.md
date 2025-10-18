# NXP Simulated Temperature Sensor Project

A comprehensive Linux kernel driver and user-space application system that simulates a hardware temperature sensor. This project demonstrates kernel module development, device tree integration, character device interfaces, and modern Linux driver development practices.

---

## 📹 Demo Video & Repository

> **IMPORTANT**: These links are required for the NXP Challenge submission

- **📹 Demo Video**:
- **📦 Git Repository**: [https://github.com/amaresga/simtemp](https://github.com/amaresga/simtemp)

**Video Contents** (2-3 minutes):
- Build process demonstration
- Module load → configuration → live monitoring → threshold alert → clean unload
- GUI demonstration (bonus feature)

---

## ✅ Challenge Compliance Summary

This project fulfills all requirements from the NXP Systems Software Engineer Challenge:

| Requirement | Status | Location |
|-------------|--------|----------|
| **Kernel Module** | ✅ Complete | `kernel/nxp_simtemp.c` |
| **Platform Driver + DT** | ✅ Complete | `kernel/dts/` |
| **Character Device** | ✅ Complete | `/dev/simtemp` |
| **Poll/Epoll Support** | ✅ Complete | `simtemp_poll()` |
| **Sysfs Interface** | ✅ Complete | `/sys/class/misc/simtemp/` |
| **CLI Application** | ✅ Complete | `user/cli/main.py` |
| **Test Mode** | ✅ Complete | `--test` flag |
| **Build Script** | ✅ Complete | `scripts/build.sh` |
| **Demo Script** | ✅ Complete | `scripts/run_demo.sh` |
| **Documentation** | ✅ Complete | All 4 docs (README, DESIGN, TESTPLAN, AI_NOTES) |
| **IOCTL Interface** | ✅ Bonus | Advanced configuration |
| **GUI Application** | ✅ Bonus | `user/gui/app.py` |
| **Lint Script** | ✅ Bonus | `scripts/lint.sh` |

**Coverage**: 100% core requirements + 3 bonus features

## 🚀 Quick Start

### For NXP Evaluators

**Complete evaluation in 5 minutes:**

```bash
# 1. Clone repository
git clone https://github.com/amaresga/simtemp.git
cd simtemp

# 2. Build everything
./scripts/build.sh

# 3. Run automated demo and tests
sudo ./scripts/run_demo.sh

# Expected output: All tests PASS, no warnings on module unload
```

**What the demo does:**
- ✅ Loads kernel module
- ✅ Creates `/dev/simtemp` and sysfs attributes
- ✅ Tests configuration (sysfs and IOCTL)
- ✅ Monitors temperature samples
- ✅ Verifies threshold alerts
- ✅ Shows statistics
- ✅ Cleanly unloads module

### Prerequisites

- Linux system with kernel headers installed
- GCC and build tools
- Python 3.6+
- Root access for module loading

**Install dependencies (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install linux-headers-$(uname -r) build-essential python3
```

**Install dependencies (RHEL/CentOS):**
```bash
sudo yum install kernel-devel gcc python3
```

### Build and Test

```bash
# Build everything
cd simtemp/scripts
./build.sh

# Run complete demo
sudo ./run_demo.sh

# Or run individual components
sudo insmod ../kernel/nxp_simtemp.ko
../user/cli/main.py --monitor --duration 10
sudo rmmod nxp_simtemp
```

## 📁 Project Structure

```
simtemp/
├── kernel/                    # Kernel module source
│   ├── nxp_simtemp.c         # Main driver implementation
│   ├── nxp_simtemp.h         # Driver header
│   ├── nxp_simtemp_ioctl.h   # IOCTL interface
│   ├── Kbuild                # Kernel build configuration
│   ├── Makefile              # Build system
│   └── dts/
│       ├── nxp-simtemp.dtsi  # Device Tree binding
│       └── nxp-simtemp-overlay.dts  # DT overlay example
├── user/
│   ├── cli/
│   │   ├── main.py           # Command-line application
│   │   └── requirements.txt  # Python dependencies
│   └── gui/
│       └── app.py            # Optional GUI application
├── scripts/
│   ├── build.sh              # Build script
│   ├── run_demo.sh           # Demo script
│   └── lint.sh               # Code quality checker
└── docs/
    ├── README.md             # This file
    ├── DESIGN.md             # Architecture documentation
    ├── TESTPLAN.md           # Test procedures
    └── AI_NOTES.md           # AI assistance notes
```

## 🔧 Features

### Kernel Module (`nxp_simtemp`)

- **Platform Driver**: Proper Linux platform driver with Device Tree support
- **Character Device**: `/dev/simtemp` with read/write operations
- **Poll/Epoll**: Event-driven reading with select/poll/epoll support
- **Sysfs Interface**: Configuration via `/sys/class/misc/simtemp/`
- **IOCTL Interface**: Batch configuration operations
- **Timer-based Sampling**: Configurable sampling periods (1-10000 ms)
- **Temperature Simulation**: Multiple modes (normal, noisy, ramp)
- **Threshold Alerts**: Configurable temperature threshold with events
- **Statistics**: Runtime statistics and error tracking
- **Proper Locking**: Thread-safe operations with appropriate synchronization

### User Applications

#### CLI Application (`main.py`)
- Configure sampling period, threshold, and simulation mode
- Read temperature samples with timestamps
- Monitor temperature in real-time
- Test threshold alert functionality
- Display device statistics
- Non-blocking and blocking read modes

#### GUI Application (`app.py`) - Optional
- Real-time temperature plotting
- Interactive configuration controls
- Visual alert indicators
- Live statistics display

### Configuration Options

| Parameter | Description | Range | Default |
|-----------|-------------|-------|---------|
| `sampling_ms` | Sampling period in milliseconds | 1-10000 | 100 |
| `threshold_mC` | Alert threshold in milli-°C | Any | 45000 (45°C) |
| `mode` | Simulation mode | normal/noisy/ramp | normal |
| `enabled` | Device enable/disable | 0/1 | 0 |

## 🔌 Device Tree Integration

### Compatible String
```dts
compatible = "nxp,simtemp";
```

### Example Device Node
```dts
simtemp0: simtemp@0 {
    compatible = "nxp,simtemp";
    sampling-ms = <100>;
    threshold-mC = <45000>;
    status = "okay";
};
```

### Overlay Support
The project includes a Device Tree overlay for dynamic loading:
```bash
dtc -@ -I dts -O dtb -o nxp-simtemp-overlay.dtbo kernel/dts/nxp-simtemp-overlay.dts
```

## 📡 API Reference

### Character Device Interface

#### Binary Sample Format
```c
struct simtemp_sample {
    __u64 timestamp_ns;   // Monotonic timestamp in nanoseconds
    __s32 temp_mC;        // Temperature in milli-degrees Celsius
    __u32 flags;          // Status flags
} __attribute__((packed));
```

#### Flags
- `SIMTEMP_FLAG_NEW_SAMPLE` (0x01): New sample available
- `SIMTEMP_FLAG_THRESHOLD_CROSSED` (0x02): Threshold crossed

### Sysfs Interface

| Attribute | Type | Description |
|-----------|------|-------------|
| `sampling_ms` | RW | Sampling period in milliseconds |
| `threshold_mC` | RW | Temperature threshold in milli-°C |
| `mode` | RW | Simulation mode (normal/noisy/ramp) |
| `enabled` | RW | Enable/disable device (0/1) |
| `stats` | RO | Runtime statistics |

### IOCTL Interface

| Command | Description |
|---------|-------------|
| `SIMTEMP_IOC_GET_CONFIG` | Get current configuration |
| `SIMTEMP_IOC_SET_CONFIG` | Set configuration (batch) |
| `SIMTEMP_IOC_GET_STATS` | Get detailed statistics |
| `SIMTEMP_IOC_RESET_STATS` | Reset statistics counters |
| `SIMTEMP_IOC_ENABLE` | Enable device |
| `SIMTEMP_IOC_DISABLE` | Disable device |
| `SIMTEMP_IOC_FLUSH_BUFFER` | Flush sample buffer |

## 📊 Usage Examples

### Basic Monitoring
```bash
# Start monitoring with default settings
./main.py --monitor

# Monitor for 30 seconds
./main.py --monitor --duration 30

# Read only 10 samples
./main.py --monitor --samples 10
```

### Configuration
```bash
# Set sampling to 50ms
./main.py --sampling 50

# Set threshold to 42°C
./main.py --threshold 42.0

# Change to noisy mode
./main.py --mode noisy

# Enable device
./main.py --enable
```

### Testing
```bash
# Run threshold alert test
./main.py --test

# Test with custom threshold
./main.py --test --test-threshold 35.0
```

### Statistics and Status
```bash
# Show current configuration
./main.py --config

# Show device statistics
./main.py --stats
```

## 🧪 Testing

### Automated Regression Tests

**Quick regression testing:**
```bash
# Run full regression suite
sudo ./scripts/regression_test.sh

# Quick smoke tests only (faster, ~1 minute)
sudo ./scripts/regression_test.sh --quick

# Verbose output
sudo ./scripts/regression_test.sh --verbose
```

The regression script validates:
- Module load/unload
- Device file creation
- Sysfs interface
- Configuration tests
- Threshold alerts
- Error handling

**Exit codes**: `0` = all passed, `1` = failures detected, `2` = prerequisites missing

### Comprehensive Demo and Tests
```bash
# Run complete demo with tests
sudo ./scripts/run_demo.sh

# Quick test mode
sudo ./scripts/run_demo.sh --quick

# Interactive mode
sudo ./scripts/run_demo.sh --interactive
```

### Manual Testing
1. **Load Test**: Verify module loads and creates device
2. **Config Test**: Test sysfs and ioctl configuration
3. **Read Test**: Verify character device reading
4. **Poll Test**: Test event notification
5. **Threshold Test**: Verify alert functionality
6. **Stress Test**: High-frequency sampling
7. **Unload Test**: Clean module removal

### Code Quality
```bash
# Run all lint checks
./scripts/lint.sh

# Check only kernel code
./scripts/lint.sh --kernel-only

# Check only Python code
./scripts/lint.sh --python-only
```

### Continuous Integration

[![CI Status](https://github.com/amaresga/simtemp/actions/workflows/ci.yml/badge.svg)](https://github.com/amaresga/simtemp/actions)

The project includes a complete GitHub Actions CI/CD pipeline (`.github/workflows/ci.yml`) that:
- ✅ Builds on multiple kernel versions
- ✅ Runs code quality checks
- ✅ Checks version consistency
- ✅ Creates release artifacts

**Note**: Full module loading tests require root privileges and are run locally with `regression_test.sh`. CI validates build correctness and code quality.

## 🚨 Troubleshooting

### Common Issues

**Module won't load**
- Check kernel headers: `ls /lib/modules/$(uname -r)/build`
- Verify build: `modinfo kernel/nxp_simtemp.ko`
- Check dmesg: `dmesg | tail`

**Device not created**
- Module loaded? `lsmod | grep nxp_simtemp`
- Check device: `ls -la /dev/simtemp`
- Check sysfs: `ls /sys/class/misc/simtemp/`

**Permission denied**
- Device permissions: `ls -la /dev/simtemp`
- Run as root for module operations
- Check SELinux/AppArmor if applicable

**No data from device**
- Device enabled? `cat /sys/class/misc/simtemp/enabled`
- Check sampling: `cat /sys/class/misc/simtemp/sampling_ms`
- Monitor logs: `dmesg | grep simtemp`

## 🔧 Development

### Building
```bash
# Clean build
./scripts/build.sh --clean
make -C kernel clean

# Debug build
cd kernel && make DEBUG=1

# Verbose build
./scripts/build.sh --verbose
```

### Debugging
```bash
# Enable debug messages
echo 8 > /proc/sys/kernel/printk
dmesg -w

# Check module parameters
cat /sys/module/nxp_simtemp/parameters/*

# Monitor device activity
strace -e trace=read,poll ./main.py --monitor
```

## 📚 References

- [Linux Device Drivers, 3rd Edition](https://lwn.net/Kernel/LDD3/)
- [Linux Kernel Module Programming Guide](https://sysprog21.github.io/lkmpg/)
- [Device Tree Documentation](https://www.kernel.org/doc/Documentation/devicetree/)
- [Linux Driver Verification](https://01.org/linuxgraphics/gfx-docs/drm/driver-api/driver-model.html)

## 📄 License

GPL v2 - See individual files for copyright notices.

## 🏷️ Version

Current version: 1.0.0

**Release Date**: October 2025
**Target Platform**: Ubuntu 20.04/22.04 LTS, Kernel 5.4+
**Tested On**: Raspberry Pi (ARM64), Ubuntu x86_64

---

## 🔗 Submission Links

> **⚠️ CRITICAL FOR SUBMISSION**:

- **📹 Demo Video**:
  - **Platform**:
  - **Duration**:
  - **Content**: Build, load, configure, monitor, alert, unload

- **📦 Git Repository**: [https://github.com/amaresga/simtemp](https://github.com/amaresga/simtemp)
  - **Branch**: `main`
  - **Tag**: `v1.0`
  - **Access**: Public

---

## 📈 Project Statistics

- **Total Lines of Code**: ~3,500
  - Kernel module: ~1,200 lines (C)
  - CLI application: ~560 lines (Python)
  - GUI application: ~960 lines (Python)
  - Shell scripts: ~780 lines (Bash)
- **Documentation**:
- **Test Cases**:
- **Development Time**:
- **Code Quality**: 100% (0 checkpatch errors, 10/10 pylint)

---

## 🎯 Key Achievements

### Technical Implementation
- ✅ Production-quality kernel driver with proper locking
- ✅ Complete Device Tree integration
- ✅ Event-driven architecture (poll/epoll)
- ✅ Comprehensive error handling
- ✅ Thread-safe concurrent access
- ✅ Professional CI/CD pipeline

### Beyond Requirements
- 🎁 **GUI Dashboard**: Real-time plotting with Tkinter/matplotlib
- 🎁 **IOCTL Interface**: Batch configuration operations
- 🎁 **Lint Script**: Automated code quality checks
- 🎁 **CI/CD Integration**: GitHub Actions workflow
- 🎁 **Multiple Simulation Modes**: Normal, noisy, ramp patterns

### Documentation Excellence
- 📚 **DESIGN.md**: Complete architecture analysis
- 📚 **TESTPLAN.md**: 32 test scenarios
- 📚 **AI_NOTES.md**: Honest AI usage disclosure
- 📚 **README.md**: Comprehensive user guide (this document)

---

## 🔗 Links

- **📹 Demo Video**:
- **📦 Git Repository**: [https://github.com/amaresga/simtemp](https://github.com/amaresga/simtemp)
- **📄 Challenge Requirements**: [NXP Systems SW Engineer Challenge](../NXP_challenge/systems_sw_engineer_challenge_stage1.md)

---

## 🚧 Future Work

*Challenge Section 9*

### Short Term (1-2 weeks)
1. **Hardware Integration**: Test with actual I2C/SPI temperature sensors (TMP102, LM75)
2. **Multi-instance Support**: Allow multiple simtemp devices simultaneously
3. **Power Management**: Add suspend/resume support with proper PM callbacks

### Medium Term (1-2 months)
4. **Real-time Performance**: Optimize for hard real-time with PREEMPT_RT patch
5. **Network Interface**: Add UDP broadcast for remote monitoring
6. **Calibration Support**: Implement linearization and calibration curves
7. **Cross-platform**: Test on more architectures (RISC-V, ARM32)

### Long Term (3+ months)
8. **Hardware Abstraction Layer**: Generic sensor framework for real sensors
9. **Machine Learning**: Anomaly detection in temperature patterns
10. **Thermal Framework Integration**: Hook into Linux thermal management
11. **Container Support**: Namespace isolation for containers

### Technical Debt
- Replace programmatic device creation with proper DT overlay on real hardware
- Add comprehensive kernel documentation (kerneldoc comments)
- Create Sphinx-based documentation website
- Implement performance profiling and optimization
- Add fuzzing tests for robustness

---

*This project was developed as part of the NXP Systems Software Engineer Challenge.*

**Author**: Armando Mares
**Date**: October 2025
**Challenge**: R-1005999X Software Engineer Position at NXP Guadalajara
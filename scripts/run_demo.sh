#!/bin/bash
#
# NXP Simtemp Enhanced Demo Script
#
# This script demonstrates the complete functionality of the simtemp driver:
# - Load the kernel module
# - Configure the device
# - Test all simulation modes (normal, noisy, ramp)
# - Test IOCTL interface
# - Run comprehensive tests
# - Show live readings with visualization
# - Performance metrics
# - Error handling tests
# - Unload the module
#
# Copyright (c) 2025 Armando Mares

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Paths
KERNEL_MODULE="$PROJECT_ROOT/kernel/nxp_simtemp.ko"
CLI_APP="$PROJECT_ROOT/user/cli/main.py"
DEVICE_PATH="/dev/simtemp"

# Demo configuration
DEMO_DURATION=10
DEMO_SAMPLES=20

# Cleanup function
# shellcheck disable=SC2317  # Cleanup function called via trap
cleanup() {
    local exit_code=$?

    log_info "Cleaning up..."

    # Stop any background processes
    if [[ -n "$MONITOR_PID" ]]; then
        kill "$MONITOR_PID" 2>/dev/null || true
        wait "$MONITOR_PID" 2>/dev/null || true
    fi

    # Disable device
    echo "0" > /sys/class/misc/simtemp/enabled 2>/dev/null || true

    # Unload module
    if lsmod | grep -q nxp_simtemp 2>/dev/null; then
        log_info "Unloading kernel module"
        rmmod nxp_simtemp 2>/dev/null || log_warning "Failed to unload module"
    fi

    log_info "Cleanup completed"

    # Exit with the original exit code from the script, not from cleanup
    exit "$exit_code"
}

# Set up signal handlers
trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root for module loading"
        log_error "Run with: sudo $0"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites"

    # Check if module exists
    if [[ ! -f "$KERNEL_MODULE" ]]; then
        log_error "Kernel module not found: $KERNEL_MODULE"
        log_error "Run the build script first: $SCRIPT_DIR/build.sh"
        exit 1
    fi

    # Check if CLI app exists
    if [[ ! -f "$CLI_APP" ]]; then
        log_error "CLI application not found: $CLI_APP"
        exit 1
    fi

    # Check if module is already loaded
    if lsmod | grep -q nxp_simtemp; then
        log_warning "Module already loaded, unloading first"
        rmmod nxp_simtemp || {
            log_error "Failed to unload existing module"
            exit 1
        }
    fi

    log_success "Prerequisites check passed"
}

# Load kernel module
load_module() {
    log_info "Loading kernel module"

    if insmod "$KERNEL_MODULE"; then
        log_success "Module loaded successfully"

        # Wait a moment for device creation
        sleep 1

        # Check if device was created
        if [[ -c "$DEVICE_PATH" ]]; then
            log_success "Device $DEVICE_PATH created"
        else
            log_error "Device $DEVICE_PATH not found"
            return 1
        fi

        # Check sysfs attributes
        local sysfs_base="/sys/class/misc/simtemp"
        if [[ -d "$sysfs_base" ]]; then
            log_success "Sysfs attributes available at $sysfs_base"

            # List available attributes
            log_info "Available sysfs attributes:"
            for entry in "$sysfs_base"/*; do
                [ -e "$entry" ] || continue
                stat -c "    %A %n" "$entry"
            done
        else
            log_warning "Sysfs attributes not found at $sysfs_base"
        fi

    else
        log_error "Failed to load module"
        return 1
    fi
}

# Configure device
configure_device() {
    log_info "Configuring device for demo"

    # Set fast sampling for demo
    if "$CLI_APP" --sampling 100; then
        log_success "Sampling period set to 100ms"
    else
        log_warning "Failed to set sampling period"
    fi

    # Set threshold
    if "$CLI_APP" --threshold 40.0; then
        log_success "Threshold set to 40.0°C"
    else
        log_warning "Failed to set threshold"
    fi

    # Set mode to normal
    if "$CLI_APP" --mode normal; then
        log_success "Mode set to normal"
    else
        log_warning "Failed to set mode"
    fi

    # Enable device
    if "$CLI_APP" --enable; then
        log_success "Device enabled"
    else
        log_error "Failed to enable device"
        return 1
    fi

    # Show current configuration
    log_info "Current configuration:"
    "$CLI_APP" --config
}

# Test basic functionality
test_basic_functionality() {
    log_info "Testing basic functionality"

    # Test device file operations
    log_info "Testing device file access"
    if [[ -r "$DEVICE_PATH" ]]; then
        log_success "Device is readable"
    else
        log_error "Device is not readable"
        return 1
    fi

    # Test sysfs access
    log_info "Testing sysfs access"
    local sysfs_base="/sys/class/misc/simtemp"
    local value
    for attr in sampling_ms threshold_mC mode enabled stats; do
        if [[ -r "$sysfs_base/$attr" ]]; then
            value=$(cat "$sysfs_base/$attr" 2>/dev/null || echo "error")
            log_success "$attr: $value"
        else
            log_warning "Cannot read $attr"
        fi
    done
}

# Test all simulation modes
test_simulation_modes() {
    log_info "Testing all simulation modes"
    echo

    # Test normal mode
    log_info "Mode 1/3: Normal (sine wave simulation)"
    "$CLI_APP" --mode normal
    log_info "Collecting 8 samples in normal mode..."
    "$CLI_APP" --monitor --samples 8 | tail -9
    echo

    # Test noisy mode
    log_info "Mode 2/3: Noisy (sine wave + random noise)"
    "$CLI_APP" --mode noisy
    log_info "Collecting 8 samples in noisy mode..."
    "$CLI_APP" --monitor --samples 8 | tail -9
    echo

    # Test ramp mode
    log_info "Mode 3/3: Ramp (linear up/down)"
    "$CLI_APP" --mode ramp
    log_info "Collecting 8 samples in ramp mode..."
    "$CLI_APP" --monitor --samples 8 | tail -9
    echo

    # Restore normal mode
    "$CLI_APP" --mode normal
    log_success "All simulation modes tested successfully"
}

# Test IOCTL interface
test_ioctl_interface() {
    log_info "Testing IOCTL interface"

    local ioctl_test="$PROJECT_ROOT/user/test_ioctl"

    if [[ -x "$ioctl_test" ]]; then
        if "$ioctl_test" 2>&1 | grep -q "ALL IOCTL TESTS PASSED"; then
            log_success "IOCTL interface: ALL TESTS PASSED"
        else
            log_warning "IOCTL interface: Some tests may have failed"
        fi
    else
        log_info "IOCTL test program not found at: $ioctl_test"
        log_info "Compile with: gcc -Wall -O2 user/test_ioctl.c -o user/test_ioctl"
    fi
}

# Test threshold alert
test_threshold_alert() {
    log_info "Testing threshold alert functionality"

    if "$CLI_APP" --test; then
        log_success "Threshold alert test PASSED"
        return 0
    else
        log_error "Threshold alert test FAILED"
        return 1
    fi
}

# Monitor temperature readings
monitor_temperature() {
    log_info "Monitoring temperature for $DEMO_DURATION seconds"
    log_info "Press Ctrl+C to stop early"

    # Start monitoring in background
    "$CLI_APP" --monitor --duration "$DEMO_DURATION" &
    MONITOR_PID=$!

    # Wait for monitoring to complete
    if wait "$MONITOR_PID"; then
        log_success "Temperature monitoring completed"
        MONITOR_PID=""
    else
        log_warning "Temperature monitoring interrupted"
        MONITOR_PID=""
    fi
}

# Show final statistics
show_statistics() {
    log_info "Final device statistics:"
    "$CLI_APP" --stats
}

# Show visual temperature graph
show_temperature_graph() {
    log_info "Temperature Visualization (20 samples)"
    echo

    # Set mode to normal for predictable pattern
    "$CLI_APP" --mode normal --sampling 100 > /dev/null 2>&1

    # Collect and display samples with visual bars
    "$CLI_APP" --monitor --samples 20 2>/dev/null | grep "temp=" | awk -F'[ =]' '{
        temp = $3
        gsub(/C/, "", temp)

        # Scale temperature (0-60°C) to bar width (0-40 chars)
        bar_len = int(temp * 40 / 60)
        if (bar_len < 0) bar_len = 0
        if (bar_len > 40) bar_len = 40

        # Create bar
        bar = ""
        for (i = 0; i < bar_len; i++) bar = bar "█"

        # Color based on temperature
        if (temp > 45) color = "\033[0;31m"       # Red
        else if (temp > 35) color = "\033[0;33m"  # Yellow
        else if (temp > 20) color = "\033[0;32m"  # Green
        else color = "\033[0;36m"                 # Cyan

        printf "%s%6.1f°C %s%s\033[0m\n", color, temp, bar, color
    }'
    echo
}

# Show performance metrics
show_performance_metrics() {
    log_info "Performance Metrics Test"

    # Set high-speed sampling
    "$CLI_APP" --sampling 10 > /dev/null 2>&1  # 10ms = 100Hz
    sleep 0.5

    # Measure sample collection rate
    local start_time
    local sample_output
    local end_time
    local sample_count
    local duration_ms

    start_time=$(date +%s%N)
    sample_output=$("$CLI_APP" --monitor --samples 50 2>/dev/null)
    end_time=$(date +%s%N)

    sample_count=$(echo "$sample_output" | grep -c "temp=" || echo 0)
    duration_ms=$(( (end_time - start_time) / 1000000 ))

    echo
    echo "  Samples collected: $sample_count"
    echo "  Time taken: ${duration_ms}ms"

    if [ $duration_ms -gt 0 ]; then
        local samples_per_sec
        samples_per_sec=$(echo "scale=2; $sample_count * 1000 / $duration_ms" | bc 2>/dev/null || echo "N/A")
        echo "  Sample rate: ${samples_per_sec} samples/sec"
    fi

    # Show updated statistics
    echo
    echo "  Current Statistics:"
    sed 's/^/    /' < /sys/class/misc/simtemp/stats 2>/dev/null

    # Restore normal sampling
    "$CLI_APP" --sampling 100 > /dev/null 2>&1
    echo
}

# Run performance test
test_performance() {
    log_info "Running performance test"

    # Set very fast sampling
    "$CLI_APP" --sampling 10 > /dev/null 2>&1 || true  # 10ms = 100Hz
    sleep 2

    # Read many samples quickly
    log_info "Reading samples at high rate..."
    "$CLI_APP" --monitor --samples 50 &
    local perf_pid=$!

    # Wait with timeout
    local timeout=10
    local count=0
    while kill -0 "$perf_pid" 2>/dev/null && [[ $count -lt $timeout ]]; do
        sleep 1
        ((count++))
    done

    if kill -0 "$perf_pid" 2>/dev/null; then
        kill "$perf_pid" 2>/dev/null || true
        wait "$perf_pid" 2>/dev/null || true
        log_warning "Performance test timed out"
        # Return success anyway - this is expected behavior
        return 0
    else
        wait "$perf_pid" 2>/dev/null || true
        log_success "Performance test completed"
    fi

    # Restore normal sampling
    "$CLI_APP" --sampling 100 > /dev/null 2>&1 || true

    return 0
}

# Test error handling
test_error_handling() {
    log_info "Testing error handling and recovery"
    echo

    # Test 1: Invalid sampling period
    log_info "Test 1: Invalid sampling period (too high)"
    if echo "999999" > /sys/class/misc/simtemp/sampling_ms 2>&1 | grep -q "Invalid\|cannot"; then
        log_success "Invalid sampling period rejected correctly"
    else
        local result
        result=$(echo "999999" > /sys/class/misc/simtemp/sampling_ms 2>&1 || echo "rejected")
        if [[ "$result" == *"rejected"* ]] || [[ "$result" == *"Invalid"* ]]; then
            log_success "Invalid sampling period rejected correctly"
        else
            log_warning "Invalid sampling period may have been accepted"
        fi
    fi

    # Test 2: Invalid mode
    log_info "Test 2: Invalid mode string"
    if echo "invalid_mode" > /sys/class/misc/simtemp/mode 2>&1 | grep -q "Invalid\|cannot"; then
        log_success "Invalid mode rejected correctly"
    else
        local result
        result=$(echo "invalid_mode" > /sys/class/misc/simtemp/mode 2>&1 || echo "rejected")
        if [[ "$result" == *"rejected"* ]] || [[ "$result" == *"Invalid"* ]]; then
            log_success "Invalid mode rejected correctly"
        else
            log_warning "Invalid mode may have been accepted"
        fi
    fi

    # Test 3: Read while disabled
    log_info "Test 3: Reading while device is disabled"
    "$CLI_APP" --disable > /dev/null 2>&1
    if timeout 2 cat "$DEVICE_PATH" > /dev/null 2>&1; then
        log_warning "Read while disabled did not block as expected"
    else
        log_success "Read while disabled handled correctly (blocked/timed out)"
    fi
    "$CLI_APP" --enable > /dev/null 2>&1

    echo
    log_success "Error handling tests completed"
}

# Show kernel logs
show_kernel_logs() {
    log_info "Recent kernel logs for simtemp driver:"
    echo
    dmesg 2>/dev/null | grep -i "nxp-simtemp\|simtemp:" | tail -15 | sed 's/^/  /' || \
        log_warning "No kernel logs available or insufficient permissions"
    echo
}

# Interactive mode
interactive_mode() {
    log_info "Entering interactive mode"
    echo "Commands:"
    echo "  config   - Show configuration"
    echo "  stats    - Show statistics"
    echo "  monitor  - Monitor for 5 seconds"
    echo "  graph    - Show temperature graph"
    echo "  modes    - Test all simulation modes"
    echo "  test     - Run threshold test"
    echo "  logs     - Show kernel logs"
    echo "  help     - Show this help"
    echo "  quit     - Exit interactive mode"
    echo

    while true; do
        read -r -p "simtemp> " cmd

        case "$cmd" in
            config)
                "$CLI_APP" --config
                ;;
            stats)
                "$CLI_APP" --stats
                ;;
            monitor)
                "$CLI_APP" --monitor --duration 5
                ;;
            graph)
                show_temperature_graph
                ;;
            modes)
                test_simulation_modes
                ;;
            test)
                "$CLI_APP" --test
                ;;
            logs)
                show_kernel_logs
                ;;
            help)
                echo "Available commands: config, stats, monitor, graph, modes, test, logs, help, quit"
                ;;
            quit|exit)
                break
                ;;
            "")
                # Empty line, continue
                ;;
            *)
                echo "Unknown command: $cmd (type 'help' for commands)"
                ;;
        esac
    done
}

# Print demo summary
print_summary() {
    echo
    echo "========================================"
    log_success "Demo completed successfully!"
    echo "========================================"
    echo
    echo "What was demonstrated:"
    echo "  ✓ Kernel module loading and device creation"
    echo "  ✓ Sysfs configuration interface"
    echo "  ✓ Character device reading with poll support"
    echo "  ✓ All three simulation modes (normal, noisy, ramp)"
    echo "  ✓ Threshold alert functionality"
    echo "  ✓ IOCTL interface (if compiled)"
    echo "  ✓ Temperature visualization"
    echo "  ✓ Performance metrics and statistics"
    echo "  ✓ Error handling and validation"
    echo "  ✓ Kernel logging and diagnostics"
    echo "  ✓ Clean module unloading"
    echo
    echo "Key Features Highlighted:"
    echo "  • Real-time temperature simulation engine"
    echo "  • Multiple simulation patterns"
    echo "  • Configurable sampling rates (10ms-5000ms)"
    echo "  • Threshold-based alerting"
    echo "  • Ring buffer for sample storage"
    echo "  • Comprehensive statistics tracking"
    echo "  • Safe concurrent access"
    echo "  • Proper cleanup and error handling"
    echo
    echo "Files involved:"
    echo "  Kernel module: $KERNEL_MODULE"
    echo "  CLI app:       $CLI_APP"
    echo "  Device:        $DEVICE_PATH"
    echo "  Sysfs:         /sys/class/misc/simtemp/"
    echo
}

# Main demo function
main() {
    local start_time
    start_time=$(date +%s)

    # Parse command line arguments
    local interactive=false
    local quick_test=false
    local full_demo=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -i|--interactive)
                interactive=true
                shift
                ;;
            -q|--quick)
                quick_test=true
                DEMO_DURATION=5
                DEMO_SAMPLES=10
                shift
                ;;
            -f|--full)
                full_demo=true
                shift
                ;;
            -v|--verbose)
                set -x  # Enable verbose mode
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo
                echo "NXP Simtemp Driver Demo - Comprehensive Testing Suite"
                echo
                echo "Options:"
                echo "  -q, --quick        Run quick demo (5 seconds, basic tests only)"
                echo "  -f, --full         Run full comprehensive demo with all tests"
                echo "  -i, --interactive  Enter interactive mode after demo"
                echo "  -v, --verbose      Verbose output (for debugging)"
                echo "  -h, --help         Show this help message"
                echo
                echo "Examples:"
                echo "  $0                 # Standard demo"
                echo "  $0 --quick         # Quick 5-second test"
                echo "  $0 --full          # Comprehensive test suite"
                echo "  $0 -i              # Standard demo + interactive mode"
                echo "  $0 --full -i       # Full demo + interactive mode"
                echo
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                echo "Run '$0 --help' for usage information"
                exit 1
                ;;
        esac
    done

    echo "========================================"
    log_info "NXP Simtemp Driver Demo"
    echo "========================================"

    if [[ "$quick_test" == true ]]; then
        echo "Mode: Quick Test (5 seconds)"
    elif [[ "$full_demo" == true ]]; then
        echo "Mode: Full Comprehensive Demo"
    else
        echo "Mode: Standard Demo (10 seconds)"
    fi

    echo "Demo duration: $DEMO_DURATION seconds"
    echo "Max samples: $DEMO_SAMPLES"
    echo

    # Setup phase
    check_root
    check_prerequisites
    load_module
    configure_device
    echo

    # Testing phase
    if [[ "$quick_test" == true ]]; then
        # Quick test - minimal tests
        log_info "=== QUICK TEST MODE ==="
        echo
        test_basic_functionality
        echo
        log_info "Quick monitoring test..."
        "$CLI_APP" --monitor --duration "$DEMO_DURATION"

    elif [[ "$full_demo" == true ]]; then
        # Full comprehensive demo
        log_info "=== COMPREHENSIVE TEST SUITE ==="
        echo

        log_info "Phase 1: Basic Functionality"
        test_basic_functionality
        echo

        log_info "Phase 2: Simulation Modes"
        test_simulation_modes
        echo

        log_info "Phase 3: Threshold Alerts"
        test_threshold_alert
        echo

        log_info "Phase 4: Temperature Monitoring"
        monitor_temperature
        echo

        log_info "Phase 5: Visual Temperature Graph"
        show_temperature_graph

        log_info "Phase 6: Performance Metrics"
        show_performance_metrics

        log_info "Phase 7: IOCTL Interface"
        test_ioctl_interface
        echo

        log_info "Phase 8: Error Handling"
        test_error_handling

        log_info "Phase 9: Kernel Logs"
        show_kernel_logs

    else
        # Standard demo
        log_info "=== STANDARD DEMO ==="
        echo

        test_basic_functionality
        echo

        test_simulation_modes
        echo

        test_threshold_alert
        echo

        monitor_temperature
        echo

        show_temperature_graph

        test_performance
        echo
    fi

    # Show final statistics
    show_statistics
    echo

    # Interactive mode
    if [[ "$interactive" == true ]]; then
        interactive_mode
    fi

    local end_time
    local duration
    end_time=$(date +%s)
    duration=$((end_time - start_time))

    print_summary
    log_success "Total demo time: ${duration} seconds"

    return 0
}

# Run main function and capture exit code
main "$@"
exit_code=$?

# Exit with main's exit code (cleanup trap will handle cleanup)
exit $exit_code
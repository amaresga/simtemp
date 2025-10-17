#!/bin/bash
#
# NXP Simtemp Regression Test Suite
#
# This script runs automated regression tests for the simtemp driver.
# It validates core functionality without requiring manual intervention.
#
# Usage:
#   sudo ./scripts/regression_test.sh           # Run all tests
#   sudo ./scripts/regression_test.sh --quick   # Run quick smoke tests only
#   sudo ./scripts/regression_test.sh --verbose # Verbose output
#
# Exit codes:
#   0: All tests passed
#   1: One or more tests failed
#   2: Prerequisites not met
#
# Copyright (c) 2025 Armando Mares

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Configuration
VERBOSE=false
QUICK_MODE=false

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Paths
KERNEL_MODULE="$PROJECT_ROOT/kernel/nxp_simtemp.ko"
CLI_APP="$PROJECT_ROOT/user/cli/main.py"
DEVICE_PATH="/dev/simtemp"
SYSFS_PATH="/sys/class/misc/simtemp"

# Parse arguments
while [[ $# -gt 0 ]]; do
	case $1 in
	--quick)
		QUICK_MODE=true
		shift
		;;
	--verbose | -v)
		VERBOSE=true
		shift
		;;
	--help | -h)
		echo "Usage: $0 [OPTIONS]"
		echo ""
		echo "Options:"
		echo "  --quick       Run quick smoke tests only"
		echo "  --verbose     Enable verbose output"
		echo "  --help        Show this help message"
		exit 0
		;;
	*)
		echo "Unknown option: $1"
		exit 2
		;;
	esac
done

# Logging functions
log_info() {
	echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
	echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
	echo -e "${RED}[✗]${NC} $1"
}

log_warning() {
	echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_test_start() {
	if $VERBOSE; then
		echo -e "${BLUE}[TEST]${NC} Running: $1"
	fi
}

# Cleanup function
cleanup() {
	local exit_code=$?

	log_info "Cleaning up test environment..."

	# Disable device if exists
	if [[ -d "$SYSFS_PATH" ]]; then
		echo "0" >"$SYSFS_PATH/enabled" 2>/dev/null || true
	fi

	# Unload module if loaded
	if lsmod | grep -q nxp_simtemp 2>/dev/null; then
		rmmod nxp_simtemp 2>/dev/null || log_warning "Failed to unload module"
	fi

	# Return original exit code
	exit "$exit_code"
}

trap cleanup EXIT INT TERM

# Check if running as root
check_root() {
	if [[ $EUID -ne 0 ]]; then
		log_error "This script must be run as root"
		log_error "Run with: sudo $0"
		exit 2
	fi
}

# Check prerequisites
check_prerequisites() {
	log_info "Checking prerequisites..."

	local missing=false

	if [[ ! -f "$KERNEL_MODULE" ]]; then
		log_error "Kernel module not found: $KERNEL_MODULE"
		log_error "Run './scripts/build.sh' first"
		missing=true
	fi

	if [[ ! -f "$CLI_APP" ]]; then
		log_error "CLI application not found: $CLI_APP"
		missing=true
	fi

	if [[ ! -x "$CLI_APP" ]]; then
		chmod +x "$CLI_APP" 2>/dev/null || true
	fi

	if $missing; then
		exit 2
	fi

	log_success "Prerequisites check passed"
}

# Test execution wrapper
run_test() {
	local test_name="$1"
	local test_cmd="$2"
	local is_critical="${3:-false}"

	log_test_start "$test_name"

	if eval "$test_cmd" >/dev/null 2>&1; then
		log_success "$test_name"
		TESTS_PASSED=$((TESTS_PASSED + 1))
		return 0
	else
		log_error "$test_name"
		TESTS_FAILED=$((TESTS_FAILED + 1))

		if $is_critical; then
			log_error "Critical test failed, stopping test suite"
			exit 1
		fi
		return 1
	fi
}

# Test: Module load
test_module_load() {
	insmod "$KERNEL_MODULE"
}

# Test: Device file creation
test_device_creation() {
	[[ -c "$DEVICE_PATH" ]]
}

# Test: Sysfs directory creation
test_sysfs_creation() {
	[[ -d "$SYSFS_PATH" ]] &&
		[[ -f "$SYSFS_PATH/enabled" ]] &&
		[[ -f "$SYSFS_PATH/sampling_ms" ]] &&
		[[ -f "$SYSFS_PATH/threshold_mC" ]] &&
		[[ -f "$SYSFS_PATH/mode" ]] &&
		[[ -f "$SYSFS_PATH/stats" ]]
}

# Test: Module appears in lsmod
test_module_listed() {
	lsmod | grep -q nxp_simtemp
}

# Test: No kernel errors in dmesg
test_no_kernel_errors() {
	! dmesg | tail -20 | grep -i "simtemp.*error\|simtemp.*warning\|simtemp.*oops"
}

# Test: Basic configuration via CLI
test_basic_configuration() {
	"$CLI_APP" --config >/dev/null 2>&1
}

# Test: Enable device
test_enable_device() {
	"$CLI_APP" --enable >/dev/null 2>&1 &&
		[[ "$(cat "$SYSFS_PATH/enabled")" == "1" ]]
}

# Test: Disable device
test_disable_device() {
	"$CLI_APP" --disable >/dev/null 2>&1 &&
		[[ "$(cat "$SYSFS_PATH/enabled")" == "0" ]]
}

# Test: Threshold alert test
test_threshold_alert() {
	"$CLI_APP" --test >/dev/null 2>&1
}

# Test: Basic monitoring (short duration)
test_basic_monitoring() {
	# Enable device first
	"$CLI_APP" --enable >/dev/null 2>&1 || return 1
	# timeout exits with 124 if command times out (which is success for monitoring)
	# timeout exits with command's exit code if it finishes early
	timeout 3 "$CLI_APP" --monitor >/dev/null 2>&1
	local exit_code=$?
	# Exit code 124 means timeout (success), 0 also means success
	[[ $exit_code -eq 124 || $exit_code -eq 0 ]]
}

# Test: Sampling rate configuration
test_sampling_configuration() {
	echo "200" >"$SYSFS_PATH/sampling_ms" &&
		[[ "$(cat "$SYSFS_PATH/sampling_ms")" == "200" ]]
}

# Test: Threshold configuration
test_threshold_configuration() {
	echo "40000" >"$SYSFS_PATH/threshold_mC" &&
		[[ "$(cat "$SYSFS_PATH/threshold_mC")" == "40000" ]]
}

# Test: Mode configuration
test_mode_configuration() {
	echo "noisy" >"$SYSFS_PATH/mode" &&
		[[ "$(cat "$SYSFS_PATH/mode")" == "noisy" ]]
}

# Test: Statistics readable
test_stats_readable() {
	cat "$SYSFS_PATH/stats" >/dev/null 2>&1
}

# Test: Invalid input rejected
test_invalid_input() {
	! echo "-1" >"$SYSFS_PATH/sampling_ms" 2>/dev/null &&
		! echo "invalid" >"$SYSFS_PATH/mode" 2>/dev/null
}

# Test: Module unload
test_module_unload() {
	rmmod nxp_simtemp 2>/dev/null
}

# Test: Clean unload (no device file)
test_clean_unload() {
	[[ ! -c "$DEVICE_PATH" ]] && [[ ! -d "$SYSFS_PATH" ]]
}

# Test: No warnings in dmesg after unload
test_no_unload_warnings() {
	! dmesg | tail -10 | grep -i "warning\|error\|oops"
}

# Print test summary
print_summary() {
	local total=$((TESTS_PASSED + TESTS_FAILED + TESTS_SKIPPED))

	echo ""
	echo "=========================================="
	echo "          Test Summary"
	echo "=========================================="
	echo -e "Total tests:   $total"
	echo -e "${GREEN}Passed:        $TESTS_PASSED${NC}"
	echo -e "${RED}Failed:        $TESTS_FAILED${NC}"

	if [[ $TESTS_SKIPPED -gt 0 ]]; then
		echo -e "${YELLOW}Skipped:       $TESTS_SKIPPED${NC}"
	fi

	echo "=========================================="

	if [[ $TESTS_FAILED -eq 0 ]]; then
		echo -e "${GREEN}✓ All tests PASSED${NC}"
		return 0
	else
		echo -e "${RED}✗ Some tests FAILED${NC}"
		return 1
	fi
}

# Main test execution
main() {
	echo "=========================================="
	echo "  NXP Simtemp Regression Test Suite"
	echo "=========================================="
	echo ""

	if $QUICK_MODE; then
		log_info "Running in QUICK mode (smoke tests only)"
	fi

	check_root
	check_prerequisites

	echo ""
	log_info "Starting regression tests..."
	echo ""

	# Phase 1: Module Loading
	log_info "Phase 1: Module Load Tests"
	run_test "T1.1: Module loads successfully" test_module_load true
	run_test "T1.1: Device file created" test_device_creation true
	run_test "T1.1: Sysfs directory created" test_sysfs_creation true
	run_test "T1.1: Module listed in lsmod" test_module_listed
	run_test "T1.1: No kernel errors" test_no_kernel_errors

	if $QUICK_MODE; then
		log_info "Quick mode: Skipping extended tests"
		TESTS_SKIPPED=10
	else
		# Phase 2: Configuration Tests
		echo ""
		log_info "Phase 2: Configuration Tests"
		run_test "T2: Basic configuration" test_basic_configuration
		run_test "T2: Enable device" test_enable_device
		run_test "T2: Sampling rate configuration" test_sampling_configuration
		run_test "T2: Threshold configuration" test_threshold_configuration
		run_test "T2: Mode configuration" test_mode_configuration
		run_test "T2: Statistics readable" test_stats_readable

		# Phase 3: Functional Tests
		echo ""
		log_info "Phase 3: Functional Tests"
		run_test "T3: Threshold alert test" test_threshold_alert
		run_test "T2: Basic monitoring" test_basic_monitoring

		# Phase 4: Error Handling
		echo ""
		log_info "Phase 4: Error Handling Tests"
		run_test "T4: Invalid input rejected" test_invalid_input
		run_test "T2: Disable device" test_disable_device
	fi

	# Phase 5: Cleanup Tests
	echo ""
	log_info "Phase 5: Unload Tests"
	run_test "T1.3: Module unloads cleanly" test_module_unload
	run_test "T1.3: Device files removed" test_clean_unload
	run_test "T1.3: No unload warnings" test_no_unload_warnings

	# Print summary
	echo ""
	print_summary
}

# Run main function
main "$@"

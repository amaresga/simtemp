#!/bin/bash
#
# NXP Simtemp Build Script
#
# This script builds the kernel module and user applications.
# It performs environment checks and provides helpful error messages.
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

log_info "NXP Simtemp Build Script"
log_info "Project root: $PROJECT_ROOT"

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    log_warning "Running as root. Some operations may not work as expected."
fi

# Check if we have kernel headers
check_kernel_headers() {
    local kernel_version
    kernel_version=$(uname -r)
    local kdir="/lib/modules/$kernel_version/build"

    log_info "Checking kernel headers for version $kernel_version"

    if [[ ! -d "$kdir" ]]; then
        log_error "Kernel headers not found at $kdir"
        log_error "Please install kernel headers for your current kernel:"
        log_error "  Ubuntu/Debian: sudo apt-get install linux-headers-\$(uname -r)"
        log_error "  RHEL/CentOS:   sudo yum install kernel-devel"
        log_error "  Fedora:        sudo dnf install kernel-devel"
        return 1
    fi

    if [[ ! -f "$kdir/Makefile" ]]; then
        log_error "Kernel build system not found. Headers may be incomplete."
        return 1
    fi

    log_success "Kernel headers found at $kdir"
    return 0
}

# Check build tools - make sure we have the basic compilation toolchain
check_build_tools() {
    log_info "Checking build tools"

    local tools=("make" "gcc")
    for tool in "${tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            log_error "$tool is required but not installed"
            log_error "Please install build essentials:"
            log_error "  Ubuntu/Debian: sudo apt-get install build-essential"
            log_error "  RHEL/CentOS:   sudo yum groupinstall 'Development Tools'"
            log_error "  Fedora:        sudo dnf groupinstall 'Development Tools'"
            return 1
        fi
    done

    log_success "Build tools available"
    return 0
}

# Check Python setup - verify Python 3 is available for the CLI tool
check_python() {
    log_info "Checking Python environment"

    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not installed"
        return 1
    fi

    local python_version
    python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
    log_success "Python $python_version found"

    # Check if we can import required modules
    if ! python3 -c "import sys, os, struct, select, time, argparse, signal, datetime, typing, fcntl, ctypes" 2>/dev/null; then
        log_warning "Some Python modules may not be available. CLI app might not work properly."
    fi

    return 0
}

# Build kernel module - Runs 'make clean' then 'make' in kernel directory, validates output
build_kernel_module() {
    log_info "Building kernel module"

    cd "$PROJECT_ROOT/kernel"

    # Clean first
    if make clean &> /dev/null; then
        log_info "Cleaned previous build"
    fi

    # Build
    if make; then
        log_success "Kernel module built successfully"

        # Check if module was created
        if [[ -f "nxp_simtemp.ko" ]]; then
            local module_size
            module_size=$(stat -c%s "nxp_simtemp.ko")
            log_info "Module size: $module_size bytes"

            # Check basic module info
            if command -v modinfo &> /dev/null; then
                log_info "Module information:"
                modinfo nxp_simtemp.ko | grep -E "(description|author|license|version)" || true
            fi
        else
            log_error "Module file nxp_simtemp.ko not found after build"
            return 1
        fi
    else
        log_error "Kernel module build failed"
        return 1
    fi

    return 0
}

# Set up user applications - prepare the CLI tool for execution
setup_user_apps() {
    log_info "Setting up user applications"

    # Make CLI executable
    local cli_script="$PROJECT_ROOT/user/cli/main.py"
    if [[ -f "$cli_script" ]]; then
        chmod +x "$cli_script"
        log_success "CLI application ready at $cli_script"
    else
        log_error "CLI script not found at $cli_script"
        return 1
    fi

    return 0
}

# Validate build - double-check everything compiled correctly
validate_build() {
    log_info "Validating build"

    local kernel_module="$PROJECT_ROOT/kernel/nxp_simtemp.ko"
    local cli_app="$PROJECT_ROOT/user/cli/main.py"

    # Check kernel module
    if [[ ! -f "$kernel_module" ]]; then
        log_error "Kernel module not found: $kernel_module"
        return 1
    fi

    # Check if module is loadable (basic validation)
    if command -v modinfo &> /dev/null; then
        if modinfo "$kernel_module" &> /dev/null; then
            log_success "Kernel module passes basic validation"
        else
            log_error "Kernel module failed validation"
            return 1
        fi
    fi

    # Check CLI app
    if [[ ! -f "$cli_app" ]]; then
        log_error "CLI application not found: $cli_app"
        return 1
    fi

    if [[ ! -x "$cli_app" ]]; then
        log_error "CLI application is not executable"
        return 1
    fi

    # Basic syntax check
    if python3 -m py_compile "$cli_app" 2>/dev/null; then
        log_success "CLI application passes syntax check"
    else
        log_error "CLI application has syntax errors"
        return 1
    fi

    # Check unit tests (optional bonus feature)
    local unit_tests="$PROJECT_ROOT/tests/test_record_parsing.py"
    if [[ -f "$unit_tests" ]]; then
        log_info "Unit tests found at $unit_tests"
        if python3 -m py_compile "$unit_tests" 2>/dev/null; then
            log_success "Unit tests pass syntax check"
        else
            log_warn "Unit tests have syntax errors"
        fi
    fi

    return 0
}

# Print usage information - show user what to do next after successful build
print_usage_info() {
    log_info "Build completed successfully!"
    echo
    echo "Next steps:"
    echo "1. Load the kernel module:"
    echo "   sudo insmod $PROJECT_ROOT/kernel/nxp_simtemp.ko"
    echo
    echo "2. Run the CLI application:"
    echo "   $PROJECT_ROOT/user/cli/main.py --help"
    echo
    echo "3. Or run the demo script:"
    echo "   sudo $SCRIPT_DIR/run_demo.sh"
    echo
    echo "4. To unload the module:"
    echo "   sudo rmmod nxp_simtemp"
    echo
}

# Main build process - orchestrates the entire build sequence
main() {
    local start_time
    start_time=$(date +%s)

    # Parse command line arguments
    local clean_only=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -v|--verbose)
                # Verbose mode could be implemented later
                shift
                ;;
            -c|--clean)
                clean_only=true
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  -v, --verbose    Verbose output"
                echo "  -c, --clean      Clean only (don't build)"
                echo "  -h, --help       Show this help"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    # Clean mode
    if [[ "$clean_only" == true ]]; then
        log_info "Cleaning build artifacts"
        cd "$PROJECT_ROOT/kernel"
        make clean || true
        log_success "Clean completed"
        exit 0
    fi

    # Run checks
    check_kernel_headers || exit 1
    check_build_tools || exit 1
    check_python || exit 1

    # Build
    build_kernel_module || exit 1
    setup_user_apps || exit 1
    validate_build || exit 1

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log_success "Build completed in ${duration} seconds"
    print_usage_info
}

# Run main function
main "$@"
# End of script

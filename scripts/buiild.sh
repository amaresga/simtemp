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

# Check kernel headers
check_kernel_headers() {
    local kernel_version=$(uname -r)
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

# Check build tools
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

# Check Python
check_python() {
    log_info "Checking Python environment"
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not installed"
        return 1
    fi
    
    local python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
    log_success "Python $python_version found"
    
    # Check if we can import required modules
    if ! python3 -c "import sys, os, struct, select, time, argparse, signal, datetime, typing, fcntl, ctypes" 2>/dev/null; then
        log_warning "Some Python modules may not be available. CLI app might not work properly."
    fi
    
    return 0
}
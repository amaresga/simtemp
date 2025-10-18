#!/bin/bash
#
# NXP Simtemp Lint Script
#
# This script runs various code quality checks on the simtemp project:
# - checkpatch.pl for kernel code
# - clang-format for code formatting
# - Python linting with flake8/pylint
# - Shell script linting with shellcheck
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
log_info()    { [[ $QUIET_MODE == false ]] && echo -e "${BLUE}[INFO]${NC} $1"    >&2; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"                              >&2; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"                             >&2; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"                                  >&2; }
log_debug()   { [[ $QUIET_MODE == false ]] && echo -e "${BLUE}[DEBUG]${NC} $1"   >&2; }

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# Configuration
AUTO_FIX=false
QUIET_MODE=false
CHANGED_FILES_ONLY=false
BASE_BRANCH="main"

# CI Environment detection
CI_MODE=false
if [[ -n "${CI_ENVIRONMENT:-}" ]] || [[ -n "${CI:-}" ]] || [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    CI_MODE=true
    log_info "CI environment detected - enabling CI-safe mode"
fi

# Track results
track_result() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    if [[ $1 -eq 0 ]]; then
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        log_success "$2"
    else
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        log_error "$2"
    fi
}

# Find checkpatch.pl
find_checkpatch() {
    local checkpatch_paths=(
        "/usr/src/linux-headers-$(uname -r)/scripts/checkpatch.pl"
        "/lib/modules/$(uname -r)/build/scripts/checkpatch.pl"
        "/usr/share/kernel-checkpatch/checkpatch.pl"
        "$(which checkpatch.pl 2>/dev/null || echo "")"
    )

    for path in "${checkpatch_paths[@]}"; do
        if [[ -f "$path" ]]; then
            echo "$path"
            return 0
        fi
    done

    return 1
}

# Get list of changed files
get_changed_files() {
    local file_type="$1"  # c, python, shell, docs, all
    local changed_files=()

    if [[ $CHANGED_FILES_ONLY == true ]]; then
        log_debug "Detecting changed files against $BASE_BRANCH"

        # Check if we're in a git repository
        if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            log_warning "Not in a git repository, scanning all files"
            CHANGED_FILES_ONLY=false
            return 0
        fi

        # Get list of changed files
        local git_diff_cmd=""
        if git show-ref --verify --quiet refs/heads/"$BASE_BRANCH"; then
            git_diff_cmd="git diff --name-only $BASE_BRANCH...HEAD"
        elif git rev-parse --verify HEAD~1 >/dev/null 2>&1; then
            git_diff_cmd="git diff --name-only HEAD~1"
        else
            log_warning "Cannot determine base for diff, scanning all files"
            CHANGED_FILES_ONLY=false
            return 0
        fi

        local all_changed
        all_changed=$($git_diff_cmd 2>/dev/null || echo "")

        if [[ -z "$all_changed" ]]; then
            log_info "No changed files detected"
            return 0
        fi

        log_debug "Changed files detected: $(echo "$all_changed" | wc -l) files"

        # Filter by file type
        case "$file_type" in
            c|kernel)
                mapfile -t changed_files < <(printf '%s\n' "$all_changed" | grep -E '\.(c|h)$' | grep -E '^kernel/' || true)
                ;;
            python)
                mapfile -t changed_files < <(printf '%s\n' "$all_changed" | grep -E '\.py$' || true)
                ;;
            shell)
                mapfile -t changed_files < <(printf '%s\n' "$all_changed" | grep -E '\.sh$' || true)
                ;;
            docs)
                mapfile -t changed_files < <(printf '%s\n' "$all_changed" | grep -E '\.(md|rst|txt)$' || true)
                ;;
            all)
                mapfile -t changed_files < <(printf '%s\n' "$all_changed")
                ;;
        esac

        # Convert relative paths to absolute paths
        local abs_files=()
        for file in "${changed_files[@]}"; do
            if [[ -f "$PROJECT_ROOT/$file" ]]; then
                abs_files+=("$PROJECT_ROOT/$file")
            fi
        done

        printf '%s\n' "${abs_files[@]}"
    fi
}

# Check tool versions
check_tool_versions() {
    log_info "Checking tool versions:"

    command -v python3 >/dev/null && log_info "Python: $(python3 --version 2>&1)"
    command -v flake8 >/dev/null && log_info "Flake8: $(flake8 --version 2>&1 | head -n1)"
    command -v pylint >/dev/null && log_info "Pylint: $(pylint --version 2>&1 | head -n1)"
    command -v shellcheck >/dev/null && log_info "Shellcheck: $(shellcheck --version | grep version | head -n1)"
    command -v clang-format >/dev/null && log_info "Clang-format: $(clang-format --version)"

    local checkpatch
    if checkpatch=$(find_checkpatch); then
        log_info "Checkpatch: Found at $checkpatch"
    else
        log_info "Checkpatch: Not found"
    fi
    echo
}

# Check kernel code with checkpatch.pl
lint_kernel_code() {
    log_info "Linting kernel code with checkpatch.pl"

    # In CI mode, be extra careful about kernel operations
    if [[ $CI_MODE == true ]]; then
        log_info "CI mode: Using safe kernel code analysis"
    fi

    local kernel_files=()

    # Get files to check
    if [[ $CHANGED_FILES_ONLY == true ]]; then
        mapfile -t kernel_files < <(get_changed_files "kernel")
        if [[ ${#kernel_files[@]} -eq 0 ]]; then
            log_info "No changed kernel files, skipping checkpatch"
            return 0
        fi
        log_info "Checking ${#kernel_files[@]} changed kernel file(s)"
    else
        kernel_files=(
            "$PROJECT_ROOT/kernel/nxp_simtemp.c"
            "$PROJECT_ROOT/kernel/nxp_simtemp.h"
            "$PROJECT_ROOT/kernel/nxp_simtemp_ioctl.h"
        )
    fi

    local checkpatch
    if checkpatch=$(find_checkpatch); then
        log_info "Found checkpatch at: $checkpatch"

        local failed=0
        for file in "${kernel_files[@]}"; do
            if [[ -f "$file" ]]; then
                log_info "Checking $(basename "$file")"

                # Run checkpatch and capture output
                local checkpatch_output
                checkpatch_output=$(perl "$checkpatch" --no-tree --file "$file" --terse 2>&1) || true

                # Check if there are any ERROR lines (not just warnings)
                if echo "$checkpatch_output" | grep -q "ERROR:"; then
                    # Has actual errors
                    local error_count
                    error_count=$(echo "$checkpatch_output" | grep -c "ERROR:" || echo "0")
                    log_error "$(basename "$file") has $error_count checkpatch error(s)"
                    echo "$checkpatch_output"
                    failed=1
                else
                    # No errors, just warnings (or clean)
                    log_success "$(basename "$file") passes checkpatch"

                    # Show warnings but don't fail on them
                    if echo "$checkpatch_output" | grep -q "WARNING:"; then
                        local warning_count
                        warning_count=$(echo "$checkpatch_output" | grep -c "WARNING:" || echo "0")
                        log_warning "$(basename "$file") has $warning_count checkpatch warning(s) (not failing)"
                    fi
                fi
            fi
        done

        track_result $failed "Kernel code checkpatch"
    else
        log_warning "checkpatch.pl not found, skipping kernel code style check"
        log_info "To install: sudo apt-get install linux-source"
    fi
}

# Check code formatting with clang-format
lint_code_formatting() {
    log_info "Checking code formatting with clang-format"

    # In CI mode, be extra careful about compilation-related tools
    if [[ $CI_MODE == true ]]; then
        log_info "CI mode: Using safe formatting analysis"
    fi

    if command -v clang-format &> /dev/null; then
        local kernel_files=()

        # Get files to check
        if [[ $CHANGED_FILES_ONLY == true ]]; then
            mapfile -t kernel_files < <(get_changed_files "kernel")
            if [[ ${#kernel_files[@]} -eq 0 ]]; then
                log_info "No changed kernel files, skipping format check"
                return 0
            fi
            log_info "Checking format of ${#kernel_files[@]} changed kernel file(s)"
        else
            kernel_files=(
                "$PROJECT_ROOT/kernel/nxp_simtemp.c"
                "$PROJECT_ROOT/kernel/nxp_simtemp.h"
                "$PROJECT_ROOT/kernel/nxp_simtemp_ioctl.h"
            )
        fi

        local failed=0
        for file in "${kernel_files[@]}"; do
            if [[ -f "$file" ]]; then
                log_info "Checking formatting of $(basename "$file")"

                # Check if file would be reformatted
                local format_diff
                format_diff=$(clang-format "$file" | diff -u "$file" - 2>/dev/null || true)
                
                if [[ -z "$format_diff" ]]; then
                    log_success "$(basename "$file") is properly formatted"
                else
                    if [[ $AUTO_FIX == true ]]; then
                        log_info "Auto-fixing formatting of $(basename "$file")"
                        clang-format -i "$file"
                        log_success "$(basename "$file") formatting fixed"
                    else
                        log_warning "$(basename "$file") formatting could be improved"
                        log_info "Formatting differences found:"
                        echo "$format_diff" | head -20  # Show first 20 lines of diff
                        if [[ $(echo "$format_diff" | wc -l) -gt 20 ]]; then
                            log_info "... (showing first 20 lines, use --fix to auto-format)"
                        fi
                        log_info "Run with --fix to auto-format files"
                        failed=1
                    fi
                fi
            fi
        done

        track_result $failed "Code formatting check"
    else
        log_warning "clang-format not found, skipping formatting check"
        log_info "To install: sudo apt-get install clang-format"
    fi
}

# Check Python code
lint_python_code() {
    log_info "Linting Python code"

    local python_files=()

    # Get files to check
    if [[ $CHANGED_FILES_ONLY == true ]]; then
        mapfile -t python_files < <(get_changed_files "python")
        if [[ ${#python_files[@]} -eq 0 ]]; then
            log_info "No changed Python files, skipping Python checks"
            return 0
        fi
        log_info "Checking ${#python_files[@]} changed Python file(s)"
    else
        python_files=(
            "$PROJECT_ROOT/user/cli/main.py"
            "$PROJECT_ROOT/user/gui/app.py"
        )
    fi

    # Check syntax first
    local syntax_failed=0
    for file in "${python_files[@]}"; do
        if [[ -f "$file" ]]; then
            log_info "Checking syntax of $(basename "$file")"
            
            # In CI mode, be careful with Python compilation
            if [[ $CI_MODE == true ]]; then
                # Use basic syntax check instead of py_compile in CI
                if python3 -m ast "$file" >/dev/null 2>&1; then
                    log_success "$(basename "$file") syntax OK"
                else
                    log_error "$(basename "$file") has syntax errors"
                    syntax_failed=1
                fi
            else
                if python3 -m py_compile "$file"; then
                    log_success "$(basename "$file") syntax OK"
                else
                    log_error "$(basename "$file") has syntax errors"
                    syntax_failed=1
                fi
            fi
        fi
    done

    track_result $syntax_failed "Python syntax check"

    # Check with flake8 if available
    if command -v flake8 &> /dev/null; then
        local flake8_failed=0
        for file in "${python_files[@]}"; do
            if [[ -f "$file" ]]; then
                log_info "Running flake8 on $(basename "$file")"
                if flake8 --max-line-length=120 --ignore=E402,W503 "$file"; then
                    log_success "$(basename "$file") passes flake8"
                else
                    log_warning "$(basename "$file") has flake8 warnings"
                    flake8_failed=1
                fi
            fi
        done

        track_result $flake8_failed "Python flake8 check"
    else
        log_warning "flake8 not found, skipping Python style check"
        log_info "To install: pip3 install flake8"
    fi

    # Check with pylint if available
    if command -v pylint &> /dev/null; then
        local pylint_failed=0
        for file in "${python_files[@]}"; do
            if [[ -f "$file" ]]; then
                log_info "Running pylint on $(basename "$file")"
                # Pylint score of 7.0 or higher is considered good
                if pylint --score=y "$file" 2>/dev/null | grep -q "rated at [7-9]\|rated at 10"; then
                    log_success "$(basename "$file") passes pylint"
                else
                    log_warning "$(basename "$file") has pylint issues"
                    pylint_failed=1
                fi
            fi
        done

        track_result $pylint_failed "Python pylint check"
    else
        log_warning "pylint not found, skipping advanced Python analysis"
        log_info "To install: pip3 install pylint"
    fi
}

# Check shell scripts
lint_shell_scripts() {
    log_info "Linting shell scripts"

    local shell_scripts=()

    # Get files to check
    if [[ $CHANGED_FILES_ONLY == true ]]; then
        mapfile -t shell_scripts < <(get_changed_files "shell")
        if [[ ${#shell_scripts[@]} -eq 0 ]]; then
            log_info "No changed shell scripts, skipping shell checks"
            return 0
        fi
        log_info "Checking ${#shell_scripts[@]} changed shell script(s)"
    else
        shell_scripts=(
            "$PROJECT_ROOT/scripts/build.sh"
            "$PROJECT_ROOT/scripts/run_demo.sh"
            "$PROJECT_ROOT/scripts/regression_test.sh"
            "$PROJECT_ROOT/scripts/lint.sh"
        )
    fi

    # Check syntax first
    local syntax_failed=0
    for script in "${shell_scripts[@]}"; do
        if [[ -f "$script" ]]; then
            log_info "Checking syntax of $(basename "$script")"
            if bash -n "$script"; then
                log_success "$(basename "$script") syntax OK"
            else
                log_error "$(basename "$script") has syntax errors"
                syntax_failed=1
            fi
        fi
    done

    track_result $syntax_failed "Shell script syntax check"

    # Check with shellcheck if available
    if command -v shellcheck &> /dev/null; then
        local shellcheck_failed=0
        for script in "${shell_scripts[@]}"; do
            if [[ -f "$script" ]]; then
                log_info "Running shellcheck on $(basename "$script")"
                if shellcheck -x "$script"; then
                    log_success "$(basename "$script") passes shellcheck"
                else
                    log_warning "$(basename "$script") has shellcheck issues"
                    shellcheck_failed=1
                fi
            fi
        done

        track_result $shellcheck_failed "Shell script shellcheck"
    else
        log_warning "shellcheck not found, skipping shell script analysis"
        log_info "To install: sudo apt-get install shellcheck"
    fi
}

# Check documentation
lint_documentation() {
    log_info "Checking documentation"

    local doc_files=(
        "$PROJECT_ROOT/docs/README.md"
        "$PROJECT_ROOT/docs/DESIGN.md"
        "$PROJECT_ROOT/docs/TESTPLAN.md"
        "$PROJECT_ROOT/docs/AI_NOTES.md"
    )

    # Changed-only mode: only check docs that actually changed
    if [[ $CHANGED_FILES_ONLY == true ]]; then
        mapfile -t doc_files < <(get_changed_files "docs" || true)
        if [[ ${#doc_files[@]} -eq 0 ]]; then
            log_info "No changed documentation files, skipping"
            track_result 0 "Documentation check"
            return 0
        fi
    else
        # If none of the expected docs exist yet, don't fail early repos
        if ! ls "${doc_files[@]}" >/dev/null 2>&1; then
            log_warning "Documentation files not present yet, skipping"
            track_result 0 "Documentation check"
            return 0
        fi
    fi

    local missing_docs=0
    for doc in "${doc_files[@]}"; do
        if [[ -f "$doc" ]]; then
            log_success "$(basename "$doc") exists"
            if [[ -s "$doc" ]]; then
                log_success "$(basename "$doc") is not empty"
            else
                log_warning "$(basename "$doc") is empty"
                missing_docs=1
            fi
        else
            log_warning "$(basename "$doc") is missing"
            # optional: still treat as soft-fail during bootstrap
            # missing_docs=1
        fi
    done

    track_result $missing_docs "Documentation check"

    # Markdown linter (optional)
    if command -v markdownlint >/dev/null; then
        local md_failed=0
        for doc in "${doc_files[@]}"; do
            [[ -f "$doc" ]] || continue
            log_info "Checking markdown syntax of $(basename "$doc")"
            markdownlint "$doc" || md_failed=1
        done
        track_result $md_failed "Markdown lint check"
    else
        log_warning "Markdown linter not found, skipping markdown syntax check"
        log_info "To install: npm install -g markdownlint-cli"
    fi
}

# Check file permissions
check_file_permissions() {
    log_info "Checking file permissions"

    local executable_files=(
        "$PROJECT_ROOT/scripts/build.sh"
        "$PROJECT_ROOT/scripts/run_demo.sh"
        "$PROJECT_ROOT/scripts/lint.sh"
        "$PROJECT_ROOT/user/cli/main.py"
        "$PROJECT_ROOT/user/gui/app.py"
        "$PROJECT_ROOT/tests/test_record_parsing.py"
    )

    local perm_failed=0
    for file in "${executable_files[@]}"; do
        if [[ -f "$file" ]]; then
            if [[ -x "$file" ]]; then
                log_success "$(basename "$file") is executable"
            else
                log_warning "$(basename "$file") should be executable"
                perm_failed=1
            fi
        fi
    done

    track_result $perm_failed "File permissions check"
}

# Check for TODO/FIXME/HACK comments
check_todos() {
    log_info "Checking for TODO/FIXME/HACK comments"

    local todo_count=0
    local source_files=(
        "$PROJECT_ROOT/kernel/"*.c
        "$PROJECT_ROOT/kernel/"*.h
        "$PROJECT_ROOT/user/cli/"*.py
        "$PROJECT_ROOT/user/gui/"*.py
        "$PROJECT_ROOT/scripts/"*.sh
        "$PROJECT_ROOT/tests/"*.sh
    )

    for pattern in "${source_files[@]}"; do
        for file in $pattern; do
            [[ -f "$file" ]] || continue
                # Skip this linter itself
                [[ "$(basename "$file")" == "lint.sh" ]] && continue

                local todos
                todos=$(grep -n -E '\<(TODO|FIXME|HACK)\>' "$file" || true)
                if [[ -n "$todos" ]]; then
                    log_info "Found TODO/FIXME/HACK in $(basename "$file"):"
                    echo "$todos"
                    todo_count=$((todo_count + 1))
                fi
        done
    done

    if [[ $todo_count -eq 0 ]]; then
        log_success "No TODO/FIXME/HACK comments found"
        track_result 0 "TODO/FIXME check"
    else
        log_warning "Found $todo_count files with TODO/FIXME/HACK comments"
        track_result 1 "TODO/FIXME check"
    fi
}

# Print summary
print_summary() {
    echo
    echo "================================"
    echo "        LINT SUMMARY"
    echo "================================"
    echo "Total checks: $TOTAL_CHECKS"
    echo "Passed: $PASSED_CHECKS"
    echo "Failed: $FAILED_CHECKS"
    echo

    if [[ $FAILED_CHECKS -eq 0 ]]; then
        log_success "All lint checks passed!"
        return 0
    else
        log_warning "$FAILED_CHECKS out of $TOTAL_CHECKS checks failed"
        echo
        echo "To improve code quality:"
        echo "1. Install missing tools (checkpatch, clang-format, flake8, shellcheck)"
        echo "2. Fix the reported issues"
        echo "3. Re-run this script"
        return 1
    fi
}

# Main function
main() {
    log_info "Starting NXP Simtemp Lint Checks"
    echo "Project root: $PROJECT_ROOT"

    # Parse command line arguments
    local check_kernel=true
    local check_python=true
    local check_shell=true
    local check_docs=true
    local check_perms=true
    local check_todos=true

    while [[ $# -gt 0 ]]; do
        case $1 in
            --kernel-only)
                check_python=false
                check_shell=false
                check_docs=false
                check_perms=false
                check_todos=false
                shift
                ;;
            --python-only)
                check_kernel=false
                check_shell=false
                check_docs=false
                check_perms=false
                check_todos=false
                shift
                ;;
            --shell-only)
                check_kernel=false
                check_python=false
                check_docs=false
                check_perms=false
                check_todos=false
                shift
                ;;
            --changed-only)
                CHANGED_FILES_ONLY=true
                shift
                ;;
            --base-branch)
                BASE_BRANCH="$2"
                shift 2
                ;;
            --fix)
                AUTO_FIX=true
                shift
                ;;
            --quiet|-q)
                QUIET_MODE=true
                shift
                ;;
            --no-todos)
                check_todos=false
                shift
                ;;
            --versions)
                check_tool_versions
                exit 0
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  --kernel-only        Check only kernel code"
                echo "  --python-only        Check only Python code"
                echo "  --shell-only         Check only shell scripts"
                echo "  --changed-only       Check only files changed from base branch"
                echo "  --base-branch BRANCH Base branch for --changed-only (default: main)"
                echo "  --fix                Auto-fix issues where possible"
                echo "  --quiet, -q          Suppress info messages"
                echo "  --no-todos           Skip TODO/FIXME check"
                echo "  --versions           Show tool versions and exit"
                echo "  -h, --help           Show this help"
                echo ""
                echo "Examples:"
                echo "  $0                                    # Check all files"
                echo "  $0 --changed-only                     # Check only changed files"
                echo "  $0 --changed-only --base-branch dev   # Check changes from 'dev' branch"
                echo "  $0 --kernel-only --fix                # Check and auto-fix kernel code"
                echo "  $0 --quiet --changed-only             # Quiet mode, changed files only"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    if [[ $CHANGED_FILES_ONLY == true ]]; then
        log_info "Mode: Changed files only (base: $BASE_BRANCH)"
    else
        log_info "Mode: Full codebase scan"
    fi

    if [[ $AUTO_FIX == true ]]; then
        log_info "Auto-fix: Enabled"
    fi

    echo

    # Run checks
    [[ $check_kernel == true ]] && lint_kernel_code
    [[ $check_kernel == true ]] && lint_code_formatting
    [[ $check_python == true ]] && lint_python_code
    [[ $check_shell == true ]] && lint_shell_scripts
    [[ $check_docs == true ]] && lint_documentation
    [[ $check_perms == true ]] && check_file_permissions
    [[ $check_todos == true ]] && check_todos

    # Print summary and exit with appropriate code
    print_summary
}

# Run main function
main "$@"
#!/usr/bin/env bash
# Copy application modules and resources from a checkout into an installation.
# The calling installer enables errexit and pipefail.

install_application_files() (
    local checkout_dir=$1
    local install_dir=$2
    local service_account=$3
    local staging_dir

    staging_dir=$(mktemp -d -- "$install_dir/.application.XXXXXX")
    cleanup_application_files() {
        if [[ ( -e $staging_dir/previous || -L $staging_dir/previous ) &&
              ! -e $install_dir/ax3l && ! -L $install_dir/ax3l ]]; then
            mv -- "$staging_dir/previous" "$install_dir/ax3l" || return
        fi
        rm -rf -- "$staging_dir"
    }
    trap cleanup_application_files EXIT

    cd -- "$checkout_dir"
    find ax3l -type f \( \
        -name '*.py' -o \
        -name '*.schema.json' -o \
        -path 'ax3l/presentation/prompts/*.md' -o \
        -path 'ax3l/presentation/reporting/templates/*.html' -o \
        -path 'ax3l/presentation/reporting/fonts/*' \
    \) -print0 |
        while IFS= read -r -d '' source; do
            install -D -m 644 -o "$service_account" -g "$service_account" \
                -- "$source" "$staging_dir/$source"
        done

    [[ -d $staging_dir/ax3l ]] || { printf 'No application files found.\n' >&2; exit 1; }
    if [[ -e $install_dir/ax3l || -L $install_dir/ax3l ]]; then
        mv -- "$install_dir/ax3l" "$staging_dir/previous"
    fi
    if ! mv -- "$staging_dir/ax3l" "$install_dir/ax3l"; then
        exit 1
    fi
)

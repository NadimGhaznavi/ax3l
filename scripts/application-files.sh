#!/usr/bin/env bash
# Copy application modules and resources from a checkout into an installation.
# The calling installer enables errexit and pipefail.

install_application_files() (
    local checkout_dir=$1
    local install_dir=$2
    local service_account=$3

    cd -- "$checkout_dir"
    find ax3l -type f \( \
        -name '*.py' -o \
        -name '*.schema.json' -o \
        -path 'ax3l/presentation/prompts/*.md' -o \
        -path 'ax3l/server/templates/*.html' -o \
        -path 'ax3l/activity/fonts/*' \
    \) -print0 |
        while IFS= read -r -d '' source; do
            install -D -m 644 -o "$service_account" -g "$service_account" \
                -- "$source" "$install_dir/$source"
        done
)

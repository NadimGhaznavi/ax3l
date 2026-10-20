#!/usr/bin/env bash
# Apply network overrides without reinstalling application code or dependencies.
set -euo pipefail
umask 022
if [[ $# == 1 && ( $1 == --help || $1 == -h ) ]]; then
    printf 'Usage: sudo scripts/restart.sh [-model qwen|phi|qwenv]\nApply conf/ax3l.json and restart the selected model and application services.\n'
    exit 0
fi
selected_model=qwen
if [[ $# == 2 && $1 == -model && ( $2 == qwen || $2 == phi || $2 == qwenv ) ]]; then
    selected_model=$2
elif [[ $# != 0 ]]; then
    printf 'Expected no arguments or -model qwen|phi|qwenv.\n' >&2
    exit 2
fi
[[ $EUID == 0 ]] || { printf 'Run scripts/restart.sh as root.\n' >&2; exit 1; }
checkout_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
install_dir=/opt/prod/ax3l
config_dir=/etc/ax3l
service_account=ax3l
. "$checkout_dir/scripts/service-configuration.sh"
resolve_service_configuration
render_service_units
"$checkout_dir/scripts/services.sh" stop
install_service_units
"$checkout_dir/scripts/services.sh" start -model "$selected_model"
printf 'Applied network configuration and restarted Ax3l.\n'

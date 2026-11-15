#!/usr/bin/env bash
# Apply network overrides without reinstalling application code or dependencies.
set -euo pipefail
umask 022
if [[ $# == 1 && ( $1 == --help || $1 == -h ) ]]; then
    printf 'Usage: sudo scripts/restart.sh\nApply conf/ax3l.json and restart Ax3l services.\n'
    exit 0
fi
if [[ $# != 0 ]]; then
    printf 'Expected no arguments.\n' >&2
    exit 2
fi
[[ $EUID == 0 ]] || { printf 'Run scripts/restart.sh as root.\n' >&2; exit 1; }
checkout_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
install_dir=/opt/prod/ax3l
config_dir=/etc/ax3l
. "$checkout_dir/scripts/service-configuration.sh"
resolve_service_configuration
render_service_units
"$checkout_dir/scripts/services.sh" stop
install_service_units
"$checkout_dir/scripts/services.sh" start
printf 'Applied network configuration and restarted Ax3l.\n'

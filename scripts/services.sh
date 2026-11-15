#!/usr/bin/env bash
# Start or stop Ax3l's application services in dependency order.
set -euo pipefail

usage() {
    printf 'Usage: sudo scripts/services.sh start|stop\n'
}

if [[ $# == 1 && ( $1 == -h || $1 == --help ) ]]; then
    usage
    exit 0
fi
if [[ $# != 1 || ( ${1:-} != start && ${1:-} != stop ) ]]; then
    usage >&2
    exit 2
fi

[[ $EUID == 0 ]] || { printf 'Run service commands as root.\n' >&2; exit 1; }

if [[ $1 == start ]]; then
    for name in reporting-server ax3l-server watchdog; do
        printf 'Starting %s.\n' "$name"
        systemctl start "$name.service"
    done
else
    for name in watchdog ax3l-server reporting-server; do
        printf 'Stopping %s.\n' "$name"
        if [[ $(systemctl show -p LoadState --value "$name.service") != not-found ]]; then
            systemctl stop "$name.service"
        fi
    done
fi

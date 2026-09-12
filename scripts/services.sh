#!/usr/bin/env bash
# Start or stop all four services in dependency order.
set -euo pipefail

usage() {
    printf 'Usage: scripts/services.sh -env dev|qa|prod start|stop\n'
}

if [[ $# == 1 && ( $1 == -h || $1 == --help ) ]]; then
    usage
    exit 0
fi
if [[ $# != 3 || $1 != -env || ( $3 != start && $3 != stop ) ]]; then
    usage >&2
    exit 2
fi

system_admin=()
case "$2" in
    dev)
        suffix=-dev
        if [[ $EUID != 0 ]]; then
            system_admin=(sudo)
        fi
        ;;
    qa|prod)
        [[ $EUID == 0 ]] || { printf 'QA/prod require root.\n' >&2; exit 1; }
        if [[ $2 == qa ]]; then suffix=-qa; else suffix=; fi
        ;;
    *) usage >&2; exit 2 ;;
esac

if [[ $3 == start ]]; then
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
    startup_seconds=$(python3 -c 'from ax3l.constants.DQwen import DQwen; print(DQwen.STARTUP_SECONDS)')
    printf 'Starting llm-server%s; waiting %s seconds.\n' "$suffix" "$startup_seconds"
    "${system_admin[@]}" systemctl start "llm-server$suffix.service"
    sleep "$startup_seconds"
    for name in reporting-server ax3l-server watchdog; do
        printf 'Starting %s%s.\n' "$name" "$suffix"
        "${system_admin[@]}" systemctl start "$name$suffix.service"
    done
else
    for name in watchdog ax3l-server reporting-server llm-server; do
        printf 'Stopping %s%s.\n' "$name" "$suffix"
        "${system_admin[@]}" systemctl stop "$name$suffix.service"
    done
fi

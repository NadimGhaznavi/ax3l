#!/usr/bin/env bash
# Start or stop the selected model and application services in dependency order.
set -euo pipefail

usage() {
    printf 'Usage: scripts/services.sh -env dev|qa|prod start|stop [-model qwen|phi]\n'
}

if [[ $# == 1 && ( $1 == -h || $1 == --help ) ]]; then
    usage
    exit 0
fi
if [[ ( $# != 3 && $# != 5 ) || $1 != -env || ( $3 != start && $3 != stop ) ]]; then
    usage >&2
    exit 2
fi

model=qwen
if [[ $# == 5 ]]; then
    [[ $4 == -model && ( $5 == qwen || $5 == phi ) ]] || { usage >&2; exit 2; }
    model=$5
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
    startup_seconds=$(python3 - "$model" <<'PYMODEL'
import sys
from ax3l.constants.DQwen import DQwen
from ax3l.constants.DPhi import DPhi
print({"qwen": DQwen, "phi": DPhi}[sys.argv[1]].STARTUP_SECONDS)
PYMODEL
)
    other=phi
    if [[ $model == phi ]]; then other=qwen; fi
    "${system_admin[@]}" systemctl disable --now "$other-server$suffix.service"
    "${system_admin[@]}" systemctl enable "$model-server$suffix.service"
    printf 'Starting %s-server%s; waiting %s seconds.\n' "$model" "$suffix" "$startup_seconds"
    "${system_admin[@]}" systemctl start "$model-server$suffix.service"
    sleep "$startup_seconds"
    for name in reporting-server ax3l-server watchdog; do
        printf 'Starting %s%s.\n' "$name" "$suffix"
        "${system_admin[@]}" systemctl start "$name$suffix.service"
    done
else
    for name in watchdog ax3l-server reporting-server qwen-server phi-server llm-server; do
        printf 'Stopping %s%s.\n' "$name" "$suffix"
        if [[ $(systemctl show -p LoadState --value "$name$suffix.service") != not-found ]]; then
            "${system_admin[@]}" systemctl stop "$name$suffix.service"
        fi
    done
fi

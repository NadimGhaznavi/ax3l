#!/usr/bin/env bash
# Start or stop the selected model and application services in dependency order.
set -euo pipefail

usage() {
    printf 'Usage: sudo scripts/services.sh start|stop [-model qwen|phi|qwen2.5]\n'
}

if [[ $# == 1 && ( $1 == -h || $1 == --help ) ]]; then
    usage
    exit 0
fi
if [[ ( $# != 1 && $# != 3 ) || ( ${1:-} != start && ${1:-} != stop ) ]]; then
    usage >&2
    exit 2
fi

model=qwen
if [[ $# == 3 ]]; then
    [[ $2 == -model && ( $3 == qwen || $3 == phi || $3 == qwen2.5 ) ]] || { usage >&2; exit 2; }
    model=$3
fi

[[ $EUID == 0 ]] || { printf 'Run service commands as root.\n' >&2; exit 1; }

if [[ $1 == start ]]; then
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
    startup_seconds=$(python3 - "$model" <<'PYMODEL'
import sys
from ax3l.constants.DQwen import DQwen
from ax3l.constants.DPhi import DPhi
from ax3l.constants.DQwen25 import DQwen25
print({"qwen": DQwen, "phi": DPhi, "qwen2.5": DQwen25}[sys.argv[1]].STARTUP_SECONDS)
PYMODEL
)
    systemctl enable "$model-server.service"
    printf 'Starting %s-server; waiting %s seconds.\n' "$model" "$startup_seconds"
    systemctl start "$model-server.service"
    sleep "$startup_seconds"
    for name in reporting-server ax3l-server watchdog; do
        printf 'Starting %s.\n' "$name"
        systemctl start "$name.service"
    done
else
    for name in watchdog ax3l-server reporting-server qwen-server phi-server qwen2.5-server qwenv-server llm-server; do
        printf 'Stopping %s.\n' "$name"
        if [[ $(systemctl show -p LoadState --value "$name.service") != not-found ]]; then
            systemctl stop "$name.service"
        fi
    done
fi

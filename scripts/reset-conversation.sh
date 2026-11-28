#!/usr/bin/env bash
# Rebuild the pending conversation from its saved experiment stage.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: sudo scripts/reset-conversation.sh

Interrupts the current Ax3l request and restarts ax3l-server.service.
The pending selection or evaluation starts a new conversation with a freshly
rendered prompt and image, using the installed templates, code, and run data.
Preserves experiment progress, completed simulations, and conversation logs.
Temporarily stops the watchdog if running, then restores it, including on failure.
Reporting, SnakeLab, and LlamaSrv remain running.

Run as root after deploying any prompt or plotting changes. This helper does
not install code or dependencies; use scripts/upgrade.sh to update the installation.
HELP
}

if [[ $# == 1 && ( $1 == -h || $1 == --help ) ]]; then
    usage
    exit 0
fi
if [[ $# != 0 ]]; then
    usage >&2
    exit 2
fi
[[ $EUID == 0 ]] || { printf 'Run scripts/reset-conversation.sh as root.\n' >&2; exit 1; }
[[ $(systemctl show -p LoadState --value ax3l-server.service) == loaded ]] || {
    printf 'Install ax3l-server.service before resetting a conversation.\n' >&2
    exit 1
}

(
    if systemctl is-active --quiet watchdog.service; then
        trap 'systemctl start watchdog.service' EXIT
        systemctl stop watchdog.service
    fi
    printf 'Interrupting the current request and restarting Ax3l.\n'
    systemctl restart ax3l-server.service
)
printf 'Ax3l restarted. The pending conversation will rebuild its prompt and image from the saved stage.\n'

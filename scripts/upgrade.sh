#!/usr/bin/env bash
# Update an existing installation from this checkout.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: sudo scripts/upgrade.sh

Updates application modules and systemd units from the current checkout,
then starts Ax3l's three services in dependency order. Services are stopped
before files are replaced. Existing database, credentials, and accounts
are preserved; no MariaDB administrative access is needed.

Run as root. Run install.sh first if Ax3l has not been installed.
LlamaSrv is managed separately. This does not pull Git changes.
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

checkout_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
"$checkout_dir/scripts/install-services.sh"
printf 'Upgraded Ax3l from %s.\n' "$checkout_dir"

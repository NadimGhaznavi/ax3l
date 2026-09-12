#!/usr/bin/env bash
# Update an existing installation from this checkout.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: scripts/upgrade.sh -env dev|qa|prod [-model qwen|phi|qwenv]

Updates application modules and systemd units from the current checkout,
then starts all four services in dependency order. Services are stopped
before files are replaced. Existing database, credentials, and accounts
are preserved; no MariaDB administrative access is needed.

Run dev as the development user (uses sudo); QA/prod require root.
Run install.sh first if this environment has not been installed.
This does not pull Git changes or update llama.cpp or model files.
HELP
}

if [[ $# == 1 && ( $1 == -h || $1 == --help ) ]]; then
    usage
    exit 0
fi
if [[ ( $# != 2 && $# != 4 ) || $1 != -env ]]; then
    usage >&2
    exit 2
fi
case "$2" in
    dev|qa|prod) ;;
    *) usage >&2; exit 2 ;;
esac

checkout_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
"$checkout_dir/scripts/install-services.sh" "$@"
printf 'Upgraded %s from %s.\n' "$2" "$checkout_dir"

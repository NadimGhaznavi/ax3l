#!/usr/bin/env bash
# Discard only the current unsubmitted setup, then start a fresh experiment.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: sudo scripts/wipe-experiment-workspace.sh

Clears the current unsubmitted experiment's draft, saved choices, conversations,
and related tool/chart events. Preserves golden, completed runs, and analyses.
Stops Ax3l services before clearing state and starts them again afterward.
Refuses experiments whose simulation submission or seed rotation has started.
Leaves Ax3l stopped if clearing fails. SnakeLab and LlamaSrv remain running.
Uses /etc/ax3l/database.env and the installed Python environment.
Run from the current project checkout; no reinstall is required for this helper.
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
[[ $(id -u) == 0 ]] || { printf 'Run as root using sudo.\n' >&2; exit 1; }
checkout_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
install_dir=/opt/prod/ax3l
config_file=/etc/ax3l/database.env
[[ -x $install_dir/.venv/bin/python ]] || { printf 'Ax3l Python environment is missing.\n' >&2; exit 1; }
[[ -r $config_file ]] || { printf 'Cannot read %s\n' "$config_file" >&2; exit 1; }

# Read the generated key/value file literally; never execute credentials.
unset DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD
while IFS='=' read -r name value; do
    case $name in
        DB_HOST|DB_PORT|DB_NAME|DB_USER|DB_PASSWORD) export "$name=$value" ;;
    esac
done < "$config_file"
for name in DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD; do
    [[ -n ${!name:-} ]] || { printf 'Missing %s in %s\n' "$name" "$config_file" >&2; exit 1; }
done

cd -- "$checkout_dir"
"$install_dir/.venv/bin/python" -m ax3l.app.snakelab.WipeExperimentWorkspace --check
"$checkout_dir/scripts/services.sh" stop
if ! "$install_dir/.venv/bin/python" -m ax3l.app.snakelab.WipeExperimentWorkspace; then
    printf 'Workspace reset failed. Ax3l services remain stopped.\n' >&2
    exit 1
fi
"$checkout_dir/scripts/services.sh" start
printf 'Ax3l services started. The next experiment begins from golden with a fresh conversation.\n'

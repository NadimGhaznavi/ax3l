#!/usr/bin/env bash
# Dump the configured local Ax3l database into the current directory.

set -Eeuo pipefail
umask 077

usage() {
    cat <<'HELP'
Usage: sudo scripts/backup-db.sh

Backs up the local Ax3l database named in the checkout's
prod_etc/ax3l/database.env (DEV), or /etc/ax3l/database.env (PROD).
Writes a private, timestamped SQL dump into the current directory.
Uses MariaDB root socket authentication. Does not include SnakeLab.
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
config_file="$checkout_dir/prod_etc/ax3l/database.env"
if [[ ! -f $config_file ]]; then
    config_file=/etc/ax3l/database.env
fi
# Read only the database name; do not execute the credentials file.
database=$(sed -n 's/^DB_NAME=//p' "$config_file")
if [[ ! $database =~ ^[a-zA-Z0-9_]+$ ]]; then
    printf 'Missing or invalid DB_NAME in %s\n' "$config_file" >&2
    exit 1
fi

readonly OUTPUT="$(date +'%Y-%m-%d_%H:%M')-${database}-db.dump"

# Refuse to overwrite a backup created in the same minute.
set -o noclobber
exec 3>"${OUTPUT}"
trap 'rm -f -- "${OUTPUT}"' EXIT

mariadb-dump --no-defaults --user=root --protocol=socket --single-transaction --quick \
    --routines --events --triggers --databases "$database" >&3
exec 3>&-

trap - EXIT
printf 'Backup saved to %s/%s\n' "${PWD}" "${OUTPUT}"

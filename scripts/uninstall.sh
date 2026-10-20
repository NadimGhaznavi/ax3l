#!/usr/bin/env bash
# Remove the resources provisioned by install.sh for Ax3l.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: sudo scripts/uninstall.sh

Stops and removes Ax3l service units, then deletes /opt/prod/ax3l,
/etc/ax3l/database.env, the local ax3l MariaDB database/account, and the
ax3l Linux account/group. All Ax3l data is deleted. Requires root and
MariaDB administrative access through local socket authentication.
HELP
}

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

if [[ $# == 1 && ( $1 == -h || $1 == --help ) ]]; then
    usage
    exit 0
fi
if [[ $# != 0 ]]; then
    usage >&2
    exit 2
fi
[[ $EUID == 0 ]] || fail "Run uninstallation as root."
install_dir=/opt/prod/ax3l
config_dir=/etc/ax3l
database=ax3l
service_account=ax3l
admin=(mariadb --protocol=socket)

credentials_file="$config_dir/database.env"
if [[ -e "$credentials_file" ]]; then
    grep -Fxq "DB_NAME=$database" "$credentials_file" ||
        fail "Credentials do not match the installation."
fi

for name in watchdog ax3l-server reporting-server qwen-server phi-server qwen2.5-server qwenv-server llm-server; do
    unit="$name.service"
    if [[ -f /etc/systemd/system/$unit ]]; then
        systemctl disable --now "$unit"
        rm -- "/etc/systemd/system/$unit"
    fi
done
systemctl daemon-reload

"${admin[@]}" <<SQL
DROP DATABASE IF EXISTS \`$database\`;
DROP USER IF EXISTS '$database'@'localhost';
SQL

rm -rf -- "$install_dir"
rm -f -- "$credentials_file"
if [[ -d "$config_dir" ]]; then
    rmdir -- "$config_dir"
fi
if getent passwd "$service_account" >/dev/null; then
    userdel "$service_account"
fi
if getent group "$service_account" >/dev/null; then
    groupdel "$service_account"
fi

printf 'Removed Ax3l installation, credentials, database/account %s, and Linux account/group %s.\n' \
    "$database" "$service_account"

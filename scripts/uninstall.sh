#!/usr/bin/env bash
# Remove the resources provisioned by install.sh for one environment.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: scripts/uninstall.sh -env dev|qa|prod [-db-admin-sudo]

Deletes the selected installation directory, database credentials, local
MariaDB database/account, and Linux service account/group:
  dev:  <checkout>/ax3l_prod, <checkout>/prod_etc/ax3l/database.env,
        database/account ax3l_dev, Linux account/group ax3l_dev
  qa:   /opt/qa/ax3l, /etc/ax3l/database.env,
        database/account ax3l_qa, Linux account/group ax3l
  prod: /opt/prod/ax3l, /etc/ax3l/database.env,
        database/account ax3l, Linux account/group ax3l

All data in the selected database and installation directory is deleted.
Run dev as the development user; sudo handles Linux account and directory
removal. -db-admin-sudo also uses sudo for MariaDB administration.
Run QA/prod as root on the corresponding machine. Stop any processes using
the installation before uninstalling. Installed Ax3l units are stopped,
disabled, and removed before their application resources are deleted.
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
if [[ ( $# != 2 && $# != 3 ) || ${1:-} != -env ]]; then
    usage >&2
    exit 2
fi
if [[ $# == 3 && $3 != -db-admin-sudo ]]; then
    fail "Unknown option '$3'."
fi

case "$2" in
    dev)
        [[ $EUID != 0 ]] || fail "Run dev uninstallation as the development user, not root."
        checkout_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
        install_dir="$checkout_dir/ax3l_prod"
        config_dir="$checkout_dir/prod_etc/ax3l"
        database=ax3l_dev
        service_account=ax3l_dev
        system_admin=(sudo)
        ;;
    qa|prod)
        [[ $EUID == 0 ]] || fail "Environment '$2' requires root."
        [[ $# == 2 ]] || fail "-db-admin-sudo is only supported for dev."
        install_dir="/opt/$2/ax3l"
        config_dir=/etc/ax3l
        if [[ $2 == qa ]]; then
            database=ax3l_qa
        else
            database=ax3l
        fi
        service_account=ax3l
        system_admin=()
        ;;
    *) fail "Invalid environment '$2'; expected dev, qa, or prod." ;;
esac

admin=(mariadb --protocol=socket)
if [[ $# == 3 ]]; then
    admin=(sudo mariadb --protocol=socket --user=root)
fi

credentials_file="$config_dir/database.env"
# QA and prod use the same credentials path on their respective machines.
if [[ -e "$credentials_file" ]]; then
    grep -Fxq "DB_NAME=$database" "$credentials_file" ||
        fail "Credentials do not match the selected environment."
fi

case "$2" in
    dev) suffix=-dev ;;
    qa) suffix=-qa ;;
    prod) suffix= ;;
esac
for name in watchdog ax3l-server reporting-server qwen-server phi-server llm-server; do
    unit="$name$suffix.service"
    if [[ -f /etc/systemd/system/$unit ]]; then
        "${system_admin[@]}" systemctl disable --now "$unit"
        "${system_admin[@]}" rm -- "/etc/systemd/system/$unit"
    fi
done
"${system_admin[@]}" systemctl daemon-reload

"${admin[@]}" <<SQL
DROP DATABASE IF EXISTS \`$database\`;
DROP USER IF EXISTS '$database'@'localhost';
SQL

"${system_admin[@]}" rm -rf -- "$install_dir"
rm -f -- "$credentials_file"
if [[ -d "$config_dir" ]]; then
    rmdir -- "$config_dir"
fi
if getent passwd "$service_account" >/dev/null; then
    "${system_admin[@]}" userdel "$service_account"
fi
if getent group "$service_account" >/dev/null; then
    "${system_admin[@]}" groupdel "$service_account"
fi

printf 'Removed %s installation, credentials, database/account %s, and Linux account/group %s.\n' \
    "$2" "$database" "$service_account"

#!/usr/bin/env bash
# Prepare local MariaDB storage and credentials for an Ax3l installation.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: sudo scripts/install.sh

Prepares /opt/prod/ax3l, the ax3l Linux account/group, the local ax3l
MariaDB database/account, and /etc/ax3l/database.env. Existing credentials
are reused; existing account passwords are not reset. Requires root and
MariaDB administrative access through local socket authentication.
Installs application modules and enables/starts the model and application
services. Requires the llama.cpp binary and model configured in constants.
No release publication is performed.
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
[[ $EUID == 0 ]] || fail "Run installation as root."
install_dir=/opt/prod/ax3l
config_dir=/etc/ax3l

command -v mariadb >/dev/null || fail "Install the MariaDB client first."
command -v openssl >/dev/null || fail "Install openssl first."
admin=(mariadb --protocol=socket)

DB_HOST=localhost
DB_PORT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &&
    python3 -c 'from ax3l.constants.DDbMgr import DDbMgr; print(DDbMgr.PORT)')
DB_NAME=ax3l
DB_USER=$DB_NAME
# Underscores are wildcards in MariaDB database-level grants.
grant_database=${DB_NAME//_/\\_}
credentials_file="$config_dir/database.env"
[[ ! -L "$credentials_file" ]] || fail "Credentials path must not be a symlink."
if [[ -e "$credentials_file" ]]; then
    [[ -f "$credentials_file" && -O "$credentials_file" ]] ||
        fail "Existing credentials must be a regular file owned by the current user."
    [[ $(stat -c '%a' "$credentials_file") == 600 ]] ||
        fail "Existing credentials must have mode 600."
    # Accept only the exact generated contract; never execute a credentials file.
    mapfile -t config_lines < "$credentials_file"
    [[ ${#config_lines[@]} == 5 ]] || fail "Invalid credentials file format."
    [[ ${config_lines[0]} == "DB_HOST=$DB_HOST" &&
       ${config_lines[1]} == "DB_PORT=$DB_PORT" &&
       ${config_lines[2]} == "DB_NAME=$DB_NAME" &&
       ${config_lines[3]} == "DB_USER=$DB_USER" &&
       ${config_lines[4]} =~ ^DB_PASSWORD=([a-f0-9]{64})$ ]] ||
        fail "Existing credentials do not match the installation contract."
    DB_PASSWORD=${BASH_REMATCH[1]}
else
    DB_PASSWORD=$(openssl rand -hex 32)
fi

# All SQL identifiers are fixed by the installation contract; the password is hex.
# Check administrative access before creating files or directories.
"${admin[@]}" --batch --skip-column-names -e 'SELECT 1' >/dev/null ||
    fail "MariaDB administrative access failed."

umask 077
mkdir -p -- "$config_dir"
service_account=ax3l
if ! getent group "$service_account" >/dev/null; then
    groupadd --system "$service_account"
fi
if ! getent passwd "$service_account" >/dev/null; then
    useradd --system --gid "$service_account" --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin "$service_account"
fi
install -d -m 755 -o "$service_account" -g "$service_account" -- "$install_dir"
if [[ ! -e "$credentials_file" ]]; then
    # Keep the generated password if provisioning fails, so a rerun can recover.
    (
        set -o noclobber
        printf 'DB_HOST=%s\nDB_PORT=%s\nDB_NAME=%s\nDB_USER=%s\nDB_PASSWORD=%s\n' \
            "$DB_HOST" "$DB_PORT" "$DB_NAME" "$DB_USER" "$DB_PASSWORD" > "$credentials_file"
    )
fi

"${admin[@]}" <<SQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\`;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON \`$grant_database\`.* TO '$DB_USER'@'localhost';
GRANT SELECT ON \`snakelab\`.* TO '$DB_USER'@'localhost';
SQL

MYSQL_PWD="$DB_PASSWORD" mariadb --no-defaults --protocol=socket \
    --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" --database="$DB_NAME" \
    --batch --skip-column-names -e 'SELECT 1' >/dev/null ||
    fail "Database login failed. An existing account may have a different password; it was not reset."

printf 'Installation directory ready: %s\n' "$install_dir"
printf 'Credentials ready: %s\n' "$credentials_file"
printf 'Verified local MariaDB account %s on database %s.\n' "$DB_USER" "$DB_NAME"

"$(dirname -- "${BASH_SOURCE[0]}")/install-services.sh"

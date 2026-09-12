#!/usr/bin/env bash
# Prepare local MariaDB storage and credentials for an Ax3l installation.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: scripts/install.sh -env dev|qa|prod [-db-admin-sudo]

dev:  <checkout>/ax3l_prod and <checkout>/prod_etc/ax3l/database.env
qa:   /opt/qa/ax3l and /etc/ax3l/database.env (requires root)
prod: /opt/prod/ax3l and /etc/ax3l/database.env (requires root)

Creates a local database and matching account:
  dev: ax3l_dev    qa: ax3l_qa    prod: ax3l
Run prod on the production machine to provision its local MariaDB server.
Generates a password, creates the installation directory, and writes
owner-only credentials.
Creates a Linux system user/group if absent: ax3l_dev for dev, ax3l for QA/prod.
These accounts have no home directory or interactive login. Each owns its
installation directory. Dev uses sudo for Linux account and directory setup.
Existing credentials are reused; existing account passwords are not reset.
MariaDB must already be running. Its current administrative connection must
have permission to create databases/users and grant database privileges.
For dev, -db-admin-sudo additionally uses sudo for the MariaDB administrative client.
No code deployment, service startup, or release publication is performed.
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
install_env=$2
case "$install_env" in
    dev)
        [[ $EUID != 0 ]] || fail "Run dev installation as the development user, not root."
        checkout_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
        install_dir="$checkout_dir/ax3l_prod"
        config_dir="$checkout_dir/prod_etc/ax3l"
        ;;
    qa|prod)
        [[ $EUID == 0 ]] || fail "Environment '$install_env' requires root."
        [[ $# == 2 ]] || fail "-db-admin-sudo is only supported for dev."
        install_dir="/opt/$install_env/ax3l"
        config_dir=/etc/ax3l
        ;;
    *) fail "Invalid environment '$install_env'; expected dev, qa, or prod." ;;
esac

command -v mariadb >/dev/null || fail "Install the MariaDB client first."
command -v openssl >/dev/null || fail "Install openssl first."
admin=(mariadb --protocol=socket)
if [[ $# == 3 ]]; then
    admin=(sudo mariadb --protocol=socket --user=root)
fi

DB_HOST=localhost
DB_PORT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &&
    python3 -c 'from ax3l.constants.DDbMgr import DDbMgr; print(DDbMgr.PORT)')
case "$install_env" in
    dev) DB_NAME=ax3l_dev ;;
    qa) DB_NAME=ax3l_qa ;;
    prod) DB_NAME=ax3l ;;
esac
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
        fail "Existing credentials do not match the '$install_env' installation contract."
    DB_PASSWORD=${BASH_REMATCH[1]}
else
    DB_PASSWORD=$(openssl rand -hex 32)
fi

# All SQL identifiers are fixed by the validated environment; the password is hex.
# Check administrative access before creating files or directories.
"${admin[@]}" --batch --skip-column-names -e 'SELECT 1' >/dev/null ||
    fail "MariaDB administrative access failed; for dev, configure access or use -db-admin-sudo."

umask 077
mkdir -p -- "$config_dir"
if [[ $install_env == dev ]]; then
    service_account=ax3l_dev
    system_admin=(sudo)
else
    service_account=ax3l
    system_admin=()
fi
if ! getent group "$service_account" >/dev/null; then
    "${system_admin[@]}" groupadd --system "$service_account"
fi
if ! getent passwd "$service_account" >/dev/null; then
    "${system_admin[@]}" useradd --system --gid "$service_account" --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin "$service_account"
fi
"${system_admin[@]}" install -d -m 755 -o "$service_account" -g "$service_account" -- "$install_dir"
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
SQL

MYSQL_PWD="$DB_PASSWORD" mariadb --no-defaults --protocol=socket \
    --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" --database="$DB_NAME" \
    --batch --skip-column-names -e 'SELECT 1' >/dev/null ||
    fail "Database login failed. An existing account may have a different password; it was not reset."

printf 'Installation directory ready: %s\n' "$install_dir"
printf 'Credentials ready: %s\n' "$credentials_file"
printf 'Verified local MariaDB account %s on database %s.\n' "$DB_USER" "$DB_NAME"

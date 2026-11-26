#!/usr/bin/env bash
# Install Ax3l services after install.sh has provisioned the account/DB.
set -euo pipefail

# install.sh uses 077 for database credentials; service files must be readable.
umask 022

if [[ $# != 0 ]]; then
    printf 'Usage: sudo scripts/install-services.sh\n' >&2
    exit 2
fi
[[ $EUID == 0 ]] || { printf 'Run service installation as root.\n' >&2; exit 1; }
checkout_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
service_account=ax3l
install_dir=/opt/prod/ax3l
config_dir=/etc/ax3l

. "$checkout_dir/scripts/service-configuration.sh"
. "$checkout_dir/scripts/application-files.sh"
printf '\n[1/8] Validating installation configuration...\n'
resolve_service_configuration

if [[ ! -x $install_dir/.venv/bin/python ]]; then
    python3 "$checkout_dir/scripts/install-progress.py" --label '[2/8] Creating Python virtual environment' \
        -- python3 -m venv "$install_dir/.venv"
else
    printf '\n[2/8] Reusing existing Python virtual environment.\n'
fi
python3 "$checkout_dir/scripts/install-progress.py" --label '[3/8] Installing Python dependencies' \
    -- "$install_dir/.venv/bin/python" -m pip install --progress-bar on -r "$checkout_dir/requirements.txt"
printf '\n[4/8] Preparing runtime directories and permissions...\n'
# Allow service-account access to the prepared runtime.
chgrp -R "$service_account" "$install_dir/.venv"
chmod -R g+rX "$install_dir/.venv"
install -d -m 755 "$install_dir/games"
printf '\n[5/8] Rendering and validating service definitions...\n'
render_service_units
printf '\n[6/8] Stopping Ax3l services and installing application files...\n'
"$checkout_dir/scripts/services.sh" stop

install_application_files "$checkout_dir" "$install_dir" "$service_account"

# install.sh creates this directory under umask 077. Allow service-account
# traversal; database credentials retain mode 600.
chgrp "$service_account" "$config_dir"
chmod 750 "$config_dir"

printf '\n[7/8] Installing and enabling service definitions...\n'
install_service_units
printf '\n[8/8] Starting Ax3l services...\n'
"$checkout_dir/scripts/services.sh" start
printf 'Installed: %s\n' "${units[*]}"

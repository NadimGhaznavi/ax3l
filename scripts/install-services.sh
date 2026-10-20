#!/usr/bin/env bash
# Install the model and application services after install.sh has provisioned the account/DB.
set -euo pipefail

# install.sh uses 077 for database credentials; service files must be readable.
umask 022

if [[ $# != 0 && $# != 2 ]]; then
    printf 'Usage: sudo scripts/install-services.sh [-model qwen|phi|qwenv]\n' >&2
    exit 2
fi
selected_model=qwen
if [[ $# == 2 ]]; then
    [[ $1 == -model && ( $2 == qwen || $2 == phi || $2 == qwenv ) ]] || { printf 'Expected -model qwen|phi|qwenv.\n' >&2; exit 2; }
    selected_model=$2
fi
[[ $EUID == 0 ]] || { printf 'Run service installation as root.\n' >&2; exit 1; }
checkout_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
service_account=ax3l
install_dir=/opt/prod/ax3l
config_dir=/etc/ax3l

. "$checkout_dir/scripts/service-configuration.sh"
resolve_service_configuration

if [[ ! -x $install_dir/.venv/bin/python ]]; then
    python3 -m venv "$install_dir/.venv"
fi
"$install_dir/.venv/bin/python" -m pip install -r "$checkout_dir/requirements.txt"
"$install_dir/.venv/bin/python" "$checkout_dir/scripts/install-chrome.py" --app "$install_dir"
# Repair environments created under install.sh's former inherited umask 077.
# Ax3l launches its private MCP sessions as the service account.
chgrp -R "$service_account" "$install_dir/.venv"
chmod -R g+rX "$install_dir/.venv"
install -d -m 755 "$install_dir/games"
render_service_units
"$checkout_dir/scripts/services.sh" stop

legacy_unit="llm-server.service"
if [[ -f /etc/systemd/system/$legacy_unit ]]; then
    systemctl disable --now "$legacy_unit"
    rm -- "/etc/systemd/system/$legacy_unit"
fi

cd -- "$checkout_dir"
while IFS= read -r -d '' source; do
    install -D -m 644 -o "$service_account" -g "$service_account" \
        -- "$source" "$install_dir/$source"
done < <(find ax3l -type f \( -name '*.py' -o -name '*.schema.json' -o -name '*.jinja' -o -path 'ax3l/server/templates/*.html' -o -path 'ax3l/activity/fonts/*' \) -print0)

# install.sh creates this directory under umask 077. Allow service-account
# traversal; database credentials retain mode 600.
chgrp "$service_account" "$config_dir"
chmod 750 "$config_dir"

install_service_units
"$checkout_dir/scripts/services.sh" start -model "$selected_model"
printf 'Installed: %s\n' "${units[*]}"

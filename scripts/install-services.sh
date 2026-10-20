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

ports=$(cd -- "$checkout_dir" && python3 - <<'PY'
from ax3l.constants.DAx3l import DAx3l
from ax3l.constants.DLlama import DLlama
from ax3l.constants.DReportMgr import DReportMgr

print(DLlama.PORT, DReportMgr.PORT)
print(DAx3l.ZMQ_ENDPOINT)
PY
)
read -r llm_port report_port <<< "$ports"
ax3l_zmq_endpoint=${ports##*$'\n'}
ax3l_args="--llm-url http://127.0.0.1:$llm_port --output /var/lib/ax3l/snakelab"
llm_paths=$(cd -- "$checkout_dir" && python3 - <<'PY'
from pathlib import Path
from ax3l.constants.DLlama import DLlama
from ax3l.constants.DQwen import DQwen
from ax3l.constants.DPhi import DPhi
from ax3l.constants.DQwenV import DQwenV

print(Path(DLlama.BASE_DIR) / DLlama.BIN_DIR / DLlama.SERVER)
print(Path(DLlama.MODEL_DIR) / DQwen.GGUF)
print(DLlama.HOST)
print(Path(DLlama.MODEL_DIR) / DPhi.GGUF)
print(Path(DLlama.MODEL_DIR) / DQwenV.GGUF)
print(Path(DLlama.MODEL_DIR) / DQwenV.MMPROJ)
print(DQwenV.CONTEXT_SIZE)
print(DQwen.CONTEXT_SIZE)
print(Path(DLlama.MODEL_DIR) / DQwen.MMPROJ)
PY
)
mapfile -t paths <<< "$llm_paths"
llm_binary=${paths[0]}
qwen_model=${paths[1]}
phi_model=${paths[3]}
qwenv_model=${paths[4]}
qwenv_mmproj=${paths[5]}
qwenv_context=${paths[6]}
qwen_context=${paths[7]}
qwen_mmproj=${paths[8]}
model=$qwen_model
mmproj=$qwen_mmproj
if [[ $selected_model == phi ]]; then model=$phi_model; fi
if [[ $selected_model == qwenv ]]; then
    model=$qwenv_model
    mmproj=$qwenv_mmproj
fi
if [[ $selected_model == qwen || $selected_model == qwenv ]]; then
    [[ -r $mmproj ]] || {
        printf 'Install the vision projector at %s first.\n' "$mmproj" >&2
        exit 1
    }
fi
llm_host=${paths[2]}
[[ -x $llm_binary && -r $model ]] || {
    printf 'Install llama.cpp at %s and the model at %s first.\n' "$llm_binary" "$model" >&2
    exit 1
}
qwen_command="$llm_binary --model $qwen_model --mmproj $qwen_mmproj -c $qwen_context --host $llm_host --port $llm_port --metrics --jinja"
phi_command="$llm_binary --model $phi_model --host $llm_host --port $llm_port --metrics --jinja"
qwenv_command="$llm_binary --model $qwenv_model --mmproj $qwenv_mmproj -c $qwenv_context --host $llm_host --port $llm_port --metrics --jinja"

[[ -d $install_dir && -f $config_dir/database.env ]] || {
    printf 'Run install.sh first.\n' >&2
    exit 1
}

unit_dir=$(mktemp -d)
trap 'rm -rf -- "$unit_dir"' EXIT
units=()
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
for name in qwen-server phi-server qwenv-server ax3l-server reporting-server watchdog; do
    unit="$name.service"
    units+=("$unit")
    sed -e "s|@USER@|$service_account|g" \
        -e "s|@APP@|$install_dir|g" -e "s|@CONFIG@|$config_dir|g" \
        -e "s|@QWEN_COMMAND@|$qwen_command|g" -e "s|@PHI_COMMAND@|$phi_command|g" \
        -e "s|@QWENV_COMMAND@|$qwenv_command|g" -e "s|@MODEL@|$selected_model|g" \
        -e "s|@LLM_PORT@|$llm_port|g" \
        -e "s|@REPORT_PORT@|$report_port|g" \
        -e "s|@AX3L_ZMQ_ENDPOINT@|$ax3l_zmq_endpoint|g" \
        -e "s|@AX3L_ARGS@|$ax3l_args|g" \
        "$checkout_dir/systemd/$name.service" > "$unit_dir/$unit"
done

systemd-analyze verify "$unit_dir/"*.service
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

for unit in "${units[@]}"; do
    install -m 644 -- "$unit_dir/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable "reporting-server.service" "ax3l-server.service" "watchdog.service"
"$checkout_dir/scripts/services.sh" start -model "$selected_model"
printf 'Installed: %s\n' "${units[*]}"

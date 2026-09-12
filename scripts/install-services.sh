#!/usr/bin/env bash
# Install the model and application services after install.sh has provisioned the account/DB.
set -euo pipefail

if [[ ( $# != 2 && $# != 4 ) || $1 != -env ]]; then
    printf 'Usage: scripts/install-services.sh -env dev|qa|prod [-model qwen|phi|qwenv]\n' >&2
    exit 2
fi
selected_model=qwenv
if [[ $# == 4 ]]; then
    [[ $3 == -model && ( $4 == qwen || $4 == phi || $4 == qwenv ) ]] || { printf 'Expected -model qwen|phi|qwenv.\n' >&2; exit 2; }
    selected_model=$4
fi
checkout_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
install_env=$2
case "$install_env" in
    dev)
        [[ $EUID != 0 ]] || { printf 'Run dev as the development user.\n' >&2; exit 1; }
        system_admin=(sudo)
        service_account=ax3l_dev
        install_dir="$checkout_dir/ax3l_prod"
        config_dir="$checkout_dir/prod_etc/ax3l"
        suffix=-dev
        ;;
    qa|prod)
        [[ $EUID == 0 ]] || { printf 'QA/prod require root.\n' >&2; exit 1; }
        system_admin=()
        service_account=ax3l
        install_dir="/opt/$install_env/ax3l"
        config_dir=/etc/ax3l
        if [[ $install_env == qa ]]; then
            suffix=-qa
        else
            suffix=
        fi
        ;;
    *) printf 'Invalid environment: %s\n' "$install_env" >&2; exit 2 ;;
esac

ports=$(cd -- "$checkout_dir" && python3 - "$install_env" <<'PY'
import sys
from ax3l.constants.DAx3l import DAx3l
from ax3l.constants.DLlama import DLlama
from ax3l.constants.DReportMgr import DReportMgr

attribute = {"dev": "PORT_DEV", "qa": "PORT_QA", "prod": "PORT"}[sys.argv[1]]
print(*(getattr(constants, attribute) for constants in (DLlama, DAx3l, DReportMgr)))
print(getattr(DAx3l, {"dev": "ZMQ_ENDPOINT_DEV", "qa": "ZMQ_ENDPOINT_QA", "prod": "ZMQ_ENDPOINT"}[sys.argv[1]]))
PY
)
read -r llm_port ax3l_port report_port <<< "$ports"
ax3l_zmq_endpoint=${ports##*$'\n'}
ax3l_args=
if [[ $install_env == prod ]]; then
    ax3l_args="--llm-url http://127.0.0.1:$llm_port --output /var/lib/ax3l/haiku"
fi
if [[ $install_env == dev || $install_env == qa ]]; then
    qwen_command="/usr/bin/python3 -m ax3l.server.LLMHealthStub --port $llm_port"
    phi_command=$qwen_command
    qwenv_command=$qwen_command
else
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
PY
)
    mapfile -t paths <<< "$llm_paths"
    llm_binary=${paths[0]}
    qwen_model=${paths[1]}
    phi_model=${paths[3]}
    qwenv_model=${paths[4]}
    qwenv_mmproj=${paths[5]}
    qwenv_context=${paths[6]}
    model=$qwen_model
    if [[ $selected_model == phi ]]; then model=$phi_model; fi
    if [[ $selected_model == qwenv ]]; then
        model=$qwenv_model
        [[ -r $qwenv_mmproj ]] || {
            printf 'Install the vision projector at %s first.\n' "$qwenv_mmproj" >&2
            exit 1
        }
    fi
    llm_host=${paths[2]}
    [[ -x $llm_binary && -r $model ]] || {
        printf 'Install llama.cpp at %s and the model at %s first.\n' "$llm_binary" "$model" >&2
        exit 1
    }
    qwen_command="$llm_binary --model $qwen_model --host $llm_host --port $llm_port --metrics --mcp-servers-config $config_dir/mcp.json"
    phi_command="$llm_binary --model $phi_model --host $llm_host --port $llm_port --metrics --mcp-servers-config $config_dir/mcp.json"
    qwenv_command="$llm_binary --model $qwenv_model --mmproj $qwenv_mmproj -c $qwenv_context --host $llm_host --port $llm_port --metrics --mcp-servers-config $config_dir/mcp.json"
fi

[[ -d $install_dir && -f $config_dir/database.env ]] || {
    printf 'Run install.sh for this environment first.\n' >&2
    exit 1
}

unit_dir=$(mktemp -d)
trap 'rm -rf -- "$unit_dir"' EXIT
units=()
python3 "$checkout_dir/scripts/generate-mcp-config.py" --app "$install_dir" --zmq-endpoint "$ax3l_zmq_endpoint" > "$unit_dir/mcp.json"
if [[ ! -x $install_dir/.venv/bin/python ]]; then
    "${system_admin[@]}" python3 -m venv "$install_dir/.venv"
fi
"${system_admin[@]}" "$install_dir/.venv/bin/python" -m pip install -r "$checkout_dir/requirements.txt"
for name in qwen-server phi-server qwenv-server ax3l-server reporting-server watchdog; do
    unit="$name$suffix.service"
    units+=("$unit")
    sed -e "s|@ENV@|$install_env|g" -e "s|@USER@|$service_account|g" \
        -e "s|@APP@|$install_dir|g" -e "s|@CONFIG@|$config_dir|g" \
        -e "s|@SUFFIX@|$suffix|g" -e "s|@QWEN_COMMAND@|$qwen_command|g" -e "s|@PHI_COMMAND@|$phi_command|g" \
        -e "s|@QWENV_COMMAND@|$qwenv_command|g" \
        -e "s|@LLM_PORT@|$llm_port|g" -e "s|@AX3L_PORT@|$ax3l_port|g" \
        -e "s|@REPORT_PORT@|$report_port|g" \
        -e "s|@AX3L_ZMQ_ENDPOINT@|$ax3l_zmq_endpoint|g" \
        -e "s|@AX3L_ARGS@|$ax3l_args|g" \
        "$checkout_dir/systemd/$name.service" > "$unit_dir/$unit"
done

systemd-analyze verify "$unit_dir/"*.service
"$checkout_dir/scripts/services.sh" -env "$install_env" stop

legacy_unit="llm-server$suffix.service"
if [[ -f /etc/systemd/system/$legacy_unit ]]; then
    "${system_admin[@]}" systemctl disable --now "$legacy_unit"
    "${system_admin[@]}" rm -- "/etc/systemd/system/$legacy_unit"
fi

cd -- "$checkout_dir"
while IFS= read -r -d '' source; do
    "${system_admin[@]}" install -D -m 644 -o "$service_account" -g "$service_account" \
        -- "$source" "$install_dir/$source"
done < <(find ax3l -type f \( -name '*.py' -o -name '*.schema.json' -o -path 'ax3l/server/templates/*.html' \) -print0)

"${system_admin[@]}" install -m 644 -o "$service_account" -g "$service_account" \
    -- "$unit_dir/mcp.json" "$config_dir/mcp.json"

for unit in "${units[@]}"; do
    "${system_admin[@]}" install -m 644 -- "$unit_dir/$unit" "/etc/systemd/system/$unit"
done
"${system_admin[@]}" systemctl daemon-reload
"${system_admin[@]}" systemctl enable "reporting-server$suffix.service" "ax3l-server$suffix.service" "watchdog$suffix.service"
"$checkout_dir/scripts/services.sh" -env "$install_env" start -model "$selected_model"
printf 'Installed: %s\n' "${units[*]}"

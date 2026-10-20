#!/usr/bin/env bash
# Shared service configuration for installation and network restarts.
# Caller supplies checkout_dir, install_dir, config_dir, service_account, and selected_model.

resolve_service_configuration() {
    [[ -d $install_dir && -f $config_dir/database.env ]] || {
        printf 'Run install.sh first.\n' >&2
        exit 1
    }
    network=$(cd -- "$checkout_dir" && python3 -B - <<'PY'
from ax3l.interface.Configuration import Configuration
from ax3l.interface.Network import Network

Configuration.install()
print(*Network.binding('llm'), *Network.binding('report'), Network.endpoint())
print('http://{}:{}'.format(*Network.destination('llm')))
PY
    )
    read -r llm_host llm_port report_host report_port ax3l_zmq_endpoint <<< "$network"
    llm_url=${network##*$'\n'}
    ax3l_args="--llm-url $llm_url --output /var/lib/ax3l/snakelab"
    llm_paths=$(cd -- "$checkout_dir" && python3 - <<'PY'
from pathlib import Path
from ax3l.constants.DLlama import DLlama
from ax3l.constants.DQwen import DQwen
from ax3l.constants.DPhi import DPhi
from ax3l.constants.DQwen25 import DQwen25

print(Path(DLlama.BASE_DIR) / DLlama.BIN_DIR / DLlama.SERVER)
print(Path(DLlama.MODEL_DIR) / DQwen.GGUF)
print(Path(DLlama.MODEL_DIR) / DPhi.GGUF)
print(Path(DLlama.MODEL_DIR) / DQwen25.GGUF)
print(Path(DLlama.MODEL_DIR) / DQwen25.MMPROJ)
print(DQwen25.CONTEXT_SIZE)
print(DQwen.CONTEXT_SIZE)
print(Path(DLlama.MODEL_DIR) / DQwen.MMPROJ)
PY
    )
    mapfile -t paths <<< "$llm_paths"
    llm_binary=${paths[0]}
    qwen_model=${paths[1]}
    phi_model=${paths[2]}
    qwen25_model=${paths[3]}
    qwen25_mmproj=${paths[4]}
    qwen25_context=${paths[5]}
    qwen_context=${paths[6]}
    qwen_mmproj=${paths[7]}
    model=$qwen_model
    mmproj=$qwen_mmproj
    if [[ $selected_model == phi ]]; then model=$phi_model; fi
    if [[ $selected_model == qwen2.5 ]]; then
        model=$qwen25_model
        mmproj=$qwen25_mmproj
    fi
    if [[ $selected_model == qwen || $selected_model == qwen2.5 ]]; then
        [[ -r $mmproj ]] || {
            printf 'Install the vision projector at %s first.\n' "$mmproj" >&2
            exit 1
        }
    fi
    [[ -x $llm_binary && -r $model ]] || {
        printf 'Install llama.cpp at %s and the model at %s first.\n' "$llm_binary" "$model" >&2
        exit 1
    }
    qwen_command="$llm_binary --model $qwen_model --mmproj $qwen_mmproj -c $qwen_context --host $llm_host --port $llm_port --metrics --jinja"
    phi_command="$llm_binary --model $phi_model --host $llm_host --port $llm_port --metrics --jinja"
    qwen25_command="$llm_binary --model $qwen25_model --mmproj $qwen25_mmproj -c $qwen25_context --host $llm_host --port $llm_port --metrics --jinja"
}

render_service_units() {
    unit_dir=$(mktemp -d)
    trap 'rm -rf -- "$unit_dir"' EXIT
    units=()
    for name in qwen-server phi-server qwen2.5-server ax3l-server reporting-server watchdog; do
        unit="$name.service"
        units+=("$unit")
        sed -e "s|@USER@|$service_account|g" \
            -e "s|@APP@|$install_dir|g" -e "s|@CONFIG@|$config_dir|g" \
            -e "s|@QWEN_COMMAND@|$qwen_command|g" -e "s|@PHI_COMMAND@|$phi_command|g" \
            -e "s|@QWEN25_COMMAND@|$qwen25_command|g" -e "s|@MODEL@|$selected_model|g" \
            -e "s|@REPORT_PORT@|$report_port|g" -e "s|@REPORT_HOST@|$report_host|g" \
            -e "s|@LLM_URL@|$llm_url|g" \
            -e "s|@AX3L_ZMQ_ENDPOINT@|$ax3l_zmq_endpoint|g" \
            -e "s|@AX3L_ARGS@|$ax3l_args|g" \
            "$checkout_dir/systemd/$name.service" > "$unit_dir/$unit"
    done

    systemd-analyze verify "$unit_dir/"*.service
}

install_service_units() {
    # Remove the former Qwen2.5 unit so it cannot start alongside the renamed service.
    if [[ -f /etc/systemd/system/qwenv-server.service ]]; then
        systemctl disable --now qwenv-server.service
        rm -- /etc/systemd/system/qwenv-server.service
    fi
    for unit in "${units[@]}"; do
        install -m 644 -- "$unit_dir/$unit" "/etc/systemd/system/$unit"
    done
    systemctl daemon-reload
    systemctl enable "reporting-server.service" "ax3l-server.service" "watchdog.service"
}

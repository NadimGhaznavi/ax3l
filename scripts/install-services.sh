#!/usr/bin/env bash
# Install the four service skeletons after install.sh has provisioned the account/DB.
set -euo pipefail

if [[ $# != 2 || $1 != -env ]]; then
    printf 'Usage: scripts/install-services.sh -env dev|qa|prod\n' >&2
    exit 2
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
        llm_binary="/opt/$install_env/llama.cpp/bin/llama-server"
        model="/opt/$install_env/models/Qwen3.5-4B-Q4_K_M.gguf"
        [[ -x $llm_binary && -r $model ]] || {
            printf 'Install llama.cpp at %s and the model at %s first.\n' "$llm_binary" "$model" >&2
            exit 1
        }
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
PY
)
read -r llm_port ax3l_port report_port <<< "$ports"
if [[ $install_env == dev ]]; then
    llm_command="/usr/bin/python3 -m ax3l.server.LLMHealthStub --port $llm_port"
else
    llm_command="$llm_binary --model $model --host 127.0.0.1 --port $llm_port"
fi

[[ -d $install_dir && -f $config_dir/database.env ]] || {
    printf 'Run install.sh for this environment first.\n' >&2
    exit 1
}

unit_dir=$(mktemp -d)
trap 'rm -rf -- "$unit_dir"' EXIT
units=()
for name in llm-server ax3l-server reporting-server watchdog; do
    unit="$name$suffix.service"
    units+=("$unit")
    sed -e "s|@ENV@|$install_env|g" -e "s|@USER@|$service_account|g" \
        -e "s|@APP@|$install_dir|g" -e "s|@CONFIG@|$config_dir|g" \
        -e "s|@SUFFIX@|$suffix|g" -e "s|@LLM_COMMAND@|$llm_command|g" \
        -e "s|@LLM_PORT@|$llm_port|g" -e "s|@AX3L_PORT@|$ax3l_port|g" \
        -e "s|@REPORT_PORT@|$report_port|g" \
        "$checkout_dir/systemd/$name.service" > "$unit_dir/$unit"
done

cd -- "$checkout_dir"
while IFS= read -r -d '' source; do
    "${system_admin[@]}" install -D -m 644 -o "$service_account" -g "$service_account" \
        -- "$source" "$install_dir/$source"
done < <(find ax3l -type f -name '*.py' -print0)

systemd-analyze verify "$unit_dir/"*.service
for unit in "${units[@]}"; do
    "${system_admin[@]}" install -m 644 -- "$unit_dir/$unit" "/etc/systemd/system/$unit"
done
"${system_admin[@]}" systemctl daemon-reload
"${system_admin[@]}" systemctl enable "${units[@]}"
"$checkout_dir/scripts/services.sh" -env "$install_env" stop
"$checkout_dir/scripts/services.sh" -env "$install_env" start
printf 'Installed and started: %s\n' "${units[*]}"

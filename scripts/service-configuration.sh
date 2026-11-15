#!/usr/bin/env bash
# Shared service configuration for installation and network restarts.
# Caller supplies checkout_dir, install_dir, and config_dir.

resolve_service_configuration() {
    [[ -d $install_dir && -f $config_dir/database.env ]] || {
        printf 'Run install.sh first.\n' >&2
        exit 1
    }
    network=$(cd -- "$checkout_dir" && python3 -B - <<'PY'
from ax3l.interface.Configuration import Configuration
from ax3l.interface.Network import Network

Configuration.install()
print(*Network.binding('report'), Network.endpoint())
PY
    )
    read -r report_host report_port ax3l_zmq_endpoint <<< "$network"
}

render_service_units() {
    unit_dir=$(mktemp -d)
    trap 'rm -rf -- "$unit_dir"' EXIT
    units=()
    for name in ax3l-server reporting-server watchdog; do
        unit="$name.service"
        units+=("$unit")
        sed -e "s|@APP@|$install_dir|g" -e "s|@CONFIG@|$config_dir|g" \
            -e "s|@REPORT_PORT@|$report_port|g" -e "s|@REPORT_HOST@|$report_host|g" \
            -e "s|@AX3L_ZMQ_ENDPOINT@|$ax3l_zmq_endpoint|g" \
            "$checkout_dir/systemd/$name.service" > "$unit_dir/$unit"
    done

    systemd-analyze verify "$unit_dir/"*.service
}

install_service_units() {
    for unit in "${units[@]}"; do
        install -m 644 -- "$unit_dir/$unit" "/etc/systemd/system/$unit"
    done
    systemctl daemon-reload
    systemctl enable "reporting-server.service" "ax3l-server.service" "watchdog.service"
}

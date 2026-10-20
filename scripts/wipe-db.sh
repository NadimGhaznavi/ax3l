#!/usr/bin/env bash
# Reset both sides of the experiment without removing schemas or accounts.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: sudo scripts/wipe-db.sh

Permanently deletes all Ax3l events and SnakeLab simulations on this machine.
Includes event details/checkpoints, simulation episodes, and configurations.
Targets ax3l and snakelab.
Stops the Ax3l, reporting, and watchdog services and snake-lab.service.
Leaves them stopped. The model service is left running.
Preserves table definitions, credentials, users, grants, and installations.
Resets auto-increment counters so the next event and simulation IDs start at 1.
Uses local MariaDB root socket authentication.
HELP
}

if [[ $# == 1 && ( $1 == -h || $1 == --help ) ]]; then
    usage
    exit 0
fi
if [[ $# != 0 ]]; then
    usage >&2
    exit 2
fi
database=ax3l
[[ $(id -u) == 0 ]] || { printf 'Run as root using sudo.\n' >&2; exit 1; }
admin=(mariadb --no-defaults --protocol=socket --user=root --batch)
# Check database access before stopping services. Do not print stored data.
"${admin[@]}" --execute="SELECT 1 FROM \`$database\`.events LIMIT 0; SELECT 1 FROM snakelab.simulation_runs LIMIT 0;"

for unit in "watchdog.service" "ax3l-server.service" "reporting-server.service" snake-lab.service; do
    if [[ $(systemctl show -p LoadState --value "$unit") != not-found ]]; then
        systemctl stop "$unit"
    fi
done

# All tables are InnoDB. ON DELETE CASCADE clears event_messages,
# event_list_items, event_key_values, and experiment_highscores from events,
# plus simulation_episodes
# (SnakeLab v1) and configurations (v3) from simulation_runs. The v2 index
# change needs no extra cleanup. Round-robin checkpoints are events too.
# Clear event parent links first so self references cannot block deletion.
"${admin[@]}" <<SQL
START TRANSACTION;
UPDATE \`$database\`.events SET parent_event_id = NULL WHERE parent_event_id IS NOT NULL;
DELETE FROM \`$database\`.events;
DELETE FROM snakelab.simulation_runs;
COMMIT;
SQL
# ALTER TABLE implicitly commits, so reset counters only after the deletion
# transaction succeeds. These are the only auto-increment columns in the schemas.
"${admin[@]}" --execute="ALTER TABLE \`$database\`.events AUTO_INCREMENT = 1; ALTER TABLE snakelab.simulation_runs AUTO_INCREMENT = 1;"
printf 'Cleared %s events and snakelab simulations; reset auto-increment counters. Services remain stopped.\n' "$database"
printf 'Restart SnakeLab first: sudo systemctl start snake-lab.service\n'
printf 'Then restart Ax3l: sudo systemctl start reporting-server.service ax3l-server.service watchdog.service\n'

# Haiku experiment

`SnakeLab().get_num_sims()` returns the number of rows in Snake Lab's
`simulation_runs` table, across all statuses and including repeated configurations.
Set `SNAKELAB_DB_HOST`, `SNAKELAB_DB_USER`, `SNAKELAB_DB_PASSWORD`, and
`SNAKELAB_DB_NAME` in the calling process's environment. `SNAKELAB_DB_PORT`
defaults to 3306. These credentials are separate from AX3L's `DB_*` settings;
the account only needs SELECT access to `simulation_runs`. Each call opens and
closes its connection without initializing tables. Database errors propagate.

At startup, `main-loop.py` checks that count. When it is zero,
`GenerateDefaultConfig` builds a complete configuration from the adjacent JSON
spec's defaults and validates it against that spec. AX3L submits it once and
logs `simulation_submitted` with the returned run ID as `process_id`. The log's
“config” link opens `/simulations/<run_id>/config`, which reads the configuration
from Snake Lab through the DAL on each request. AX3L stores no configuration copy.
The reporting process also needs the `SNAKELAB_DB_*` environment variables.

The loop polls `simulation.status` for that run every five seconds, controlled by
`DSnakeLab.STATUS_POLL_SECONDS`, and logs `simulation_started` when it observes
`running`. It continues sleeping and polling until the run is completed, failed,
or cancelled, then logs that outcome and closes the simulation cycle. The start
entry is logged only once, including across pause/resume transitions. If a
terminal state arrives before running is observed, it logs that outcome instead.
After the cycle closes, the existing haiku loop continues. Submission and status errors stop
startup; submissions are never retried automatically.

Raw file capture is off by default. Set `DAx3l.RAW_LOGS_ENABLED = True` in
`ax3l/constants/DAx3l.py` to enable the capture files described below.
When off, no haiku output directory or files are created, including under
`/var/lib/ax3l/haiku`. Database logging continues; status and errors go to the
console (the systemd journal for service runs). Existing captures are retained.

From the checkout root, load the installed database credentials into the
environment, then point the loop at the running model server. For DEV:

```sh
set -a
. prod_etc/ax3l/database.env
set +a
python3 -m ax3l.app.snakelab.main-loop --url http://HOST:27770
```

On production, source `/etc/ax3l/database.env` instead. The Python environment
must have the project's PyMySQL dependency installed.

The loop records conversation start/end, prompts, full reply JSON, waits, and
LLM failures through `DbMgr.log()`. Events share a process ID printed in
`run.log`, and replies link to their prompt events. Reply metrics remain in
the captured JSON for now. Database errors stop the loop.

Each turn picks a random integer from 0 through 30 and sends
`Write a haiku based on the number X.`, saves the response, sleeps for
`DSnakeLab.HAIKU_SLEEP_SECONDS` (default: 5 seconds),
and repeats until Ctrl-C. Each request has fresh context. It uses whichever
model is already running on that server. Dev/QA health stubs cannot generate text.

The printed directory under `tmp/haiku/` contains `run.log` (stdout, stderr,
and tracebacks), plus each request JSON, HTTP response headers/status, and exact
response body bytes. Responses are not parsed or filtered. HTTP and transport
errors stop the loop and are recorded in the log.

Set `DSnakeLab.HAIKU_COUNT` in `ax3l/constants/DSnakeLab.py` to control the number
of requests for manual and service runs. The default is `0` (repeat until stopped).
Use `--count 2` to override it for a short manual run, or `--output /tmp/haiku`
to change the output root. With a positive count, the Ax3l service exits after
the configured number of requests.
Production `ax3l-server` starts this loop automatically alongside its health
endpoint. Service captures are in `/var/lib/ax3l/haiku`; database credentials
come from the unit's environment file. Stop a manual loop before deploying
to avoid running both. `systemctl stop ax3l-server` stops the service loop.
DEV/QA services retain health-only startup because their LLMs are stubs.

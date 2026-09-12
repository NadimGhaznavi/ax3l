# Haiku experiment

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

The loop sends `Write a haiku.`, saves the response, sleeps for
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

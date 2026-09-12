# First learning-rate iteration

## MCP tools

The SnakeLab MCP entry point is `python -m ax3l.app.snakelab.tools` and uses
stdio. Register domain tool functions in `tools/server.py` with `@mcp.tool()`.
It exposes `submit_single_value(parameter, value)` through `SubmitSingleValue`.
The parameter is its exact JSON spec key (for example `learning_rate`); the value
is a JSON integer or number. MCP rejects strings and booleans as numeric values.
Parameter existence, permitted ranges, duplicates, and submission decisions
belong to Ax3l, not the MCP tool.

`scripts/install-services.sh` generates the installation's `mcp.json` and adds
`--mcp-servers-config` to all three production model commands. It installs the
project requirements in `<app>/.venv`, used by both Ax3l and the MCP child process.
Installation needs Python's venv/pip support and package-index access for this step.
DEV/QA retain their existing health-only LLM stubs.

For a checkout, generate the same configuration with:

```sh
python3 scripts/generate-mcp-config.py --app /opt/dev/ax3l > tmp/mcp.json
```

Pass that file to a llama-server build supporting `--mcp-servers-config`.
llama-server discovers the tool names through MCP. The tool forwards requests
over ZeroMQ using the project-wide `ax3l/zmq/ZMQMsg.py` and `ZMQClient.py`:

```json
{
  "protocol_version": 1,
  "sender": "mcp-snakelab",
  "target": "snakelab",
  "method": "submit_single_value",
  "payload": {"parameter": "learning_rate", "value": 0.003}
}
```

The default endpoint is `DAx3l.ZMQ_ENDPOINT` (`tcp://127.0.0.1:61970`), separate
from Ax3l's HTTP health port. Override it with `AX3L_ZMQ_ENDPOINT` in the MCP
process environment, including through the `env` entry in `mcp.json`.
Ax3l replies with the same envelope shape and an application result in `payload`;
the tool returns that payload as JSON text without changing acceptance or rejection.
`DZMQ.TIMEOUT_SECONDS` bounds send and receive waits. Transport failures propagate
as tool errors; calls are never retried automatically because a timed-out request
may already have been processed. No database or Snake Lab submission occurs in
the tool.

Ax3l starts `ZMQServer` alongside its HTTP health server and keeps it available
while the LLM request runs. Domain dispatch lives in `server/ToolHandler.py`;
SnakeLab validation and submission live in `SubmitSingleValueHandler.py`.
The installer assigns endpoint ports 61968 (DEV), 61969 (QA), and 61970 (PROD)
to both the listener and the generated MCP config. `--zmq-endpoint` overrides
the listener endpoint for manual runs.

The handler verifies the exact payload fields, finite numeric values, parameter
name, and JSON-schema constraints before building a candidate from the golden
configuration. It changes only the selected parameter. A legal but unchanged
configuration is rejected; `SnakeLab.is_config_unique(config)` then checks all
stored runs through `SnakeLabDb`, regardless of status or project version.
Equality compares the full JSON configuration, including seed, while ignoring
object key order and equivalent numeric representations. This uses MariaDB's
`JSON_EQUALS` (MariaDB 10.7 or newer).

Illegal values return `status: rejected`, `code: invalid_value`, and an
`InvalidValue` prompt. Duplicates return `code: duplicate_config` and a
`NoDupesSingle` prompt. These prompt messages travel back in the MCP result;
the handler does not start a separate LLM conversation. Accepted candidates
return `status: ok` and their submitted `run_id`, with proposal and submission
events logged. Golden selection is unchanged. The listener handles requests
serially; external writers to SnakeLab are outside that serialization boundary.

## Conversation snippets

LLM conversation snippets can include the golden configuration and its loss plot:

```python
import json

from ax3l.app.snakelab.prompts.GoldenConfig import GoldenConfig
from ax3l.app.snakelab.prompts.LossPlot import LossPlot

golden = GoldenConfig(db)
loss_plot = LossPlot(golden.run_id)
messages = [json.loads(golden.to_json()), json.loads(loss_plot.to_json())]
```

`LossPlot.refresh()` reads that same run's `simulation_episodes` rows through the
DAL and regenerates an in-memory PNG. The x-axis uses stored episode numbers;
null losses remain gaps. A run without recorded losses raises `ValueError`.
`to_json()` embeds a caption and base64 PNG image content for the vision model.
Resolve the golden configuration once per conversation; recreate the loss prompt
from its run ID after changing the golden selection. PNG generation requires
Plotly, Kaleido, and Chrome; the local packages are installed in `.venv`.
The existing haiku loop does not yet assemble these snippets.

`SnakeLab().get_num_sims()` returns the number of rows in Snake Lab's
`simulation_runs` table, across all statuses and including repeated configurations.
Reads use Ax3l's existing `DB_*` credentials and select the `snakelab` database.
Installation grants the Ax3l database user `SELECT` on `snakelab`.*. No separate
SnakeLab credentials are needed. Each call opens and closes its connection without
initializing tables. Simulation submissions still go through SnakeLab's ZMQ API.

At startup, `main-loop.py` checks the simulation count. If it is zero, it
submits the JSON spec's default configuration once and records the submission
and golden creation. It polls the submitted run through its terminal status,
then waits until Snake Lab reports idle. With an existing database it skips
seeding and waits for idle directly.

It resolves the current golden configuration once and sends one LLM request
with four messages, in order: `FirstContact`, `GoldenConfig`, `LossPlot` for that
same run, and `FirstContactSingle("learning_rate")`. Each serialized message,
including the loss PNG, is stored in a `prompt_sent` entry linked to the
conversation. The request uses those exact snapshots. Construction and refresh
do not create prompt events. The reply is logged and the iteration ends.
No follow-up parameter selection or simulation is performed yet.

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
.venv/bin/python -m ax3l.app.snakelab.main-loop --url http://HOST:27770
```

On production, source `/etc/ax3l/database.env` instead. The Python environment
must have the project's PyMySQL dependency installed.

The loop records conversation start/end, prompt snapshots, full reply JSON, and
LLM failures through `DbMgr.log()`. Events share a process ID printed in
`run.log`, and replies link to their prompt events. Reply metrics remain in
the captured JSON for now. Database errors stop the loop.

The active flow performs one request and exits after recording the reply.
Use `--output PATH` to choose the optional capture directory. PNG rendering
requires the project's `.venv` dependencies and Chrome. Service installations
run Ax3l from the installed `.venv`; Chrome must be installed for PNG rendering.

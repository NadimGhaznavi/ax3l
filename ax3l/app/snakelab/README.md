# First learning-rate iteration

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
Set `SNAKELAB_DB_HOST`, `SNAKELAB_DB_USER`, `SNAKELAB_DB_PASSWORD`, and
`SNAKELAB_DB_NAME` in the calling process's environment. `SNAKELAB_DB_PORT`
defaults to 3306. These credentials are separate from AX3L's `DB_*` settings;
the account needs SELECT access to `simulation_runs` and `simulation_episodes`. Each call opens and
closes its connection without initializing tables. Database errors propagate.

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
still use system Python and require those dependencies before running this flow.

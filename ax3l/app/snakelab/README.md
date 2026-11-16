# Complete-configuration optimization

Ax3l starts a draft from the current golden configuration and asks Qwen which
setting to change. Qwen can choose any of seven single settings—hidden size,
encoder layers, dropout, sequence length, batch size, learning rate, and gamma—or
the epsilon, distance-reward, and EpsilonNice pairs. Each value conversation
saves its choice in the durable draft. Unchanged values are permitted.

The baseline builds on SnakeLab 3.0.4's `transformer-epsilon-nice.json` sample:
a Transformer with hidden size 64, one encoder layer, four attention heads,
and dropout 0.05. Training starts with four-frame sequences, batch size 64,
learning rate 0.001, and target update rate (`tau`) 0.05. It runs 500 episodes
with required EpsilonNice starting at probability 0.05. The LLM chooses hidden
sizes from 32 to 128 in multiples of 8, encoder depth from 1 to 3 layers, and
dropout from 0 to 0.1 in steps of 0.01. Tau remains fixed at 0.05.
`SimulationConfiguration` owns defaults, schema validation, and the
non-positive-sum reward-pair rule. Seeds and fixed fields remain
application-controlled.

After every submitted value or pair, Ax3l checks the **whole configuration**
against all stored runs. A duplicate is rejected without saving it; Qwen must
submit different values for the same selected setting in the same conversation.
It cannot switch parameters or run until the setting produces a unique draft.
A unique configuration gives Qwen both `select_parameter` and
`run_simulation`: change any setting, including the same one again, or run now.
There is no fixed parameter order or requirement to change every setting.
Other values stay in the draft. Only an explicit run decision submits the
unique configuration once. Restarts resume the saved selection, value choice,
or run decision.

## Selection evidence

Ax3l freezes the latest, golden, and all-time best references when it opens a
draft. It records missing measurements directly from completed runs. The
`choose-snake-setting/SKILL.md` under `knowledge/` gives each choice the
same short procedure. The prompt supplies the assigned setting's current
values and reference results in JSON. Ax3l prepares one chart when the
assignment calls for it:

- Learning rate uses training loss, when recorded.
- The epsilon pair uses the score trend.
- The distance-reward pair uses the score distribution.

The chart comes from the latest run on the draft seed, or from the current
golden run if the latest run used a different seed. The prompt supplies
measured facts from the chart's source run. The all-time best is available
through the data tool. Reference runs sharing several roles appear once in
the run menu. All-time score ties resolve to the earliest stored run.

`data_tool(url)` opens a small page. Use `/draft` for current values,
`/` for the run menu, or a direct path such as `/golden/activity` for a
specific result. English labels explain each path. Data is JSON. Run pages
contain scores, termination counts and percentages, activity counts, and
settings. Notes from previously analyzed runs remain available.
The data tool is available before the first parameter selection and during
every next-step decision, so Qwen can research which setting to tweak.
Qwen has an advisory five-minute budget to select a parameter and find values
that produce a unique configuration, or decide to run an already unique draft.
After every data request, it receives the time remaining, including inference
and lookup time. Duplicate attempts keep the same countdown. An accepted unique
change resets it to five minutes for the next parameter or run decision.
At zero, the reminder urges a decision; it does not stop the conversation or
disable tools. Restarting the optimizer begins a fresh budget.

`kb_tool(url)` opens one short local guide. Use `/` for the guide list.
Run IDs and draft IDs are bound privately to the conversation.

## MCP tools

The stdio entry point is `python -m ax3l.app.snakelab.tools`. Ax3l starts a private
MCP session for each conversation and sends the assigned submission tool plus
`kb_tool` and `data_tool` to LlamaSrv. Submission
and data functions forward requests over ZeroMQ; Ax3l owns validation,
persistence, and reads through `ExperimentDb` and the shared `DbMgr`.
KB reads use only the explicitly addressed local page. Reads never save choices
or submit simulations. Qwen receives the requested page content, including its
JSON data; transport envelopes and full identifiers remain internal.

| Tool | Model arguments | Bound by Ax3l |
| --- | --- | --- |
| `submit_single_value` | `value` | Draft UUID and assigned parameter |
| `submit_pair_values` | `value_1`, `value_2` | Draft UUID and assigned pair |
| `select_parameter` | `parameter` | Active draft UUID |
| `run_simulation` | None | Unique draft UUID |
| `kb_tool` | `url` | Allowlisted local reference pages |
| `data_tool` | `url` | Selection draft and frozen references |

`AX3L_CONVERSATION_PARAMETER` identifies the single or pair.
It is `revision` while Qwen chooses the next step. `AX3L_ALLOW_RUN=1` exposes
the run action only after the configuration passes its uniqueness check.
`AX3L_CONFIGURATION_DRAFT` binds the selection session. Numeric inputs reject
strings, booleans, nonfinite values, and schema violations. The model cannot
replace the bound identifiers in its tool arguments.

`AX3L_ZMQ_ENDPOINT` overrides the configured Ax3l listener for a session.
Transport errors propagate without automatic retries. Explicit validation
rejections receive feedback in the same conversation. Missing or unexpected
tool calls stop the conversation with a logged error. A successful KB lookup
or data lookup continues the conversation; an accepted parameter selection,
value submission, or run decision finishes it.

## Persistence and restart

`ExperimentDb` stores draft snapshots, setup events, and measured results
in the existing Ax3l event tables through `DbMgr`. No new tables or migrations
are required.
Resetting experiment events also removes drafts and saved analyses.
After resetting source data, rebuild reporting projections with
`python -m ax3l.app.ReportingRefresh --rebuild` using the installed database
environment, before using the cached reports.

A restart resumes the explicit parameter or next-step decision, including when
an accepted choice's MCP reply was lost. Older drafts keep their in-progress
choice and switch to Qwen's decisions afterward. A draft records submission intent before
calling SnakeLab. If interrupted during submission, Ax3l reconciles by the full
configuration and monitors the existing run; it never automatically sends an
ambiguous submission again. A missing matching run raises an explicit error.
Recorded comparisons and promotions are recovered before the next draft starts.
Failed or cancelled runs mark their draft failed and stop the current loop;
a later startup begins a new draft using the retained golden configuration.

A completed configuration comparison counts as one experiment cycle. After nine
proposals without a new golden score, seed rotation reruns the golden settings
on the next seed and establishes a new baseline. The old per-parameter cycle
and exhaustion rules are no longer used by the optimization loop.

## Running and reporting

Load the installed database environment and run:

```sh
set -a
. /etc/ax3l/database.env
set +a
.venv/bin/python -m ax3l.app.snakelab.main-loop
```

The loop uses configured `llamasrv_url`, defaulting to
`http://127.0.0.1:51001`; `--url` overrides it. LlamaSrv must serve the loaded
Qwen model with image input and tool calling enabled. Model provisioning and
service lifecycle remain owned by LlamaSrv.

Fresh startup submits the default configuration once and promotes its completed
result as the initial golden. Ax3l records its measurements before selection.

Prompts (including embedded PNGs), replies, tool results, draft snapshots, and
measurements are logged to MariaDB. Experiment Status lists chart preparation,
Qwen requests, lookups, and submissions under the relevant choice. Each step
shows its own elapsed time, and each Qwen reply shows its reported input and
output tokens. Simulation details show exact termination percentages and any
previously saved narrative. Raw file capture remains controlled by
`DAx3l.RAW_LOGS_ENABLED` and is off by default.

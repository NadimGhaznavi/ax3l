# Complete-configuration optimization

Ax3l asks Qwen to choose every tunable setting before executing one SnakeLab
simulation. A pass contains five single choices—hidden size, sequence length,
batch size, learning rate, and gamma—followed by the epsilon, distance-reward,
and EpsilonNice pairs. Each conversation saves its choice in a durable draft.
It never submits a simulation. Unchanged values are permitted.

The baseline still uses SnakeLab 3.0.1, a four-head Transformer, 500 episodes,
and required EpsilonNice. `SimulationConfiguration` owns defaults, schema
validation, and the non-positive-sum reward-pair rule. Seeds and fixed fields
remain application-controlled.

After the last pair is chosen, Ax3l checks the **whole configuration** against
all stored runs. A duplicate is rejected within the last conversation so Qwen
can select a different final pair. Individual parameter domains are not skipped
as exhausted: other settings can change within the same draft.

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
| `kb_tool` | `url` | Allowlisted local reference pages |
| `data_tool` | `url` | Selection draft and frozen references |

`AX3L_CONVERSATION_PARAMETER` identifies the single or pair.
`AX3L_CONFIGURATION_DRAFT` binds the selection session. Numeric inputs reject
strings, booleans, nonfinite values, and schema violations. The model cannot
replace the bound identifiers in its tool arguments.

`AX3L_ZMQ_ENDPOINT` overrides the configured Ax3l listener for a session.
Transport errors propagate without automatic retries. Explicit validation
rejections receive feedback in the same conversation. Missing or unexpected
tool calls stop the conversation with a logged error. A successful KB lookup
or data lookup continues the conversation; only the assigned submission tool
can finish it.

## Persistence and restart

`ExperimentDb` stores draft snapshots, setup events, and measured results
in the existing Ax3l event tables through `DbMgr`. No new tables or migrations
are required.
Resetting experiment events also removes drafts and saved analyses.
After resetting source data, rebuild reporting projections with
`python -m ax3l.app.ReportingRefresh --rebuild` using the installed database
environment, before using the cached reports.

A restart resumes the first unselected parameter, including when an accepted
choice's MCP reply was lost. A complete draft records submission intent before
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

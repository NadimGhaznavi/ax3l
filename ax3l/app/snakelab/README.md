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

## Analysis and reference context

Before any configuration choice, Ax3l completes the image jobs for the frozen
latest, golden, and all-time best reference runs. This also applies when resuming
a partially selected draft: saved analyses are reused, unfinished chart tasks
finish first, and accepted configuration choices are preserved. Qwen browses
the resulting observations, exact measurements, and draft through small data
pages instead of receiving their full JSON in each choice prompt.

Each completed run receives one saved analysis containing its configuration,
exact measurements, and three short observations. Ax3l runs three distinct
conversations, each with one static PNG and one question:

1. Score trends: is the final 50-episode mean higher, lower, or equal to the
   first 50-episode mean of the same run? Both exact averages are supplied.
   The image includes episode scores, a trailing mean of up to 20 episodes,
   the target at analysis time, and an ordinary-epsilon-end marker when observed.
2. Score distribution: are high scores common or rare within this run?
3. Training loss: does recorded mean Smooth L1 loss rise, fall, or stabilize,
   with spikes or gaps for unrecorded measurements?

Each prompt includes only relevant measured facts and an explicitly invented
answer example. Qwen submits 1–2 sentences, at most 40 words, about that chart
and stops. Analysis prompts omit the general project context and full
configuration. Accepted sections are durable; a restart resumes the first
unfinished section. The final submission combines the three labeled observations
into the saved analysis without a fourth LLM conversation. Later parameter
choices can request all three observations through each run's notes page.

The image includes a title, seed, episode count, the high-score objective,
and labeled axes with units. SnakeLab's loss is a training
diagnostic in its native scale; changing rewards can change that scale.

Termination reasons do not require vision. Ax3l calculates wall/body collisions,
move-limit endings, board completions, and unrecorded/other outcomes as counts
and percentages of all recorded episodes. These are available on separate
data pages alongside score statistics, steps, and exploration counts.
Vision prompts receive only their chart's facts, with English labels. Missing loss
is not treated as zero.

## Reference drill-down

`kb_tool(url)` reads one small local Markdown reference page. The index `/`
links to chart guides, parameter selection, models/inputs, exploration, and
rewards. `/analysis/` links to one guide per chart. Read only what the assigned
task requires; navigation never injects the entire knowledge base. Chart prompts
provide their direct guide URL and selection context points to `/selection`.
General background lives in `knowledge/`, not in every prompt.

`data_tool(url)` reads one small page of experiment data. Start at `/`
for reference runs or `/draft` for current values marked chosen or pending.
Use the short labels `latest`, `golden`, and `best`; Qwen never needs a run UUID.
The draft ID is bound privately to the conversation. The root groups labels
that refer to the same run. Navigation stays in readable text with links;
actual values are JSON, including the draft choices and run comparisons in
overview pages' JSON blocks. Terminal data pages return a JSON object directly.

Each reference overview links to `scores`, `endings`, `activity`, `notes`,
`model`, `training`, `exploration`, `rewards`, and `game`. For example,
`/latest/notes` reads saved chart observations and `/golden/model` reads only
model settings. Draft pages expose the five configuration sections. Endings
include numeric counts and exact recorded percentages. Missing statistics are
JSON null, and saved observations are JSON strings. Settings retain their
configuration keys and numeric types. Selection rules use English in the
submission tool's description.

Every parameter conversation can browse saved analyses for:

- The latest completed simulation, including unsuccessful proposals.
- The current golden simulation, whose score on the current seed is the target.
- The all-time best completed simulation across seeds in this experiment.
  Ties select the earliest stored run for a stable reference.

A run serving multiple roles appears once with all its role labels. Different
runs retain separate analyses, even if only their seeds differ. Reference roles
and target comparisons are attached separately from the saved interpretation,
so promotions do not require another vision call. All reference IDs are frozen
for the duration of a draft. Every selection is directed to read the current
draft and its previously selected settings before choosing.

## MCP tools

The stdio entry point is `python -m ax3l.app.snakelab.tools`. Ax3l starts a private
MCP session for each conversation and sends the assigned submission tool plus
`kb_tool` to LlamaSrv. Selection sessions also receive `data_tool`. Submission
and data functions forward requests over ZeroMQ; Ax3l owns validation,
persistence, and reads through `ExperimentDb` and the shared `DbMgr`.
KB reads use only the explicitly addressed local page. Reads never save choices
or submit simulations. Qwen receives the requested page content, including its
JSON data; transport envelopes and full identifiers remain internal.

| Tool | Model arguments | Bound by Ax3l |
| --- | --- | --- |
| `submit_single_value` | `value` | Draft UUID and assigned parameter |
| `submit_pair_values` | `value_1`, `value_2` | Draft UUID and assigned pair |
| `submit_simulation_summary` | `summary` | Completed run UUID and chart section |
| `kb_tool` | `url` | Allowlisted local reference pages |
| `data_tool` | `url` | Draft UUID and its frozen reference runs |

`AX3L_CONVERSATION_PARAMETER` identifies the single, pair, or `simulation_summary`.
`AX3L_CONFIGURATION_DRAFT` binds selection sessions;
`AX3L_ANALYSIS_RUN` and `AX3L_ANALYSIS_SECTION` bind analysis sessions. Numeric
inputs reject strings, booleans, nonfinite values, and schema violations.
Chart observations require 1–2 sentences and at most 40 words. Unbound sessions
permit guide reads and discovery but reject data reads and submissions.
The model cannot replace the bound identifiers in its tool arguments.

`AX3L_ZMQ_ENDPOINT` overrides the configured Ax3l listener for a session.
Transport errors propagate without automatic retries. Explicit validation
rejections receive feedback in the same conversation. Missing or unexpected
tool calls stop the conversation with a logged error. A successful KB lookup
or data lookup continues the conversation; only the assigned submission tool
can finish it.

## Persistence and restart

`ExperimentDb` stores immutable draft snapshots, analysis progress, and analyses
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
result as the initial golden. Analysis follows before the first draft.

Prompts (including embedded PNGs), replies, tool results, draft snapshots, and
analyses are logged to MariaDB. Simulation details display the saved narrative
and exact termination percentages. Displayed run IDs use their first eight
characters; storage and navigation use full UUIDs. The metrics report includes
all parameter conversations for a draft and its run's vision-analysis time.
Raw file capture remains controlled by `DAx3l.RAW_LOGS_ENABLED` and is off by
default; `--output` selects its directory when enabled.

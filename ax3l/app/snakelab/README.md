# Complete-configuration optimization

Ax3l starts a draft from the current golden configuration and asks Qwen which
setting to change. Qwen can choose any of eleven single settings—hidden size,
encoder layers, dropout, sequence length, batch size, learning rate, gamma,
food reward, empty space reward, snake collision reward, and wall collision reward—or
the epsilon, distance-reward, and EpsilonNice pairs, or request a seed change.
Each choice conversation
saves its choice in the durable draft. Once selected, a setting must change:
a single value must differ, and at least one value in a pair must differ.

The baseline builds on SnakeLab 3.0.4's `transformer-epsilon-nice.json` sample:
a Transformer with hidden size 64, one encoder layer, four attention heads,
and dropout 0.05. Training starts with four-frame sequences, batch size 64,
learning rate 0.001, and target update rate (`tau`) 0.05. It runs 750 episodes
with required EpsilonNice starting at probability 0.05. The LLM chooses hidden
sizes from 32 to 128 in multiples of 8, encoder depth from 1 to 3 layers, and
dropout from 0 to 0.1 in steps of 0.01. Tau remains fixed at 0.05.
Empty space rewards accept any number from -2 to +2, defaulting to 0.
Food rewards accept any number from 0 to +20, defaulting to +10.
Snake and wall collision rewards each accept any number from -20 to 0,
defaulting to -10. The move-limit penalty remains -10.
Positive empty rewards require deployment of SnakeLab's updated v2 schema.
`SimulationConfiguration` owns defaults, schema validation, and the
non-positive-sum reward-pair rule. Selecting `seed` immediately accepts the seed
change without choosing a number or opening another conversation. Ax3l
increments the seed, skipping complete configurations stored in any status.
Fixed fields remain application-controlled.

After every submitted value or pair, Ax3l checks the **whole configuration**
against all stored runs. A duplicate is rejected without saving it; Qwen must
submit different values for the same selected setting in the same conversation.
`run_simulation` remains available throughout configuration setup. It checks
the saved whole configuration for duplicates, including when no settings have
changed. A rejection redisplays the current screen without discarding research
or resetting the decision timer. An accepted run uses saved values and clears
any pending setting assignment. Each parameter can be
selected only once within a draft, including after a restart. Used parameters
are omitted from the next selection prompt and rejected by the selection tool.
There is no fixed parameter order or requirement to change every setting.
Before offering a setting, Ax3l checks finite domains, such as encoder layers,
against stored configurations with the draft's current seed and all other
settings unchanged. A setting is omitted when every changed choice already
exists in any run status. The current values cannot count as an available change.
The selection tool enforces the same check before saving the assignment.
Availability is recalculated after accepted changes, including seed changes.
On restart, an exhausted pending assignment returns to the next-step decision.
Other values stay in the draft. Only an explicit run decision submits the
unique configuration once. Restarts resume the saved selection, value choice,
or run decision.

## Selection evidence

Ax3l freezes the latest, golden, and all-time best references when it opens a
draft. It records missing measurements directly from completed runs. The
[`choose-snake-setting/SKILL.md`](../../presentation/snakelab/guides/choose-snake-setting/SKILL.md) remains available as optional reference.
Per-item prompts omit generic rules and menus, and supply the assigned setting's current
values and reference results in JSON. Ax3l prepares one chart when the
assignment calls for it:

- Learning rate uses training loss, when recorded, with faint raw traces and
  trailing means over up to 20 episodes. A distinct golden run's loss and mean
  appear in orange when recorded. Missing losses are excluded from the means
  and remain gaps in both traces.
- The epsilon pair uses the score trend.
- The distance-reward pair and the food and empty space rewards use the score distribution.
- Snake and wall collision rewards use three horizontal bars for snake collisions,
  wall collisions, and max moves. Labels show whole percentages and exact counts.
  All episodes remain in the denominator, with other outcomes noted below the bars.
  The prompt's JSON retains full measured precision.

EpsilonNice choices use `EpsilonNiceChoice`, which adds a compact definition of
the custom exploration rule, its probability and duration, and episode resets.

The chart comes from the latest run on the draft seed, or from the current
golden run if the latest run used a different seed. The prompt supplies
each reference's seed and whether it matches the draft. Chart sources are
selected again after seed changes; measurements from other seeds are historical
context. It also supplies measured facts from the chart's source run. All-time
score ties resolve to the earliest stored run.

The main configuration page compares best, golden, latest, and draft values
for every configurable setting. Saved edits remain visible, with `editable`
indicating which settings can currently be selected. Historical results and
saved observations appear in a separate JSON block by metric, with best,
golden, and latest values together. Nested metrics place the reference values
after the metric path. Report previews show these comparisons in columns,
without repeated configurations or redundant roles.

`kb_tool(url)` opens the linked definitions or optional lab reference. Reading
a definition from the main page redisplays that page afterward in the same
conversation. Definition pages include "Don't show your reasoning in the
prompt." Saving a setting returns to the main page with updated draft values.
Older draft and run data URLs remain readable. Navigation uses English and
payloads use JSON.
Ax3l internally allows seven minutes to select a parameter and find values
that produce a unique configuration, or decide to run an already unique draft.
The timer includes inference and lookup time. Prompts and tool feedback do not
mention the timer, remaining time, or expiry actions; the countdown remains
visible in Experiment Status. Rejected attempts keep the same countdown.
An accepted unique change resets it to seven minutes for the next parameter
or run decision.
Sending a choice prompt with a chart adds two minutes to the remaining decision
budget and the Experiment Status deadline. This allowance is added once for
that prompt; data reads and rejected values keep the extended deadline. A choice
without an image receives no extra time, including learning rate when no loss
is recorded.
Expiry gives Qwen a grace period controlled by `decision_grace_seconds` in
`/opt/prod/ax3l/conf/ax3l.json`, defaulting to 420 seconds (seven minutes).
Before the first unique change,
the end of grace restarts from the initial prompt in a fresh conversation with
a fresh seven-minute budget. The tentative parameter selection, prior research,
reasoning, and rejected proposals are discarded. Once a unique draft is saved,
the end of grace submits that configuration through the normal simulation,
comparison, and measurement cycle, and starts the next experiment.
A pending edit is not included unless its changed values were accepted.
Restarting the optimizer begins a fresh budget.

Use `/` for the shared browser home and `/guides` for short local guides.
Run IDs and draft IDs are bound privately to the conversation.

## Presentation boundaries

Qwen sees **Patrick Loeber's AI Snake Lab**, with the role Data Scientist and
an experiment menu. Navigation uses English labels and existing URLs. Settings,
measurements, and saved observations remain JSON, including numbers and nulls.
Prompts display the current task and available actions; the lab reference holds
implementation details and experiment rules. Domain tutorials and prescribed
analysis strategies are omitted.

`/latest`, `/golden`, and `/best` each return the complete run configuration,
measured results, and saved observations in one JSON snapshot. `/draft` returns
the full current configuration, saved setting names, and the active setting.
These pages link back to the experiment menu rather than to individual data
sections. Older section URLs remain readable for existing conversations.

The [`presentation/snakelab`](../../presentation/snakelab) package owns the
Markdown guides and Jinja Markdown templates. Its `templates/pages` directory
controls data-page wording, layout, and navigation; `templates/prompts` controls
choice, next-step, and EpsilonNice guidance; `templates/tools` controls MCP tool
descriptions. JSON values are inserted with the `json` filter, preserving numbers,
nulls, and quoted text. Template values are strict: missing values fail clearly.
Templates are read on every render so presentation edits take effect on the next
read or newly constructed prompt; MCP descriptions are rendered at session startup.

[`SimulationDataValues`](../../activity/SimulationDataValues.py) and
[`ConfigurationEvidence`](../../activity/ConfigurationEvidence.py) prepare values
without composing prose. [`DataPages`](../../presentation/snakelab/DataPages.py)
connects those values to page templates. Each settings or measurement page has
its own template under `templates/pages/config` or `templates/pages/run`, initially
including the shared JSON layout. Customize an individual page by editing its
template, or edit the shared layout to change all data pages together.
[`PageBrowser`](PageBrowser.py) joins allowlisted guide pages under `/guides`
with the current conversation's data reader and adds the shared home page.
Only the requested page is loaded.

The prompt classes select the applicable instruction and evidence, then render
templates. Experiment sequencing, available actions, acceptance rules, and timers
remain application decisions. Templates do not query databases, select runs, or
save choices. The data reader still uses frozen references and the original
chart run. These boundaries let wording and layout change independently of
querying and conversation control.

## MCP tools

The stdio entry point is `python -m ax3l.app.snakelab.tools`. Ax3l starts a private
MCP session for each conversation and sends the assigned submission tool plus
`kb_tool` to LlamaSrv. Submission
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
| `run_simulation` | None | Active draft UUID |
| `request_seed_change` (legacy) | None | Draft UUID and selected seed choice |
| `kb_tool` | `url` | Local guides, selection draft and frozen references, or analysis run |

`AX3L_CONVERSATION_PARAMETER` identifies the single or pair.
It is `revision` while Qwen chooses the next step. The run action is exposed
in every configuration session; chart-summary sessions cannot run simulations.
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

To discard an interrupted setup rather than resume it, run
[`scripts/wipe-experiment-workspace.sh`](../../../scripts/wipe-experiment-workspace.sh)
as root from the current checkout. It stops Ax3l services, deletes only the
current unsubmitted draft's events and linked tool receipts in one transaction,
and restarts services. The next draft starts from golden. Completed runs,
golden history, and analyses are preserved. Submissions and seed rotations
already in progress are refused.
Failed or cancelled runs mark their draft failed and stop the current loop;
a later startup begins a new draft using the retained golden configuration.

A completed configuration comparison counts as one experiment cycle. Qwen can
research its references, then select `seed` once per draft to immediately save
the next unique seed while preserving other choices. There is no separate
seed confirmation conversation or tool call. A pending seed selection saved
by an older version is completed automatically on restart. The legacy
`request_seed_change()` entry point remains supported; replaying it after
acceptance cannot increment the seed again.
Repeated seed selections or requests return `parameter_space_exhausted`, reopening
the available choices and explaining that the seed cannot change again in this draft.
The normal run decision and deadlines apply. When the draft runs, Ax3l first
runs the current golden configuration with only the new seed and accepts its
score as the local golden baseline, even if it is lower. A seed-only draft
finishes with that run. If other settings changed, Ax3l then runs the complete
draft on the same new seed and compares it against the new baseline; ties and
losses retain that baseline. Seed choices skip stored configurations for both
the draft and its golden baseline. Seeds are nonnegative integers bounded
by Ax3l's signed `BIGINT` score-history column. They are not offered as numeric
value choices or enumerated as a finite search grid.

There is no nine-proposal automatic rotation. Interrupted seed rotations resume
their recorded baseline without resubmitting, including when the baseline was
accepted just before a restart. Startup also finishes rotations recorded under
the former automatic policy. Historical rotation events and scores remain
readable. Seed-only rotations do not count as configuration comparisons.
The old per-parameter cycle is no longer
used; finite-domain exhaustion now filters Qwen's available parameter choices.

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

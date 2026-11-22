---
title: Snake Lab Prompts
author_profile: true
layout: single
---

# Snake Lab Prompts

Qwen works as the Data Scientist in **Patrick Loeber's AI Snake Lab**, an ongoing
experiment. The main configuration page explains the editing flow and offers
linked definitions and the run action. Setting pages show the current task.
Menu links keep the existing URL system; measurements and configuration values
remain JSON. The presentation supplies implementation details and available
actions, leaving the analysis method to Qwen.

| Prompt | Purpose |
| --- | --- |
| `ConfigurationNextStep` | Presents the main configuration page, editing instructions, linked definitions, and separate JSON blocks for configurable values and historical results. Saved draft values remain visible. Always offers Run next simulation. |
| `ConfigurationChoice` | Shows the lab heading, current setting, configuration comparison, and historical results. Chart images remain available. Generic instructions and menus stay on the main page. |
| `EpsilonNiceChoice` | Adds a compact definition of the custom EpsilonNice exploration rule when choosing its probability and steps. |
| `InvalidValue` | Explains why Ax3l rejected a value. |
| `NoDupes` | Identifies the duplicate proposal and asks Qwen to try different values for the same setting. |

Use `select_parameter(parameter)` with a key from `settings` whose `editable`
flag is true. Each setting can be chosen
once per draft, in any order. `submit_single_value` and `submit_pair_values`
save changes using the limits in their tool descriptions. Ax3l binds the draft
and setting identifiers. Duplicate proposals stay in the same conversation
while untested values remain for that setting.

The main page lists Run next simulation and says, "Choose
the Run next simulation option when you are done making changes to the
configuration." The run tool remains available during value choices. Running checks the
saved configuration for duplicates. A rejected run returns to the same screen
and preserves the conversation and its decision timer. Unsaved values are not
included in an accepted run.

`select_parameter("seed")` immediately saves the next unused seed once per
draft, without a separate seed confirmation conversation or tool call. After
the run decision, golden runs first on the new seed and sets the baseline even
if its score is lower. If other settings changed, Ax3l tests them on the new seed
and requires a higher score to promote the draft.

The internal seven-minute decision timer spans setting selection and value
choice. Prompts and tool feedback do not mention the timer or its expiry actions.
Experiment Status continues to display the countdown. Saving a unique change
resets the timer. A prompt with a chart adds two minutes to the remaining
decision budget once; reads and rejected values keep that
extended deadline. After the configured grace period (seven minutes by default),
Ax3l restarts the conversation if there is no saved change or runs the saved
unique draft.

The main page's first JSON block contains `settings`: only configurable
elements, each with a label, an `editable` flag, and `values` for `best`,
`golden`, `latest`, and `draft`. Single settings use numbers; pairs retain their
field names. Edited and currently exhausted settings remain visible with
`editable: false`. After saving, the main page is rendered again from the saved
draft, updating these values and flags.

Decimal values display at most five places; stored values keep their precision.

The second JSON block starts with metric names, each containing `best`,
`golden`, and `latest` values, for example
`"episodes": {"best": 750, "golden": 750, "latest": 750}`. Nested metrics keep
their structure before those reference values:
`termination_reasons.wall.percent.best` is best's percentage of wall endings.
Seed context and saved observations use the same layout. The parameter screen
uses these same two JSON blocks. Report previews show metrics as rows and
reference runs as columns. Repeated configurations and redundant roles are
omitted. Missing statistics and observations remain null. Reference values
come from the draft's frozen references; no data read is needed.

`kb_tool(url)` opens the linked definitions under `/definitions/`. Best, golden,
latest, and draft each have a short definition including "Don't show your
reasoning in the prompt." A successful definition read from the main page is
followed by that page again, in the same conversation and under the same
deadline. A definition read does not change configuration values.

`kb_tool(url)` also reads optional lab reference, starting at `/guides`. Navigation
uses English and payloads use JSON. The setup menus and tool descriptions do
not advertise `/latest`, `/golden`, `/best`, or `/draft`; those URLs and their
section URLs remain readable for older sessions. `/` is the shared browser menu.
The reference menu covers experiment rules, model inputs, exploration and reward
implementation, and metric and chart definitions. It supplies no prescribed
analysis sequence or hyperparameter tuning strategy.

Presentation lives under `ax3l/presentation/snakelab`: `guides` contains static
Markdown, and `templates` contains Markdown templates for pages, prompts, and
tool descriptions. Prepared values are inserted with a JSON filter. The Python
application retains evidence selection, validation, and conversation sequencing.

A read continues the conversation. An accepted submission finishes the
choice. Prompt events preserve the exact text, JSON evidence, and PNG that
Qwen received.

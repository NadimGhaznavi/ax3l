---
title: Snake Lab Prompts
author_profile: true
layout: single
---

# Snake Lab Prompts

Qwen works as the Data Scientist in **Patrick Loeber's AI Snake Lab**, an ongoing
experiment. Prompts show the current task, draft status, and an English menu.
Menu links keep the existing URL system; measurements and configuration values
remain JSON. The presentation supplies implementation details and available
actions, leaving the analysis method to Qwen.

| Prompt | Purpose |
| --- | --- |
| `ConfigurationNextStep` | Presents the experiment menu, draft status, and JSON with best, golden, latest, and draft values for each available setting, full reference-run data, and the saved draft. Always offers Run next simulation. |
| `ConfigurationChoice` | Presents the selected setting, set and save action, run action, lab-reference link, and the inline comparison and run data. Learning rate, epsilon, and distance rewards can include a chart. |
| `EpsilonNiceChoice` | Adds a compact definition of the custom EpsilonNice exploration rule when choosing its probability and steps. |
| `InvalidValue` | Explains why Ax3l rejected a value. |
| `NoDupes` | Identifies the duplicate proposal and asks Qwen to try different values for the same setting. |

Use `select_parameter(parameter)` with a key from `settings`. Each setting can be chosen
once per draft, in any order. `submit_single_value` and `submit_pair_values`
save changes using the limits in their tool descriptions. Ax3l binds the draft
and setting identifiers. Duplicate proposals stay in the same conversation
while untested values remain for that setting.

Run next simulation stays visible throughout setup. The screen says, "Choose
the Run next simulation option when you are done making changes to the
configuration." Saved changes are labelled Changes saved. Running checks the
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

The setup JSON includes `settings`, `runs`, and `draft`. Each available setting
has a label and `values` containing `best`, `golden`, `latest`, and `draft`.
Single settings use numbers; pairs retain their field names. `runs` contains
the three reference runs' complete configurations, measured results, and saved
observations. `draft` contains the complete saved configuration, phase, and
saved and current setting names. Missing statistics and observations remain null.
These values come from the draft's frozen references; no data read is needed.

`kb_tool(url)` reads optional lab reference, starting at `/guides`. Navigation
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

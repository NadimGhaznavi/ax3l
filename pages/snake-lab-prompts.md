---
title: Snake Lab Prompts
author_profile: true
layout: single
---

# Snake Lab Prompts

Qwen starts with golden's configuration and chooses which settings to change
before running a simulation. Each prompt opens with the available decision.
For value choices, `choose-snake-setting` tells Qwen how to weigh the evidence.

| Prompt | Purpose |
| --- | --- |
| `ConfigurationNextStep` | Lists available keys and current values. Gives Qwen the option to run once the draft is unique. |
| `ConfigurationChoice` | Names the submission tool and supplies current values, reference scores, and data paths. Learning rate, epsilon, and distance rewards can include a chart. |
| `EpsilonNiceChoice` | Adds a compact definition of the custom EpsilonNice exploration rule when choosing its probability and steps. |
| `InvalidValue` | Explains why Ax3l rejected a value. |
| `NoDupes` | Identifies the duplicate proposal and asks Qwen to try different values for the same setting. |

Use `select_parameter(parameter)` with a listed key. Each setting can be chosen
once per draft, in any order. `submit_single_value` and `submit_pair_values`
save changes using the limits in their tool descriptions. Ax3l binds the draft
and setting identifiers. Duplicate proposals stay in the same conversation
while untested values remain for that setting.

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

`data_tool(url)` reads one small page. Use `/draft` for saved and inherited
values, `/` for the run menu, and direct paths such as `/latest/scores` or
`/golden/activity` for details. Navigation uses English. Values are JSON
and missing statistics are null. Previously saved observations remain
available through a run's notes page. `kb_tool(url)` serves short local
guides, starting at `/`.

A read continues the conversation. An accepted submission finishes the
choice. Prompt events preserve the exact text, JSON evidence, and PNG that
Qwen received.

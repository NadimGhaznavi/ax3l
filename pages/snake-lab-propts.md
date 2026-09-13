---
title: Snake Lab Prompts
author_profile: true
layout: single
---

# Snake Lab Prompts

These prompts are used by the current Snake Lab learning-rate optimization loop,
using text-only messages, including feedback sent when a submission needs correcting. The golden
configuration is the current baseline used to evaluate new proposals.

| Prompt name | Description |
| --- | --- |
| `FirstContact` | Introduces the Snake experiment and asks the model to choose values that improve the high score, including exploring less promising ranges to gather evidence. Sent at the start of the initial optimization conversation. |
| `GoldenConfig` | Presents the current golden configuration as JSON, excluding the managed seed, together with the reason it was selected. Supplies the baseline for the initial conversation. |
| `FirstContactSingle` | Describes the selected parameter and its JSON Schema rules. Currently targets `learning_rate` and requires exactly one `submit_single_value` tool call that changes only that parameter from its golden value. |
| `Comparison` | Presents learning rates and high scores for configurations matching the current baseline's other settings, with current-seed results and earlier-seed score history. Identifies the previous golden, latest, and current golden runs, and explains that only a strictly higher high score replaces the golden run. |
| `ComparisonSingle` | Requests the next learning rate after reviewing results. Gives its allowed range and asks for an unexplored value, changing only `learning_rate`, submitted through `submit_single_value`. |
| `UseTool` | Reminds the model to submit its choice using `submit_single_value` when its response contains no tool call. |
| `InvalidValue` | Explains why a submission was invalid and asks the model to choose a legal value from the JSON specification and resubmit. |
| `NoDupesSingle` | Explains that a proposed configuration matches the golden configuration or an existing simulation, and asks the model to submit a different value. |

This list follows `LearningRateLoop.py`, `ToolConversation.py`, and
`SubmitSingleValueHandler.py` in `ax3l/app/snakelab/`. `GenerateHaiku` belongs to
the separate helper workflow and is not used by the optimization entry point.
Unused placeholder prompts for epsilon and reward pairs are also excluded.

`LossPlot` and `ComparisonPlot` are no longer used by the optimization flow.

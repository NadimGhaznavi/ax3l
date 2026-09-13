---
title: Snake Lab Prompts
author_profile: true
layout: single
---

# Snake Lab Prompts

These prompts are used by the current Snake Lab single-parameter optimization loop,
using text-only messages, including feedback sent when a submission needs correcting. The golden
configuration is the current baseline used to evaluate new proposals.

| Prompt name | Description |
| --- | --- |
| `FirstContact` | Introduces the Snake experiment and asks the model to choose values that improve the high score, including exploring less promising ranges to gather evidence. Sent at the start of the initial optimization conversation. |
| `GoldenConfig` | Presents the current golden configuration as JSON, excluding the managed seed, together with the reason it was selected. Supplies the baseline for the initial conversation. |
| `FirstContactSingle` | Describes the selected parameter and its JSON Schema rules. Offers `hidden_size`, `sequence_length`, `batch_size`, `learning_rate`, and `gamma` and requires exactly one `submit_single_value` tool call that changes only that parameter from its golden value. |
| `Comparison` | Presents per-parameter values and high scores for configurations matching the current baseline's other settings, with current-seed results and earlier-seed score history. Identifies the previous golden, latest, and current golden runs, and explains that only a strictly higher high score replaces the golden run. |
| `ComparisonSingle` | Requests the next single-parameter change after reviewing results. Gives schema rules for all five eligible parameters and asks for an unexplored value, changing only one parameter, submitted through `submit_single_value`. |
| `InvalidValue` | Explains why a submission was invalid and asks the model to choose a legal value from the JSON specification and resubmit. |
| `NoDupesSingle` | Explains that a proposed configuration matches the golden configuration or an existing simulation, and asks the model to submit a different value. |

This list follows `SnakeLabLoop.py`, `ToolConversation.py`, and
`SubmitSingleValueHandler.py` in `ax3l/app/snakelab/`.
Unused placeholder prompts for epsilon and reward pairs are also excluded.

Requests require one tool call through the API's tool metadata. A response without
the expected tool call ends the conversation with a logged error. Rejected values
still receive validation feedback within the same conversation.

`LossPlot` and `ComparisonPlot` are no longer used by the optimization flow.

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
| `FirstContact` | Introduces Patrick Loeber's AI Snake Game, sets the high-score objective, and encourages exploring apparently poor choices to gather data and discover higher plateaus. |
| `FirstContactSingle` | Requests an untested value for the assigned parameter using `submit_single_value({"value": number})`. |
| `Comparison` | Shows only the assigned parameter's golden value, high score, and comparable history on the current and earlier seeds. Used from the first conversation onward. |
| `ComparisonSingle` | Requests the next untested value for the assigned parameter. |
| `InvalidValue` | Explains why a submission was invalid and asks the model to choose a legal value from the JSON specification and resubmit. |
| `NoDupesSingle` | Explains that a proposed configuration matches the golden configuration or an existing simulation, and asks the model to submit a different value. |

This list follows `SnakeLabLoop.py`, `ToolConversation.py`, and
`SubmitSingleValueHandler.py` in `ax3l/app/snakelab/`.
Unused placeholder prompts for epsilon and reward pairs are also excluded.

Requests require one tool call through the API's tool metadata. A response without
the expected tool call ends the conversation with a logged error. Rejected values
still receive validation feedback within the same conversation.

`LossPlot` and `ComparisonPlot` are no longer used by the optimization flow.

The MCP tool description supplies only the assigned parameter’s meaning and schema rules. The full golden configuration and other parameters’ histories are not sent.

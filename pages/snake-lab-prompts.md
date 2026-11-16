---
title: Snake Lab Prompts
author_profile: true
layout: single
---

# Snake Lab Prompts

Ax3l activates the `choose-snake-setting` skill for each parameter choice and
sends a single prompt with the assignment and relevant evidence. The skill
defines how to use the evidence and when to keep the current value. Ax3l
supplies the setting, the chart when applicable, and the tools for the choice.

| Prompt | Purpose |
| --- | --- |
| `ConfigurationChoice` | Names the choice, supplies current values and reference scores in JSON, and gives direct data paths. The learning rate, epsilon, and reward choices can include one chart. |
| `InvalidValue` | Explains why Ax3l rejected a value. |
| `NoDupes` | Explains a duplicate completed draft and requests different values for its final pair. |

The seven single choices (hidden size, layers, dropout, sequence length, batch
size, learning rate, and gamma) precede the epsilon, distance-reward, and
EpsilonNice pairs. `submit_single_value` and `submit_pair_values` save one choice. Ax3l
runs the simulation after it accepts the complete configuration. Draft and
parameter identifiers are bound outside the model's arguments. The tool
description contains the allowed values.

`data_tool(url)` reads one small page. Use `/draft` for saved and inherited
values, `/` for the run menu, and direct paths such as `/latest/scores` or
`/golden/activity` for details. Navigation uses English. Values are JSON
and missing statistics are null. Previously saved observations remain
available through a run's notes page. `kb_tool(url)` serves short local
guides, starting at `/`.

A read continues the conversation. An accepted submission finishes the
choice. Prompt events preserve the exact text, JSON evidence, and PNG that
Qwen received.

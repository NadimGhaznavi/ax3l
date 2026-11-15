---
title: Snake Lab Prompts
author_profile: true
layout: single
---

# Snake Lab Prompts

The optimizer chooses all tunable settings in a draft before executing one
simulation. Parameter conversations use text; three separate conversations per
completed run interpret one chart each and produce reusable observations.

| Prompt | Purpose |
| --- | --- |
| `ProjectContext` | States the high-score goal and task boundary; points to short KB guides for background. |
| `AnalyzeSimulation` | Asks one question about score trends, score distribution, or training loss. Supplies one PNG, relevant facts, an invented example, and the chart's KB URL. Requests 1–2 sentences, at most 40 words, through `submit_simulation_summary`. |
| `ConfigurationChoice` | Supplies deduplicated latest/golden/all-time analyses, their configurations and seeds, the exact current target, the draft and selected settings, and the assigned single/pair schema rules. |
| `InvalidValue` | Returns an explicit validation rejection within the current conversation. |
| `NoDupes` | Rejects a duplicate completed draft and requests different values for its final pair. |

The five single choices precede the epsilon, distance-reward, and EpsilonNice
pairs. `submit_single_value` and `submit_pair_values` save choices; neither
runs a simulation. Unchanged values are allowed until the final full-config
duplicate check. Ax3l binds draft, parameter, and analysis-run identifiers
outside the model's tool arguments. Each analysis conversation also binds its
chart section outside the model's arguments.

`kb_tool(url)` offers a small reference index at `/` and linked pages for models,
exploration, rewards, selection, and individual chart guides. Qwen can drill down
to the needed page before submitting its answer. General reference material is
read on demand rather than repeated in each task.

Saved interpretations describe the run's intrinsic behavior. Current roles
and score comparisons are added when building selection context. One run can
serve several roles without repeated context or repeated vision inference.
Different-seed results remain explicitly identified as historical context.
Each accepted chart observation is saved. A restart skips finished sections;
the final submission combines all three observations for later parameter choices
without another LLM call.

Each response requires exactly one call to the assigned submission tool or
`kb_tool`. A KB read continues the conversation; the assigned submission finishes
it. A missing or unexpected tool call stops the conversation; explicit validation
rejections receive feedback.
Prompt events store the exact text/image snapshot supplied to Qwen.

---
title: Snake Lab Prompts
author_profile: true
layout: single
---

# Snake Lab Prompts

The optimizer chooses all tunable settings in a draft before executing one
simulation. Parameter conversations use text; one additional conversation per
completed run uses Qwen's image processing to produce a reusable interpretation.

| Prompt | Purpose |
| --- | --- |
| `ProjectContext` | Explains the high-score goal, 24-feature vector, Transformer training, EpsilonNice, and complete-configuration workflow. |
| `AnalyzeSimulation` | Supplies a three-panel PNG, exact observations including termination counts/percentages, and configuration. Requests 2–3 sentences, at most 80 words, through `submit_simulation_summary`. |
| `ConfigurationChoice` | Supplies deduplicated latest/golden/all-time analyses, their configurations and seeds, the exact current target, the draft and selected settings, and the assigned single/pair schema rules. |
| `InvalidValue` | Returns an explicit validation rejection within the current conversation. |
| `NoDupes` | Rejects a duplicate completed draft and requests different values for its final pair. |

The five single choices precede the epsilon, distance-reward, and EpsilonNice
pairs. `submit_single_value` and `submit_pair_values` save choices; neither
runs a simulation. Unchanged values are allowed until the final full-config
duplicate check. Ax3l binds draft, parameter, and analysis-run identifiers
outside the model's tool arguments.

Saved interpretations describe the run's intrinsic behavior. Current roles
and score comparisons are added when building selection context. One run can
serve several roles without repeated context or repeated vision inference.
Different-seed results remain explicitly identified as historical context.

Requests require exactly one assigned tool call. A missing or unexpected tool
call stops the conversation; explicit validation rejections receive feedback.
Prompt events store the exact text/image snapshot supplied to Qwen.

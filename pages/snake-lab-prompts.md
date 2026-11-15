---
title: Snake Lab Prompts
author_profile: true
layout: single
---

# Snake Lab Prompts

The optimizer first completes the reference runs' image-analysis jobs, then
lets Qwen browse their saved observations through small English data pages.
It chooses all tunable settings in a draft before executing one simulation.
Three separate conversations per completed run interpret one chart each and
produce reusable observations. Resuming a draft completes unfinished reference
analysis before the next configuration choice and reuses saved observations.

| Prompt | Purpose |
| --- | --- |
| `ProjectContext` | States the high-score goal and task boundary; points to short KB guides for background. |
| `AnalyzeSimulation` | Asks one question about score trends, score distribution, or training loss. Supplies one PNG, relevant facts, an invented example, and the chart's KB URL. Requests 1–2 sentences, at most 40 words, through `submit_simulation_summary`. |
| `ConfigurationChoice` | Names one choice and the score to beat; directs Qwen to `data_tool` for the draft and reference runs. Choice rules use English in the submission tool description. |
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

`data_tool(url)` reads experiment data, using short labels rather than UUIDs.
The `/` index links to `draft`, `latest`, `golden`, and `best`. Reference pages
link to scores, endings, activity, notes, and five settings sections. For example,
`/latest/notes` reads the saved observations, and `/draft/training` reads current
training settings. `/draft` shows each tunable value as chosen or pending.
Only the requested page is returned, as plain English text. Full identifiers
stay in storage and transport. Chart facts also use compact English labels.

Saved interpretations describe the run's intrinsic behavior. Current roles
and score comparisons are added when building selection context. One run can
serve several roles without repeated context or repeated vision inference.
Different-seed results remain explicitly identified as historical context.
Each accepted chart observation is saved. A restart skips finished sections;
the final submission combines all three observations for later parameter choices
without another LLM call.

Each response requires exactly one call to the assigned submission tool or
`kb_tool`, or (for choices) `data_tool`. A read continues the conversation; the assigned submission finishes
it. A missing or unexpected tool call stops the conversation; explicit validation
rejections receive feedback.
Prompt events store the exact text/image snapshot supplied to Qwen.

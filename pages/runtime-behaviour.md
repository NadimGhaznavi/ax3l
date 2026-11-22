---
title: Runtime Behaviour
author_profile: true
layout: single
---

# Complete-configuration experiments

Qwen chooses which settings to adjust and when to run one 750-episode SnakeLab
simulation. It can research measured data before selecting a setting, then
receives a chart when it can inform the value choice.

## Initial startup

With an empty experiment, Ax3l submits the schema defaults once. The baseline
builds on SnakeLab 3.0.4's `transformer-epsilon-nice.json` sample and runs 750
episodes with required EpsilonNice:

| Setting | Initial value |
| --- | --- |
| Hidden size / encoder layers / attention heads | 64 / 1 / 4 |
| Dropout | 0.05 |
| Sequence length / batch size | 4 / 64 |
| Learning rate | 0.001 |
| Gamma / target update rate (`tau`) | 0.96 / 0.05 |
| EpsilonNice probability / steps | 0.05 / 20 |

Tau remains fixed during optimization. On completion,
the baseline becomes the initial golden configuration and has its measurements
saved before the first choice. Interrupted initial seeding resumes its recorded
submission.

## Choosing a complete configuration

A new draft starts from the current golden configuration. It freezes the latest,
golden, and all-time best reference runs for the entire selection pass. The
draft is saved while Ax3l records any missing measurements. A restart uses
the same frozen references and resumes the saved parameter or next-step decision.
Qwen can choose any unused setting from the following list. Each setting can be
chosen only once per experiment, including after a restart:

| Parameter | Purpose | Allowed values | Tuned with |
| --- | --- | --- | --- |
| Hidden Size | Number of neurons in each Transformer hidden layer. | Integers from 32 to 128, in multiples of 8. | Individually |
| Encoder Layers | Number of Transformer encoder layers. | 1, 2, or 3. | Individually |
| Dropout | Dropout probability in the Transformer. | Numbers from 0 to 0.1, in steps of 0.01. | Individually |
| Sequence Length | Number of consecutive frames in each training sequence. | Integers from 4 to 48, in multiples of 4. | Individually |
| Batch Size | Number of sequences sampled for each training update. | Integers from 8 to 64, in multiples of 2. | Individually |
| Learning Rate | Size of gradient updates during training. | Numbers from 0.0005 to 0.005. | Individually |
| Gamma | Discount factor controlling the value of future rewards. | Numbers from 0.9 to 0.99. | Individually |
| Random Seed | Change the simulation seed. | Ax3l increments the seed, skipping already stored complete configurations. Qwen supplies no number. | Immediately on selection |
| Epsilon: initial | Starting probability of choosing a random action. | Numbers from 0.85 to 0.999. | Epsilon: decay |
| Epsilon: decay | Multiplier applied to epsilon after each episode. | Numbers from 0.9 to 0.999. | Epsilon: initial |
| Food Reward: closer | Reward for moving closer to the food. | 0, 0.1, 0.25, 0.5, 1, 2, 3, 4, 5. | Food Reward: further |
| Food Reward: further | Penalty for moving farther from the food. | -5, -4, -3, -2, -1, -0.5, -0.25, -0.1, 0. | Food Reward: closer |
| EpsilonNice: probability | Chance per eligible move of starting a safe detour. | Numbers greater than 0 and at most 0.1 (10%). | EpsilonNice: steps |
| EpsilonNice: steps | Duration of each detour, reset each episode. | Integers from 1 to 40. | EpsilonNice: probability |

The epsilon settings, distance rewards, and EpsilonNice settings are chosen in
pairs. The sum of the two distance rewards must be non-positive. Selecting
`seed` immediately accepts the seed change; there is no separate seed
confirmation conversation or tool call. Ax3l increments the draft seed until
the complete configuration and its golden baseline are unique across every
stored run and status, preserving all other settings. Seed can be selected only
once per experiment. Numeric seed proposals are rejected; schema-fixed settings remain
controlled by Ax3l.

Ax3l loads the same short selection skill at the start of each choice. The
setup and choice prompts include best, golden, latest, and draft values in
JSON for configurable settings, together with reference-run results and saved
observations. The main page keeps saved draft values visible and marks which
settings are editable. Historical results omit repeated configurations and
redundant run roles. Qwen receives at most one chart per choice.

| Choice | Chart | Measured facts alongside it |
| --- | --- | --- |
| Learning rate | Training loss | Episodes with recorded loss |
| Epsilon | Score trend | Mean scores in the first and last 50 episodes and number of random actions |
| Distance rewards | Score distribution | Median score and counts of zero-score and high-score episodes |

Ax3l uses the latest run's charts when it shares the draft seed. Otherwise it
uses the current golden run. The learning rate choice uses data alone when
the run has no recorded loss. Its loss chart overlays a trailing mean of up to
20 episodes on the faint raw trace, with the golden run's loss and mean in
orange when it is a different run with recorded loss. Means exclude missing
losses and preserve their gaps. The source is selected again for each choice;
after a seed change, runs on other seeds are labeled as historical context.
Ax3l records the completed simulation's
measurements directly from episode data.

English definition links open through `kb_tool` and return to the main
configuration page. Saving a setting returns to a freshly rendered main page
with the updated draft values. Definition pages include "Don't show your
reasoning in the prompt." `/guides` remains available for lab reference.
Configuration and run data are already in the screen;
the menus no longer offer separate draft and reference-run reads. Older data
URLs remain readable. Navigation uses English
and experiment values use JSON. Guide and data pages, prompt wording, and tool
descriptions use a dedicated Markdown presentation package. Choice rules appear in the
submission tool description. Accepted choices are saved without starting a
simulation. A selected setting must change its current value, or at least one
value for a pair. Submitting all the same values is rejected before the uniqueness
check. After every submitted change, Ax3l
checks the complete draft for duplicates.

At startup and after a unique change, Qwen can use `select_parameter` to choose
a single or paired setting. `kb_tool` is available while making that
decision. Ax3l opens the selected setting's value conversation with the usual
evidence and tools, or immediately saves the next unused seed when `seed` is
selected; other values stay saved. A duplicate proposal is rejected
without saving it. Qwen stays on the selected setting and must submit different
values until the complete configuration is unique. After a unique change, Qwen can
use `run_simulation` or select an unused setting. Used settings cannot be selected
again and are omitted from the next selection prompt. Unselected settings keep their
baseline values. Qwen can submit the unique draft through an explicit run decision.
Each selection, value choice, and run decision resumes after a restart.

Parameters with finite choices are also omitted when all changed choices already
exist for the draft's current seed and other settings. For example, encoder layers
cannot be selected if both alternatives to the current layer count have already
been stored with those settings. Every run status counts, matching duplicate
protection. The selection tool rejects exhausted settings before saving an
assignment. Availability is recalculated against the current draft after each
accepted change. A restart reopens selection if the pending assignment is exhausted.

Ax3l internally allows seven minutes to select a parameter and find a unique
setting, or decide to run the current unique draft. Prompts and tool feedback
do not mention the timer, remaining time, or expiry actions. Experiment Status
continues to display the countdown. Parameter selection and duplicate-value
retries share the countdown; every accepted unique change resets it to seven
minutes for the next parameter or run decision. Sending a prompt with a chart adds two minutes
to the remaining decision budget and the displayed countdown. That allowance
applies once for the prompt; tool reads and rejected values keep the extended
deadline. Prompts without an image receive no extra time.
Expiry starts a grace period configured by
`decision_grace_seconds` in `/opt/prod/ax3l/conf/ax3l.json`, defaulting to 420
seconds (seven minutes).
Before the first unique change, the end of grace discards the tentative parameter
selection and starts a fresh conversation from the initial prompt with a new
seven-minute budget. Earlier messages, research, reasoning, and rejected proposals
are not carried into the new context. With a saved unique draft, the end of grace
submits that configuration through the normal simulation, comparison, and
measurement cycle, then starts the next experiment.
Any pending edit is excluded unless its changed values were accepted. Restarting
begins a new budget.

Experiment Status shows the settings to be chosen and the saved selections.
The experiment title and LLM countdown share a full-width section header above
the experiment details and table. The countdown occupies the right side of that
header, stacking below the title on small screens. The same header remains visible
in active, inactive, and empty states. The timer ticks every second using the
current decision deadline. At zero it turns amber.
With a saved unique draft, it switches to a **Simulation Start
Countdown** with **Time remaining** below the number. Before the first unique
change, it instead shows a **Conversation Reset Countdown**. Both use the
configured grace period, which defaults to seven minutes.
It resets after an accepted unique change and becomes inactive when the
configuration is submitted. The table scrolls horizontally on its own, keeping
the experiment details and countdown visible; refreshes retain its scroll position.
It lists chart rendering, each Qwen request, each data or guide lookup, and
each submission under the relevant setting or pair. Each step has its own
elapsed time. Any item with task rows has a +/− control before its label,
including Experiment decision. Task rows start collapsed; opening or closing
one group does not affect the others, and refreshes retain each group's state.
Saved prompt messages have their own rows with a Prompt link in
the LLM details column. Completed Qwen requests link to their captured Reasoning
when Qwen returned nonempty reasoning text. Hovering or focusing either link
shows a scrollable preview using the same Markdown and JSON-table parser as
Read results; prompts also include their captured chart images. Clicking these
links opens the original content in a separate tab.
Each returned Qwen request shows its own input and output token
counts when reported by the server. The chart link opens the prompt with
the exact image sent to Qwen. Read targets link to their recorded responses;
hovering or focusing a link shows a scrollable preview, with JSON formatted as
compact tables. The preview shows what Qwen received at that time, including
rejected or failed reads. The page refreshes every five seconds.

## Golden configurations and seed changes

A candidate becomes golden only if its high score strictly exceeds the current
golden score. A tie retains the golden. Each completed configuration comparison
counts as one experiment cycle.

Seed requests save the draft choice; the usual run decision or countdown starts
the simulations. Ax3l first runs the current golden configuration with only the
new seed and accepts its score as the local golden baseline, even if lower.
This seed rotation appears as a purple point on Experiment High Scores. If
seed is the only change, that single run completes the draft. If other settings
changed, a second simulation runs the complete draft on the new seed and must
beat the new baseline to become golden. A tie or loss retains the new baseline.
Seed-only rotations do not count as configuration comparisons.
There is no automatic rotation after nine unsuccessful proposals. Interrupted
rotations resume their recorded baseline without resubmitting. Ax3l also finishes
rotations recorded under the former automatic policy before resuming choices. The
all-time best remains a separate historical reference and can come from an
earlier seed.

## Restart behavior

Drafts, choices, submission intent, comparisons, and measurements are stored in
MariaDB's shared event log. Restarting during selection resumes the saved
parameter or next-step decision. An interrupted submission is reconciled by its full
configuration; an ambiguous send is never retried automatically. A saved
comparison or promotion is completed before another proposal begins.

Failed or cancelled simulations mark their draft failed and stop the loop.
A later startup starts a new draft from the retained golden. Transport and
database failures propagate with their cause.

The experiment-reset script clears the draft snapshots, setup trace, and
saved measurements along with the original experiment data.

[Back](/)

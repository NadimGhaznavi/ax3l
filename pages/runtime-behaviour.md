---
title: Runtime Behaviour
author_profile: true
layout: single
---

# Complete-configuration experiments

Ax3l chooses every tunable setting before running one 500-episode SnakeLab
simulation. Qwen receives the assigned setting, measured data, and a chart
when it can inform that choice.

## Initial startup

With an empty experiment, Ax3l submits the schema defaults once. The baseline
builds on SnakeLab 3.0.4's `transformer-epsilon-nice.json` sample and runs 500
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
the same frozen references and resumes the first unselected parameter. Qwen
chooses the following settings in order:

| Parameter | Purpose | Allowed values | Tuned with |
| --- | --- | --- | --- |
| Hidden Size | Number of neurons in each Transformer hidden layer. | Integers from 32 to 128, in multiples of 8. | Individually |
| Encoder Layers | Number of Transformer encoder layers. | 1, 2, or 3. | Individually |
| Dropout | Dropout probability in the Transformer. | Numbers from 0 to 0.1, in steps of 0.01. | Individually |
| Sequence Length | Number of consecutive frames in each training sequence. | Integers from 4 to 48, in multiples of 4. | Individually |
| Batch Size | Number of sequences sampled for each training update. | Integers from 8 to 64, in multiples of 2. | Individually |
| Learning Rate | Size of gradient updates during training. | Numbers from 0.0005 to 0.005. | Individually |
| Gamma | Discount factor controlling the value of future rewards. | Numbers from 0.9 to 0.99. | Individually |
| Epsilon: initial | Starting probability of choosing a random action. | Numbers from 0.85 to 0.999. | Epsilon: decay |
| Epsilon: decay | Multiplier applied to epsilon after each episode. | Numbers from 0.9 to 0.999. | Epsilon: initial |
| Food Reward: closer | Reward for moving closer to the food. | 0, 0.1, 0.25, 0.5, 1, 2, 3, 4, 5. | Food Reward: further |
| Food Reward: further | Penalty for moving farther from the food. | -5, -4, -3, -2, -1, -0.5, -0.25, -0.1, 0. | Food Reward: closer |
| EpsilonNice: probability | Chance per eligible move of starting a safe detour. | Numbers greater than 0 and at most 0.1 (10%). | EpsilonNice: steps |
| EpsilonNice: steps | Duration of each detour, reset each episode. | Integers from 1 to 40. | EpsilonNice: probability |

The epsilon settings, distance rewards, and EpsilonNice settings are chosen in
pairs. The sum of the two distance rewards must be non-positive. Seeds and
schema-fixed settings remain controlled by Ax3l.

Ax3l loads the same short selection skill at the start of each choice. The
prompt includes current values and same-setting values and scores from the
latest and golden runs. Qwen receives at most one chart per choice.

| Choice | Chart | Measured facts alongside it |
| --- | --- | --- |
| Learning rate | Training loss | Episodes with recorded loss |
| Epsilon | Score trend | Mean scores in the first and last 50 episodes and number of random actions |
| Distance rewards | Score distribution | Median score and counts of zero-score and high-score episodes |

Ax3l uses the latest run's charts when it shares the draft seed. Otherwise it
uses the current golden run. The learning rate choice uses data alone when
the run has no recorded loss. Ax3l records the completed simulation's
measurements directly from episode data.

English directions in the prompt lead to relevant `data_tool` pages when
Qwen needs more detail. The tool menu at `/` links to `draft`, `latest`,
`golden`, and `best`. Navigation uses English and experiment values use
JSON. `kb_tool` serves optional background. Choice rules appear in the
submission tool description. Accepted choices are saved without starting a
simulation. A value can remain unchanged. After all ten choices, Ax3l
checks the complete draft for duplicates and submits one simulation.

If the complete draft is a duplicate, Ax3l saves every choice and asks Qwen
which setting to revise. Qwen can choose any single setting or paired setting
using `select_parameter`. Ax3l then opens that setting's value conversation
with the usual evidence and tools. The other choices stay saved. After the
revision, Ax3l checks the complete configuration again. Each further duplicate
returns to parameter selection; only a unique configuration reaches Snake Lab.
Both the selection step and the reopened value conversation resume after a restart.

Experiment Status shows the settings to be chosen and the saved selections.
It lists chart rendering, each Qwen request, each data or guide lookup, and
each submission under the relevant setting or pair. Each step has its own
elapsed time. Each returned Qwen request shows its own input and output token
counts when reported by the server. The chart link opens the prompt with
the exact image sent to Qwen. The page refreshes every five seconds.

## Golden configurations and seed rotation

A candidate becomes golden only if its high score strictly exceeds the current
golden score. A tie retains the golden. Each completed configuration comparison
counts as one experiment cycle.

After nine complete proposals without an improvement, Ax3l increments the seed
and reruns the golden settings to establish a fresh score baseline. Ax3l
records its measurements before parameter selection resumes. The all-time best remains a
separate historical reference and can come from an earlier seed.

## Restart behavior

Drafts, choices, submission intent, comparisons, and measurements are stored in
MariaDB's shared event log. Restarting during selection resumes the first
unselected parameter. An interrupted submission is reconciled by its full
configuration; an ambiguous send is never retried automatically. A saved
comparison or promotion is completed before another proposal begins.

Failed or cancelled simulations mark their draft failed and stop the loop.
A later startup starts a new draft from the retained golden. Transport and
database failures propagate with their cause.

The experiment-reset script clears the draft snapshots, setup trace, and
saved measurements along with the original experiment data.

[Back](/)

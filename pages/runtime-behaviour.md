---
title: Runtime Behaviour
author_profile: true
layout: single
---

# Complete-configuration experiments

Ax3l chooses every tunable setting before running one 500-episode SnakeLab
simulation. It uses Qwen's visual interpretation of completed runs, combined
with exact numeric diagnostics, to inform each parameter conversation.

## Initial startup

With an empty experiment, Ax3l submits the schema defaults once. The baseline
uses SnakeLab 3.0.1, a four-head Transformer, required EpsilonNice, and 500
episodes. On completion, it becomes the initial golden configuration and
receives its first simulation analysis. Interrupted initial seeding resumes
its recorded submission.

## Choosing a complete configuration

A new draft starts from the current golden configuration. It freezes the latest,
golden, and all-time best reference runs for the entire selection pass. The
draft is saved in a preparation phase while missing reference analyses are
generated, so the Experiment Status report can show prerequisites before the
first choice. A restart resumes preparation using the same frozen references.
Image preparation, LLM analysis, completion, and failures are recorded as tasks
in the shared event log and appear on the report's next five-second refresh. Qwen
chooses the following settings in order:

| Parameter | Purpose | Allowed values | Tuned with |
| --- | --- | --- | --- |
| Hidden Size | Number of neurons in each Transformer hidden layer. | Integers from 64 to 384, in multiples of 16. | Individually |
| Sequence Length | Number of consecutive frames in each training sequence. | Integers from 4 to 48, in multiples of 4. | Individually |
| Batch Size | Number of sequences sampled for each training update. | Integers from 8 to 64, in multiples of 2. | Individually |
| Learning Rate | Size of gradient updates during training. | Numbers from 0.0005 to 0.005. | Individually |
| Gamma | Discount factor controlling the value of future rewards. | Numbers from 0.9 to 0.99. | Individually |
| Epsilon: initial | Starting probability of choosing a random action. | Numbers from 0.85 to 0.999. | Epsilon: decay |
| Epsilon: decay | Multiplier applied to epsilon after each episode. | Numbers from 0.9 to 0.999. | Epsilon: initial |
| Food Reward: closer | Reward for moving closer to the food. | 0, 0.1, 0.25, 0.5, 1, 2, 3, 4, 5, 6. | Food Reward: further |
| Food Reward: further | Penalty for moving farther from the food. | -6, -5, -4, -3, -2, -1, -0.5, -0.25, -0.1, 0. | Food Reward: closer |
| EpsilonNice: probability | Chance per eligible move of starting a safe detour. | Numbers greater than 0 and at most 1. | EpsilonNice: steps |
| EpsilonNice: steps | Duration of each detour, reset each episode. | Integers from 1 to 1000. | EpsilonNice: probability |

The epsilon settings, distance rewards, and EpsilonNice settings are chosen in
pairs. The sum of the two distance rewards must be non-positive. Seeds and
schema-fixed settings remain controlled by Ax3l.

Each conversation receives the project goal, the reference analyses and their
configurations, the current draft, and previous choices. Accepted choices are
saved without starting a simulation. A value can remain unchanged. After all
eight selection steps, Ax3l checks the full draft for duplicates, submits one
simulation, and waits for its result.

## Simulation analysis

For each completed run, Ax3l runs three separate conversations: score trends,
score distribution, and training loss. Each receives one PNG, one chart-specific
question, relevant exact facts, and an invented answer example. Plots include
titles, labeled axes and units, the high-score objective, seed, episode count,
and the first eight characters of the run UUID. Loss is mean Smooth L1 loss in
its native training scale; missing measurements remain gaps.

The score-trends task compares the first 50 episodes with the final 50 episodes
of that same run. Both exact averages are supplied; Qwen states whether the
final average is higher, lower, or equal.

Ax3l calculates score statistics and termination counts/percentages directly
from episode data. Termination categories include wall collisions, body
collisions, move-limit endings, board completion, and unrecorded/other outcomes.
Percentages use all recorded episodes as their denominator.

Qwen calls `submit_simulation_summary` with 1–2 sentences, at most 40 words,
about its assigned chart. Accepted sections are saved, so a restart skips
finished tasks. The final submission combines the three labeled observations
into one run analysis, without another inference call. Observations describe
behavior without assuming that an individual parameter caused it.

General background lives in short local knowledge-base pages. `kb_tool(url)`
reads one page at a time, starting at `/` or the direct guide URL in the prompt.
Qwen follows relevant links to drill down. These reads continue the conversation;
only the assigned submission tool finishes it. Full project background and
configuration are omitted from chart prompts.

Every parameter conversation receives up to three distinct saved analyses:

| Reference | Role |
| --- | --- |
| Latest simulation | Feedback from the most recently completed run, even if it lost. |
| Current golden | Current-seed baseline and score to beat. |
| All-time best | Highest completed simulation score across seeds in this experiment. |

A shared run appears once with multiple role labels. Different runs retain
separate analyses even when their tunable values match. Seeds are explicit;
results on different seeds are historical context rather than controlled
comparisons. The all-time reference uses the earliest stored run to resolve
score ties. Current comparisons are calculated separately from the saved
interpretation, so role changes do not require another vision call.

## Golden configurations and seed rotation

A candidate becomes golden only if its high score strictly exceeds the current
golden score. A tie retains the golden. Each completed configuration comparison
counts as one experiment cycle.

After nine complete proposals without an improvement, Ax3l increments the seed
and reruns the golden settings to establish a fresh score baseline. Its analysis
is generated before parameter selection resumes. The all-time best remains a
separate historical reference and can come from an earlier seed.

## Restart behavior

Drafts, choices, submission intent, comparisons, and analyses are stored in
MariaDB's shared event log. Restarting during selection resumes the first
unselected parameter. An interrupted submission is reconciled by its full
configuration; an ambiguous send is never retried automatically. A saved
comparison or promotion is completed before another proposal begins.

Failed or cancelled simulations mark their draft failed and stop the loop.
A later startup starts a new draft from the retained golden. Transport and
database failures propagate with their cause.

This workflow is intended for a reset experiment; no migration or backward
compatibility path is provided. The experiment-reset script clears its event
snapshots and saved analyses along with the original experiment data.

[Back](/)

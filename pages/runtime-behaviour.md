---
title: Runtime Behaviour
author_profile: true
layout: single
---

Ax3l evaluates experiment results in four focused conversations, then
runs another four conversations to assemble the next SnakeLab configuration.
It submits that configuration, waits for the simulation, compares its high
score with the golden reference, and evaluates the results again.
Every simulation runs for 1,500 episodes, including the initial baseline,
synthetic experiment, and both runs when rotating the seed.
When a new seed is requested, it first runs the golden settings on that seed to
establish the comparison baseline.

## Four views

Both passes cover Reward Signals, Architecture, Training, and Exploration.
Evaluations run in the order below. The following configuration pass shuffles
the views; that order is saved and retained across restarts.

| View | Tunable parameters |
| --- | --- |
| Reward Signals | Food, wall, snake, empty-space, closer-to-food, and farther-from-food rewards, and gamma |
| Architecture | Hidden size, encoder layers, dropout, and sequence length |
| Training | Learning rate, batch size, sequence length, and gamma |
| Exploration | Epsilon initial/decay and EpsilonNice probability/steps |

All four views can request `new seed`. The numeric random seed is read-only.

### Result evaluation

Each evaluation starts with its own role, the hypothesis and parameter choices
used for the completed simulation, and an attached golden/latest comparison
image. The four evaluation templates are skeletons. Their PNG images currently
identify the view and compared runs but contain no measurements. The instructions
ask the model to record this limitation instead of inventing observations.

Qwen submits only Observations through the required native `submit_observations`
function. Observations must contain nonblank text and have at most 280 characters.
No new configuration is requested during evaluation. Each accepted result is
checkpointed, and all four evaluations finish before configuration tuning begins.

### Configuration tuning

Each tuning conversation receives its previous hypothesis, parameter choices,
and the Observations from its separate evaluation conversation.
The editable settings include their current values and schema rules. Other
settings appear as read-only JSON; accepted proposals from earlier views carry
`(draft)` markers. The numeric simulation configuration is stored separately
from these display strings.

Sequence length is shared by Architecture and Training; gamma is shared by
Training and Reward Signals. The shuffled order determines which eligible view
gets the first opportunity to tune each shared parameter. Once a view submits
a value, including an unchanged value, that parameter becomes read-only for
later views and is excluded from their submission tools. If the earlier view
omits it, the next eligible view can still tune it. These restrictions survive
restarts and reset at the start of each configuration cycle.

The shared `new seed` choice starts as `false` each cycle. A view can omit it,
leave it `false`, or submit `"new seed": true` in its parameter values. False
does not prevent a later view from requesting a new seed. Once true, the choice
moves into read-only parameters for every remaining view and cannot be changed,
including after restart.

Qwen returns a new hypothesis and parameter values through the required native
`submit_view` function. The hypothesis must contain nonblank text and have at
most 280 characters, including its expected observable effect. It may change several
settings within the current view. The application validates that response at the
LLM boundary, including the view's available settings, numeric limits, and the combined
closer/farther reward constraint. Invalid responses stop the run with logged
errors; there are no repair prompts or automatic inference retries.

The shuffle, draft assembly, and submission sequence are internal to Ax3l. The
model receives one view at a time, with a fresh context for every conversation.
After all four accepted proposals, Ax3l submits the complete configuration,
running the new-seed baseline first when requested.

## Baseline and results

On a fresh installation, Ax3l runs the default configuration to establish a real
baseline, then runs a file-backed synthetic experiment on the same seed. No LLM
requests occur between these simulations. The synthetic result is compared with
the baseline using the usual high-score rule. Qwen then evaluates that comparison
in all four views and begins the autonomous configuration loop.
Without Ax3l's own saved state or golden reference, both startup runs execute
even if SnakeLab contains older simulations. Those older results are preserved
and do not become the new baseline. An existing Ax3l golden reference is reused.

### Editable first experiment

The startup files live in [`conf/synthetic/`](../conf/synthetic/) in the checkout
and `/opt/prod/ax3l/conf/synthetic/` after installation:

- [`config.json`](../conf/synthetic/config.json) is the complete synthetic SnakeLab
  configuration. The bundled example changes food reward, hidden size, learning
  rate, and epsilon decay. Edit any per-view settings within the simulation schema;
  keep the baseline seed and fixed settings, and change at least one tunable value.
- [`reward-signals.md`](../conf/synthetic/reward-signals.md),
  [`architecture.md`](../conf/synthetic/architecture.md),
  [`training.md`](../conf/synthetic/training.md), and
  [`exploration.md`](../conf/synthetic/exploration.md) each contain that view's
  hypothesis as plain text, up to 280 characters. Update them alongside the
  configuration so they describe the intended changes and expected results.

Install and upgrade copy missing startup files and preserve existing edits.
When upgrading from 750 episodes, update `epochs` in the installed synthetic
configuration to `1500` and start a fresh experiment history so the baseline and
candidate simulations use the same length.
Ax3l validates all five files before submitting the initial baseline. It saves
the resolved per-view choices and hypotheses in the first checkpoint; restarting
resumes those saved inputs even if the files have since changed. File edits apply
to the next fresh experiment history, not a running or completed initialization.
The synthetic origin is recorded in checkpoints and the accepted-configuration
event. Qwen receives the same prompt shape as on later cycles. All scores and
comparison measurements come from real simulations.

Every later cycle starts from the current golden configuration. A strictly higher
high score becomes golden; ties and losses retain the comparison baseline.

If `new seed` is true, Ax3l increments the golden configuration's seed by one
after assembling all proposals. It performs two full SnakeLab simulations in order:

1. Run the current golden settings with only the seed changed. This result becomes
   the new golden baseline even if its high score is lower than the previous seed's.
2. Run Qwen's proposed settings with that same new seed. Promote this configuration
   only if it beats the new baseline; retain the new baseline on a tie or loss.

Both simulations run even when Qwen changes no other settings. No evaluation or
tuning conversations take place between them. `new seed` controls the experiment
and is never sent as a SnakeLab configuration field. Without a new seed request,
the cycle runs just the proposed configuration on the current seed.

The next conversations compare the preceding trial against the golden reference
used for that trial. That reference is retained even when the trial is promoted,
so an improvement does not disappear into an identical golden/latest comparison.
All four views evaluate the same combined simulation result. Each subsequent
tuning prompt receives its own view's Observations. Their context contains only
the preceding experiment and the current draft; accumulated history remains in
MariaDB.

## Persistence and restart

The reporting homepage shows eight collapsible Experiment Status sections: the
four result evaluations followed by the four parameter selections in their saved
order. Each section links to its recorded LLM prompt and response and shows its
hypothesis, observations where applicable, parameter descriptions, baseline and
chosen values, and saved state. Elapsed time and input/output tokens appear in
each section's title bar, including when collapsed. The Totals box sums the
recorded conversation metrics across all eight sections and updates on refresh.
Shared parameter choices identify the view that submitted them.
Evaluation sections show Observations beneath the hypothesis, using the current
status until observations are submitted, followed by Reasoning and Response
(details) links. Their tables compare Configuration Setting, Baseline, and Latest.
Waiting views do not reuse submissions from an older selection pass. Synthetic
startup choices are identified separately and have no fabricated prompt or token
counts. Automatic refresh retains expanded sections and horizontal table scroll.

Ax3l saves experiment snapshots in the shared event log through `DbMgr`. Each
accepted evaluation or proposal is checkpointed before continuing. Restart
resumes the current pass and skips accepted views. Older combined-flow
checkpoints enter evaluation before resuming unfinished tuning, preserving
accepted choices. Prompts, full model responses, native tool results,
submissions, completions, comparisons, and promotions are logged for reporting.

Submission intent is saved before calling SnakeLab. If the reply is lost, restart
looks for a newly recorded matching configuration, excluding a matching run that
already existed before submission. An unresolved submission raises an error and
is never automatically resent. Failed or cancelled simulations stop the loop;
the saved run must be resolved before the cycle can continue. Interrupted
comparison and promotion work is reconciled before beginning another cycle.
The golden baseline and candidate runs use the same submission recovery rules.
Checkpoints retain which of the two is in progress, so a restart does not repeat
the baseline or increment the seed again.

## Running

Load the installation's `DB_*` environment and run:

```sh
.venv/bin/python -m ax3l.server.Ax3lServer
```

The default is continuous operation. For one complete four-view experiment:

```sh
.venv/bin/python -m ax3l.server.Ax3lServer --cycles 1
```

Baseline creation and the synthetic experiment, including its evaluations, do
not count toward `--cycles`. A cycle
finishes after its simulation or pair of simulations and all four result evaluations complete.
`--llm-url http://HOST:PORT`
overrides the configured LlamaSrv URL. `--zmq-endpoint` and `AX3L_ZMQ_ENDPOINT`
select the Ax3l listener. The LlamaSrv model must support native function calling;
MCP sessions and the removed conversation tools are not used. SIGINT closes the
database and listener and exits with status 130.

The reporting server and watchdog retain their existing responsibilities. See
[Architecture](/pages/architecture) and [Project Scripts](/pages/scripts) for
service operations and [test instructions](../README.md#tests) for disposable
end-to-end verification.

---

[Back](/)

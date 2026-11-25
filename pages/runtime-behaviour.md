---
title: Runtime Behaviour
author_profile: true
layout: single
---

Ax3l evaluates each completed simulation in four focused conversations, then
runs another four conversations to assemble the next SnakeLab configuration.
It submits that configuration once, waits for the simulation, compares its high
score with the golden reference, and evaluates the results again.

## Four views

Both passes cover Reward Signals, Architecture, Training, and Exploration.
Evaluations run in the order below. The following configuration pass shuffles
the views; that order is saved and retained across restarts.

| View | Tunable parameters |
| --- | --- |
| Reward Signals | Food, wall, snake, empty-space, closer-to-food, and farther-from-food rewards, and gamma |
| Architecture | Hidden size, encoder layers, dropout, and sequence length |
| Training | Learning rate, batch size, sequence length, gamma, and random seed |
| Exploration | Epsilon initial/decay and EpsilonNice probability/steps |

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

Qwen returns a new hypothesis and parameter values through the required native
`submit_view` function. The hypothesis must contain nonblank text and have at
most 280 characters, including its expected observable effect. It may change several
settings within the current view. The application validates that response at the
LLM boundary, including the view's available settings, numeric limits, and the combined
closer/farther reward constraint. Invalid responses stop the run with logged
errors; there are no repair prompts or automatic inference retries.

The shuffle, draft assembly, and submission sequence are internal to Ax3l. The
model receives one view at a time, with a fresh context for every conversation.
After all four accepted proposals, Ax3l submits the complete configuration.

## Baseline and results

On a fresh installation, Ax3l runs the default configuration to establish a real
baseline. If completed simulations already exist without a golden event, it
adopts the best completed result. An existing golden reference is reused.

The initial hypotheses and per-view choices are seeded examples, paired with the
real baseline run. It receives the same four evaluation conversations before
the first tuning pass. No simulation scores are fabricated. Their seeded
origin is recorded in the experiment checkpoint through `previous_seeded`;
Qwen receives the same prompt shape as on later cycles.

Every later cycle starts from the current golden configuration. A strictly higher
high score becomes golden; ties and losses retain the previous golden. Random
seed remains a normal Training parameter in this initial implementation.

The next conversations compare the preceding trial against the golden reference
used for that trial. That reference is retained even when the trial is promoted,
so an improvement does not disappear into an identical golden/latest comparison.
All four views evaluate the same combined simulation result. Each subsequent
tuning prompt receives its own view's Observations. Their context contains only
the preceding experiment and the current draft; accumulated history remains in
MariaDB.

## Persistence and restart

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

## Running

Load the installation's `DB_*` environment and run:

```sh
.venv/bin/python -m ax3l.server.Ax3lServer
```

The default is continuous operation. For one complete four-view experiment:

```sh
.venv/bin/python -m ax3l.server.Ax3lServer --cycles 1
```

Baseline creation and its evaluations do not count toward `--cycles`. A cycle
finishes after its simulation and all four result evaluations complete.
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

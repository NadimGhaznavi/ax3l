---
title: Runtime Behaviour
author_profile: true
layout: single
---

Ax3l runs four focused view conversations to assemble one complete SnakeLab
configuration. It submits that configuration once, waits for the simulation,
and compares its high score with the golden reference.

## Four views

Each cycle shuffles Reward Signals, Architecture, Training, and Exploration.
The order is saved before the first conversation and is retained across restarts.

| View | Tunable parameters |
| --- | --- |
| Reward Signals | Food, wall, snake, empty-space, closer-to-food, and farther-from-food rewards |
| Architecture | Hidden size, encoder layers, dropout, and sequence length |
| Training | Learning rate, batch size, gamma, and random seed |
| Exploration | Epsilon initial/decay and EpsilonNice probability/steps |

Each conversation starts with its own role and focused golden/latest comparison.
It receives its previous hypothesis, expected effect, and parameter choices.
The editable settings include their current values and schema rules. Other
settings appear as read-only JSON; accepted proposals from earlier views carry
`(draft)` markers. The numeric simulation configuration is stored separately
from these display strings.

Qwen returns an evaluation, a new hypothesis, its expected effect, and parameter
values through the required native `submit_view` tool call. It may change several
settings within the current view. The application validates that response at the
LLM boundary, including setting ownership, numeric limits, and the combined
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
real baseline measurements. No simulation scores are fabricated. Their seeded
origin is recorded in the experiment checkpoint through `previous_seeded`;
Qwen receives the same prompt shape as on later cycles.

Every later cycle starts from the current golden configuration. A strictly higher
high score becomes golden; ties and losses retain the previous golden. Random
seed remains a normal Training parameter in this initial implementation.

The next conversations compare the preceding trial against the golden reference
used for that trial. That reference is retained even when the trial is promoted,
so an improvement does not disappear into an identical golden/latest comparison.
All four views evaluate the same combined simulation result. Their context
contains only the preceding experiment and the current draft; accumulated history
remains in MariaDB.

## Persistence and restart

Ax3l saves experiment snapshots in the shared event log through `DbMgr`. Each
accepted view is checkpointed before continuing. Restart resumes the saved order
and skips accepted views. Prompts, full model responses, native tool results,
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

Baseline creation does not count toward `--cycles`. `--llm-url http://HOST:PORT`
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

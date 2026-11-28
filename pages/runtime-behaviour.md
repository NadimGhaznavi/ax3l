---
title: Runtime Behaviour
author_profile: true
layout: single
---

Ax3l starts with the default baseline and tunes one view at a time. Each view
selects settings, runs a simulation, compares its score with the current golden,
and evaluates the results before the next view starts. Every simulation runs
for 1,500 episodes, including default and rotated-seed baselines.

## Four views

Each round shuffles these four views. The order and current position are saved
and retained across restarts.

| View | Tunable parameters |
| --- | --- |
| Reward Signals | Food, wall, snake, empty-space, closer-to-food, and farther-from-food rewards, and gamma |
| Architecture | Hidden size, encoder layers, dropout, and sequence length |
| Training | Learning rate, batch size, sequence length, and gamma |
| Exploration | Epsilon initial/decay and EpsilonNice probability/steps |

Sequence length is shared by Architecture and Training; gamma is shared by
Training and Reward Signals. Each eligible view can tune these settings on its
own turn because every proposal is simulated separately. There are no pending
choices from other views and no draft locks. The numeric seed is read-only;
seed rotation is controlled by Ax3l.

### Configuration tuning

Every candidate starts from the current golden configuration. If that golden
was produced by the active view, the selection conversation receives the winning
hypothesis, parameter choices, observations, and original golden/latest chart.
The original reference remains available after promotion, so the comparison
continues to show what changed. A later losing attempt does not replace this
winning evidence.

Other views use the [no-history prompts](../ax3l/presentation/prompts/selections-no-history/)
and receive only the current golden's recorded results as their baseline.
The initial default baseline and each rotated-seed baseline have no producing
view, so all views initially use no-history prompts. A promotion replaces the
previous owner's evidence with the new owner's evidence, including on a tie.

Both prompt types contain the active view's editable settings with current
values and schema rules, plus the other settings as read-only JSON. Each request
has a fresh conversation. Qwen submits a nonblank hypothesis of at most 280
characters and parameter values through the required native `submit_view`
function. It may change several settings within the active view.

Ax3l checks response format and view scope. SnakeLab owns simulation-configuration
validation against its JSON schema. Ax3l does not add cross-field reward rules.
If a hypothesis or observation exceeds its character limit, Ax3l returns a tool
result explaining the actual length and limit, and asks Qwen to shorten and
resubmit it in the same conversation. Other malformed submissions remain errors.

Before submission, Ax3l checks for an existing run with all the same settings,
including the seed. Duplicate candidates return to the same active view with the
[shared duplicate notice](../ax3l/presentation/prompts/common/duplicate-configuration.md),
rejected hypothesis, and rejected values. Other settings remain read-only.
Each revised configuration is checked again. Revisions do not count as simulations
or increment the loss counter. Default and rotated-seed baselines still run even
when matching configurations already exist.

### Result evaluation

After each candidate run, the system applies the golden rule and runs the active
view's evaluation. It receives that candidate's hypothesis, chosen settings,
reference and candidate high scores, and a per-view image of recorded results.
No other view evaluates that simulation. Qwen submits nonblank Observations of
at most 280 characters through `submit_observations`.

All eight selection prompts and all four evaluation prompts ask Qwen to aim for
five minutes and use the argument-free `timer` tool to check its progress. Each
conversation starts its own countdown when its first prompt is sent, using
`DViewConversation.TIMER_SECONDS` (300 seconds). It returns `MM:SS`, reaches
`00:00`, and continues as negative time such as `-00:01`. Expiry is advisory:
Qwen can keep checking the timer and submit its proposal or observations afterward.
Timer calls and submission corrections keep the original countdown; each fresh
conversation, including after a timeout or restart, starts a new one.

Inference responses stream into a durable **Captured output** event in the
EventLog. Reasoning, assistant text, and tool-call fragments are saved as they
arrive, with updates every five seconds and a final flush when the request
completes or fails. The capture records the last received chunk's time and
whether the response completed or was interrupted. A hard process termination
retains the last committed snapshot, possibly missing the latest five seconds.
Only a fully received response can proceed to submission validation and tool
execution. See the [event reference](events.md) for capture fields and links.

Inference connection and response-read timeouts, including HTTP 408 and 504,
leave the server running in the pending selection or evaluation phase. Ax3l logs
the failure, discards the timed-out conversation's assistant replies and tool
feedback from the retry's context, and waits thirty seconds. Captured output and
earlier conversation events remain available for diagnosis. It then rebuilds the
stage's original prompt and sends a new HTTP request containing only that user
message, including the original text and image. This also applies to timeouts
during length correction.
It does not resubmit the simulation, repeat its comparison, or advance the view
until that stage succeeds.

Score percentiles and aggregated rates use consecutive 150-epoch windows,
retaining a shorter final window. Epsilon uses every recorded epoch:

- Architecture: 90th and 25th score percentiles on shared axes.
- Exploration: recorded epsilon values on a separate 0–1 panel, including early
  decay and the zero tail, and the two score percentile panels. EpsilonNice
  overrides are omitted from the image.
- Reward Signals: food collected per 100 moves, terminal wall/snake collisions as
  percentages of episodes on 0–100% axes, plus the score percentiles.
- Training: score percentiles and mean recorded training loss, preserving gaps
  where losses were not measured.

Comparison images show the original reference in orange and the candidate in
blue. No-history images show only the current golden baseline in orange. Missing
measurements remain unavailable rather than appearing as zero. These are
individual training runs, not independent validation.

## Baseline, golden configurations, and seed rotation

Fresh initialization runs the default configuration before making an LLM request.
There is no synthetic experiment. Without Ax3l's own checkpoint or golden
reference, it establishes this baseline even if SnakeLab contains older results;
those older results are preserved. An existing Ax3l golden reference is reused.

A candidate with a high score **equal to or higher than** the golden becomes the
new golden. Its producing view becomes the sole owner of comparison history,
and the consecutive-loss counter resets to zero. A strictly lower score retains
the golden and increments the counter once. Failed, cancelled, or unresolved
runs stop progress and do not count as completed losses.

After **16 consecutive strictly lower candidate scores**, the system increments
the seed by one and runs the current golden settings with only that seed changed.
This result becomes the new golden baseline even if its score is lower than the
previous seed's score. It resets the counter and clears comparison history for
all views. The pending view then selects from this new baseline; rotation does
not consume or skip its turn. Baseline runs require no LLM conversation and do
not count as candidate experiments.

## Persistence and reporting

`ExperimentState` stores the shuffled order, active position, candidate settings,
run IDs, consecutive-loss count, and the current golden's `ViewHistory`.
`ExperimentDb` saves these checkpoints through the shared `DbMgr` and event log.
Accepted proposals and evaluations are saved before continuing. Restart resumes
the pending stage without repeating accepted work or reshuffling the round.
These checkpoints target a fresh installation and experiment history.

Submission intent is saved before calling SnakeLab. If the acknowledgement is
lost, restart looks for a newly recorded matching configuration, excluding a
matching run that existed before submission. An unresolved submission raises an
error and is never automatically resent. Failed or cancelled runs must be
resolved before continuing. Comparison decisions store the resulting loss count,
so replay after interruption neither increments it twice nor duplicates a
committed promotion. Rotated baselines use the same recovery rules.

The reporting homepage shows the active view, current phase, seed, and consecutive
losses out of sixteen. It has at most two collapsible conversation sections:
Selection first, then Evaluation, both for that view. A simulation status block
between them links to the baseline and candidate runs, shows their completed high
scores, and identifies promotion, tie promotion, or retention of the golden.
Default and rotated-seed baselines show simulation status without conversation
sections. Duplicate revisions reuse the Selection section. Other views and older
experiments do not contribute conversation sections or saved choices.

Each section links to its recorded prompt and response, shows its hypothesis,
observations where applicable, baseline and chosen values, and elapsed time and
token usage in the title bar. The Totals box sums recorded conversation metrics.
Automatic refresh retains expanded sections and horizontal table scroll within
the same experiment, and uses the new experiment's initial panel state when the
active experiment changes. Tie promotions appear once in golden score history,
and per-simulation LLM costs
include both its selection and evaluation.

## Running

Load the installation's `DB_*` environment and run:

```sh
.venv/bin/python -m ax3l.server.Ax3lServer
```

The default is continuous operation. For one completed single-view experiment:

```sh
.venv/bin/python -m ax3l.server.Ax3lServer --cycles 1
```

A cycle completes after one candidate's simulation, comparison, and evaluation.
Use `--cycles 4` for four view turns. Initial and rotated-seed baselines do not
count toward this limit. `--llm-url http://HOST:PORT` overrides the configured
LlamaSrv URL. `--zmq-endpoint` and `AX3L_ZMQ_ENDPOINT` select the Ax3l listener.
The LlamaSrv model must support native function calling. SIGINT closes the
database and listener and exits with status 130.

See [Architecture](/pages/architecture), [Project Scripts](/pages/scripts), and
[test instructions](../README.md#tests) for service operations and disposable
end-to-end verification.

---

[Back](/)

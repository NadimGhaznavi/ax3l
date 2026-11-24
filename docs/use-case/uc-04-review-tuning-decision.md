# UC-04: Review a tuning decision

[Use Case View](index.md)

**Goal:** Understand what the language model proposed and how Ax3l handled it.

**Primary actor:** Researcher.

**Trigger:** The researcher investigates a tuning conversation or a golden
configuration change in the recorded experiment history.

**Preconditions:** Ax3l's reporting service is available and relevant experiment
events have been recorded.

## Main flow

1. The researcher locates the relevant conversation and configuration events.
2. The researcher opens the recorded prompt to inspect the settings, hypothesis,
   and observations supplied to the language model.
3. The researcher opens the response to inspect the proposed hypothesis and
   parameter values.
4. The researcher examines the recorded acceptance or failure and, for a completed
   trial, its comparison and any golden promotion.
5. When investigating a golden change, the researcher opens the associated
   configuration and simulation for further evidence.

## Alternatives and failures

- **Evaluation conversation:** The response contains observations rather than a
  new configuration proposal.
- **Rejected proposal or failed request:** The recorded failure is the outcome;
  the researcher may have no accepted configuration or simulation to inspect.
- **No separate reasoning text:** The researcher uses the recorded hypothesis,
  choices, and outcome; a separate Reason link may be absent.
- **Older history:** Records may use an earlier conversation format or omit
  information introduced later.
- **Missing record or load failure:** Ax3l reports that the requested detail is
  unavailable or could not be loaded.

## Outcome

The researcher can distinguish model proposals and observations from measured
simulation results and Ax3l's acceptance and comparison decisions. Reviewing
the record does not change those decisions.

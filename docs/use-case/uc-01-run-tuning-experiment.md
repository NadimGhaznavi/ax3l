# UC-01: Run a tuning experiment

[Use Case View](index.md)

**Goal:** Explore whether proposed settings improve the Snake AI's high score.

**Primary actor:** Experiment operator.

**Supporting actors:** SnakeLab and LlamaSrv.

**Trigger:** The operator starts or resumes Ax3l, selecting continuous operation
or a bounded number of experiment cycles.

**Preconditions:** Ax3l is configured, its persistent experiment records are
accessible, and the supporting applications are available.

## Main flow

1. Ax3l establishes a golden reference from an existing result or a new baseline
   simulation, and obtains initial observations when needed.
2. Ax3l asks the language model for a hypothesis and proposed settings from each
   of the four tuning perspectives.
3. Ax3l accepts valid proposals and assembles a complete simulation configuration.
4. SnakeLab runs the submitted configuration and supplies the completed result.
5. Ax3l compares the trial's high score with the golden reference. A strictly
   higher score becomes the new golden reference; ties and losses retain it.
6. Ax3l asks the language model to record observations from each tuning
   perspective, retaining the reference used for the trial's comparison.
7. Ax3l records the completed cycle and continues until the requested number of
   cycles is complete or the operator stops it.

## Alternatives and failures

- **Interrupted experiment:** On restart, Ax3l resumes saved progress and skips
  previously accepted proposals and observations.
- **Invalid model response:** Ax3l records the error and stops the run. It does
  not request a repair or retry inference automatically.
- **Uncertain submission:** Ax3l attempts to identify the submitted simulation
  when it resumes. If it cannot resolve the submission, it stops without
  automatically submitting another simulation.
- **Simulation failure or cancellation:** Ax3l records the outcome and stops the
  run without treating it as a completed comparison.

## Outcome

A successful cycle has recorded proposals, a simulation result, a comparison
decision, and observations. It may retain the existing golden reference.

## Current limitation

The evaluation comparison images identify the compared runs but contain no
measurements yet. Evaluation instructions require the model to acknowledge that
limitation rather than invent observations about measured differences.

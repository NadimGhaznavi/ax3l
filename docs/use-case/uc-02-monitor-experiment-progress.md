# UC-02: Monitor experiment progress

[Use Case View](index.md)

**Goal:** Understand the experiment's recent activity and overall progress.

**Primary actor:** Researcher.

**Supporting actor:** SnakeLab.

**Trigger:** The researcher opens the experiment overview.

**Preconditions:** Ax3l's reporting service is available.

## Main flow

1. Ax3l presents the current SnakeLab status, experiment totals, and high scores.
2. Ax3l presents recent experiment events, newest first.
3. The researcher filters the displayed events by category or event type.
4. The researcher refreshes the overview manually or selects periodic refresh.
5. The researcher opens a linked report or event when further investigation is
   needed.

## Alternatives and failures

- **No recorded activity:** Ax3l displays an empty event list; unavailable values
  are shown as unknown.
- **Summary refresh delayed or failed:** The overview can show the last
  successfully collected totals. Before a successful refresh, totals are unknown.
- **SnakeLab status unavailable:** Ax3l reports that the service is unavailable.
- **Overview cannot be loaded:** Ax3l returns an error; cached totals do not
  guarantee that the complete overview remains available.

## Outcome

The researcher can identify recent activity and select an area to investigate.
Viewing the overview does not change experiment settings or results.

## Related use cases

- [UC-03: Inspect a simulation](uc-03-inspect-simulation.md).
- [UC-04: Review a tuning decision](uc-04-review-tuning-decision.md).

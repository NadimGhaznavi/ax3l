# UC-03: Inspect a simulation

[Use Case View](index.md)

**Goal:** Understand the settings and outcome of a particular simulation.

**Primary actor:** Researcher.

**Supporting actor:** SnakeLab.

**Trigger:** The researcher selects a simulation from the experiment's events or
golden configuration history.

**Preconditions:** Ax3l's reporting service is available and the researcher has
identified a recorded simulation.

## Main flow

1. Ax3l presents the selected simulation's identity, high score, and completion
   information.
2. Ax3l presents recorded training, exploration, reward, and game-ending metrics.
3. Ax3l shows the captured high-score game when available.
4. The researcher opens the corresponding configuration entry to inspect the
   complete settings used for that run.

## Alternatives and failures

- **Animation pending or unavailable:** Ax3l shows a saved board snapshot when
  available. A generated animation appears on a later refresh.
- **No captured game:** Ax3l indicates that no saved board is available.
- **Missing metric:** Ax3l shows the value as unavailable.
- **Unknown simulation:** Ax3l reports that the simulation was not found.
- **Result cannot be loaded:** Ax3l returns an error.

## Outcome

The researcher can relate the simulation's settings to its recorded outcome.
Inspection does not change the simulation or its configuration.

## Task: Exploration Tuning

- Role: You are a data scientist tuning exploration settings in Patrick Loeber's Snake Lab.
- Task: Your objective is to improve the Snake AI's high score by tuning exploration settings.

## Experiment Description

- The Snake Lab server accepts a simulation configuration, executes it, and saves the results.
- The evaluation of the results and the selection of new parameters has been split into architecture, exploration, reward-signals, and training.
- Other teams will evaluate the results and select new parameters for architecture, reward-signals, and training.

## Improving the Snake AI's high score

- Use the simulation data from the baseline configuration run.
  - Create a new hypothesis about how to improve the Snake AI's high score.
  - Propose new parameter values to test your hypothesis in the next simulation.

## Baseline Results

The baseline is the current golden configuration.

- Baseline simulation: {{ reference_run_id }} (high score: {{ reference_high_score }})

The attached image shows the baseline run in orange, using consecutive
150-epoch windows on shared epoch axes. The final window may be shorter:

- Exploration: the solid line samples the recorded epsilon probability at each
  checkpoint, through the first zero checkpoint. The dashed line shows the
  fraction of moves overridden by EpsilonNice in windows containing post-epsilon
  episodes: total EpsilonNice overrides divided by total moves in that window.
  This is an observed move rate, not the configured probability of starting a
  detour. A window with no moves has no rate and is left as a gap.
- The 90th and 25th score percentiles summarize the scores in each window on
  shared score axes. Curves end at the baseline run's last recorded epoch.

Use exploration timing, observed overrides, the high score, and score progress
to inform your next hypothesis. These are training results from a single run,
not independent validation. Report missing measurements shown in the chart
instead of inventing results.

## Parameters to tune

```json
{{ parameters | tojson(indent=2) }}
```

## Other parameters (read-only)

Here are the other parameters that are going to be used in the next simulation. You cannot change these parameters.

```json
{{ other_parameters | tojson(indent=2) }}
```

## Submit your new hypothesis and parameter values

Use the provided `submit_view` function with the fields `hypothesis` and `values` to submit your new hypothesis and parameter values for the next simulation.

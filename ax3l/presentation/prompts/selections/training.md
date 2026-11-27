## Task: Training Tuning

- Role: You are a data scientist tuning training settings in Patrick Loeber's Snake Lab.
- Task: Your objective is to improve the Snake AI's high score by tuning training settings.

## Experiment Description

- The Snake Lab server accepts a simulation configuration, executes it, and saves the results.
- The evaluation of the results and the selection of new parameters has been split into architecture, exploration, reward-signals, and training.
- Other teams will evaluate the results and select new parameters for architecture, exploration, and reward-signals.

## Improving the Snake AI's high score

- Use the results of the previous simulation to:
  - Create a new hypothesis about how to improve the Snake AI's high score.
  - Propose new parameter values to test your hypothesis in the next simulation.

## Previous Simulation Results

### Previous hypothesis:

{{ previous_hypothesis }}

### Previous choices

```json
{{ previous_values | tojson(indent=2) }}
```

### Previous observations

{{ previous_observations }}

## Results Comparison

- Golden reference: {{ reference_run_id }} (high score: {{ reference_high_score }})
- Latest simulation: {{ latest_run_id }} (high score: {{ latest_high_score }})

The attached image compares Golden (orange) and Latest (blue) in consecutive
150-epoch windows. The final window may be shorter:

- Score percentiles: solid lines show the 90th percentile; dashed lines show the
  25th percentile. Both runs share the same score axis.
- Training loss: each point is the arithmetic mean of the recorded episode
  losses in that window. Missing loss values are excluded, and a window with
  no recorded loss is left as a gap. A measured zero loss is included. Both
  runs share a loss axis that scales to their recorded values.

Judge the hypothesis using high scores, score progress, lower-tail performance,
and loss trends together. Lower training loss alone does not establish better
game performance. These are training results from individual runs, not independent
validation. Curves stop at each run's final recorded epoch. If both run IDs match,
this is a baseline self-comparison, not evidence of improvement. Treat missing
measurements as unavailable rather than zero.

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

Use the provided submission tool to submit your new hypothesis and parameter values for the next simulation.

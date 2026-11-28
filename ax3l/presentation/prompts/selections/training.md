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

The attached image compares Golden (orange) and Latest (blue).

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

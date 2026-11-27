## Task: Training Tuning

- Role: You are a data scientist tuning training settings in Patrick Loeber's Snake Lab.
- Task: Your objective is to improve the Snake AI's high score by tuning training settings.

## Experiment Description

- The Snake Lab server accepts a simulation configuration, executes it, and saves the results.
- The evaluation of the results and the selection of new parameters has been split into architecture, exploration, reward-signals, and training.
- Other teams will evaluate the results and select new parameters for architecture, exploration, and reward-signals.

## Improving the Snake AI's high score

- Use the simulation data from the baseline configuration run.
  - Create a new hypothesis about how to improve the Snake AI's high score.
  - Propose new parameter values to test your hypothesis in the next simulation.

## Baseline Results

The baseline is the current golden configuration.

- Baseline simulation: {{ reference_run_id }} (high score: {{ reference_high_score }})

The attached image shows the baseline run in orange, using consecutive
150-epoch windows. The final window may be shorter:

- Score percentiles: the solid line shows the 90th percentile; the dashed line
  shows the 25th percentile on the same score axis.
- Training loss: each point is the arithmetic mean of the recorded episode
  losses in that window. Missing loss values are excluded, and a window with
  no recorded loss is left as a gap. A measured zero loss is included. The
  loss axis scales to the recorded values.

Use the high score, score progress, lower-tail performance, and loss trends
together to inform your next hypothesis. Lower training loss alone does not
establish better game performance. These are training results from a single run,
not independent validation. Curves stop at the baseline run's final recorded
epoch. Treat missing measurements as unavailable rather than zero.

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

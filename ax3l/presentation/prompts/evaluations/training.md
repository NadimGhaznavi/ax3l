## Task: Training Evaluation

- Role: You are a data scientist evaluating training settings in Patrick Loeber's Snake Lab.
- Task: Evaluate the completed simulation against its hypothesis and submit Observations.

## Experiment Description

- The Snake Lab server has completed the simulation and saved the results.
- Evaluate the results shown in the comparison image against the hypothesis below.
- Your observations will inform the next hypothesis and parameter choices.

## Previous Simulation

### Hypothesis

{{ previous_hypothesis }}

### Parameter choices

```json
{{ previous_values | tojson(indent=2) }}
```

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

## Submit Observations

- Give a short conclusion about whether the results support the hypothesis.
- Keep Observations within {{ observations_max_length }} characters.
- Use the provided `submit_observations` function with the field `observations`.

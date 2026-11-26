## Task: Reward Signals Evaluation

- Role: You are a data scientist evaluating reward signals in Patrick Loeber's Snake Lab.
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
150-epoch windows. The final window may be shorter. Each rate is total events
divided by total moves in that window, multiplied by 100:

- Food collected uses recorded episode scores as the number of food pickups.
- Wall and snake collisions count episodes ending with the corresponding terminal
  outcome. They are collision events per 100 moves, not percentages of episodes.
  Windows with missing outcomes or no moves show gaps.
- Score percentiles share the last panel: solid lines show the 90th percentile;
  dashed lines show the 25th percentile. These are scores, not move rates.

Judge the hypothesis using food collection, collision rates, high scores, and
score progress. These are training results from individual runs, not independent
validation. Curves stop at each run's final recorded epoch. If both run IDs match,
this is a baseline self-comparison, not evidence of improvement. Treat missing
measurements as unavailable rather than zero.

## Submit Observations

- Give a short conclusion about whether the results support the hypothesis.
- Keep Observations within {{ observations_max_length }} characters.
- Use the provided `submit_observations` function with the field `observations`.

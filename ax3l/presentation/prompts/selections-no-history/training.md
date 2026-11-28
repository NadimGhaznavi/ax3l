## Task: Training Tuning

- Role: You are a data scientist tuning training settings in Patrick Loeber's Snake Lab.
- Task: Your objective is to improve the Snake AI's high score by tuning training settings.

This process shouldn't take more than 5 minutes. Once you decide on a hypothesis, don't second guess yourself. This is an iterative process, and the goal is to improve the Snake AI's
high score, not to find the perfect training settings.

Use the 'timer' tool to check how long you have been working on this task. The timer is there to help you manage your time. When it hits zero, it will just continue counting.

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

- Baseline high score: {{ reference_high_score }}

The attached image shows the baseline run in orange.

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

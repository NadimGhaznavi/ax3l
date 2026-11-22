# Exploration implementation

```json
{
  "epsilon": {
    "initial": "initial random-action probability",
    "decay": "per-episode probability multiplier",
    "zero_threshold": 0.001,
    "value_below_threshold": 0
  },
  "epsilon_nice": {
    "label": "safe detours",
    "eligible_when": "ordinary epsilon is zero and no detour is active",
    "probability": "chance per eligible move of starting a detour on the next move",
    "steps": "detour duration in moves",
    "action": "an immediately safe alternative to the model's pick, if available",
    "reset_each_episode": true
  },
  "activity_metrics": {
    "epsilon_random_actions": "recorded ordinary epsilon injections",
    "nice_overrides": "recorded EpsilonNice injections"
  }
}
```

- [Experiment rules](/guides/selection)
- [Lab reference](/guides)

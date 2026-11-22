# Reward implementation

```json
{
  "distance_shaping": {
    "metric": "Manhattan progress toward food",
    "paired_settings": ["closer_to_food", "further_from_food"],
    "constraint": "closer_to_food + further_from_food <= 0"
  },
  "independent_settings": ["food", "empty", "snake", "wall"],
  "fixed_rewards": {"max_moves": -10}
}
```

Current rewards are on the configuration pages. Submission tools provide allowed values.

- [Experiment rules](/guides/selection)
- [Lab reference](/guides)

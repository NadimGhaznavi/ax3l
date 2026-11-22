# Model implementation

The model's 24-value feature vector and training units:

```json
{
  "architecture": "Transformer",
  "heads": 4,
  "actions": ["left", "straight", "right"],
  "action_frame": "relative to current heading",
  "features": [
    {"indices": [0, 1, 2], "meaning": "body danger: left, straight, right"},
    {"indices": [3, 4, 5], "meaning": "wall danger: left, straight, right"},
    {"indices": [6, 7, 8, 9], "meaning": "heading: left, right, up, down"},
    {"indices": [10, 11, 12, 13], "meaning": "food direction: left, right, up, down"},
    {"indices": [14, 15], "meaning": "food alignment: X, Y"},
    {"indices": [16, 17, 18, 19, 20, 21, 22], "meaning": "snake length: big-endian bits, saturated at 127"},
    {"indices": [23], "meaning": "remaining move-budget fraction"}
  ],
  "full_board_input": false,
  "food_distance_input": false,
  "sequence_length_unit": "consecutive frames",
  "batch_size_unit": "sampled sequences",
  "move_limit": "max_moves_multiplier * current_snake_length"
}
```

Current values are on the configuration pages. Submission tools provide allowed values.

- [Experiment rules](/guides/selection)
- [Lab reference](/guides)

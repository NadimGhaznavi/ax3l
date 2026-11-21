# Model and input features

Ax3l uses Snake Lab to train a Transformer with four attention heads for 1500
episodes. The LLM chooses hidden width from 32 to 128 in steps of 8, encoder
depth from 1 to 3 layers, and dropout from 0 to 0.1 in steps of 0.01. The
defaults are width 64, one encoder layer, and dropout 0.05. The target update
rate (`tau`) is fixed at 0.05.
Actions are left, straight, and right relative to the current heading.

Its 24-value feature vector contains:

- 0–2: body danger left, straight, right.
- 3–5: wall danger left, straight, right.
- 6–9: heading left, right, up, down.
- 10–13: food direction left, right, up, down.
- 14–15: food alignment on X and Y.
- 16–22: seven big-endian length bits, saturating at 127.
- 23: remaining move-budget fraction.

There is no full-board view or food-distance measurement. Sequence length
controls how many consecutive frames training uses. Hidden size controls
Transformer width; batch size counts sampled sequences. Learning rate controls
update size, and gamma discounts future rewards. Choice rules are in your
submission tool.

The move limit is max_moves_multiplier times the current snake length.

- [Choosing one setting](/selection)
- [Reference index](/)

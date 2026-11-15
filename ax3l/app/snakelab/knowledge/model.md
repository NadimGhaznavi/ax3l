# Model and input features

Snake Lab 3.0.1 trains a Transformer with four attention heads for 500 episodes.
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
update size, and gamma discounts future rewards. Valid domains are supplied
in each selection task.

- [Choosing one setting](/selection)
- [Reference index](/)

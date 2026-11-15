# Training loss

Describe whether recorded mean Smooth L1 loss rises, falls, or stabilizes, and
whether spikes or gaps appear. A gap means loss was unrecorded, not zero. If
none was recorded, say so; do not invent a trend.

Lower loss alone does not demonstrate better game scores. Reward changes can
change loss scale, so do not compare loss values across runs.

Use 1–2 sentences and at most 40 words. You may suggest one concrete value to
try next after reading current settings through data_tool /run and allowed
values through /run/rules. No theory or causal explanations.

Example with invented data: Recorded loss spiked late; try
training.learning_rate=0.001 next.

- [Chart guides](/analysis/)

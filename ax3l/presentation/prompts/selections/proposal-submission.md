## Submission rules

- Keep your hypothesis within {{ hypothesis_max_length }} characters, including its expected observable effect.
- If other parameters have been tuned by other teams already (they are not drafts), then you may also decide not to tune any parameters.
- You do not have to tune all parameters.
- Use the provided `submit_view` function with the fields `hypothesis` and `values`; its schema defines the submission format.
- Propose values only for the parameters listed under Parameters to tune. You may change several of these parameters together.
- The shared `new seed` choice starts as `false`. Omit it or leave it `false` to keep the current random seed, or pass `"new seed": true` in `values` to request a new one. Once requested, it is read-only for the remaining teams. The numeric seed is read-only; Ax3l increments it by one.
- With a new seed, the current golden settings run first to establish a baseline, followed by your proposed settings on that same seed. The proposed settings are compared against this new baseline.

### Example

For example, if  `training.learning_rate` is listed under the Parameters to tune, you could call `submit_view` with arguments such as:

```json
{
  "hypothesis": "A lower learning rate should stabilize training and improve the high score.",
  "values": {
    "training.learning_rate": 0.0005
  }
}
```

Use the parameters from your own view and provide your own short hypothesis. The example above is only an example.

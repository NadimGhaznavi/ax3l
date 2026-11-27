## Submission rules

- Keep your hypothesis within {{ hypothesis_max_length }} characters, including its expected observable effect.
- You do not have to tune all parameters.
- Use the provided `submit_view` function with the fields `hypothesis` and `values`; its schema defines the submission format.
- Propose values only for the parameters listed under Parameters to tune. You may change several of these parameters together.

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

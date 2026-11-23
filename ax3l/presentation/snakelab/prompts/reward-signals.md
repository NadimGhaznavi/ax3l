You are the data scientist tuning reward signals in Patrick Loeber's Snake Lab.
Your objective is to improve the Snake AI's high score.

Investigate how the reward signals affect Snake's behaviour. Examine the golden
and latest results, paying attention to scoring and how games end.

## Previous hypothesis

{{ previous_hypothesis }}

## Previous choices

```json
{{ previous_values | tojson(indent=2) }}
```

## Golden and latest results

```json
{{ comparison | tojson(indent=2) }}
```

## Parameters to tune

```json
{{ parameters | tojson(indent=2) }}
```

## Other parameters (read-only)

```json
{{ other_parameters | tojson(indent=2) }}
```

Evaluate the previous hypothesis against the results. Then propose your next
hypothesis and the parameter values to test it. State the observable effect you
expect. Propose values only for the parameters listed under Parameters to tune.
You may change several of these parameters together.

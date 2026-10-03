# How to Implement "Full Control" Safely

To make this work, you must treat the LLM not as a random searcher, but as a Hypothesis-Driven Researcher. You need to constrain the search space and force it to justify its choices.

## The "Challenger" Protocol (Instead of Pure Replacement)

Do not throw away the "Golden Configuration" entirely. Instead, use a Challenger System:

1. The LLM is presented with the current Golden Configuration and its score.
2. It is also presented with the Top 3 Historical Configurations and their scores.
3. The LLM is asked to generate one complete, new configuration (the "Challenger") that modifies multiple parameters at once.
4. If the Challenger beats the Golden score, it becomes the new Golden. If it fails, the Golden remains, but the LLM learns from the failure in the next prompt.

## Prompt Engineering for Qwen 3.5 4B

You must force the LLM to output a reasoning field. Qwen 3.5 4B is highly capable of this. Your prompt to the LLM should look like this:
```
"You are an expert Reinforcement Learning engineer. Your goal is to maximize the Snake game high score while respecting a strict compute budget (max 3000 epochs).
Current Golden Configuration Score: 145
Historical Top 3: [List configs and scores]
Propose a COMPLETE new configuration. You may change any parameter, but you MUST provide a 'reasoning' string explaining the RL theory behind your joint choices.
Example reasoning: 'I increased hidden_size to 256 and layers to 2 to capture longer-term dependencies. To prevent gradient explosion from this larger network, I lowered learning_rate to 0.0015 and increased max_gradient_norm to 1.5. I also increased epochs to 2000 to ensure the larger model has time to converge.'
Output valid JSON matching the schema."
```

## Introduce "Efficiency" as a Metric

To prevent the LLM from just maxing out epochs, feed it a secondary metric: Score per 1000 Epochs (or Score per Minute).

- Config A: Score 160 in 3000 epochs = 53.3 per 1000 epochs.
- Config B: Score 145 in 1500 epochs = 96.6 per 1000 epochs.

If you tell the LLM, *"Config B is preferred because it is more compute-efficient,"* it will learn to find elegant, fast-converging solutions rather than brute-forcing with high epochs.

## Summary of the Shift

Aspect | Current (Round Robin) | Proposed (Joint Hypothesis)
--- | --- | ---
Search Strategy | Coordinate Descent (1-2 params) | Joint Hypothesis (All params)
LLM Role | Local optimizer | Holistic RL Researcher
Interactions | Misses coupled effects (e.g., LR + Batch) | Explicitly reasons about couplings
Risk | Slow convergence, local optima | Wasted runs if hypothesis is wild
Mitigation | N/A | Require reasoning field, cap epochs, use Challenger protocol

---

## Golden Configuration 

Multi-Run Validation: Currently, a new golden configuration is accepted after one simulation. Adding a minimum validation (e.g., multiple runs on the same seed) could reduce false positives.

---

Based on the Ax3l architecture and the goal of tuning hyperparameters using Qwen 3.5 4B's vision capabilities, here are the most impactful visualizations for the LLM to make informed tuning decisions:

### 1. **Training Progress Curve**
   - **What it shows**: Score over time during a training run
   - **Why it helps**: The LLM can see if training is converging, plateauing, or diverging. A sudden drop or plateau might indicate a learning rate issue or overfitting.
   - **Key insight**: Helps decide if the learning rate, hidden size, or gamma needs adjustment.

### 2. **Episode Survival Duration**
   - **What it shows**: Average number of frames the AI survives across episodes
   - **Why it helps**: Directly reflects training quality. If survival is low, the AI isn't learning efficiently.
   - **Key insight**: Indicates whether the neural network architecture or epsilon decay needs tuning.

### 3. **Parameter Performance Heatmap**
   - **What it shows**: How each parameter value affects final score across different seeds
   - **Why it helps**: The LLM can visually identify which parameter ranges perform best across seeds.
   - **Key insight**: Helps prioritize which parameters to tune and in what direction.

### 4. **Golden Configuration Comparison**
   - **What it shows**: Side-by-side of the current golden config vs. the new config being tested
   - **Why it helps**: The LLM can see if the new configuration is genuinely better or just noisy.
   - **Key insight**: Reduces false positives from lucky seeds or transient improvements.

### 5. **Score Distribution**
   - **What it shows**: Histogram of scores across all runs on the current seed
   - **Why it helps**: Shows the variability in performance. A narrow distribution suggests stable training.
   - **Key insight**: Helps identify if the LLM should be more conservative or aggressive with parameter changes.

### 6. **Failure Mode Analysis**
   - **What it shows**: Where and when the AI dies (e.g., crashes near food, early episodes, late episodes)
   - **Why it helps**: The LLM can identify systematic issues (e.g., "AI keeps crashing when food appears")
   - **Key insight**: Guides the LLM to tune parameters that address specific failure patterns.

### 7. **Parameter Correlation Plot**
   - **What it shows**: How pairs of parameters interact (e.g., learning rate vs. hidden size)
   - **Why it helps**: Reveals non-linear relationships between parameters.
   - **Key insight**: Helps the LLM understand that tuning one parameter may require adjusting another.

---

### Top Priority for Ax3l

Based on the system's goals (tuning a golden configuration), I'd recommend focusing on these three:

| Priority | Visualization | Impact on Tuning |
|----------|---------------|-------------------|
| 1 | **Training Progress Curve** | Shows convergence, helps catch early issues |
| 2 | **Score Distribution** | Shows stability and achievable score range |
| 3 | **Golden Configuration Comparison** | Ensures the LLM doesn't optimize for noise |

These give the LLM the most direct feedback on whether a parameter change is meaningful or just a random fluctuation.

---

Would you like me to elaborate on any of these visualization types?
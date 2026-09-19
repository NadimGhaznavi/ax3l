---
title: Runtime Behaviour
author_profile: true
layout: single
---

The runtime behaviour has two phases: an initial phase, which runs once and finishes quickly, and the **Round Robin Phase**, which governs subsequent operation.

## Initial Experiment Startup

When the Ax3l system is started for the first time, there must be no simulation records in the [Snake Server](https://snakelabserver.osoyalce.com) database. The [Snake Lab Server](https://snakelabserver.osoyalce.com) simulation configuration is defined as a JSON document that enforces data type choices (e.g. the **seed** must be a non-zero integer). That document also defines default values. 

The initial startup executes the following steps.

1. The Ax3l server queries the Snake Lab database and sees that there are no simulations present.
2. The Ax3l server generates a configuration using the defaults in the JSON configuration document.
3. The Ax3l server submits the simulation run request to the Snake Lab server.

After this, the system enters the **Round Robin Phase**.

## Round Robin Phase


### Tunable Parameters

The system currently allows the LLM to configure the following parameters:

| Parameter | Purpose | Allowed values | Tuned with |
| --- | --- | --- | --- |
| Hidden Size | Number of neurons in each recurrent hidden layer. | Integers from 64 to 384, in multiples of 16. | Individually |
| Sequence Length | Number of consecutive frames in each training sequence. | Integers from 4 to 48, in multiples of 4. | Individually |
| Batch Size | Number of sequences sampled for each training update. | Integers from 8 to 64, in multiples of 2. | Individually |
| Learning Rate | Size of gradient updates during training. | Numbers from 0.0005 to 0.005. | Individually |
| Gamma | Discount factor controlling the value of future rewards. | Numbers from 0.9 to 0.99. | Individually |
| Epsilon: initial | Starting probability of choosing a random action. | Numbers from 0.85 to 0.999. | Epsilon: decay |
| Epsilon: decay | Multiplier applied to epsilon after each episode. | Numbers from 0.9 to 0.999. | Epsilon: initial |
| Food Reward: closer | Reward for moving closer to the food. | Integers from 0 to 6. | Food Reward: further |
| Food Reward: further | Penalty for moving farther from the food. | Integers from -6 to 0. | Food Reward: closer |

The *initial epsilon* and *epsilon decay* are tuned together; i.e., the LLM submits values for both parameters in a single submission. The two *food reward* parameters are also tuned together.

One Ax3l experiment cycle visits all seven parameter steps, with up to seven
submissions of one or two values before the cycle repeats.

An exhausted parameter is skipped and still counts as a completed step in the
cycle. After nine complete cycles without a new golden configuration, Ax3l
increments the seed and runs the golden configuration again to establish a fresh
baseline. Previously tested parameter values become eligible on the new seed,
except for configurations already run on that seed, including the fresh baseline.
A new golden configuration resets the stagnation count.

### For Each Tunable Parameter or Parameter Pair

The **Ax3l Server** executes the following steps 7 times for one complete experiment cycle:

1. Communicate with the `llama-server` that houses the LLM.
  1(a). Present the LLM with simulation run data.
  1(b). Ask the LLM to tune one or two parameters.
2. Validate the LLM's new parameter choice(s).
3. Create a simulation configuration with the new value(s).
4. Submit the configuration to the [Snake Lab Server](https://snakelabserver.osoyalce.com/) service for execution.
5. Wait for the simulation to finish.
6. Return to step 1.

The system has been built to be resilient. The services can be interrupted or restarted and the server can be rebooted. The system will resume from where it left off.

---

## Golden Configuration

Ax3l maintains a **golden configuration**, which is the current reference configuration for the experiment.

Each new parameter experiment begins with the golden configuration and changes only the parameter, or parameter pair, currently being tested. All other configuration values remain unchanged. This allows Ax3l to evaluate one part of the configuration at a time while preserving the strongest configuration discovered so far.

When a completed simulation produces a high score greater than the current golden high score, that simulation's configuration becomes the new golden configuration.

The new golden configuration is then used as the starting point for subsequent parameter experiments.

Promoting a new golden configuration also resets the stagnation counter used to determine when the experiment should move to a new seed.

The golden configuration should not be confused with the all-time high score. When the seed changes, the golden configuration is re-run to establish its performance under the new seed. The new run has historically always produced a lower score. This lower score, with the new seed, becomes the score for the LLM to beat.

---

## Seed Incrementing

A single random seed can result in a *lucky run*, where the food randomly placed in just the right position a few times. Changing the seed changes where the food is placed. This weeds out a *lucky* configuration from a *good* configuration.

Ax3l counts complete Round Robin cycles that finish without producing a new golden configuration.

After **nine complete cycles** without a new golden configuration:

1. Ax3l increments the simulation seed.
2. The current golden configuration is submitted unchanged using the new seed.
3. The result of that simulation becomes the baseline for the new seed.
4. Parameter tuning resumes from the golden configuration.

The new score for the system to beat is the one that was achieved using the previous golden configuration, but with a new seed value.

[Back](/)

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

This means that a full cycle involves the LLM making seven submissions of one or two values before the cycle repeats. This is the definition of one Ax3l experiment cycle.

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

[Back](/)
---
title: The Ax3l Project
author_profile: true
layout: single
---

![Ax3l Logo](/pages/images/ax3l.png)

The **Ax3l Project uses** [Qwen 3.5 4B](https://huggingface.co/Qwen/Qwen3.5-4B), small, locally hosted AI tp ask the question, *"Can an AI improve another AI's performance by adjusting it's model and operating environment settings?"*

This project uses the [Snake Lab Server](https://snakelabserver.osoyalce.com) which houses a small and simple AI. The Snake Lab AI is trainable. The Snake Lab Server accepts a configuration to set the AI's hyper-parameters and configure the training environment. The Snake Lab server also runs the training simulation. The high score and other simulation results are stored in a database.

The Ax3l system submits simulation configurations and analyzes the result data. It adjusts the configuration and submits a new simulation. This creates a continuous experimental loop in which the Ax3l AI explores the configuration space and attempts to improve the Snake AI's performance over time.

---

## Live Experiment Data

This is a long-running project expected to operate for well over a month. The current experiment began on **September 15, 2026**. Real-time project status can be viewed:

- [Live Site](https://snakeweb.osoyalce.com) with event log
- [Simulation Scores Distribution Histogram](https://snakeweb.osoyalce.com/reports/score-distribution.html)
- [Simulation Highscore History](https://snakeweb.osoyalce.com/reports/experiment-highscores.html)
- [Gallery of the Snake in Action](https://snakeweb.osoyalce.com/reports/top-100.html)
- [A random sampling of the LLM's Thinking](https://snakeweb.osoyalce.com/reports/ax3l-thinking.html)

---

## Project Documentation

- [Environment Setup](/pages/env-setup)
- [Architecture](/pages/architecture)
- [Runtime Behaviour](/pages/runtime-behaviour)
- [Project Scripts](/pages/scripts)
- [LLM Security Architecture](/pages/llm-security)
- [Project Screenshots](/pages/gallery)
- [Ax3l on GitHub](https://github.com/NadimGhaznavi/ax3l)



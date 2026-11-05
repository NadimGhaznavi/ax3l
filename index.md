---
title: The Ax3l Project
author_profile: true
layout: single
---

![Ax3l Logo](/pages/images/ax3l.png)

The **Ax3l Project uses** [Qwen 3.5 4B](https://huggingface.co/Qwen/Qwen3.5-4B), small, locally hosted AI to ask the question, *"Can an AI improve another AI's performance by adjusting it's model and operating environment settings?"*

This project uses the [Snake Lab Server](https://snakelabserver.osoyalce.com) which houses a small and simple AI. The Snake Lab AI is trainable. The Snake Lab Server accepts a configuration to set the AI's hyper-parameters and configure the training environment. The Snake Lab server also runs the training simulation. The high score and other simulation results are stored in a database.

The Ax3l system submits simulation configurations and analyzes the result data. It adjusts the configuration and submits a new simulation. This creates a continuous experimental loop in which the Ax3l AI explores the configuration space and attempts to improve the Snake AI's performance over time.

---

## Live Experiment Data

This is a long-running experiment that was started on **September 15, 2026**. Ax3l experiment data is exported every 30 minutes and can be viewed on the [SnakeWeb](https://snakeweb.osoyalce.com) website. The published information shows the day's top games as well as a histogram showing simulation high scores over time.

---

## Conclusion

As of November 5, 2026, the experimental evidence support the following conclusions:

- The LLM is proficient at basic neural network tuning.
- The LLM was not able to improve the performance of the snake AI beyond a basic threshold.

A QA environment ran this same codebase but simulations only ran for 500 epochs, not 1500 as they do in production. The results were very similar, with the exception of the high score being lower. This can be attributed to the lack of opportunity that the configurations had to make those higher scores. Therefore:

---

## Next Steps

Until the hardware is needed for another project, Ax3l will continue to run. The hope is that at some point a configuration will be found that breaks through the current ceiling and results in an overall performance improvement.

A new architecture is being designed to try this experiment again, but with a different framework. Check the [Bear & Moose](https://www.osoyalce.com) or my [blog](https://blog.osoyalce.com) for updates!

---

## Project Documentation

- [Environment Setup](/pages/env-setup)
- [Architecture](/pages/architecture)
- [Runtime Behaviour](/pages/runtime-behaviour)
- [Project Scripts](/pages/scripts)
- [LLM Security Architecture](/pages/llm-security)
- [Project Screenshots](/pages/gallery)
- [Ax3l on GitHub](https://github.com/NadimGhaznavi/ax3l)



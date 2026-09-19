---
title: The Ax3l Project
author_profile: true
layout: single
---

![Ax3l Logo](/pages/images/ax3l.png)

The **Ax3l Project uses** a locally hosted [Large Language Model (LLM)](https://en.wikipedia.org/wiki/Large_language_model) to run experiments and learn from their results. This project asks the question, "Can an LLM can tune the configuration of another AI that is learning to play Snake?". The project includes a rich reporting server to track ongoing progress.

Ax3l uses the [Snake Lab Server](https://snakelabserver.osoyalce.com), which accepts configuration requests for AI Snake simulations. Snake Lab runs the simulation and stores the results in a database.

Ax3l analyzes those results, adjusts the configuration, and submits a new simulation. This creates a continuous experimental loop in which the LLM explores the configuration space and attempts to improve the Snake AI's performance over time.

This is a long-running project expected to operate for well over a month. The current experiment began on **September 15, 2026**. Real-time project status can be viewed on the [Snake Website](https://snakeweb.osoyalce.com).


## Project Documentation

- [Environment Setup](/pages/env-setup)
- [Architecture](/pages/architecture)
- [Runtime Behaviour](/pages/runtime-behaviour)
- [Runtime Behaviour](/pages/runtime-behaviour)
- [AI Security Sandbox](/pages/ai-security)
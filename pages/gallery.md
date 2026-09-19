---
title: Gallery
author_profile: true
layout: single
---

Screenshots of the reporting dashboard, simulation results, and the prompts and responses used to choose simulation parameters. Select an image to view it at full size.

## Reporting dashboard

The current experiment, high-score board, report links, and event log.

[![Reporting dashboard showing experiment status and the event log]({{ '/pages/images/report-server.png' | relative_url }})]({{ '/pages/images/report-server.png' | relative_url }})

## Simulation configuration

The game, model, and training settings used for a simulation run.

[![Simulation configuration with parameter names and values]({{ '/pages/images/config.png' | relative_url }})]({{ '/pages/images/config.png' | relative_url }})

## Parameter history prompt

The current golden configuration and comparable results supplied to the LLM before it selects a new parameter value.

[![Comparison prompt containing batch-size results and the current golden score]({{ '/pages/images/parm-history-prompt.png' | relative_url }})]({{ '/pages/images/parm-history-prompt.png' | relative_url }})

## Parameter selection prompt

The instruction to choose an untested batch size and submit it through a tool call.

[![Parameter selection prompt asking the LLM to choose an untested batch size]({{ '/pages/images/parm-prompt.png' | relative_url }})]({{ '/pages/images/parm-prompt.png' | relative_url }})

## LLM response

The recorded reply, including the selected value, reasoning, tool call, token usage, and timings.

[![Complete LLM response selecting a batch size of 58]({{ '/pages/images/llm-response.png' | relative_url }})]({{ '/pages/images/llm-response.png' | relative_url }})

## Completed simulation

A completed run's high-score board, run identifier, project version, score, and completion time.

[![Completed simulation showing its high-score board and a score of 47]({{ '/pages/images/sim-completed.png' | relative_url }})]({{ '/pages/images/sim-completed.png' | relative_url }})

## Score distribution

Run high scores across the experiment, comparing all scored runs with the oldest half.

[![Histogram comparing scores from all runs with scores from the oldest half]({{ '/pages/images/histogram.png' | relative_url }})]({{ '/pages/images/histogram.png' | relative_url }})

## Experiment high scores

The accepted configuration's high score over the course of the experiment, including changes after seed rotation.

[![Chart of the accepted configuration's high score against the number of simulations]({{ '/pages/images/highscores.png' | relative_url }})]({{ '/pages/images/highscores.png' | relative_url }})

## Golden configurations

Accepted configurations with their scores, parameter changes, and links to the reasons for acceptance.

[![Golden configurations table showing accepted parameter changes and high scores]({{ '/pages/images/golden-configs.png' | relative_url }})]({{ '/pages/images/golden-configs.png' | relative_url }})

---

[Back](/)

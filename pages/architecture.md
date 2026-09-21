---
title: Architecture
author_profile: true
layout: single
---

![Ax3l]({{ '/pages/images/ax3l.png' | relative_url }})

The project runs on [Debian Linux](https://debian.org) and uses [systemd](https://systemd.io/) to run the components as services.

## Ax3l Server

The **Ax3l Server** is the heart of the system. It is implemented as a *systemd service*. See the [runtime behaviour page](/pages/runtime-behaviour) for more information. Key events are logged and reported on by the **Reporting Server**.

## llama-server

The **llama-server** is part of [llama.cpp](https://llama-cpp.com/). The Ax3l project uses a *systemd service* to run the llama-server. The llama-server hosts the **Qwen 3.5 4B** model.

### Qwen 3.5 4B LLM

The LLM used by the project is [Qwen 3.5 - 4B](https://huggingface.co/Qwen/Qwen3.5-4B). This is an open source model created by the [Alibaba Group](https://www.alibabagroup.com/en-US/about-alibaba) out of China.

## MCP servers and tools

The MCP tool framework is a feature of llama.cpp and is well supported by the Qwen 3.5 4B model.

- The MCP tools provide a way for the LLM to communicate its parameter choices to the Ax3l server.
- The tools use the [ZeroMQ](http://zeromq.org) messaging framework to deliver the results to the Ax3l server.

## MariaDB

- The MariaDB database stores application data, history, results, and events.
- It also stores Ax3l's own execution state, including conversation and workflow progress needed for continuity across interruptions, restarts, and reboots.

## Reporting server

- Reads from MariaDB.
- Summarizes the current system state, e.g., the number of simulations run.
- Presents a histogram showing score distribution across simulation runs.
- Presents a plot of the high score over time, including the dips due to seed rotation events.
- Presents an event log with filtering.

## Watchdog service

- Checks Ax3l, reporting, and the model selected during service installation every 10 seconds; restarts inactive or failed units through systemd.
- Restarts the selected model after three consecutive failed `/health` checks, with a 60-second grace period at watchdog startup and after model restarts.
- Logs only problems and recovery attempts to the systemd journal; successful polls are silent, including health requests to the dev/QA LLM stub. Runs as root to manage system services.
- Does not detect a stalled optimization loop in an otherwise active Ax3l process. Stop the watchdog before intentionally stopping individual services (`services.sh stop` does this automatically).
- Reinstall services with `-model` when changing the model monitored by the watchdog.

---

[Back](/)
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
- Retrieves captured high-score games from Snake Lab over ZMQ and shows animated GIFs in simulation reports and the current experiment panel. Runs without captured frames retain their saved SVG board; control-service transport outages also use that fallback.
- Schedules missing GIFs in a background worker on first view and reuses files named by run ID, under a directory containing the renderer version and frame duration. The report shows its saved SVG until the GIF is available on a subsequent refresh. No animation metadata is stored in the database.
- Caches games-played and moves-made totals in memory. Views schedule a background refresh when the cache is older than 60 seconds, using a separate worker from GIF generation. Reports show the last successful totals during refreshes and database outages, or an em dash before the first result. Missing captures and transport failures are retried at most once per minute when viewed.
- Also caches completed experiments, submitted simulations, all-time high score, and control-service status in a separate background worker, refreshing stale results on views after 60 seconds. Report reads do not initialize database tables. The event query limits the latest 500 events before joining their details; operations taking at least one second are logged for diagnosis.

GIFs loop forever at 75 ms per move by default, holding the final frame for
1 second before restarting. Each food pickup inserts a stationary sequence at
50 ms per frame: the snake moves onto the food at its previous length, and a
darker shade of the food colour travels from head to tail. The captured growth
frame and replacement food appear after that sequence, then normal playback
resumes. These display frames do not alter the captured game data. GIF delays
use 10 ms ticks; cumulative rounding alternates 80 and 70 ms move delays to
preserve the requested average speed.
The reporting entry point accepts
`--gif-dir` (default `/opt/prod/ax3l/games`) and `--gif-duration-ms` (at least
10 ms). The production service keeps GIFs in
`/opt/prod/ax3l/games`; DEV and QA use their own installed application's `games`
directory. These directories are writable through systemd's
`ReadWritePaths` even with `ProtectSystem=strict`. Removing a cached GIF causes
it to be regenerated on the next view. Old Snake Lab runs are not backfilled.

## Watchdog service

- Checks Ax3l, reporting, and the model selected during service installation every 10 seconds; restarts inactive or failed units through systemd.
- Restarts the selected model after three consecutive failed `/health` checks, with a 60-second grace period at watchdog startup and after model restarts.
- Logs only problems and recovery attempts to the systemd journal; successful polls are silent, including health requests to the dev/QA LLM stub. Runs as root to manage system services.
- Does not detect a stalled optimization loop in an otherwise active Ax3l process. Stop the watchdog before intentionally stopping individual services (`services.sh stop` does this automatically).
- Reinstall services with `-model` when changing the model monitored by the watchdog.

---

[Back](/)

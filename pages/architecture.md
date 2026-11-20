---
title: Architecture
author_profile: true
layout: single
---

The project runs on [Debian Linux](https://debian.org) and uses [systemd](https://systemd.io/) to run the components as services.

## Ax3l Server

The **Ax3l Server** is the heart of the system. It is implemented as a *systemd service*. See the [runtime behaviour page](/pages/runtime-behaviour) for more information. Key events are logged and reported on by the **Reporting Server**.

## Shared LlamaSrv inference

The standalone [LlamaSrv](https://llamasrv.osoyalce.com/) application manages
the shared **llama-server** and its loaded **Qwen 3.5 4B** model. Ax3l sends
OpenAI-compatible chat requests to the configured `llamasrv_url`, which
defaults to `http://127.0.0.1:51001`. Model provisioning, inference settings,
and service lifecycle belong to LlamaSrv. Its production server supports four
concurrent slots against the same loaded model.

### Qwen 3.5 4B LLM

The LLM used by the project is [Qwen 3.5 - 4B](https://huggingface.co/Qwen/Qwen3.5-4B). This is an open source model created by the [Alibaba Group](https://www.alibabagroup.com/en-US/about-alibaba) out of China.

## MCP servers and tools

Ax3l starts a private stdio MCP session for each optimization conversation and
sends its discovered tool definitions with inference requests. Ax3l executes
the returned tool calls; the shared inference service has no global Ax3l tool
registration.

- The MCP tools let Qwen look up measurements and save parameter choices in an
  Ax3l-owned configuration draft. Ax3l submits the complete draft after it
  accepts every choice.
- The tools use the [ZeroMQ](http://zeromq.org) messaging framework to deliver the results to the Ax3l server.

## MariaDB

- The MariaDB database stores application data, history, results, and events.
- It also stores Ax3l's own execution state, including conversation and workflow progress needed for continuity across interruptions, restarts, and reboots.

## Reporting server

- Reads from MariaDB.
- Summarizes the current system state, e.g., the number of simulations run.
- Offers an Experiment Status report card with fourteen configuration values and
  read-only checkmarks for accepted LLM choices, including unchanged values.
  Paired settings advance together, inherited pending values remain visible,
  and the next selection is highlighted. Simulation and measurement phases are
  shown separately, with the result compared against the golden baseline on
  the same seed. Current and Last completed views refresh every five seconds;
  a failed refresh keeps the last successful card and its timestamp visible.
  Each choice shows its chart preparation, inference requests, tool lookups,
  and submission with per-step timings and per-request input and output tokens.
- Presents a histogram showing score distribution across simulation runs.
- Simulation details show exact termination counts and percentages and any previously saved Qwen notes. Run labels use the first UUID group; navigation retains full UUIDs.
- Presents a plot of the high score over time, including local golden baselines
  established by seed rotations, which may decrease the score.
- Presents an event log with filtering.
- Handles HTTP connections in separate threads with a 30-second client timeout, so idle browser connections cannot block other pages or health checks. Shared background cache scheduling is serialized.
- Retrieves captured high-score games from Snake Lab over ZMQ and shows animated GIFs in simulation reports and the current experiment panel. Runs without captured frames retain their saved SVG board; control-service transport outages also use that fallback.
- Schedules missing GIFs in a background worker on first view and reuses files named by run ID, under a directory containing the renderer version and frame duration. The report shows its saved SVG until the GIF is available on a subsequent refresh. No animation metadata is stored in the database.
- Maintains Ax3l-owned `report_runs`, `report_events`, `report_turns`, and `report_state` tables. The first background refresh explicitly creates and populates them; later refreshes summarize only previously unseen completed runs and project new experiment events. SnakeLab and original event tables are read only. Games, moves, and all-time high score exclude running, queued, cancelled, and failed runs. Submitted simulations still counts every status.
- Saves summaries, totals, complete-configuration progress, and duplicate suppression in one transaction, serialized by the reporting state row. Source IDs identify records rather than acting as committed-data watermarks: older runs that finish later and late-committing events are revisited. Earlier comparisons cause experiment progress to be reconstructed from the small reporting projection; each compared configuration counts once. Completed runs and their episodes are assumed final and immutable.
- Caches reporting totals in memory. Views schedule a background refresh when the cache is older than 60 seconds, using a separate worker from GIF generation and control-service status. Reports show the last successful totals during refreshes and database outages, or an em dash before the first result. Missing captures and transport failures are retried at most once per minute when viewed. Completed background results appear on the next view or browser refresh.
- Reconciles the cached all-time high score with the live golden score on each
  event-log view so a newly promoted golden cannot exceed the displayed all-time
  high while the background totals are catching up.
- Caches control-service status independently, refreshing stale results on views after 60 seconds, so a control-service timeout cannot hold up reporting counters. Direct HTTP database reads do not initialize tables. The event query limits the latest 500 events before joining their details; operations taking at least one second are logged for diagnosis.

With the installation's `DB_*` environment loaded, reporting can also
be populated before serving views:

```bash
.venv/bin/python -m ax3l.app.ReportingRefresh
```

The command prints the persisted counters as JSON. It is safe to repeat and
uses the same incremental update as the background worker. Use `--rebuild`
to extract everything again after resetting source data or changing the
reporting calculation. Rebuild replaces only the four reporting tables' data,
inside a transaction; it does not alter or delete original data. Initial
extraction can run while ingestion continues, with subsequent refreshes picking
up changes outside the extraction's transaction snapshot. This does not
require another service or changes to SnakeLab. The normal Ax3l credentials
already have write access to the Ax3l database and SELECT access to SnakeLab.

GIFs embed the simulation number, captured high score, and current score in a bordered
panel using the bundled DejaVu Sans Mono font. The live score updates on food pickup,
including during digestion.

GIFs loop forever at 75 ms per move by default, holding the final frame for
1 second before restarting. Each food pickup inserts a stationary sequence at
50 ms per frame: the snake moves onto the food at its previous length and shows
the replacement food for one move interval before digestion starts. The new food
stays visible while a darker shade of the food colour travels from head to tail. The captured growth
appears on the next captured move: the head advances and the visible tail stays
in place with its normal body colour. The pickup's full-length board is skipped
so the previous tail square does not flash after digestion. If the game ends
before another move, the final board keeps the visible length. These display
frames do not alter the captured game data. GIF delays
use 10 ms ticks; cumulative rounding alternates 80 and 70 ms move delays to
preserve the requested average speed.
The reporting entry point accepts
`--gif-dir` (default `/opt/prod/ax3l/games`) and `--gif-duration-ms` (at least
10 ms). The reporting service keeps GIFs in
`/opt/prod/ax3l/games`. This directory is writable through systemd's
`ReadWritePaths` even with `ProtectSystem=strict`. Removing a cached GIF causes
it to be regenerated on the next view. Old Snake Lab runs are not backfilled.

Ax3l's reporting and ZeroMQ bindings are declared in `DAx3l.CMDB_NETWORK` and overridden in
`/opt/prod/ax3l/conf/ax3l.json`. The configuration interface validates the
file once per process through `Network`. Installation and the network restart
helper render Ax3l's service units from those same values. The outbound
`llamasrv_url` is configured separately in the same file and read by the
optimization process at startup. See [network configuration](/pages/scripts.html#network-configuration).

## Watchdog service

- Checks Ax3l and reporting every 10 seconds; restarts inactive or failed units through systemd.
- Shared LlamaSrv inference is managed independently; the watchdog does not control its services.
- Logs only problems and recovery attempts to the systemd journal; successful polls are silent. Runs as root to manage system services.
- Does not detect a stalled optimization loop in an otherwise active Ax3l process. Stop the watchdog before intentionally stopping individual services (`services.sh stop` does this automatically).

---

[Back](/)

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Changed

- Display Simulation Runtime and LLM Time in minutes on the Simulation Metrics page.

### Added

- Add a matching Steps per Simulation plot showing mean total steps per run with the same configurable sequential buckets.

## [1.6.2] - 2026-09-22 @ 04:57

### Changed

- Thin the Simulation Metrics data:
  - Aggregate Simulation Metrics into consecutive simulation buckets (default 20, configurable), plotting mean runtime and LLM time and showing high-score and step summaries in hover details. Include every completed simulation and the final partial bucket.

## [1.6.0] - 2026-09-22 @ 04:46

### Added

- Add Simulation Metrics below Golden Configurations in the Report Server, with matching plot styling and smoothed Simulation Runtime and LLM Time lines for successfully completed simulations, numbered oldest first. LLM time sums logged prompt-to-response intervals, including proposal retries.

## [1.5.0] - 2026-09-21 @ 17:31

### Removed

- Remove Ax3l's static HTTP health endpoint and its production, dev, and QA port constants. Ax3l continues to serve tool requests over ZeroMQ; the dev/QA LLM health stub remains available.

### Added

- Make the watchdog restart inactive or failed Ax3l, reporting, and selected model services, and recover repeated LLM health failures with startup grace and journal logging limited to problems and recovery. Successful watchdog checks and dev/QA LLM stub health requests remain silent.

- Add coding guidelines adapted from R3el for Ax3l's architecture and development practices, including changelog updates, and direct repository agents to follow them through `AGENTS.md`.

## [1.4.2] - 2026-09-20 @ 12:30

### Changed

- Mark seed changes in the report server's Experiment Highscores plot with purple points, a hover label, and separate legend entries for the blue score line, orange accepted configurations, and purple seed changes.
- Show cumulative thirds in the score histogram: muted red for the oldest third, orange for the oldest two-thirds, and blue for all runs.

## [1.4.0] - 2026-09-20 @ 09:03

### Added

- Begin every LLM optimization conversation with the Snake tutorial context and responsibility for choosing parameters.

## [1.3.10] - 2026-09-20 @ 06:52

### Fixed

- Normalize the event run ID comparison to SnakeLab's collation so differing database collations do not break the Event Log.

## [1.3.9] - 2026-09-20 @ 06:45

### Fixed

- Read Event Log simulation high scores from the SnakeLab database instead of the Ax3l database.

## [1.3.8] - 2026-09-20 @ 06:40

### Changed

- Show each simulation's high score in the Report Server's Simulation Completed event message, including existing entries.

## [1.3.7] - 2026-09-19 @ 19:58

### Summary

- Remove unused categories from the Report Server's Event Log.
- Add static project website content.

### Added

- Add an explanation of the *golden config* and *seed changes* to the website.

### Removed

- Remove unused Metrics, Process, and System categories from the Event Log catalog and filter choices.

### Changed

- Clarify and verify that seed rotation occurs after nine complete round-robin
  cycles without improvement, including exhausted parameter skips. Regression
  coverage checks restart recovery and renewed eligibility on a different seed.

## [1.3.6] - 2026-09-19 @ 12:08

### HotFix Summary

This release addresses the scenario (reached at simulation number 885 in QA) where all legal choices for a finite parameter space, such as sequence length, have already been tried. Ax3l skips that parameter and advances to the next round-robin step. Exhaustion is checked against the current seed and otherwise identical settings, so a change to either can make choices available again.

### Fixed

- Skip exhausted finite parameter spaces before starting an LLM conversation,
  preserving round-robin progress and seed-rotation cycle counts across restarts.
- Record each skip as an INFO-level "Parameter space exhausted" entry in the
  Display Manager Event Log, including the parameter for filtering and a message
  explaining that Ax3l is advancing to the next round-robin step.

## [1.3.5] - 2026-09-19 @ 11:36

- Minor website polish.

## [1.3.3] - 2026-09-19 @ 10:58

- Additional minor website tweaks.

## [1.3.0] - 2026-09-19 @ 10:45

- Add a GitHub link.

## [1.3.0] - 2026-09-19 @ 10:42

- Complete rewrite of the website contents.

## [1.2.5] - 2026-09-19 @ 07:15

### Changed

- Widen the Golden Configurations report from 1200px to 1600px to give its columns more room.

## [1.1.0] - 2026-09-15 @ 05:27

### Added

- Add a Golden Configurations report with every baseline and promotion, newest first, including its recorded high score, parameter value change, and links to the saved configuration and the proposing LLM response's reasoning.

## [1.0.8] - 2026-09-15 @ 04:42

### Changed

- Record the Ax3l project version on simulation submission events, including default configurations, parameter proposals, and seed rotations. Seed rotation recovery preserves the version recorded before submission. Requires fresh event tables; no migration is provided.
- Record the assigned parameter on initial and retry prompt events. Replace the Event Log Source column and filter with Parameter; retain source in prompt details. The new event column requires recreating the event tables before running this version.
- Increase the number of rounds before a seed reset from 3 to 9.

## [1.0.7] - 2026-09-14 @ 04:22

### Added

- Add manual local Ax3l database backups using the configured DEV or PROD database name.

### Changed

- Updated the English in the `ComparisonRewardPair` prompt.

## [1.0.6] - 2026-09-13 @ 19:36

### Changed

- Recover proposal monitoring after a Snake Lab restart: read stored terminal results for forgotten runs, compare completed proposals, and skip interrupted proposals while retaining the golden configuration.

## [1.0.4] - 2026-09-13 @ 17:46

### Added

- Add a Source filter when Prompt is selected in the Event Log, preserving the selected source during automatic refresh.

## [1.0.3] - 2026-09-13 @ 17:28

### Changed

- Narrow Event Log event choices by category using the shared event catalog, and show prompt sources when the Prompt filter is selected.

## [1.0.2] - 2026-09-13 @ 17:06

### Changed

- Connect Experiment Highscores points with a smooth curve instead of steps.

- Fix SnakeLab MCP startup permissions by creating service files with umask 022 and granting the service group access to existing Python virtual environments during install or upgrade.

## [1.0.1] - 2026-09-13 @ 16:26

### Changed

- Increased epochs from 500 to 1500.

## [1.0.0] - 2026-09-13 @ 16:20

### Added

- Add Experiment Highscores, a Plotly step chart of accepted config scores against simulation count, including lower baselines after seed rotation. Store score snapshots atomically with golden creation events in the fresh database.

- Store prompt module names in `events.source_name` and show them in prompt detail titles, including correction prompts. Requires a clean database reinstall; no upgrade migration.

- Integrate epsilon and reward pair tuning into the seven-entry round robin, with pair reports, bound MCP calls, retry feedback, and complete-cycle seed rotation. Existing experiment events must be reset before using the new order.

- Show the last successful dashboard refresh date/time in UTC beside the Snake Lab server status, using the same font size as Current Highscore.

### Changed

- Increase histogram bar borders to 4 pixels and match the Experiment Highscores chart to the histogram styling, with a 4-pixel highscore line and a centered bottom legend with matching spacing.

### Removed

- Remove `simulation_runs.config` from the fresh-install schema and read configuration values from `configurations` for lookups, duplicate detection, and tuning reports. Requires the matching SnakeLab writer update and a clean database reinstall.

## [0.99.13] - 2026-09-13 @ 14:11

### Changed

- Style the score histogram in dark blue and orange with outlined bars, a chart border, and a bottom legend inside the border.

## [0.99.11] - 2026-09-13 @ 14:03

### Changed

- Run the report server as root to resolve deployment file permission errors.

## [0.99.10] - 2026-09-13 @ 13:59

### Changed

- Run the report server with the deployment virtual environment's Python so it can load Plotly and the other installed application dependencies.

## [0.99.9] - 2026-09-13 @ 13:53

### Added

- Add a Score Distribution Histogram link under Experiment Status, showing all run high scores with the oldest half overlaid in shared bins using an interactive, self-contained Plotly chart.

## [0.99.7] - 2026-09-13 @ 13:28

### Changed

- Put the experiment highscore on its own line and show total submitted simulations and completed round-robin cycles, including automatic refresh.

- Reset event and SnakeLab simulation auto-increment counters after a successful database wipe, so new IDs start at 1.

## [0.99.6] - 2026-09-13 @ 13:01

### Added

- Add Category and Event dropdown filters beneath the event log headers, defaulting to `*` (all) and preserving selections during automatic refresh.

- Add an automatically refreshed Experiment Status section showing the highest recorded Snake Lab score across all runs, independent of the current golden configuration.

### Changed

- Replace automatic dashboard refresh with a dropdown defaulting to No Refresh, with intervals of 5 seconds, 30 seconds, 1 minute, 5 minutes, and 30 minutes.

- Size event log columns to fit their full content without shrinking, leaving Message to use the remaining width.

## [0.99.5] - 2026-09-13 @ 11:50

### Changed

- Restore FirstContact's experiment background and guidance to explore apparently poor choices for useful data and potential higher scores.

## [0.99.3] - 2026-09-13 @ 11:42

### Changed

- Move the HTTP request timeout to `DAx3l.HTTP_TIMEOUT_SECONDS`, retaining the 300-second value.

- Bind each conversation’s MCP tool to Ax3l’s round-robin parameter and accept only a value. Limit tool instructions, baseline data, and history to that parameter; correct unexpected parameter arguments without submitting them.

## [0.99.2] - 2026-09-13 @ 10:58

### Added

- Persist the single-parameter round-robin position in the event DB before each conversation. Restart interrupted thinking on the same parameter and advance after accepted submissions, including lost MCP replies.

### Changed

- Rotate the seed after 3 complete stagnant round-robin cycles instead of counting individual comparisons. Reset on a new golden high score and preserve accounting across restarts.

- Configure Qwen3.5 with `DQwen.CONTEXT_SIZE` (8196 tokens) and a 5-second startup delay, matching the existing QwenV settings. Pass the context size to llama-server on installation and upgrade.

- Reduced number of epochs to 500 to support a fast PROD smoke test.

### Removed

- Remove the original Haiku POC loop, prompt, constants, and unused first-iteration helper with their obsolete tests. Rename optional capture directories to `snakelab`; retain the active optimization entry point.

## [0.99.1] - 2026-09-13 @ 10:18

### Removed

- Remove the Qwen2.5-VL custom tool chat template, missing-tool reminder retries, and extra prose-response warnings in the initial prompt. Use bundled model templates and standard required-tool metadata; missing tool calls now end the conversation with a logged error. Keep validation feedback and submission safety checks.

## [0.99.0] - 2026-09-13 @ 10:12

### Changed

- Rename `LearningRateLoop.py` to `SnakeLabLoop.py` and expand proposals to hidden size, sequence length, batch size, learning rate, and gamma. Keep reward-distance and epsilon pairs out of this iteration; use schema-backed single-parameter prompts, tool validation, per-parameter comparison histories, and actual configuration changes in comparison logs.

## [0.99.0] - 2026-09-13 @ 09:58

### Changed

- Restore Qwen3.5 (`qwen`) as the default for installation, upgrade, and service startup for text-only prompt development. Explicit `-model phi|qwenv` selections remain supported.

### Removed

- Make Snake Lab optimization conversations text-only by removing `LossPlot` and `ComparisonPlot` from initial, comparison, restart, and seed-baseline prompts, including the first-iteration helper. Update proposal instructions to use comparison history without loss curves and document the active prompts in `pages/snake-lab-propts.md`.

## [0.98.12] - 2026-09-12 @ 16:34

### Changed

- Increased num epochs to 1500

## [0.98.11] - 2026-09-12 @ 16:21

### Added

- Add `scripts/wipe-db.sh -env dev|qa|prod` to stop Ax3l and SnakeLab and clear both event and simulation data in one transaction. Schemas and accounts remain intact; services remain stopped.

## [0.98.10] - 2026-09-12 @ 16:02

## [0.98.9] - 2026-09-12 @ 15:56

### Changed

- Doubled the plot width

## [0.98.8] - 2026-09-12 @ 15:30

### Changed

- Supply QwenV with an explicit chat template combining vision inputs and Qwen tool definitions, calls, and results. The bundled model template omitted tools, causing prose replies despite required tool calls.

## [0.98.7] - 2026-09-12 @ 15:19

### Changed

- Reduce a missing-tool retry to “Please submit using the submit_single_value tool”. Do not resend the model’s prose response or original prompt material.

- When the LLM replies without a tool call, send only its latest response and a short `UseTool` reminder on the next request. Original prompts and plots are not resent; reminders remain linked to the same logged conversation.

- Make the first single-parameter prompt explicitly require one numeric `submit_single_value` tool call, include constraints from the JSON spec, and limit the change to the selected parameter.

- Explicitly enable llama-server’s Jinja tool-calling support for all production models. Unexpected tool responses now report the received function names, finish reason, and captured reply event ID.

## [0.98.6] - 2026-09-12 @ 15:05

### Changed

- Give Chrome writable config/cache paths in Ax3l’s systemd runtime directory. This fixes the browser exiting during plot rendering when home directories are hidden and the filesystem is read-only. Verified headless PNG rendering under the service’s filesystem restrictions.

## [0.98.5] - 2026-09-12 @ 14:55

### Changed

- Provision Chrome for Kaleido inside the application directory, configure its path for Ax3l’s service, and verify PNG rendering during installation. This avoids relying on a browser download in a home directory hidden by systemd.

## [0.98.3] - 2026-09-12 @ 14:39

### Added

- Load external SnakeLab database settings from `snakelab.env` beside Ax3l’s `database.env`. Production upgrades validate the required settings before stopping services; the existing Ax3l credentials file remains unchanged.

### Changed

- Grant Ax3l’s database user read-only (`SELECT`) access to `snakelab` during installation and reuse its `DB_*` credentials for simulation reads. Removed the separate `snakelab.env` requirement.

- Give the model service group access to the configuration directory and MCP registration on install/upgrade, fixing the root-only directory created during provisioning. Database credential file permissions are preserved.

## [0.98.2] - 2026-09-12 @ 14:23

### Changed

- Run `ax3l-server` as root to address the reported permission denial executing its installed virtual-environment Python.

## [0.98.1] - 2026-09-12 @ 14:19

### Added

- Prompt log entries link to detail views that display the captured text and embedded PNG plots, without regenerating images from simulation data.

## [0.9.0] - 2026-09-12 @ 14:14

### Added

- Ax3l logs each decoded MCP tool request as `tool_request_received`, including its sender, target, method, protocol version, and payload, before dispatch or validation. Unknown methods are logged too; logging failure prevents execution.

- Ax3l now runs a shared ZeroMQ listener and handles single-value proposals: JSON-spec legality checks return `InvalidValue`, duplicate golden or historical configurations return `NoDupesSingle`, and legal unique candidates are submitted once. Added `is_config_unique()` to the SnakeLab DAL using full JSON equality across all runs. Deployment assigns separate DEV/QA/PROD endpoints, installs the JSON spec, and runs Ax3l from its provisioned virtual environment.

- Added the SnakeLab `submit_single_value` MCP tool and shared `ZMQMsg`/`ZMQClient` boundary. The tool forwards the parameter and numeric value to Ax3l and returns its reply without domain validation or automatic retries. The Ax3l handler remains a separate step.

- Added the SnakeLab stdio MCP entry point and generated `mcp.json` registration. Production Qwen, Phi, and QwenV launches pass that config to llama-server; installation provisions the MCP SDK in the application's virtual environment. Domain tools will be registered in the new server module.

- The active first iteration seeds an empty Snake Lab database, waits for idle, and sends FirstContact, GoldenConfig, LossPlot, and the learning-rate introduction in one request. Each exact message snapshot is logged as a conversation-linked prompt event; the reply ends the iteration.

- Added `LossPlot`, a dynamic PNG prompt reading per-episode losses from Snake Lab through the DAL. It embeds the PNG in the LLM message and uses `GoldenConfig.run_id` to keep both snippets tied to the same simulation.

- Added Plotly and Kaleido dependencies for dynamic PNG chart generation.

- Added the `GoldenConfig` dynamic prompt. Initialization and explicit refresh read the latest golden creation's run, reason, and stored Snake Lab configuration for use in an LLM conversation.

- Added `golden_config_created` in the Configuration category with a reason. Initial creation uses `Seeded database with default config.`; subsequent creations supply the parameter comparison.

- The Snake Lab main loop submits defaults from the JSON spec when the simulation database is empty, logs the run reference without copying its configuration, and polls every five seconds through completion. It logs the start once and the final outcome to close the cycle. The submission's config link reads its detail page directly from Snake Lab's database through the DAL.

- Added `SnakeLab.get_num_sims()` to count all stored Snake Lab runs through MariaDB, using separate `SNAKELAB_DB_*` credentials without initializing external tables.

### Changed

- Default installation, upgrade, and service startup to `qwenv`, with its vision projector for PNG prompts. Explicit `-model qwen|phi|qwenv` selections remain supported.

- Reduced loss plot PNGs to 750×450 pixels, configured through `DLossPlot.WIDTH`, `HEIGHT`, and `SCALE`.

- `FirstContactSingle` now accepts a JSON parameter key and builds its introduction from a readable name and the simulation spec's description.

- Centralized log categories, event names, and display labels in `DEventCategory`, using a shared `EventCategory` class. The main loop and reporting use the catalog; existing stored event names and categories are preserved.

## [0.8.1] - 2026-09-12 @ 11:14

### Added

- Installed the system Python ZeroMQ dependency in DEV and PROD. Services using `/usr/bin/python3` require Debian's `python3-zmq` package (`sudo apt-get install python3-zmq`) for the Snake Lab status query; listing `pyzmq` in `requirements.txt` alone does not install it.

## [0.8.0] - 2026-09-12 @ 11:10

### Added

- Added a matching Snake Lab Server status bar above the event log, showing running simulation or idle and updating with automatic refresh.

- Added the SnakeLab ZeroMQ interface to query whether the local server has an active or queued simulation, with strict response validation and bounded waits.

### Changed

- Keep the event log available when Snake Lab is down: its status bar shows unavailable on ZeroMQ transport failures and checks again on each refresh.

- Replaced the event log Refresh button with automatic refresh every 30 seconds, configurable through `DReportMgr.REFRESH_SECONDS`. Updates preserve scroll position and keep the current entries visible if refresh fails.

## [0.7.10] - 2026-09-12 @ 10:26

### Added

- Added `DConversation` definitions for the conversation category and event names, shared by the main loop, reporting, and display-label mapping.

### Changed

- Each haiku request now uses a fresh random integer from 0 through 30 in the prompt: `Write a haiku based on the number X.`

## [0.7.9] - 2026-09-12 @ 10:10

### Changed

- Split the event log timestamp into Date (`YYYY-MM-DD`) and Time (`HH:MM:SS`) columns, omitting fractional seconds from the display.

## [0.7.7] - 2026-09-12 @ 10:06

### Changed

- Reduced the Event column width from `23ch` to `12ch` to give the Message column more room.

## [0.7.6] - 2026-09-12 @ 10:02

### Changed

- Changed the `reply_received` display label to `Response`.

## [0.7.5] - 2026-09-12 @ 10:01

### Changed

- Shortened the `wait_ended` display label to `Sleep`.

- Shortened the `prompt_sent` display label to `Prompt`.

- Shortened conversation lifecycle display labels to `Started` and `Ended`; the Category column already identifies them as conversation events.

## [0.7.4] - 2026-09-12 @ 09:57

### Added

- Added shared event display labels in `DEventDisplay`. The loop logs `wait_started`, displayed as `Sleep`; existing `sleep` events receive the same label. Hovering a label shows its raw event name. New sleep messages record `Sleep for seconds: (x)` using the configured interval.

### Changed

- Expanded the development guidance for the fixed platform, clear module responsibilities, strict DAL, and thin slices without speculative defensive code. Moved it into `README.md` and updated the homepage and architecture links.

## [0.7.3] - 2026-09-12 @ 09:42

### Added

- Added the global `DAx3l.RAW_LOGS_ENABLED` flag, defaulting to `False`. The haiku loop creates no capture directories or files while disabled; database events and normal console/journal status remain available. Set it to `True` to restore raw captures. Existing captures are not deleted.

- Conversation replies now link from their assistant message text to a detail page showing the event envelope and every captured response field, including usage and timings.

## [0.7.2] - 2026-09-12 @ 09:25

### Changed

- Gave the event log separate Time, ID, Level, Category, Event, and Message columns while retaining single-line striped rows.

## [0.7.1] - 2026-09-12 @ 09:20

### Changed

- Made event log entries single-line rows with alternating dark/light backgrounds. Long entries truncate with an ellipsis; hover reveals the full entry.

- Styled the event log with a dark background, green monospace lettering, and bordered sections, controls, and log entries.

- The reporting event log now shows the newest entries first.

## [0.7.0] - 2026-09-12 @ 09:06

### Changed

- Reporting now listens on `0.0.0.0` by default, including under systemd. The production event log is available at `http://neuromancer.osoyalce.com:28870/`. Use `--host 127.0.0.1` for local-only access.

## [0.6.0] - 2026-09-12 @ 09:00

### Added

- Added `DSnakeLab.HAIKU_SLEEP_SECONDS` (default: 5) to configure the delay between haiku requests and their logged wait messages.

### Changed

- The haiku request count defaults to `DSnakeLab.HAIKU_COUNT` in `ax3l/constants/DSnakeLab.py` for manual and service runs. It is initially `0` (repeat until stopped); `--count` overrides it for manual runs.

#### Service startup

- Production `ax3l-server` now starts the haiku loop against the local LLM while serving `/health`. Systemd supplies database credentials and a writable capture directory at `/var/lib/ax3l/haiku`. Stopping the service interrupts the loop and records conversation end. DEV/QA retain health-only startup because their model services are inference-free stubs.

Deploy from the updated checkout on PROD:

```bash
scripts/upgrade.sh -env prod -model qwenv
```

The loop starts automatically; stop any manually launched loop before upgrading.
Use `systemctl stop ax3l-server` to stop it. Jinja2 and PyMySQL must be available
to `/usr/bin/python3`; the upgrade does not install Python dependencies.

## [0.5.0] - 2026-09-12 @ 08:52

### Added

#### Reporting

- Added a Jinja2 event-log page at `/` with chronological log lines and a Refresh button, showing the latest 500 events. `/health` remains available. Deployment includes the HTML template; the Python environment needs `Jinja2` from `requirements.txt`.

To run the DEV reporting page from the checkout:

```bash
set -a
. prod_etc/ax3l/database.env
set +a
python3 -m ax3l.server.ReportingServer --port 28868
```

Open `http://127.0.0.1:28868/` on that machine. Use `--host 0.0.0.0` to listen
on the network for access from another machine.

- Integrated `DbMgr.log()` into the haiku loop for linked conversation, prompt, full response, wait, and failure events. Load `DB_*` credentials before running; file capture remains available.

- Added `DbMgr.log()` to atomically store an event envelope and message, returning the event ID with optional process and parent-event links.

## [0.4.1] - 2026-09-12 @ 07:24

### Added

- Added `DbMgr` with MariaDB connection ownership, generic parameterized SQL methods, and transaction support. Initialization creates shared event envelope, message, list-item, and key/value tables. Verified against the disposable DEV database.

- Added a minimal SnakeLab haiku loop with a shared prompt class and LLM HTTP interface. Saves requests, complete response bodies, headers, and a run log; waits five seconds between requests.

#### Running the haiku loop

From the project root, run:

```bash
set -a
. /etc/ax3l/database.env  # DEV: use prod_etc/ax3l/database.env instead
set +a
python3 -m ax3l.app.snakelab.main-loop --url http://neuromancer.osoyalce.com:27770
```

The loop asks the running model to write a haiku, captures the response, sleeps
five seconds, and repeats. Each request starts with fresh context. Press Ctrl-C
to stop, or append `--count 2` to stop after two requests.

Output is saved in a timestamped directory under `tmp/haiku/`, printed at startup.
It includes request JSON, exact response bodies, HTTP headers and status, and
`run.log` containing output and errors. Use `--output /tmp/haiku` to change the
output root. HTTP or transport errors are logged and stop the loop.

## [0.4.0] - 2026-09-12 @ 06:13

### Added

- Added `qwenv-server` and `-model qwenv` for Qwen2.5-VL, including its vision projector and 4096-token context. All model services are installed and upgraded together.

### Removed

- Removed model service conflicts and automatic stopping/disabling of other models. Starting a model leaves existing model processes alone.

## [0.3.0] - 2026-09-12 @ 05:13

### Added

- Added `phi-server` alongside the renamed `qwen-server`, sharing the LLM port with mutually exclusive systemd units. Service control, installation, and upgrade accept `-model qwen|phi` (default Qwen); upgrade removes legacy `llm-server` units.

- Added `scripts/upgrade.sh -env dev|qa|prod` to update application modules and systemd units from the current checkout while preserving the database, credentials, and accounts.

### Changed

- Service installation uses the shared `DLlama.MODEL_DIR` for the model path, keeping `DLlama.BASE_DIR` for llama.cpp.

- Service installation validates generated units and stops services before replacing application files.

## [0.2.2] - 2026-09-12 @ 04:25

### Added

- Added `--metrics` switch to `llama-server` to enable it

## [0.2.1] - 2026-09-12 @ 03:28

### Changed

- `install.sh` now installs, enables, and starts all four systemd services after provisioning the database and Linux account, so uninstall/install restores the service units without a separate command.

## [0.2.0] - 2026-09-12 @ 03:23

### Changed

- Production LLM now binds to `DLlama.HOST` (`0.0.0.0`) to allow connections from the dev machine.

- QA now uses the health-only LLM stub alongside dev, without requiring llama.cpp or a model. Production launches the real server using the executable and model paths from `DLlama` and `DQwen`.

## [0.1.1] - 2026-09-12 @ 03:15

### Changed

- Moved LLM, Ax3l, reporting, and MariaDB port numbers into their constants classes. Installers read the constants; existing port assignments are unchanged.

## [0.1.0] - 2026-09-12 @ 03:01

### Added

- Added a Scripts reference page, linked from the project home page, covering setup, service control, uninstall, and release commands.

- Added `scripts/services.sh -env dev|qa|prod start|stop`: starts the LLM, waits `DQwen.STARTUP_SECONDS` (7 seconds), then starts reporting, Ax3l, and watchdog. Shutdown uses the reverse order; service installation and uninstall follow the same ordering.

- Added four environment-specific systemd services: LLM, Ax3l, reporting, and watchdog. Dev runs health-only Ax3l/reporting skeletons and an explicitly labeled LLM health stub under `ax3l_dev`; the watchdog reports Ax3l systemd state and LLM health to the journal.

- Added `scripts/install-services.sh -env dev|qa|prod` to render unit templates, copy Python modules, and enable/start the selected environment's services. Uninstall now stops, disables, and removes those units.

- Added `scripts/uninstall.sh` with a required `-env dev|qa|prod` flag to remove the selected installation, credentials, MariaDB database/account, and Linux service account/group.

- Added `scripts/install.sh` with a required `-env dev|qa|prod` flag to create installation directories, provision local MariaDB databases and accounts (`ax3l_dev`, `ax3l_qa`, or `ax3l`), and generate owner-only credentials. Existing credentials are reused and database login is verified.

- Added dev installation support using `ax3l_prod/` and `prod_etc/`, with sudo for Linux account and directory setup and optional sudo for MariaDB provisioning. QA and production installations require root.

- Installation creates a Linux system user and group if absent (`ax3l_dev` for dev, `ax3l` for QA/prod), with no home directory or interactive login, and assigns application-directory ownership to that account and group.

### Changed

- Excluded disposable dev installation and credentials directories from Git.

## [0.0.4] - 2026-09-12 @ 01:11

### Changed

- Updated *Ax3l* logo!

- Site name in `_config.yml`

## [0.0.3] - 2026-09-12 @ 00:53

### Added

- GitHub Actions workflow to build and deploy the Jekyll site with GitHub Pages dependencies on pushes to `main` or manual runs, without requiring local Ruby.

## [0.0.2] - 2026-09-12 @ 00:29

## [0.0.1] - 2026-09-12 @ 00:21

### Added

- Initial release.

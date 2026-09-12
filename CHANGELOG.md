# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

- Added shared event display labels in `DEventDisplay`. The loop logs `wait_started`, displayed as `Sleep`; existing `sleep` events receive the same label. Hovering a label shows its raw event name. New sleep messages record `Sleep for seconds: (x)` using the configured interval.

- Expanded the development guidance for the fixed platform, clear module responsibilities, strict DAL, and thin slices without speculative defensive code. Moved it into `README.md` and updated the homepage and architecture links.

## [0.7.3] - 2026-09-12 @ 09:42

- Added the global `DAx3l.RAW_LOGS_ENABLED` flag, defaulting to `False`. The haiku loop creates no capture directories or files while disabled; database events and normal console/journal status remain available. Set it to `True` to restore raw captures. Existing captures are not deleted.

- Conversation replies now link from their assistant message text to a detail page showing the event envelope and every captured response field, including usage and timings.

## [0.7.2] - 2026-09-12 @ 09:25

- Gave the event log separate Time, ID, Level, Category, Event, and Message columns while retaining single-line striped rows.

## [0.7.1] - 2026-09-12 @ 09:20

- Made event log entries single-line rows with alternating dark/light backgrounds. Long entries truncate with an ellipsis; hover reveals the full entry.

- Styled the event log with a dark background, green monospace lettering, and bordered sections, controls, and log entries.

- The reporting event log now shows the newest entries first.

## [0.7.0] - 2026-09-12 @ 09:06

- Reporting now listens on `0.0.0.0` by default, including under systemd. The production event log is available at `http://neuromancer.osoyalce.com:28870/`. Use `--host 127.0.0.1` for local-only access.

## [0.6.0] - 2026-09-12 @ 09:00

- Added `DSnakeLab.HAIKU_SLEEP_SECONDS` (default: 5) to configure the delay between haiku requests and their logged wait messages.

- The haiku request count defaults to `DSnakeLab.HAIKU_COUNT` in `ax3l/constants/DSnakeLab.py` for manual and service runs. It is initially `0` (repeat until stopped); `--count` overrides it for manual runs.

### Service startup

- Production `ax3l-server` now starts the haiku loop against the local LLM while serving `/health`. Systemd supplies database credentials and a writable capture directory at `/var/lib/ax3l/haiku`. Stopping the service interrupts the loop and records conversation end. DEV/QA retain health-only startup because their model services are inference-free stubs.

Deploy from the updated checkout on PROD:

```bash
scripts/upgrade.sh -env prod -model qwenv
```

The loop starts automatically; stop any manually launched loop before upgrading.
Use `systemctl stop ax3l-server` to stop it. Jinja2 and PyMySQL must be available
to `/usr/bin/python3`; the upgrade does not install Python dependencies.

## [0.5.0] - 2026-09-12 @ 08:52

### Reporting

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

### Added

- Integrated `DbMgr.log()` into the haiku loop for linked conversation, prompt, full response, wait, and failure events. Load `DB_*` credentials before running; file capture remains available.

- Added `DbMgr.log()` to atomically store an event envelope and message, returning the event ID with optional process and parent-event links.

## [0.4.1] - 2026-09-12 @ 07:24

### Added

- Added `DbMgr` with MariaDB connection ownership, generic parameterized SQL methods, and transaction support. Initialization creates shared event envelope, message, list-item, and key/value tables. Verified against the disposable DEV database.

- Added a minimal SnakeLab haiku loop with a shared prompt class and LLM HTTP interface. Saves requests, complete response bodies, headers, and a run log; waits five seconds between requests.

### Running the haiku loop

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

### Changed

- Removed model service conflicts and automatic stopping/disabling of other models. Starting a model leaves existing model processes alone.

## [0.3.0] - 2026-09-12 @ 05:13

### Added

- Added `phi-server` alongside the renamed `qwen-server`, sharing the LLM port with mutually exclusive systemd units. Service control, installation, and upgrade accept `-model qwen|phi` (default Qwen); upgrade removes legacy `llm-server` units.

- Added `scripts/upgrade.sh -env dev|qa|prod` to update application modules and systemd units from the current checkout while preserving the database, credentials, and accounts.

### Fixed

- Service installation uses the shared `DLlama.MODEL_DIR` for the model path, keeping `DLlama.BASE_DIR` for llama.cpp.
- Service installation validates generated units and stops services before replacing application files.

## [0.2.2] - 2026-09-12 @ 04:25

### Added

- Added `--metrics` switch to `llama-server` to enable it

## [0.2.1] - 2026-09-12 @ 03:28

### Fixed

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

### Fixed

- Site name in `_config.yml`

## [0.0.3] - 2026-09-12 @ 00:53

### Added

- GitHub Actions workflow to build and deploy the Jekyll site with GitHub Pages dependencies on pushes to `main` or manual runs, without requiring local Ruby.

## [0.0.2] - 2026-09-12 @ 00:29

## [0.0.1] - 2026-09-12 @ 00:21

- Initial release.

---
title: Scripts
author_profile: true
layout: single
---

![Ax3l]({{ '/pages/images/ax3l.png' | relative_url }})

# Project Scripts

Run these commands from the project checkout as root. Ax3l uses one
configuration: `/opt/prod/ax3l`, `/etc/ax3l/database.env`, the `ax3l`
MariaDB database/account, and the `ax3l` Linux service account. Deployment
between machines is owned by DevOps; these helpers manage the local installation.
There is no environment selector or DEV/QA service variant.

| Script | Purpose | Command |
| --- | --- | --- |
| `install.sh` | Creates the installation, accounts, database, and credentials, then installs and starts the services. | `sudo scripts/install.sh` |
| `upgrade.sh` | Updates modules and service units, preserving the database, credentials, and accounts. | `sudo scripts/upgrade.sh` |
| `install-services.sh` | Copies modules, installs six systemd units, and starts the selected model and application services. | `sudo scripts/install-services.sh` |
| `services.sh` | Starts or stops services in dependency order. | `sudo scripts/services.sh start` or `sudo scripts/services.sh stop` |
| `uninstall.sh` | Removes service units, installation, credentials, database/account, and Linux account/group. **Deletes Ax3l data.** | `sudo scripts/uninstall.sh` |
| `backup-db.sh` | Dumps the configured Ax3l database to a private timestamped file. | `sudo scripts/backup-db.sh` |
| `wipe-db.sh` | Deletes Ax3l events and SnakeLab simulations, preserves schemas, and leaves services stopped. | `sudo scripts/wipe-db.sh` |

MariaDB must already be running for database setup/removal. These operations
use local root socket authentication.

The listeners use TCP ports **27770** for the model, **28870** for reporting,
and **61970** on loopback for Ax3l ZeroMQ.

Startup order: **LLM → wait 7 seconds → reporting → Ax3l → watchdog**.
The delay comes from `DQwen.STARTUP_SECONDS` or `DPhi.STARTUP_SECONDS`.
Shutdown stops the application services, then all model services.

Qwen3.5 (`qwen`, using `DQwen.GGUF`) is the default for text-only prompts. Select Phi with:

```sh
sudo scripts/services.sh start -model phi
```

Use `-model qwen`, `-model phi`, or `-model qwenv` to choose the server to
start. The helper enables and starts that model without checking or stopping
other models. All three use the same LLM port; an occupied port or insufficient
GPU memory is left for llama.cpp to report. Stop the running model yourself
before starting another. `services.sh stop` stops all model and
application services.

All six units are installed and upgraded together. `install-services.sh` and
`upgrade.sh` accept the same `-model` option to select the model started afterward;
Qwen remains the default. Upgrade removes the legacy `llm-server` unit.

Qwen Vision uses `DQwenV.GGUF`, `DQwenV.MMPROJ`, and a 4096-token context.
Place both GGUF files in `DLlama.MODEL_DIR` (`/opt/prod/models`) before starting
`qwenv-server` in production. It uses the shared executable configured by
`DLlama`, with `--mmproj`, `-c 4096`, and the existing host, port, and metrics options.
All models use their bundled chat templates with Jinja enabled. The former
Qwen2.5-VL tool-template override has been removed; use the default Qwen3.5 for
Snake Lab tool submissions.

To update the local installation, run `sudo scripts/upgrade.sh` from the
desired release checkout. Upgrade requires an existing installation and needs
no MariaDB administrative access. It does not pull Git changes or update
llama.cpp or model files. The real llama.cpp binary and selected model must
be installed before starting services; see the
[architecture]({{ '/pages/architecture' | relative_url }}).

## Releases

The operator runs releases:

```sh
scripts/new-release.sh <version> "Release message"
```

Run from a clean feature branch with local `dev` and `main` up to date. The script
updates the version and changelog, merges through `dev` to `main`, tags and pushes
the release, then creates the next feature branch. It does not deploy the release on a remote system.

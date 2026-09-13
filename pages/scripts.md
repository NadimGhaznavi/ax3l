---
title: Scripts
author_profile: true
layout: single
---

![Ax3l]({{ '/pages/images/ax3l.png' | relative_url }})

# Project Scripts

Run these commands from the project checkout. Environment commands require
`-env dev`, `-env qa`, or `-env prod`. Dev uses sudo where needed; the operator
runs QA/prod setup and service commands as root on the corresponding machine.

| Script | Purpose | Dev command |
| --- | --- | --- |
| `install.sh` | Creates the installation directory, Linux account/group, MariaDB database/account, and credentials, then installs and starts all four services. | `scripts/install.sh -env dev -db-admin-sudo` |
| `upgrade.sh` | Updates an existing installation's Python modules and systemd units from this checkout, preserving its database, credentials, and accounts. Stops services before updating and starts them afterward. | `scripts/upgrade.sh -env dev` |
| `install-services.sh` | Copies Python modules, installs six systemd units, enables the selected model and three application services, and stops/starts them in order. Called by `install.sh`; can also refresh services on an existing installation. | `scripts/install-services.sh -env dev` |
| `services.sh` | Starts or stops all four services in order. | `scripts/services.sh -env dev start` or `scripts/services.sh -env dev stop` |
| `uninstall.sh` | Stops and removes the units, then deletes the installation, credentials, database/account, and Linux account/group. **Deletes the selected environment's data.** | `scripts/uninstall.sh -env dev -db-admin-sudo` |

`-db-admin-sudo` is a dev-only option for MariaDB administration. QA/prod run
as root without it. MariaDB must already be running for database setup/removal.

Startup order: **LLM → wait 7 seconds → reporting → Ax3l → watchdog**.
The delay comes from `DQwen.STARTUP_SECONDS` or `DPhi.STARTUP_SECONDS`.
Shutdown stops the application services, then both model services.

Qwen3.5 (`qwen`, using `DQwen.GGUF`) is the default for text-only prompts. Select Phi with:

```sh
scripts/services.sh -env dev start -model phi
```

Use `-model qwen`, `-model phi`, or `-model qwenv` to choose the server to
start. The helper enables and starts that model without checking or stopping
other models. All three use the same LLM port; an occupied port or insufficient
GPU memory is left for llama.cpp to report. Stop the running model yourself
before starting another. `services.sh -env dev stop` stops all model and
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

To deploy changes, update your checkout to the desired release, then run
`scripts/upgrade.sh -env dev`, or as root on the target machine,
`scripts/upgrade.sh -env qa` or `scripts/upgrade.sh -env prod`.
Upgrade requires an existing installation and needs no MariaDB administrative
access. It does not pull Git changes or update llama.cpp or model files.

Dev and QA use a health-only LLM stub. Production service installation requires the real
llama.cpp binary and the selected model described in the
[architecture]({{ '/pages/architecture' | relative_url }}). Install the other
model file before switching to it in production.

## Releases

The operator runs releases:

```sh
scripts/new-release.sh <version> "Release message" [next-feature-branch]
```

Run from a clean feature branch with local `dev` and `main` up to date. The script
updates the version and changelog, merges through `dev` to `main`, tags and pushes
the release, then creates the next feature branch. It does not deploy the release.

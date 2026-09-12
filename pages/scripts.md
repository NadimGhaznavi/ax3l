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
| `install-services.sh` | Copies Python modules, installs/enables the four systemd units, and stops/starts them in order. Called by `install.sh`; can also refresh services on an existing installation. | `scripts/install-services.sh -env dev` |
| `services.sh` | Starts or stops all four services in order. | `scripts/services.sh -env dev start` or `scripts/services.sh -env dev stop` |
| `uninstall.sh` | Stops and removes the units, then deletes the installation, credentials, database/account, and Linux account/group. **Deletes the selected environment's data.** | `scripts/uninstall.sh -env dev -db-admin-sudo` |

`-db-admin-sudo` is a dev-only option for MariaDB administration. QA/prod run
as root without it. MariaDB must already be running for database setup/removal.

Startup order: **LLM → wait 7 seconds → reporting → Ax3l → watchdog**.
The delay is defined by `DQwen.STARTUP_SECONDS`. Shutdown reverses that order.

To deploy changes, update your checkout to the desired release, then run
`scripts/upgrade.sh -env dev`, or as root on the target machine,
`scripts/upgrade.sh -env qa` or `scripts/upgrade.sh -env prod`.
Upgrade requires an existing installation and needs no MariaDB administrative
access. It does not pull Git changes or update llama.cpp or model files.

Dev and QA use a health-only LLM stub. Production service installation requires the real
llama.cpp binary and Qwen model described in the
[architecture]({{ '/pages/architecture' | relative_url }}).

## Releases

The operator runs releases:

```sh
scripts/new-release.sh <version> "Release message" [next-feature-branch]
```

Run from a clean feature branch with local `dev` and `main` up to date. The script
updates the version and changelog, merges through `dev` to `main`, tags and pushes
the release, then creates the next feature branch. It does not deploy the release.

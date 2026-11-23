---
title: Scripts
author_profile: true
layout: single
---

![Ax3l]({{ '/pages/images/ax3l.png' | relative_url }})

# Project Scripts

Run these commands from the project checkout as root. Ax3l uses
`/opt/prod/ax3l`, `/etc/ax3l/database.env`, the `ax3l` MariaDB database/account,
and the `ax3l` Linux service account. Deployment between machines is owned by
DevOps; these helpers manage the local Ax3l installation.

Inference is provided by the independently managed [LlamaSrv](https://llamasrv.osoyalce.com/)
service. Ax3l's helpers manage only `ax3l-server.service`,
`reporting-server.service`, and `watchdog.service`.

| Script | Purpose | Command |
| --- | --- | --- |
| `install.sh` | Creates the installation, accounts, database, and credentials, then installs and starts Ax3l services. | `sudo scripts/install.sh` |
| `upgrade.sh` | Updates modules and service units, preserving the database, credentials, and accounts. | `sudo scripts/upgrade.sh` |
| `install-services.sh` | Copies modules, installs three systemd units, and starts Ax3l services. | `sudo scripts/install-services.sh` |
| `restart.sh` | Validates configuration, regenerates service units, and restarts Ax3l services. | `sudo scripts/restart.sh` |
| `services.sh` | Starts or stops Ax3l services in dependency order. | `sudo scripts/services.sh start` or `sudo scripts/services.sh stop` |
| `uninstall.sh` | Removes Ax3l service units, installation, credentials, database/account, and Linux account/group. **Deletes Ax3l data.** | `sudo scripts/uninstall.sh` |
| `backup-db.sh` | Dumps the configured Ax3l database to a private timestamped file. | `sudo scripts/backup-db.sh` |
| `wipe-db.sh` | Deletes Ax3l events and SnakeLab simulations, preserves schemas, and leaves services stopped. | `sudo scripts/wipe-db.sh` |

MariaDB must already be running for database setup/removal. These operations
use local root socket authentication. Installation requires Python's venv/pip
support and package-index access. Model binaries, weights, GPU drivers, and
inference settings belong to LlamaSrv.

## Network configuration

`DAx3l.CMDB_NETWORK` declares only listeners owned by Ax3l:

| Use | Interface | TCP port |
| --- | --- | --- |
| `report` | `0.0.0.0` | 28870 |
| `zmq` | `127.0.0.1` | 61970 |

Install and upgrade create `/opt/prod/ax3l/conf/ax3l.json` if missing and
preserve valid existing files. The generated file contains both listener
entries and the outbound `llamasrv_url` (default `http://127.0.0.1:51001`).
CMDB discovers the listener defaults in code;
LlamaSrv's ports belong to LlamaSrv's inventory.

For example, use a shared LlamaSrv on Wintermute and override the report port:

```json
{
  "llamasrv_url": "http://wintermute:51001",
  "network": {
    "report": {
      "port": 28871
    }
  }
}
```

Listener entries accept an IPv4 `interface` and an integer `port` from 1 to
65535. Omitted entries and fields use defaults. A missing file also uses
defaults. `llamasrv_url` accepts an HTTP(S) base URL without credentials,
path, query, or fragment; Ax3l appends `/v1/chat/completions`. Unknown settings,
invalid addresses or ports, malformed URLs, and malformed JSON fail with a
field-specific error.

Edit the configuration and apply it from the current release checkout:

```sh
sudoedit /opt/prod/ax3l/conf/ax3l.json
sudo scripts/restart.sh
```

The restart helper validates configuration and generated units before stopping
Ax3l services. It regenerates reporting, Ax3l, and watchdog units, reloads
systemd, and restarts them without installing code or Python dependencies.
Use it when changing listener settings, because a plain `systemctl restart`
does not regenerate listener arguments. Network values are cached per Python
process and reloaded in new processes. The shared LLM interface can use the configured LlamaSrv URL.

Internal ZeroMQ clients use `127.0.0.1` for a wildcard `0.0.0.0` binding.
Reporting's `--host`/`--port`, Ax3l's `--zmq-endpoint`, and the
`AX3L_ZMQ_ENDPOINT` variable remain available for individual invocations.
Database and SnakeLab connections retain their separate outbound settings.
Uninstall removes the application configuration with the application directory.

## Shared inference and service lifecycle

Provision LlamaSrv separately. The previous conversation and MCP tool
workflows have been removed; the Ax3l service currently runs without sending
inference requests. The configured LlamaSrv URL and shared HTTP interface
remain available for the replacement workflow.

Check the shared endpoint without sending an inference request:

```sh
curl -fsS http://wintermute:51001/health
curl -fsS http://wintermute:51001/props
```

Start the Ax3l listener with:

```sh
.venv/bin/python -m ax3l.server.Ax3lServer
```

The old optimization entry point and its `--url`, `--llm-url`, and `--output`
options have been removed. Fresh installations generate configuration without
the retired decision-grace setting.

Startup order is **reporting → Ax3l → watchdog**; shutdown uses the reverse
order. The watchdog recovers only Ax3l and reporting. LlamaSrv's configuration,
model selection, health recovery, and lifecycle are managed independently, so
stopping, upgrading, or uninstalling Ax3l leaves shared inference running.

To update the local installation, run `sudo scripts/upgrade.sh` from the
desired release checkout. Upgrade requires an existing installation and needs
no MariaDB administrative access. It does not pull Git changes.

## Releases

The operator runs releases:

```sh
scripts/new-release.sh <version> "Release message"
```

Run from a clean feature branch with local `dev` and `main` up to date. The script
updates the version and changelog, merges through `dev` to `main`, tags and pushes
the release, then creates the next feature branch. It does not deploy the release on a remote system.

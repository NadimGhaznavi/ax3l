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
| [wipe-experiment-workspace.sh](../scripts/wipe-experiment-workspace.sh) | Clears the current unsubmitted setup and restarts Ax3l from golden, preserving simulation history. | `sudo scripts/wipe-experiment-workspace.sh` |
| `wipe-db.sh` | Deletes Ax3l events and SnakeLab simulations, preserves schemas, and leaves services stopped. | `sudo scripts/wipe-db.sh` |

MariaDB must already be running for database setup/removal. These operations
use local root socket authentication. Installation requires Python's venv/pip
support and package-index access. Model binaries, weights, GPU drivers, and
inference settings belong to LlamaSrv.

## Restart an interrupted experiment setup

From the current project checkout on the server, run:

```sh
sudo scripts/wipe-experiment-workspace.sh
```

The helper checks database access using the installed Python environment and
the credentials in `/etc/ax3l/database.env`. It reads the credentials literally
and does not execute their contents. It then stops watchdog, Ax3l, and reporting
before clearing the current unsubmitted draft, saved edits (including any staged
seed change), conversations, and related tool and chart events. Event details
are deleted with their parent events in one transaction.

Golden, completed simulations, prior experiment history, and saved run analyses
remain available. Ax3l services start again afterward and prepare a fresh draft
from golden. SnakeLab and shared inference keep running. The helper runs code
from the checkout, so the helper itself does not require reinstalling Ax3l.

An experiment whose submission or seed rotation has started is refused. If
clearing fails, Ax3l services remain stopped and the deletion is rolled back.
Resolve the reported error before starting services again.

## Network configuration

`DAx3l.CMDB_NETWORK` declares only listeners owned by Ax3l:

| Use | Interface | TCP port |
| --- | --- | --- |
| `report` | `0.0.0.0` | 28870 |
| `zmq` | `127.0.0.1` | 61970 |

Install and upgrade create `/opt/prod/ax3l/conf/ax3l.json` if missing and
preserve valid existing files. The generated file contains both listener
entries, the outbound `llamasrv_url` (default `http://127.0.0.1:51001`), and
`decision_grace_seconds` (default `420`). CMDB discovers the listener defaults in code;
LlamaSrv's ports belong to LlamaSrv's inventory.

For example, use a shared LlamaSrv on Wintermute and override the report port:

```json
{
  "llamasrv_url": "http://wintermute:51001",
  "decision_grace_seconds": 420,
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

`decision_grace_seconds` must be a positive integer. It sets the grace countdown
after the seven-minute LLM decision budget, before Ax3l resets an initial
conversation or runs a saved unique draft. The default grace period is seven
minutes, including for existing files that omit this setting. The optimizer and
reporting service load it at startup; restart both services after changing it.
Prompts with an image add two minutes to the decision budget; the grace period
keeps its configured duration.

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
process and reloaded in new processes. The Ax3l process reads the LlamaSrv URL
from configuration when it starts.

Internal ZeroMQ clients use `127.0.0.1` for a wildcard `0.0.0.0` binding.
Reporting's `--host`/`--port`, Ax3l's `--zmq-endpoint`, and the MCP
`AX3L_ZMQ_ENDPOINT` variable remain available for individual invocations.
Database and SnakeLab connections retain their separate outbound settings.
Uninstall removes the application configuration with the application directory.

## Shared inference and service lifecycle

Provision LlamaSrv separately and make sure its selected model supports the
vision inputs and tool calls used by Ax3l. The production model is Qwen3.5-4B
with its vision projector. Applications share the loaded model; Ax3l supplies
its tool definitions per request and executes tools through private MCP
sessions. No Ax3l tools are registered globally with the inference service.

Check the shared endpoint without sending an inference request:

```sh
curl -fsS http://wintermute:51001/health
curl -fsS http://wintermute:51001/props
```

Both optimization entry points use the configured endpoint by default:

```sh
.venv/bin/python -m ax3l.server.Ax3lServer
.venv/bin/python -m ax3l.app.snakelab.main-loop
```

For an individual invocation, `Ax3lServer --llm-url http://HOST:51001` or
`main-loop --url http://HOST:51001` overrides the configured URL.

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

# UC-01: Deploy Ax3l software — Design realization

[Analysis realization](../analysis/uc-01-deploy-ax3l-software.md) ·
[Use case](../use-case/uc-01-deploy-ax3l-software.md) ·
[Design View](index.md) · [Glossary](../glossary.md)

**Status:** Initial draft, checked against the current installation code.

## Analysis to design

| Analysis participant | Design realization |
| --- | --- |
| Deployment interface | [install.sh](../../scripts/install.sh) accepts the request and prints usage, progress, and errors. |
| Deployment control | [install.sh](../../scripts/install.sh) checks eligibility and provisions accounts and storage, then invokes [install-services.sh](../../scripts/install-services.sh) to prepare the runtime, install files, and activate services. |
| Host access | The scripts invoke host commands and the MariaDB client. [application-files.sh](../../scripts/application-files.sh) selects and installs application files, [service-configuration.sh](../../scripts/service-configuration.sh) renders and registers service definitions, and [services.sh](../../scripts/services.sh) controls their lifecycle. |
| Deployment source | The selected checkout supplies application modules, resources, [requirements.txt](../../requirements.txt), and [service templates](../../systemd/). |
| Installation resources | Directories, Linux accounts, MariaDB resources, and systemd definitions hold the installation state. The installer detects these resources directly. |
| Database credentials | A private connection-settings file validated and reused or created by [install.sh](../../scripts/install.sh). |
| Application configuration | [Configuration](../../ax3l/interface/Configuration.py) owns the configuration file and its validation. [Network](../../ax3l/interface/Network.py) exposes resolved listener values. Defaults come from [DAx3l](../../ax3l/constants/DAx3l.py). |

```mermaid
flowchart LR
    devops["DevOps"] --> installer["install.sh"]
    installer --> database["MariaDB client"]
    installer --> services["install-services.sh"]
    services -.->|sources| settings["service-configuration.sh"]
    services -.->|sources| files["application-files.sh"]
    settings --> configuration["Configuration and Network"]
    configuration --> defaults["DAx3l"]
    services --> lifecycle["services.sh"]
    settings --> systemd["systemd tools"]
    lifecycle --> systemd
```

The diagram shows principal calls and the sourced shell helper. Host account
and file operations are performed by commands within the scripts.

## Interfaces and ownership

| Interface | Contract |
| --- | --- |
| `install.sh` | Root-only installation from the local checkout, with no deployment arguments. `-h` and `--help` display usage. Existing installation resources cause refusal before provisioning. |
| `install-services.sh` | Requires the provisioned installation directory and credentials. Installs dependencies and application files, then enables and starts the three Ax3l services. |
| `install_application_files()` | Receives the checkout directory, installation directory, and Linux account name. Copies selected application files and propagates discovery and copy failures. |
| `resolve_service_configuration()` | The caller supplies `checkout_dir`, `install_dir`, and `config_dir`. The function creates or validates application configuration through Python and sets `report_host`, `report_port`, and `ax3l_zmq_endpoint` in the calling shell. |
| `render_service_units()` | Uses those paths and listener values to render the three service templates. Sets `unit_dir` and `units`, validates the result, and arranges temporary-directory cleanup when the shell exits. |
| `install_service_units()` | Consumes the rendered units, installs them into systemd's configuration directory, reloads systemd, and enables the services. Starting them is a separate step. |
| `services.sh start` / `stop` | Root-only service control. Start order is reporting, experiment, watchdog. Stop order is watchdog, experiment, reporting, skipping units that are not loaded. |

The three configuration functions are sourced into the service installer's
shell. Configuration resolution launches a Python child process whose output
contains the reporting host, reporting port, and Ax3l ZeroMQ endpoint.

`Configuration.install()` creates the default file for this fresh installation.
`Network.binding("report")` returns the reporting host and port;
`Network.endpoint()` returns the ZeroMQ listener address. Network caches resolved
configuration within its Python process.

## Deployment collaboration

The sequence shows the successful path. Each failing command ends its stage and
prevents subsequent stages from running.

```mermaid
sequenceDiagram
    actor DevOps
    participant Install as install.sh
    participant DB as MariaDB client
    participant Services as install-services.sh
    participant Settings as service-configuration.sh
    participant Files as application-files.sh
    participant Lifecycle as services.sh
    participant Systemd as systemd tools

    DevOps->>Install: Install from local checkout
    Install->>Install: Check existing resources, prerequisites, and saved credentials
    Install->>DB: Check administrative access and absence of Ax3l database/account
    DB-->>Install: Administrative access confirmed, database/account absent
    Install->>Install: Create Linux account/group and directories, retain or save credentials
    Install->>DB: Create database/account and grant access
    Install->>DB: Verify application database login
    DB-->>Install: Login succeeded
    Install->>Services: Install application and services
    Services->>Settings: resolve_service_configuration()
    Settings->>Settings: Configuration.install(), then Network accessors
    Settings-->>Services: Reporting host/port and ZeroMQ endpoint
    Services->>Services: Prepare Python dependencies and verify browser PNG rendering
    Services->>Settings: render_service_units()
    Settings->>Systemd: systemd-analyze verify
    Systemd-->>Settings: Definitions valid
    Services->>Lifecycle: stop
    Lifecycle->>Systemd: Stop loaded units in watchdog, experiment, reporting order
    Lifecycle-->>Services: Services stopped or not loaded
    Services->>Files: install_application_files(checkout, target, account)
    Files-->>Services: Application files installed
    Services->>Services: Set configuration-directory permissions
    Services->>Settings: install_service_units()
    Settings->>Settings: Install rendered definitions
    Settings->>Systemd: daemon-reload and enable
    Services->>Lifecycle: start
    Lifecycle->>Systemd: Start in reporting, experiment, watchdog order
    Systemd-->>Lifecycle: Start commands succeeded
    Lifecycle-->>Services: Services started
    Services-->>Install: Installed services
    Install-->>DevOps: Successful exit
```

## Resource contracts

| Resource | Contract |
| --- | --- |
| Credentials | A private file containing exactly five fields: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`. The password is 64 hexadecimal characters. The file is parsed as data. |
| Database | Local `ax3l` database and `ax3l` account at `localhost`. Installation uses administrative socket access, grants full access to the Ax3l database and read access to SnakeLab, then verifies the application login. The database port default comes from [DDbMgr](../../ax3l/constants/DDbMgr.py). |
| Application configuration | Contains `network.report`, `network.zmq`, and `llamasrv_url`. Validation belongs to `Configuration`. This file is separate from database credentials. |
| Service definitions | The [experiment](../../systemd/ax3l-server.service), [reporting](../../systemd/reporting-server.service), and [watchdog](../../systemd/watchdog.service) templates receive resolved paths, listener values, and launch arguments. |

## Failure and completion contracts

- Help returns `0`, unsupported installation arguments return `2`, and explicit
  precondition failures return `1`. Failures in invoked commands propagate their
  failing status.
- Provisioning is not a transaction across host, database, and service resources.
  Completed changes can remain after failure.
- Configuration resolution, dependency installation, browser verification, and
  service-definition validation precede the service-stop step.
- Successful service-start commands complete deployment. The service templates
  use `Type=simple`; deployment performs no application-health or simulation check.
- [EXT-01](../use-case/index.md#external-use-cases) is an operator-managed external
  prerequisite. These scripts neither perform nor verify SnakeLab cleanup.

## Implementation realization

[Deployment implementation](../implementation/uc-01-deploy-ax3l-software.md)
records the source organization, installed files, runtime entry points, and
verification of these contracts.

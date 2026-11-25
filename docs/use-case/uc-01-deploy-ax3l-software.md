# UC-01: Deploy Ax3l software

[Use Case View](index.md) · [Glossary](../glossary.md)

**Status:** Initial draft, checked against the current installation code.

**Goal:** Create a fresh Ax3l installation from a local checkout and start its
services on that host.

**Primary actor:** [DevOps](../glossary.md#devops).

**Trigger:** DevOps invokes installation from the selected checkout.

## Preconditions

- The Ax3l checkout and its supporting installation files are present locally.
- The target meets the [fresh installation](../glossary.md#fresh-installation)
  conditions.
- If SnakeLab contains earlier experiment data, DevOps has cleared it through
  [EXT-01](index.md#external-use-cases). Ax3l does not perform or verify this step.
- DevOps can run installation as root on a host using systemd.
- Local MariaDB is running and permits administrative access through its local
  socket. The MariaDB client and OpenSSL are installed.
- Python 3, virtual-environment and package-installation support, and the host
  libraries needed for chart rendering are available. Python packages and the
  chart-rendering browser can be obtained.

## Main flow

1. DevOps initiates installation without deployment options; the
   installed software comes from the checkout being used.
2. Installation checks root privileges, existing installation resources, required
   commands, saved credentials, and administrative access to MariaDB. It refuses
   an existing installation before creating resources or changing services.
3. It creates the Ax3l Linux account, group, and installation directories, reusing
   saved database credentials or generating and saving new credentials.
4. It creates the Ax3l database and database account, grants access
   to Ax3l's database and read access to SnakeLab's database, and verifies the
   Ax3l database login.
5. It creates the default application configuration.
6. It prepares the Python environment, installs dependencies and the browser
   used for charts, and verifies PNG rendering.
7. It prepares and validates Ax3l's service definitions, stops any loaded Ax3l
   services, and copies application modules and supporting resources.
8. It installs and enables the service definitions, then starts reporting,
   the experiment service, and the watchdog in that order.
9. It reports the installed services to DevOps.

## Alternatives and failures

- **[Existing or partial installation](../glossary.md#existing-installation):**
  Refuse installation and direct DevOps to uninstall first. Uninstallation deletes
  Ax3l's application files and experiment data, retaining database credentials for
  the next installation.
- **Saved [database credentials](../glossary.md#database-credentials) only:**
  Validate and reuse them.
- **Invalid credentials file:** Reject a file with incorrect ownership,
  permissions, format, or installation settings, or one that is a symbolic link.
- **Database access failure:** Stop if administrative access or the newly created
  Ax3l account's login fails.
- **Configuration, dependency, browser, or service-definition failure:** Stop
  before the service-stop step. Earlier provisioning changes may already exist;
  DevOps uninstalls those resources before attempting another installation.
- **File installation or service startup failure:** Stop with a failing exit
  status. Some files may have been replaced and some services may remain stopped
  or already have started.
- **Help or unsupported arguments:** Display usage without installing. Help
  succeeds; unsupported arguments return a failing exit status.

## Outcome

On success, application files and dependencies are installed, database login
and PNG rendering have been verified, and all three service-start commands have
succeeded. Services are enabled for subsequent host startup. Ax3l has a newly
created database; runtime services initialize its tables and begin recording data.

Installation performs no application-health or end-to-end simulation check.
Successful completion does not establish that SnakeLab or LlamaSrv is reachable
or that an experiment has run successfully.

On failure, installation provides no automatic rollback. Provisioning and file
changes already made may remain. Saved credentials are retained so a later
installation after uninstall can reuse them.

## Scope

Installation uses the fixed local Ax3l installation and configuration locations.
It does not fetch a release, select a version through command-line options,
transfer software between hosts, or install or manage SnakeLab or LlamaSrv.

## Behavior references

- [Installation entry point](../../scripts/install.sh).
- [Uninstallation](../../scripts/uninstall.sh), used before replacing an existing
  installation and preserving credentials for the next deployment.
- [Service installation](../../scripts/install-services.sh) and
  [chart-browser provisioning](../../scripts/install-chrome.py).
- [Service configuration](../../scripts/service-configuration.sh),
  [application configuration](../../ax3l/interface/Configuration.py), and
  [service control](../../scripts/services.sh).

## Analysis realization

[Deployment analysis](../analysis/uc-01-deploy-ax3l-software.md) identifies the
participants, responsibilities, and collaboration that realize this use case.

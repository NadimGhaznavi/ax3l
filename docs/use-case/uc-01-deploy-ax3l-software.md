# UC-01: Deploy Ax3l software

[Use Case View](index.md)

**Status:** Initial draft, checked against the current installation code.

**Goal:** Install Ax3l from a local checkout and start its services on that host.

**Primary actor:** Administrator.

**Trigger:** The administrator invokes installation from the selected checkout.

## Preconditions

- The Ax3l checkout and its supporting installation files are present locally.
- The administrator can run installation as root on a host using systemd.
- Local MariaDB is running and permits administrative access through its local
  socket. The MariaDB client and OpenSSL are installed.
- Python 3, virtual-environment and package-installation support, and the host
  libraries needed for chart rendering are available. Python packages and the
  chart-rendering browser can be obtained.

## Main flow

1. The administrator initiates installation without deployment options; the
   installed software comes from the checkout being used.
2. Installation checks root privileges, the MariaDB client and OpenSSL, any
   existing credentials, and administrative access to MariaDB.
3. It creates any missing Ax3l Linux account, group, and installation directories,
   and saves generated database credentials when none exist.
4. It creates the Ax3l database and database account if missing, grants access
   to Ax3l's database and read access to SnakeLab's database, and verifies the
   Ax3l database login.
5. It validates the application configuration, creating defaults if the file
   is missing and preserving a valid existing file.
6. It prepares the Python environment, installs dependencies and the browser
   used for charts, and verifies PNG rendering.
7. It prepares and validates Ax3l's service definitions, then stops existing
   Ax3l services before copying application modules and supporting resources.
8. It installs and enables the service definitions, then starts reporting,
   the experiment service, and the watchdog in that order.
9. It reports the installed services to the administrator.

## Alternatives and failures

- **Existing installation:** Reuse valid configuration and saved credentials.
  Existing database account passwords are not reset, and existing experiment
  data is not deleted by installation.
- **Invalid credentials file:** Reject a file with incorrect ownership,
  permissions, format, or installation settings, or one that is a symbolic link.
- **Database access failure:** Stop if administrative access or the Ax3l login
  fails. A mismatch with an existing account password requires administrator
  intervention; installation does not reset it.
- **Configuration, dependency, browser, or service-definition failure:** Stop
  before the service-stop step. Earlier provisioning changes may already exist.
- **File installation or service startup failure:** Stop with a failing exit
  status. Some files may have been replaced and some services may remain stopped
  or already have started.
- **Help or unsupported arguments:** Display usage without installing. Help
  succeeds; unsupported arguments return a failing exit status.

## Outcome

On success, application files and dependencies are installed, database login
and PNG rendering have been verified, and all three service-start commands have
succeeded. Services are enabled for subsequent host startup.

Installation performs no application-health or end-to-end simulation check.
Successful completion does not establish that SnakeLab or LlamaSrv is reachable
or that an experiment has run successfully.

On failure, installation provides no automatic rollback. Provisioning and file
changes already made may remain. Saved credentials are retained so a later
attempt can reuse them.

## Scope

Installation uses the fixed local Ax3l installation and configuration locations.
It does not fetch a release, select a version through command-line options,
transfer software between hosts, or install or manage SnakeLab or LlamaSrv.

## Behavior references

- [Installation entry point](../../scripts/install.sh).
- [Service installation](../../scripts/install-services.sh) and
  [chart-browser provisioning](../../scripts/install-chrome.py).
- [Service configuration](../../scripts/service-configuration.sh),
  [application configuration](../../ax3l/interface/Configuration.py), and
  [service control](../../scripts/services.sh).

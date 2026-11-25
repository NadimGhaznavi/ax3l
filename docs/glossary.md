# Glossary

[Application documentation](index.md)

Shared terminology for all four documentation views. Views link directly to
these definitions; each view describes the scenarios and responsibilities
relevant to its purpose.

## Actor

A role outside the system boundary that interacts with the system. An actor
may be a person, an organization, or another application.

## Analysis View

The view describing the conceptual responsibilities, information, and
collaborations needed to realize the use cases.

## Ax3l

The application that coordinates language-model proposals, SnakeLab simulations,
result comparisons, and reporting. Its deployment tools are part of its system
boundary.

## Ax3l experiment data

Ax3l-owned event history, experiment checkpoints, reporting records, and cached
game images. SnakeLab owns its simulation configurations, episodes, and results
separately.

## Boundary

An analysis role that mediates interaction with an actor or an external resource.
Concrete technology access is specified in the Design View.

## Control

An analysis role that coordinates a use case's collaborating participants,
sequences their work, and makes workflow decisions.

## Database credentials

The connection settings and password used by Ax3l's database account: host, port,
database name, username, and password. Saved credentials are held in a private
file, separate from application configuration.

## Deployment

The process of making Ax3l available on a host by installing its software,
preparing its resources, configuring its services, and starting them.

## Design View

The view describing the concrete software elements, interfaces, dependencies,
and mechanisms that realize the analysis responsibilities.

## DevOps

The operational role responsible for deploying Ax3l and arranging its external
prerequisites. This is the primary actor for deployment.

## Entity

An analysis role representing information or resource state relevant to the
application. It may be transient or persistent.

## Existing installation

The presence of any Ax3l application directory, installed service unit, Linux
account or group, or application database or database account. A partial
installation also meets this definition. Saved [database credentials](#database-credentials)
alone do not constitute an existing installation.

## External use case

An actor's goal owned by another system. Ax3l's documentation records it when
an Ax3l use case depends on it; its detailed behavior belongs to the other system.

## Fresh installation

An installation on a host with no [existing Ax3l installation](#existing-installation).
Valid saved [database credentials](#database-credentials) may remain from an
earlier installation.

## Host

The machine on which Ax3l is installed and its services run. Deployment operates
on the host containing the selected source checkout.

## Implementation View

The view mapping the design to source packages, modules, scripts, supporting
resources, executables, and tests.

## Interface

The public contract through which a software element is used. Examples include
command-line arguments, a shell function's inputs and outputs, and Python methods.

## Interface class

The project's code-class category for a bridge to a technology, API, protocol,
or application component, as defined in the
[coding guidelines](../pages/coding-guidelines.md#classify-classes-by-responsibility).
A [boundary](#boundary) describes an analysis role; an interface class is a
concrete code element.

## LlamaSrv

The independently managed application that hosts the language model and provides
inference to Ax3l.

## MariaDB

The database platform used by Ax3l and SnakeLab. Each application owns its own
database, even when both use the same MariaDB server.

## SnakeLab

The external application that trains the Snake AI, runs simulations, and supplies
their status, results, and captured games.

## System boundary

The scope of the system being described: which responsibilities belong to Ax3l
and which belong to actors or external systems.

## systemd

The host's service manager, used to register, enable, start, and stop Ax3l's
services.

## Use case

An actor's goal and the observable interactions that achieve it, including
the main flow, alternatives, failures, and outcomes.

## Use Case View

The view describing the system boundary, actors, their goals, and the system's
observable behavior through use cases.

## Use-case realization

The explanation of how collaborating elements fulfill a use case's scenarios.
An analysis realization describes conceptual responsibilities; a design
realization describes the concrete software collaborators.

## Watchdog

The Ax3l service that monitors the experiment and reporting services and restarts
them when inactive or failed. It does not manage SnakeLab or LlamaSrv.

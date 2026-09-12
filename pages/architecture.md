---
title: Architecture
author_profile: true
layout: single
---

![Ax3l]({{ '/pages/images/ax3l.png' | relative_url }})

# Architecture

Ax3l centers on the LLM's intelligence to execute processes. Users interact through
conversations with the Ax3l server, which owns orchestration, persistent workflow
state, and access to tools. The following describes the intended architecture;
implementation proceeds in thin, working slices.

## Components

### Ax3l server

- Defines the API for conversations and tool execution, including available operations, input/output contracts, and authorization.
- Owns the main loop for conversations and autonomous workflows.
- Supplies conversation context, relevant database data, and tool definitions to the LLM.
- Validates model outputs and tool requests, authorizes actions, and dispatches permitted calls.
- Executes tools locally or forwards requests to MCP servers, then records results and returns them to the conversation.
- Persists the state needed to continue work after a restart.

### llama-server

- Hosts the LLM and provides inference to Ax3l.
- Receives context and tool definitions from Ax3l and returns model responses, including tool-call requests.
- Tool execution belongs to Ax3l. The llama-server web interface is outside the user conversation flow.
- The intended systemd service launches the llama.cpp server binary directly; no Python wrapper is needed for the current responsibilities.

### MCP servers and tools

- Provide capabilities behind Ax3l's API.
- Ax3l connects to MCP servers through interface classes and controls which tools are available to the LLM.
- Tool implementations can be added or modified behind that boundary as a slice requires them.

### MariaDB

- Stores application data, history, results, and events.
- Also stores Ax3l's own execution state, including conversation and workflow progress needed for continuity.
- Completed state survives restart. Partial data is deleted and execution continues from the stored state.

### Reporting server

- Reads from MariaDB.
- Presents current state and history.

### Watchdog service

- Monitors the `ax3l-server` service through systemd.
- Monitors `llm-server` through its `/health` endpoint.

## Conversation and tool flow

1. A user sends a message to Ax3l through its conversation API.
2. Ax3l prepares the context and available tool definitions and requests inference from llama-server.
3. The LLM returns a response or requests a tool call.
4. Ax3l validates and authorizes the tool request, then executes it locally or forwards it to the appropriate MCP server.
5. Ax3l records the tool result and includes it in the conversation for the next inference request.
6. Ax3l continues the conversation and returns responses to the user.

Autonomous workflows use the same Ax3l-controlled inference and tool execution path.

## API and security boundary

Ax3l is the security chokepoint for all tool execution. The LLM requests actions;
Ax3l determines which actions are permitted and executes or forwards them. Tools
are never invoked directly by the LLM or conversation client outside Ax3l.

Ax3l owns the public contracts even when an MCP server supplies the underlying
capability. Connecting to an MCP server does not automatically expose all of its
tools to the LLM. Ax3l controls the available operations and validates their inputs
at the interface boundary. Contract and type violations fail immediately with
clear errors.

## Class responsibilities

We use the Common Unified Development Process class roles:

- **Interface classes** communicate with external systems such as MariaDB, llama-server, and MCP servers. A distinct DB interface class owns sessions, connection pooling, and database access.
- **Entity classes** represent persistent storage data loaded from the database, including application data and Ax3l's execution state.
- **Activity classes** transform data—the T in ETL. They do not store state.

Use many small modules with one clear responsibility. MariaDB holds the durable
state needed for LLM workflow continuity.

## Implementation approach

### Current service skeleton

The four systemd definitions in `systemd/` are templates rendered by
`scripts/install-services.sh`, which is called automatically by `scripts/install.sh`
after provisioning the Linux account, database, and credentials. Install and start
the full dev environment with:

```sh
scripts/install.sh -env dev -db-admin-sudo
```

Dev runs under `ax3l_dev`. QA and production installation is performed by the
operator as root, using `-env qa` or `-env prod` on the corresponding machine.

| Service | Dev unit | Dev endpoint |
| --- | --- | --- |
| LLM | `llm-server-dev.service` | `http://127.0.0.1:18080/health` |
| Ax3l | `ax3l-server-dev.service` | `http://127.0.0.1:18081/health` |
| Reporting | `reporting-server-dev.service` | `http://127.0.0.1:18082/health` |
| Watchdog | `watchdog-dev.service` | Reports to the systemd journal |

QA units use a `-qa` suffix and ports 28080–28082. Production units have no
environment suffix. Port assignments are defined in `DLlama`, `DAx3l`, and
`DReportMgr`. The production LLM binds to `DLlama.HOST` (`0.0.0.0`) for access
from the dev machine at `http://<production-host>:27770`. Other HTTP endpoints
bind to localhost.

For this slice, Ax3l and reporting implement only `/health`; conversations,
report queries, and workflow persistence are not implemented yet. Dev and QA use
an explicitly labeled health-only LLM stub that provides no inference and requires
no model or GPU. Production launches the real llama.cpp binary directly, using
the executable path from `DLlama` and model path from `DQwen`. Their current paths
are `/opt/prod/llama.cpp/bin/llama-server` and
`/opt/prod/models/Qwen3.5-4B-Q4_K_M.gguf` respectively.

The watchdog checks Ax3l's systemd state and the LLM health endpoint every ten
seconds. It logs the observations without restarting services. The units do not
automatically restart on failure, so failures remain visible.

Use the helper to start or stop the four services together:

```sh
scripts/services.sh -env dev start
scripts/services.sh -env dev stop
```

Startup runs in this order: LLM, a seven-second wait defined by
`DQwen.STARTUP_SECONDS`, reporting, Ax3l, then watchdog. Shutdown reverses the
order: watchdog, Ax3l, reporting, then LLM. The wait is a fixed startup allowance
for Qwen GGUF, not a health check. QA/prod use the same helper as root with the
corresponding `-env` value. Service installation uses the helper for its stop/start
sequence; these commands do not change systemd's boot ordering.

`scripts/uninstall.sh -env <environment>` stops, disables, and removes that
environment's units before deleting its installation and database resources.

### Development rules

- Establish the skeleton architecture through short iterations and thin, working slices.
- Implement only the data, behavior, and modules needed by the current slice.
- Use explicit contracts and correct types; fail fast and hard when they are violated.
- Add complexity and handle "what ifs" when they are encountered. Do not add speculative abstractions, defensive recovery paths, or dead code.
- Follow the [development style]({{ '/' | relative_url }}#development-style) documented on the project home page.

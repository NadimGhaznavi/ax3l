---
title: Runtime Behaviour
author_profile: true
layout: single
---

Ax3l is being prepared for a new conversation flow. The previous optimization
and analysis conversations, draft state, prompts, tools, and recovery logic
have been removed. Earlier implementations remain available in Git history.

## Ax3l server

`python -m ax3l.server.Ax3lServer` starts the configured ZeroMQ listener.
Startup initializes the shared event tables through `DbMgr` and closes that
database connection before listening.
The server waits for requests and returns an `unknown_method` error for domain
actions while no conversation workflow is installed. It does not contact the
LLM, create configuration drafts, or submit simulations. SIGINT stops the
listener and returns exit status 130.

## Reporting and services

The reporting server continues to display the event log, simulation details,
high-score games, golden configurations, score distribution, and simulation
metrics. The flow-specific Experiment Status and analysis-image endpoints
have been removed.

The watchdog continues to monitor the Ax3l and reporting services. SnakeLab
and shared LlamaSrv inference remain independently managed dependencies.
See [Architecture](/pages/architecture) and [Project Scripts](/pages/scripts)
for configuration and service operations.

---

[Back](/)

---
title: The Ax3l Project
author_profile: true
layout: single
---

![Ax3l Logo](/pages/images/ax3l.png)

# The Ax3l Project

The current phase involves setting up the environment.

---

# Components

- The `llama-server`
- Watchdog service monitoring `ax3l-server` through systemd and `llm-server` through `/health`
- The Ax3l agent service
- An Ax3l report service
- MariaDB for data persistence

---

# Development Style

- Work in short iterations with thin, working slices that establish the skeleton architecture.
- Implement only the data and behavior the current slice needs. Add complexity and handle "what ifs" when we encounter them; do not write speculative or dead code.
- Use many small, focused modules that each do one thing well.
- Follow the Common Unified Development Process class roles: interfaces communicate with external systems, entities represent persistent data loaded from the DB, and activities transform data without storing state—the T in ETL.
- Use a distinct DB interface class to own sessions, connection pooling, and database access.
- Lean on MariaDB for both application data and the application's own state. Persist enough state to delete partial data on restart and continue LLM workflows.
- Use explicit contracts and correct types. Validate at interfaces; fail fast and hard with a clear error when a contract or type is wrong, then fix the cause.
- No fallback parsing, silent defaults, repair prompts, or retries for contract violations.
- No defensive code for hypothetical failures. Add handling when an observed problem or current requirement calls for it.
- Keep the code lean, clear, and easy to follow.

---

# Links

- [Architecture](/pages/architecture)
- [Scripts](/pages/scripts)
- [OS Setup](/pages/os-setup)
- [Driver Setup](pages/driver-setup)

---

## Models

- [Qwen Model Setup](pages/qwen-model-setup)
- [Phi Model Setup](/pages/phi-model-setup)

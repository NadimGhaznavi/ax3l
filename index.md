---
title: The Ax3l Project
author_profile: true
layout: single
---

![Ax3l Logo](/pages/images/ax3l.png)

# The Ax3l Project

The current phase involves setting up the environment.

# Components

- The `llama-server`
- LLM watchdog service
- The Ax3l agent service
- An Ax3l report service
- MariaDB for data persistence

# Development Style

- Only the data and behavior that slice actually needs.
- No fallback parsing, silent defaults, repair prompts, or retries for contract violations.
- Validate at the boundary; if the contract is broken, raise a clear error and fix the cause.
- Keep the code lean and clean

# Links

- [OS Setup](/pages/os-setup)
- [Driver Setup](pages/driver-setup)
- [Model Setup](pages/model-setup)


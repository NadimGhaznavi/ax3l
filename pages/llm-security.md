---
title: LLM Security Architecture
author_profile: true
layout: single
---

The LLM is sandboxed.

Ax3l is the security chokepoint for all tool execution. The LLM requests actions;
Ax3l determines which actions are permitted and executes or forwards them. Tools
are never invoked directly by the LLM or conversation client outside Ax3l.

Ax3l owns the public contracts even when an MCP server supplies the underlying
capability. Connecting to an MCP server does not automatically expose all of its
tools to the LLM. Ax3l controls the available operations and validates their inputs
at the interface boundary. Contract and type violations fail immediately with
clear errors.

---

[Back](/)
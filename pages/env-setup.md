---
title: Environment Setup
author_profile: true
layout: single
---

![Ax3l]({{ '/pages/images/ax3l.png' | relative_url }})

- [OS Setup](/pages/os-setup)
- [Shared LlamaSrv setup](https://llamasrv.osoyalce.com/pages/environment-setup.html)
- [Ax3l installation and configuration](/pages/scripts)

Provision LlamaSrv independently with the Qwen3.5-4B model and its vision
projector. Ax3l connects to its shared inference endpoint, normally port
`51001`; configure `llamasrv_url` in `/opt/prod/ax3l/conf/ax3l.json` when the
service runs on another host. Ax3l itself needs no model files or GPU setup.

---

[Back](/)

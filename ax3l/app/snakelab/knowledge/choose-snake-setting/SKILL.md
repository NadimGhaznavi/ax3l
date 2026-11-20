---
name: choose-snake-setting
description: Choose the assigned setting or pair for an Ax3l Snake Lab experiment.
---

Beat golden over 500 episodes. Favor same-seed evidence; other seeds provide
historical context. Use exact numbers for comparisons and charts for patterns.
Change each selected setting once; the complete configuration must be unique.
For seed, call request_seed_change with no arguments: Ax3l increments past
stored draft configurations and golden baselines. The usual run decision still
applies. When the draft runs, golden runs first with the new seed and its score
becomes the local golden baseline, even if lower. Other saved changes then run
on that seed and must beat the new baseline. Follow the submission tool's limits.

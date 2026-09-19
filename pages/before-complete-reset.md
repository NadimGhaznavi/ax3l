---
title: Before Complete Reset
author_profile: true
layout: single
---

# To Be Developed before the next Wipe/Reset

## DB Collation Mismatch

The *Snake Lab* and *Ax3l* DBs are using different collation settings making cross DB comparisons cumbersome.

| Collation               | What it means                                                        | Good for                   |
| ----------------------- | -------------------------------------------------------------------- | -------------------------- |
| `utf8mb4_unicode_ci`    | Older Unicode linguistic comparison, case-insensitive                | Human text                 |
| `utf8mb4_uca1400_ai_ci` | Newer Unicode 14 linguistic comparison, accent- and case-insensitive | Human text                 |
| `utf8mb4_bin`           | Compare characters essentially by their encoded values               | IDs, tokens, exact strings |

Fix: Standardize all databases to use the `utf8mb4_uca1400_ai_ci` standard.

# Release 1.0.8

- Include the Ax3l project version number in the *simulation submitted* db record.

# Release 0.99.14

- Remove unused `simulation_runs.config` field from the DB
- "Prompt (GoldenConfig)" Report Server feature
  - Add a `source_name` column to the logs DB table
  

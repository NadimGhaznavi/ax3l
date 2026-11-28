# Changelog

All changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Summary

Keep image prompts brief across all experiment views.

### Removed

- Remove detailed chart explanations and repeated analysis advice from evaluation,
  selection, and baseline prompts, leaving a brief cue identifying the runs shown.

## [5.0.8] - 2026-11-27 @ 19:41

### Summary

Restore report rendering and seed rotation by correcting the shared loss-limit
constant's name.

### Fixed

- Fix the misspelled `SEED_ROTATION_FAILURES` declaration that caused report
  requests and experiment transitions to fail with `AttributeError`.

## [5.0.7] - 2026-11-27 @ 19:36

### Changed

- HTTP timeout increased to 1,200 seconds to accommodate longer SnakeLab simulations.

## [5.0.6] - 2026-11-27 @ 19:23

### Summary

Align Experiment Status with the current single-view selection, simulation,
comparison, and evaluation flow.

### Changed

- Show only the active view's Selection and Evaluation sections, in flow order,
  with no prompt sections for default or rotated-seed baselines. Reuse Selection
  for duplicate revisions and retain conversation links, settings, and costs.
- Show the active view, phase, seed, and consecutive-loss count above the sections.
  Place simulation status, baseline and candidate high scores, run links, and the
  golden comparison outcome between Selection and Evaluation.
- Read the actual candidate run during simulation and preserve expanded sections
  and table scrolling only within the same experiment on refresh.

## [5.0.5] - 2026-11-27 @ 18:56

### Summary

Run and evaluate one view at a time, retain comparison history only for the
current golden's owner, and rotate seeds after sixteen consecutive losses.

### Changed

- Shuffle the four views each round, starting each view's proposal from the
  current golden and running a separate simulation and evaluation immediately.
  Shared parameters remain editable on each eligible view's turn.
- Promote candidates that match or beat the golden high score. Reset the
  consecutive-loss count on either outcome; rotate the seed after sixteen
  strictly lower candidate scores and establish a fresh golden baseline.
- Give only the current golden's producing view its winning comparison history.
  Other views use no-history prompts with baseline-only charts. Clear ownership
  on seed rotation and checkpoint ownership, order, active view, and loss count.
- Return duplicate candidates to their owning view with the shared notice and
  rejected proposal. Log selection/evaluation stages explicitly and update
  reports for multimodal selections, tie promotions, and evaluation costs.

### Removed

- Remove the synthetic startup configuration, hypotheses, loader, and installation
  copying rules. Fresh startup runs only the default baseline before tuning.
- Remove the LLM's seed choice and shared-parameter draft locks.

## [5.0.4] - 2026-11-26 @ 19:48

### Summary

Keep experiment timing and token usage visible in section title bars and a
combined totals box, and give evaluation observations their own space above the
configuration comparison.
Return duplicate configurations to a randomly selected Selection view, and leave
simulation validation to SnakeLab's JSON schema.

### Changed

- Move elapsed time and input/output token counts into each Experiment Status
  section's title bar and remove their three table columns. Widen the remaining
  settings and choice columns, and add a Totals box that sums recorded metrics
  across all eight sections and updates with the existing refresh.
- Move Evaluation observations beneath the hypothesis, showing the current status
  until observations are submitted, followed by Reasoning and Response (details)
  links. Simplify Evaluation tables to Configuration Setting, Baseline, and Latest.
- Check proposed configurations against existing simulations, including their
  seed, before submission. For duplicates, randomly select one of the four
  Selection views and prepend "This configuration is a duplicate, please select
  different values." Preserve the other choices, checkpoint the selected view
  for restart, and check each revised configuration again.

### Removed

- Remove Ax3l's combined closer/farther reward restriction and local simulation
  configuration validation from proposal acceptance, startup loading, checkpoint
  reads, seed increments, and submission. Keep JSON rules as LLM guidance and let
  SnakeLab validate simulation settings; retain LLM response-format and view-scope
  checks.

## [5.0.3] - 2026-11-26 @ 17:30

### Summary

Calculate active conversation elapsed time using the database clock.

### Fixed

- Remove the UTC/local-time mismatch that added five hours to active Experiment
  Status durations. Use MariaDB's current timestamp alongside its stored event
  timestamps; completed conversations continue using their recorded end time.

## [5.0.2] - 2026-11-26 @ 17:10

### Summary

Remove obsolete browser provisioning so installation no longer depends on a
Chrome download.
Show installer stages and elapsed-time activity during runtime preparation.

### Added

- Show eight installer stages, including virtual-environment reuse or creation,
  dependency installation, file copying, and service setup. Report activity every
  five seconds during venv creation and package installation, preserving package
  output, download progress, command failures, and interruption handling.

### Removed

- Remove the Chrome installer and Kaleido dependency. Current static images use
  Pillow and interactive charts use Plotly HTML, so neither needs Chrome on the
  server. Document resuming a partial installation with `install-services.sh`.

## [5.0.1] - 2026-11-26 @ 16:45

### Summary

Run fresh initialization even when SnakeLab retains simulations from an earlier
installation. 

This release was verified at a high level and appears to be working.

### Changed

- Increase the fixed simulation length from 750 to 1,500 episodes for the default
  baseline, synthetic first experiment, and autonomous candidates. Keep the
  comparison windows at 150 episodes.

### Fixed

- Establish the default baseline and synthetic experiment when Ax3l has no saved
  state or golden reference, instead of adopting SnakeLab's historical best run.
  Preserve existing SnakeLab results and resume existing Ax3l experiment history.

## [5.0.0] - 2026-11-26 @ 06:11

### Summary

Separate simulation evaluation from configuration tuning, with four result
conversations followed by four configuration conversations. Keep presentation
modules and prompts directly under `ax3l/presentation/`, and remove the unused
default-configuration wrapper. Begin separate application documentation with
a draft deployment Use Case View. Require a fresh installation, keeping database
credentials across explicit uninstall and reinstall operations. Share terminology
between documentation views through a common glossary, and connect deployment
responsibilities, design, and implementation through all four views. Separate
application-file installation from service orchestration and propagate discovery
failures before service activation.
Refactor the application around explicit experiment, reporting, persistence,
transport, and presentation responsibilities, removing retired tuning machinery.
Allow shared tuning parameters across views while preventing conflicting
proposals within each configuration cycle.
Show golden/latest training measurements in all four evaluation prompts, and keep
configuration tuning prompts text-only. Align evaluation headings and use
150-epoch comparison windows across all four views.
Restore seed rotation as a shared request, running the golden and proposed
settings on the same incremented seed before comparing their results.
Run an editable synthetic experiment after the fresh baseline and before Qwen
begins evaluation and autonomous tuning.
Show the four evaluation and four selection conversations in collapsible
Experiment Status sections with their recorded prompts, parameters, and costs.

### Added

- Add eight Experiment Status sections above the event log. Retain the parameter
  table headings, show hypotheses and observations, link each recorded prompt,
  response, and reasoning, and report elapsed time and input/output tokens once
  per conversation. Identify shared choices and pending, active, saved, failed,
  and synthetic steps. Preserve expanded sections and table scrolling on refresh.
- Add `conf/synthetic/config.json` and four hypothesis files for the first
  experiment. Validate them before the baseline, checkpoint the resolved inputs,
  and run both real simulations before any LLM requests. Compare the synthetic
  result against the baseline, retain that reference after promotion, and exclude
  initialization from `--cycles`. Install missing files while preserving local
  edits on upgrade.
- Add an optional `new seed` boolean to every tuning view. Start false each
  cycle, keep it editable while false, and move it into read-only parameters
  after any view requests true. Preserve the choice across restarts.
- On a new seed request, increment the numeric seed and run two full SnakeLab
  simulations: current golden settings first, then Qwen's proposed settings.
  Establish the first result as the new baseline even if lower, and compare the
  candidate against it. Recover either run and committed promotions without
  duplicate submissions or repeated conversations.
- Add a golden/latest training evaluation PNG with combined 90th/25th score
  percentiles and mean episode loss in 150-epoch windows. Retain final partial
  windows, include measured zero losses, exclude missing losses from the mean,
  and leave wholly unmeasured windows as gaps. Scale shared loss axes to both
  runs' recorded values and include their high scores in the evaluation text.
- Add a golden/latest reward-signals comparison PNG to the evaluation prompt.
  Show food pickups, wall collisions, and snake collisions per 100 moves plus both
  score percentiles in 150-epoch windows. Preserve the original reference after
  promotion, retain final partial windows, and leave gaps for missing outcomes or
  zero moves. Include both runs' high scores in the evaluation text.
- Generate golden/latest score comparison PNGs for architecture evaluation. Plot
  the 90th and 25th percentiles in 150-epoch windows, with shared axes and at least
  five interior horizontal guides per score panel, and send the image to Qwen.
- Add exploration evaluation PNGs with checkpoint epsilon probabilities, observed
  EpsilonNice move override rates, and 90th/25th score percentiles in 150-epoch
  windows. Use recorded episodes from the original reference and latest run,
  including final partial windows, and include each run's high score in both
  evaluation prompts. Identify baseline self-comparisons and missing measurements.
- Add a JSON example to the shared proposal submission instructions, showing
  `submit_view` arguments with a hypothesis and parameter values.
- Add a full-suite runner that owns a private MariaDB instance and runs database,
  HTTP, ZeroMQ, and deployment fixtures without using deployed services. Document
  the resulting package structure and runtime contracts in the Implementation View.
- Add an Implementation View index and deployment implementation realization,
  covering source ownership, file delivery, installed entry points, and verified
  contracts. Link forward from Design to complete the four-view documentation.
- Add a Design View index and deployment design realization, linking analysis
  participants to the current scripts, helper interfaces, configuration classes,
  resources, service definitions, and failure contracts. Include Mermaid
  structure and sequence diagrams and link forward from Analysis.
- Add an Analysis View index and the deployment analysis realization, with
  participant responsibilities, Mermaid class and sequence diagrams, failure
  decisions, and traceability back to UC-01. Define analysis roles in the shared
  glossary and link the use case to its realization.
- Add a shared application glossary with links from the documentation entry
  point, Use Case View, and deployment use case.
- Add a standalone documentation entry point and the initial Deploy Ax3l software
  use case under `docs/`, checked against installation and supporting code, with
  an actor and a Mermaid overview. Capture provisioning, credential reuse,
  service startup, and the limits of installation verification. Keep the
  existing Pages content, navigation, and publishing configuration unchanged.
- Add four evaluation prompts with a dedicated Observations submission.
- Checkpoint each view's Observations and feed them into that view's next tuning
  prompt. Resume interrupted evaluation and tuning passes without repeating
  accepted submissions, including checkpoints from the preceding combined flow.
- Enforce a 280-character limit on both hypotheses and Observations at the LLM
  boundary and display those limits in the prompts.

### Changed

- Align Architecture evaluation headings with the other views and use the same
  150-epoch comparison windows in its prompt and embedded PNG. Retain final
  partial windows and shared axes for the Golden and Latest score percentiles.
- Keep all configuration tuning prompts text-only; move architecture score
  imagery to result evaluation and add the latest run alongside the golden reference.
- Share sequence length between Architecture and Training, and gamma between
  Training and Reward Signals. Once submitted in the shuffled tuning pass,
  a shared parameter becomes read-only for later views, including after restart.
- Separate report queries, HTML rendering, and HTTP handling. Keep report templates,
  animations, and fonts together under `ax3l/presentation/reporting/`.
- Move database adapters under `ax3l/interface/database/`. Keep SQL and event
  persistence outside application workflows and database mechanics, preserving
  constructor-driven event schema initialization and atomic event writes.
- Group experiment and reporting workflows under `ax3l/app/`. Keep service recovery
  in application control flow, and put simulation schemas beside their interface.
- Reuse the bounded ZeroMQ client for SnakeLab requests without changing the
  protocol, correlation validation, timeout behavior, or submission retry policy.
- Count distinct compared runs directly during atomic reporting refreshes. Retain
  incremental completed-run summaries and read-only access to SnakeLab source data.
- Show the recorded decision in golden configuration history, replacing obsolete
  individual-parameter and value-change columns.
- Stage the complete application package before replacement, restore the previous
  package if replacement fails, and remove retired installed modules on upgrade.
  Preserve configuration, credentials, the runtime, and generated animations.
- Keep UC-01 and its realizations focused on fresh installation. Catalog upgrade
  and uninstall as separate use cases, retaining only brief cleanup guidance in
  UC-01 and removing duplicated lifecycle details from its realizations.
- Extract application-file selection and copying into the sourced
  `scripts/application-files.sh` helper, with explicit checkout, target, and
  account arguments. Preserve installed paths, ownership, and permission modes.
- Refuse installation when Ax3l application files, service units, Linux accounts,
  or database resources already exist. Direct DevOps to uninstall first, while
  allowing saved credentials to be reused.
- Retain the database credentials and their private directory during uninstall;
  remove Ax3l application files and data without changing SnakeLab or LlamaSrv.
- Document SnakeLab data cleanup as an undetailed external use case and a
  deployment prerequisite, performed separately by DevOps.
- Use DevOps as the deployment actor throughout the Use Case View.
- Flatten the presentation package by removing its SnakeLab subdirectory. Keep
  prompt templates in `prompts/evaluations/` and `prompts/selections/`, and update
  module imports, template loading, and installation paths.
- Finish all four evaluations before starting the next configuration pass. Evaluate
  the initial baseline too, and include final result evaluations in bounded runs.
- Match Architecture, Exploration, and Training prompt structure to the updated
  Reward Signals prompt. Keep the Reward Signals template intact and add
  shared submission instructions when rendering tuning prompts.
- Submit only a hypothesis and parameter values in tuning conversations; include
  the expected observable effect in the short hypothesis.

### Fixed

- Propagate application-file discovery failures so installation cannot continue
  to service registration and startup after discovery fails. Add a regression
  check for this failure path.
- Escape semicolons in deployment sequence-diagram messages so Mermaid can render
  the analysis realization.

### Removed

- Remove direct numeric seed tuning from Training and the unused legacy
  `SimulationConfiguration.next_seed` helper. Ax3l owns seed increments.
- Remove the comparison-image placeholder renderer now that all four evaluations
  use recorded golden/latest measurements.
- Remove unused single/pair parameter searches, comparison queries, run-analysis
  plots, round-robin reporting projections, legacy checkpoint conversion, and
  their retired-path tests. Retain current workflow and integration coverage.
- Remove the test-only `GenerateDefaultConfig` wrapper; tests now call
  `SimulationConfiguration.defaults()` directly.

## [4.23.2] - 2026-11-24 @ 04:35

### Summary

Run the four-view experiment end to end: shuffle the views, assemble their
proposals into one configuration, submit it to SnakeLab, and compare the result
with the experiment's golden reference.

### Added

- Add Reward Signals, Architecture, Training, and Exploration prompt templates,
  each introducing Qwen's role in Patrick Loeber's Snake Lab and the objective
  of improving the Snake AI's high score.
- Include sections for the previous hypothesis and choices, golden/latest
  results, editable parameters, and a read-only JSON view of the remaining
  configuration, including values marked as draft.
- Ask Qwen to evaluate the previous hypothesis and propose a new hypothesis,
  expected effect, and values for the current view's parameters. Include all
  four prompt assets in installations.
- Assign tunable parameters to the four views, show other settings as read-only
  JSON, and mark already proposed values as draft. Supply compact measurements
  for each view and retain the previous hypothesis, expected effect, and choices.
- Use local LLM native tool calls to accept one validated proposal per view.
  Keep proposal values within the view's scope and the existing simulation
  policy, including the joint reward constraint.
- Persist shuffled order, accepted proposals, submission intent, run identity,
  and comparison progress in MariaDB through the shared event log. Resume
  interrupted cycles and reconcile lost submission replies without resending.
- Add local HTTP/ZeroMQ end-to-end fixtures and disposable MariaDB checks for
  complete cycles, restart recovery, promotion recovery, and checkpoint rollback.

### Changed

- Start the experiment loop from the Ax3l service. Add `--cycles` for a bounded
  run and `--llm-url` for an inference endpoint override.
- Establish a real default baseline on an empty installation and seed initial
  hypotheses for each view. Record their seeded origin outside the model prompt.
- Promote strictly better high scores and retain golden on ties or losses.
  Preserve the reference used by the preceding trial so its improvement remains
  visible after promotion. Keep shuffling and final submission outside Qwen's
  instructions.

### Removed

- Remove the separate welcome prompt. Keep view ordering and configuration
  assembly out of the model-facing prompt text.

## [4.23.0] - 2026-11-23 @ 04:28

### Summary

Remove the existing conversation workflows so the next flow starts from a
clean application foundation. Performed extensive analysis on the experiment
goals and conversation design.

### Removed

- Remove current and legacy conversation loops, prompts, MCP tools, handlers,
  model-facing pages and guides, and conversation design notes and screenshots.
- Remove draft selection, decision timers, seed rotation, round-robin recovery,
  saved analysis workflows, and the experiment-workspace reset helper.
- Remove the flow-specific Experiment Status report and analysis-image routes.
  Retain event reports, simulation details, score charts, and shared interfaces.
- Remove the MCP dependency, conversation capture settings, decision-grace
  configuration, and optimization command-line options.

### Changed

- Keep the Ax3l ZeroMQ service running without starting conversations or
  submitting simulations. Domain requests return an unknown-method error until
  a replacement workflow is installed.
- Update installation assets, service arguments, tests, and documentation for
  a fresh uninstall/install reset.

## [4.22.0] - 2026-11-22 @ 15:09

### Summary

Restart interrupted experiment setups without erasing simulation history, and
make the per-setting submission tool and arguments explicit.

### Added

- Add `scripts/wipe-experiment-workspace.sh` to stop Ax3l services, clear the
  current unsubmitted draft and its setup conversations, and restart with a
  fresh experiment from golden. Preserve completed runs, baseline history,
  and saved analyses. Refuse submitted experiments and active seed rotations.
- Delete the selected workspace and associated tool receipts in one transaction,
  with cascading event-detail cleanup and rollback on failure.

### Changed

- State `submit_single_value(value)` or `submit_pair_values(value_1, value_2)`
  on each setting screen, identifying the paired fields in argument order.

## [4.21.5] - 2026-11-22 @ 14:48

### Summary

Keep per-item configuration prompts focused on the selected setting and its data.

### Changed

- Remove the repeated objective, draft rules, experiment menu, save/run
  directions, chart-source prose, and URL instructions from per-item prompts.
  Retain the lab heading, current setting, comparison JSON, chart images, and
  custom EpsilonNice explanation. Keep editing and run guidance on the main page.

## [4.21.4] - 2026-11-22 @ 14:35

### Summary

Compare reference runs by metric, with five-place decimal rounding and no
duplicate reference labels in report tables.

### Changed

- Present historical results by metric with best, golden, and latest values
  side by side, including nested episode-ending counts and percentages.
  Use the same comparison layout on the main and parameter screens and in
  Experiment Status previews.
- Round decimal values to at most five places in model-facing JSON and report
  previews, preserving the precision of stored configuration and measurements.
- Remove the Field column from keyed record tables when a data column already
  contains the row labels, so best, golden, and latest each appear once per row.

## [4.21.3] - 2026-11-22 @ 14:17

### Summary

Make the configuration page the main screen for setup, with linked definitions,
visible saved edits, and separate configuration comparisons and run results.

### Changed

- Use the revised first prompt to explain selecting settings, returning after
  saving, multiple edits, and seed changes. Keep Run next simulation available.
- Show all configurable settings with best, golden, latest, and current draft
  values. Mark whether each setting is editable so saved changes remain visible.
  Remove repeated full configurations from inline historical data and remove
  redundant run roles.
- Return to the configuration page after reading a linked definition, keeping
  the conversation and decision deadline. Saved edits return to a freshly
  rendered page with the updated draft values.

### Added

- Linked definitions for best, golden, latest, and draft. Each includes the
  instruction, "Don't show your reasoning in the prompt."

### Fixed

- Render grouped JSON settings as rows in Experiment Status previews so
  separate configuration and historical-results blocks stay readable.

## [4.21.2] - 2026-11-22 @ 12:45

### Summary

Put configuration comparisons and reference-run data directly in the setup
screens so Qwen can prepare the next simulation without separate data reads.

### Changed

- Include best, golden, latest, and draft values for each available setting
  in the setup screen's JSON, alongside complete reference-run results and
  observations and the saved draft. Keep the same data available when setting
  a value.
- Remove the latest, golden, best, and draft read options from setup menus
  and browser guidance. Keep existing data URLs readable for older sessions.
- State the configuration-editing task and the select, set, and save actions
  explicitly. Preserve lab-reference navigation, run availability, duplicate
  rejection, and decision timing.

## [4.21.1] - 2026-11-22 @ 11:23

### Summary

Return complete draft and reference-run snapshots in one browser read, and
keep Experiment Status previews compatible with the lab menus and JSON payloads.
Keep Run next simulation available throughout configuration setup.

### Changed

- Keep the run menu action and tool available on every configuration setup
  screen. Describe saved changes as Changes saved and tell Qwen to choose Run
  next simulation when finished making configuration changes.
- Check the saved whole configuration for duplicates on every run attempt.
  Rejected runs redisplay the current screen in the same conversation, keeping
  research and the decision timer. Accepted runs use saved values and clear
  any pending setting assignment.
- Combine each reference run's configuration, measured results, and saved
  observations on `/latest`, `/golden`, or `/best`. Show the full draft
  configuration with saved and current setting names on `/draft`, without
  repeating values for every choice. Remove section menus and direct choice
  prompts to complete run pages; keep older section URLs readable.

### Fixed

- Display captured LLM menu paths as text in report previews so they do not
  navigate to unrelated reporting routes. Preserve the original prompts and
  tool results, and keep external reference links clickable.
- Update reporting checks for the branded draft presentation.

## [4.21.0] - 2026-11-22 @ 10:32

### Summary

Separate SnakeLab conversation presentation from data preparation and expose
guides and experiment data through one browser tool, preserving experiment rules.
Present the experiment as Patrick Loeber's AI Snake Lab, with Qwen as Data
Scientist, English menus and URL navigation, and JSON data payloads.

### Changed

- Replace scripted analysis instructions with lab menus, current tasks, draft
  status, and available actions throughout the model-facing presentation.
  Keep the existing URL paths, JSON payloads, tool contracts, and experiment
  sequencing. Reduce the reference guides to implementation facts and rules.
- Extend `kb_tool(url)` to browse both guides and context-bound data from one
  home page. Move guide URLs under `/guides` and remove the separate `data_tool`.
- Move guide assets, data page layouts, choice and next-step prompts, EpsilonNice
  guidance, and MCP tool descriptions into a dedicated Markdown presentation
  package. Keep measured values, schema constraints, persistence, and workflow
  decisions in their existing application layers.
- Update installation and Experiment Status reads for the combined browser,
  retaining display support for historical data-tool events.

## [4.20.1] - 2026-11-22 @ 05:59

### Summary

Keep configuration task totals visible when Experiment Status rows are collapsed.

### Added

- Show bold elapsed time, input token, and output token totals on each
  Experiment Status row with expandable tasks, updating with the existing refresh.

## [4.20.0] - 2026-11-21 @ 11:51

### Summary

Accept seed changes as soon as the LLM selects the seed option and keep image
prompts brief.

### Changed

- Save the next unused seed immediately on selection, skipping the separate
  seed confirmation conversation. Resume pending seed selections the same way
  after restart, while retaining the normal draft review and run decision.
- Keep image prompts to brief source or comparison cues, such as "Chart: latest."
  and "Compare latest with golden." Remove chart descriptions and tuning advice
  from setting choices and standalone loss plots.

## [4.19.0] - 2026-11-21 @ 11:28

### Summary

Let the LLM tune the reward for eating food alongside the existing rewards.

### Added

- Offer food reward as an independent choice from 0 to 20, retaining the default
  of 10, with score-distribution evidence, schema-backed tool limits, and a
  labelled Experiment Status row.

## [4.18.0] - 2026-11-21 @ 10:57

### Summary

Show how games ended when choosing snake and wall collision rewards.

### Added

- Add a game-ending chart with fixed-order horizontal bars for snake collisions,
  wall collisions, and max moves, a 0–100% axis, whole-percent labels, and exact
  episode counts. All episodes remain in the denominator; omitted outcomes are
  noted below the bars.

### Changed

- Use ending-reason charts and exact JSON measurements in snake and wall reward
  prompts, with a short interpretation guide. Stored percentages retain full precision.

## [4.17.0] - 2026-11-21 @ 08:10

### Changed

- Updated Ax3l logo.

## [4.16.1] - 2026-11-21 @ 07:58

### Summary

Align the bundled SnakeLab schema with signed empty move rewards.

### Changed

- Update the bundled server schema to accept empty rewards from -2 to +2 and
  verify the new reward ranges against both Ax3l and SnakeLab validation.

## [4.16.0] - 2026-11-21 @ 07:42

### Summary

Let the LLM tune empty space and collision rewards.

### Added

- Offer empty space rewards from -2 to +2 and separate snake and wall collision
  rewards from -20 to 0 through the existing single-value tuning workflow,
  with score-distribution evidence and readable status labels. Keep defaults
  at 0, -10, and -10. Positive empty space rewards require a SnakeLab server
  whose configuration schema accepts them.

### Fixed

- Preserve the original parameter order when restoring legacy experiment drafts
  and remove fixed-reward assumptions from the LLM reward guidance.

### Changed

- Keep LLM data pages compact as the tuning menu grows.

## [4.15.0] - 2026-11-21 @ 05:06

### Summary

Keep LLM decision timing internal while preserving the Experiment Status countdown.

### Removed

- Remove timer instructions, remaining-time reminders, and expiry warnings from
  LLM prompts. Keep decision and grace periods, automatic expiry actions, and
  the web GUI countdown unchanged.

## [4.14.3] - 2026-11-21 @ 04:17

### Summary

Fit the Score Distribution histogram's Y axis to its tallest bar.

### Fixed

- Round the Y-axis maximum up to the first tick at or above the largest score count,
  retaining the same scale across all animation frames and a minimum of five.

## [4.14.2] - 2026-11-20 @ 22:28

### Summary

Run 750-episode experiments.

### Changed

- Reduce the simulation epoch default and fixed experiment duration from 1,500
  to 750, and update the LLM prompts and local guides to match.

## [4.14.1] - 2026-11-20 @ 22:24

### Summary

Run 1,500-episode experiments with longer decision and grace countdowns.

### Changed

- Set the simulation epoch default and fixed experiment duration to 1,500,
  and update the LLM prompts and local guides to match.
- Increase the decision budget and default grace period from five to seven
  minutes. Each prompt containing a chart adds two minutes to the decision
  countdown, including its saved Experiment Status deadline; tool reads and
  rejected attempts retain that deadline.

## [4.14.0] - 2026-11-20 @ 21:54

### Summary

Explain the custom EpsilonNice exploration rule when choosing its pair.

### Added

- Add a specialized EpsilonNice choice prompt with a compact definition of
  activation, detour probability and duration, safe moves, and episode resets.

## [4.13.0] - 2026-11-20 @ 21:12

### Summary

Make the LLM grace countdown configurable and extend its default to five minutes.

### Changed

- Read `decision_grace_seconds` from `conf/ax3l.json`, defaulting to 300 seconds,
  for conversation resets and automatic simulation starts. Include the setting
  in newly generated configuration files and use it for LLM reminders and the
  Experiment Status countdown.

## [4.12.0] - 2026-11-20 @ 20:15

### Summary

Shorten the live Snake Lab prompts for new Qwen 3.5 9B deployment.

### Changed

- Lead with the current decision and trim repeated text from prompts, tool
  descriptions, and countdown messages while keeping the evidence and tool
  arguments intact.

## [4.11.4] - 2026-11-20 @ 05:03

### Summary

Improve score and loss plots with same-seed golden ties and loss trend comparisons.

### Changed

- Add green markers and hover details for completed same-seed ties, including
  historical comparisons, while preserving golden promotion rules and the score line.
- Overlay a 20-episode trailing mean on the LLM's raw training-loss trace and
  show the golden run's loss and mean in orange. Preserve missing-loss gaps and
  avoid duplicating golden when it supplies the chart itself.

## [4.11.3] - 2026-11-20 @ 03:43

### Summary

Make the one-seed-change limit explicit during simulation setup and improve
plot tick readability.

### Changed

- Use axis ticks at multiples of five with spacing scaled to the data in
  report plots and chart prompts, retaining fractional ticks for training loss.
  Keep the score-distribution animation's rounded axes fixed across frames.

### Fixed

- Reject repeated seed selections and requests with the existing parameter-space
  exhaustion signal. Refresh the available choices and tell Qwen that the seed
  cannot change again in the current draft, including after a restart.

## [4.11.2] - 2026-11-20 @ 02:36

### Summary

Establish a fresh local golden baseline when Qwen changes the seed before
testing any other requested configuration changes.

### Fixed

- Run golden with only the new seed and accept its completed score, even if
  lower. Seed-only drafts finish with that single run; drafts with other
  changes run a second simulation and compare against the new seed baseline.
- Recover interrupted seed baselines without duplicate submissions or score
  history entries, and skip seeds already stored for the golden baseline.
- Explain seed baseline resets in the LLM instructions, Experiment Status, and
  High Scores report, retaining the existing seed marker color.

## [4.11.1] - 2026-11-19 @ 05:06

### Summary

Reset stalled initial configuration conversations with a fresh model context
and restore finite-domain exhaustion checks for parameter selection.

### Fixed

- Omit exhausted parameters from Qwen's available choices and reject their
  selection before locking the draft to a setting. Check legal changes against
  every stored run status with the current draft seed and other settings, and
  reopen selection for exhausted assignments recovered on restart.
- After the initial five-minute decision budget and three-minute grace period,
  discard the tentative parameter selection and restart from the opening prompt
  with a fresh timer, without carrying over conversation history or submitting
  the unchanged baseline.
- Show a Conversation Reset Countdown before the first unique change, and tell
  Qwen that expiry restarts the initial conversation.

## [4.11.0] - 2026-11-19 @ 04:16

### Summary

Let Qwen request seed changes through the existing configuration experiment
workflow instead of rotating automatically after nine unsuccessful proposals.

### Added

- PNG showing the transformer.
- Add a seed choice and argument-free `request_seed_change` MCP tool. Ax3l
  increments the seed, skipping complete configurations already stored in any
  status, and saves the unique choice without starting a simulation.

### Changed

- Keep seed changes subject to the existing configuration choices, run
  decisions, restart recovery, and strict high-score promotion rules.
- Show seed selections in Experiment Status and refresh chart-source selection
  after draft seed changes, identifying measurements from other seeds.
- Bound seed increments to the signed integer range used by Ax3l's score
  history and retain recovery of seed rotations recorded before this change.

### Removed

- Stop starting automatic seed rotations after nine unsuccessful proposals.

## [4.10.2] - 2026-11-17 @ 05:12

### Summary

Identify each setting in Golden Configurations value changes.

### Fixed

- Prefix single and paired changes with their setting labels while preserving
  the recorded before-and-after values and pair order.

## [4.10.1] - 2026-11-17 @ 04:50

### Summary

Show score-distribution progress in smaller simulation checkpoints.

### Changed

- Use cumulative score-distribution GIF checkpoints every 50 simulations.
  Keep the interval in `DScoreDistribution.CHECKPOINT_INTERVAL` and use it in
  the report description so future tuning stays consistent.

## [4.10.0] - 2026-11-16 @ 08:49

### Summary

Make prompt hover previews easier to trace to their source modules.

### Changed

- Include the recorded module name in Experiment Status prompt preview titles,
  for example `Prompt (ComparisonSingle)` or `Prompt (FirstContact)`.

## [4.9.3] - 2026-11-16 @ 06:58

### Summary

Keep Experiment Status compact with collapsible tasks and concise setting descriptions.

### Added

- Add +/− controls to every setting or experiment decision with task rows.
  Start tasks collapsed and preserve each group's expansion and keyboard focus
  across automatic refreshes. Keep configuration values and totals visible.

### Changed

- Shorten the Experiment Status setting descriptions and show food rewards
  using their labels alone.

## [4.9.2] - 2026-11-16 @ 06:35

### Summary

Present the experiment title and countdown as one consistent section header.

### Fixed

- Integrate the countdown into the full-width Experiment Status header instead
  of styling it as a separate rounded box. Keep the same header structure while
  choosing settings, awaiting submission, running, showing results, or empty,
  including the last-completed view and narrow screens.

## [4.9.1] - 2026-11-16 @ 06:27

### Summary

Improve Experiment Status layout, countdowns, and captured prompt and reasoning previews.

### Added

- Extend the existing hover and keyboard-focus popups to Prompt and Reasoning
  links. Reuse the Read preview parser to render Markdown and compact JSON
  tables, including captured chart images in prompts.

### Changed

- Use amber when the decision timer expires. For saved unique configurations,
  show a three-minute Simulation Start Countdown; otherwise continue into
  negative time with an Exceeded decision time message.

### Fixed

- Keep the experiment header and countdown in place while the line-item table
  scrolls horizontally. Stabilize header wrapping and countdown width, and
  preserve the table's scroll position across refreshes.

### Removed

- Remove the obsolete golden-notes instruction from Qwen's parameter-selection prompt.

## [4.9.0] - 2026-11-16 @ 05:59

### Summary

Inspect prompts and Qwen's recorded reasoning from the Experiment Status line items.

### Added

- Add an LLM details column with Prompt links on saved prompt rows and Reasoning
  links on completed Qwen requests that contain reasoning. Include follow-up
  prompts and timer reminders without changing elapsed or token totals.

## [4.8.4] - 2026-11-16 @ 05:38

### Summary

Inspect recorded Read results from Experiment Status with compact, readable previews.

### Added

- Link Read data and Read guide targets to their recorded results and show a
  popup on hover or keyboard focus. Keep previews open across status refreshes.
- Add a reusable JSON-to-Markdown translator for nested settings, simple lists,
  and record lists. Render tool JSON, including JSON code blocks, as compact
  tables in previews and result pages.

## [4.8.3] - 2026-11-16 @ 00:30

### Changed

- HTTP Timeout from 5 to 8 minutes.

## [4.8.2] - 2026-11-16 @ 00:24

### Summary

Keep the LLM countdown running past zero and tighten the Experiment Status layout.

### Changed

- Turn the countdown red at zero and continue downward into negative time,
  including during the existing grace period.
- Place the countdown beside the experiment details to remove the extra blank
  row above the configuration table.

## [4.8.1] - 2026-11-16 @ 00:08

## [4.8.0] - 2026-11-16 @ 00:02

### Summary

Show the live LLM countdown and keep the all-time high score consistent with the current golden.

### Added

- Add a countdown box above the configuration table on the right. Update it every
  second, follow accepted unique-change resets, and show the three-minute grace
  period when applicable. Show an inactive timer after submission.

### Fixed

- Include the live golden score in the displayed all-time high so a new record
  appears immediately while the background reporting totals refresh.

## [4.5.2] - 2026-11-15 @ 22:57

### Summary

Require meaningful parameter changes, prevent repeated selections, and run unique drafts after a decision timeout.

### Added

- Give an expired decision budget a three-minute grace period when a unique draft
  is saved. At grace expiry, submit that configuration through the normal simulation,
  comparison, and measurement cycle, then start the next experiment. Pending edits
  are excluded until their changed values are accepted.

### Changed

- Reject a selected parameter's current value, or a pair with both values
  unchanged, without saving it or checking configuration uniqueness.
- Allow each single or paired parameter to be chosen only once per experiment,
  preserving that restriction after restart. Show only unused parameters in the
  selection prompt and direct Qwen to run when every eligible setting is used.

## [4.5.1] - 2026-11-15 @ 22:24

### Summary

Guide Qwen with an advisory countdown and require unique values for each selected setting.

### Added

- Give selection and value conversations an advisory five-minute countdown, with
  updated time remaining after every data request. Reset it after each accepted
  unique change for the next parameter or run decision. At zero, urge a decision
  while keeping the conversation and tools available.

### Changed

- Reject duplicate configurations without saving the proposed values or leaving
  the selected parameter. Continue the same value conversation until Qwen submits
  a unique candidate, preserving the countdown during retries.

## [4.4.7] - 2026-11-15 @ 22:06

### Summary

Let Qwen choose which settings to adjust and when to run each experiment.

### Changed

- Start from the golden baseline and let Qwen research with the data tool before
  choosing any single or paired setting. Check the whole configuration after
  every submitted change instead of requiring a fixed pass through all settings.
- For unique configurations, offer a run action or another parameter change,
  including the same parameter again. Duplicate configurations require another
  change. Submit only after Qwen explicitly chooses to run.
- Preserve the selected parameter and next-step decision across restarts, and
  resume older drafts without discarding their saved choices. Update Experiment
  Status to show the decision stage and settings left at baseline.

## [4.4.6] - 2026-11-15 @ 21:36

### Summary

Show changed Experiment Status values on one line.

### Changed

- Remove the "Changed" label beneath LLM choices and keep the color highlight.

## [4.7.1] - 2026-11-15 @ 21:29

### Summary

Simplify the Experiment Status comparison labels.

### Changed

- Remove the redundant "No change" label beneath unchanged LLM-chosen values.
- Rename the comparison columns to "Baseline" and "LLM Choice".

## [4.7.0] - 2026-11-15 @ 21:22

### Summary

Compare inherited and LLM-chosen settings side by side in Experiment Status.

### Added

- Show an Inherited column before the LLM-chosen values using the experiment's
  starting golden configuration. Highlight changed choices, label saved matches
  as "No change", and show pending choices until they are saved.

## [4.6.0] - 2026-11-15 @ 21:14

### Summary

Let Qwen choose which setting to revise when a complete configuration is a duplicate.

### Changed

- Save duplicate drafts and open a parameter-selection conversation instead of
  forcing changes to the final EpsilonNice pair. Reopen the selected single or
  paired setting, keep the other saved values, and check the complete draft again
  after the revision. Repeat parameter selection for every further duplicate.
- Resume duplicate resolution and the selected revision after interruption.
  Show the selection step and its time and token usage in Experiment Status.

## [4.5.0] - 2026-11-15 @ 20:44

### Summary

Start fresh experiments from a smaller Transformer and let the LLM tune its
width, encoder depth, and dropout.

### Changed

- Use a baseline with hidden size 64, one encoder layer, dropout 0.05,
  four-frame sequences, batch size 64, learning rate 0.001, target update rate
  0.05, and EpsilonNice probability 0.05. Keep the target update rate fixed.
- Allow hidden widths from 32 to 128 in multiples of 8. Add encoder layers
  (1–3) and dropout (0–0.1 in steps of 0.01) to the LLM's choices, including
  tool rules, saved drafts, and experiment status reports. Each pass now makes
  seven single choices and three paired choices before submitting one run.
- Limit distance reward choices to +/-5 and safe detours to 40 moves.
- Refresh the bundled Snake Lab schema and model guidance for the new baseline.

## [4.4.5] - 2026-11-15 @ 19:12
### Changed

- Reverted HTTP timeout back to 5 minutes. 10 minutes just meant a 10 minute timeout.

## [4.4.4] - 2026-11-15 @ 17:58

### Changed

- Increased HTTP timeout from 5 minutes to 10 minutes.

## [4.4.3] - 2026-11-15 @ 17:28

### Summary

Use consistent durations and show running elapsed-time and token totals in
Experiment Status.

### Changed

- Display setup-step durations as `MM:SS`, switching to `HH:MM:SS` at one hour.

### Added

- Running totals beneath the setup steps for elapsed time, input tokens, and
  output tokens, followed by a combined token total on the next line.

## [4.4.2] - 2026-11-15 @ 16:55

### Summary

Give Qwen charts and measured data during parameter selection, and show each
setup step as it happens in Experiment Status. Improved reporting.

### Changed

- Load a short selection skill for each choice. Show training loss for learning
  rate, score trends for epsilon, and score distribution for distance rewards.
  Use the latest run on the current seed, with the golden run as the fallback.
- Give Qwen direct English directions to data pages. Keep settings and
  measurements in JSON.
- Time each chart render, Qwen request, tool lookup, and submission on its own.
  Show input and output tokens separately for each Qwen reply.

### Removed

- Remove standalone chart-summary requests from the optimization loop. Ax3l
  records measurements directly from completed runs.

## [4.4.1] - 2026-11-15 @ 13:02

### Summary

Let image analysis inspect the settings behind each chart and recommend a
concrete value to try next without explaining theory.

### Added

- `data_tool` access during chart conversations, bound to the exact simulation
  that produced the image, with JSON configuration pages and current tunable
  limits. Settings are available before the run's analysis has been saved.

### Changed

- Allow an optional value recommendation in each saved chart observation while
  retaining the 1–2 sentence, 40-word limit. Prompts and chart guides require
  checking current settings and allowed values and exclude theory and causal
  explanations. Configuration choices still apply and validate changes later.

## [4.4.0] - 2026-11-15 @ 12:17

### Summary

Deliver experiment data to Qwen as JSON while preserving linked tool navigation.

### Changed

- Return JSON payloads for settings, scores, termination reasons, activity, and
  saved observations, with JSON data blocks in draft and run overviews.
- Preserve numeric types, recorded percentage precision, and missing statistics
  as JSON null. Explain the data format in Qwen's prompt and tool instructions.

## [4.3.3] - 2026-11-15 @ 11:57

### Summary

Limit EpsilonNice detour probability to 10% and duration to 50 moves.

### Fixed

- Reject EpsilonNice probabilities above 0.1 and step counts above 50 in
  configuration choices and complete simulation configurations. Qwen's tool
  instructions and exploration guide reflect the same limits.

## [4.3.2] - 2026-11-15 @ 11:45

### Summary

Show current simulation images and resource usage throughout the experiment
checklist.

### Added

- Three prerequisite rows for the submitted simulation's score trends, score
  distribution, and training loss images, alongside the reference analyses.
- Links to each chart's latest available image, using the exact PNG sent to Qwen.
- Elapsed time and input/output token usage for every analysis and configuration
  row, with live elapsed times and a final total counting paired choices once.

### Changed

- Render saved checklist items with green checkmarks across browsers.

## [4.3.0] - 2026-11-15 @ 11:14

### Summary

Let Qwen browse small English pages of experiment data instead of receiving
full run and draft JSON dumps.

### Added

- Draft-bound `data_tool(url)` navigation for current choices and the frozen
  latest, golden, and best runs, with separate scores, endings, activity,
  notes, and configuration pages.

### Changed

- Use short readable labels in choice prompts, tool descriptions, chart facts,
  and data pages. Keep UUIDs in storage and transport, outside Qwen's text.
- Return plain page text to Qwen and avoid repeating rejection metadata.
- Preserve reference-analysis prerequisites and resume accepted draft choices;
  retrieve saved observations only when Qwen requests them.

## [4.2.2] - 2026-11-15 @ 10:06

### Summary

Show each reference image job on the report card and complete image analysis
before selecting configuration elements, including after a restart.

### Changed

- Show one prerequisite row per reference chart, with its own checkmark and
  preparation, analysis, or failure state. Shared reference runs use three rows;
  three distinct runs use nine.

### Fixed

- Resume unfinished reference image jobs before the next configuration choice,
  preserving accepted choices and reusing saved analyses. Feed the completed
  analyses directly into every element's main text prompt.

## [4.2.1] - 2026-11-15 @ 09:31

### Summary

Show reference-analysis prerequisites and the LLM's current image task in the
Experiment Status report card.

### Added

- Pre-Requisites rows above configuration items in the same checklist, with
  saved-analysis checkmarks and live image preparation, analysis, and failure states.
- Durable preparation progress before configuration selection, including restart
  recovery and shared reference runs displayed once with their combined roles.

## [4.2.0] - 2026-11-15 @ 09:15

### Summary

Show experiment progress and completed results in a compact report card and
identify the application version in the server heading.

### Added

- Experiment Status report with eleven read-only configuration checkboxes,
  accepted values, pending inherited values, and the next selection highlighted.
- Live simulation and analysis phases, golden-score comparisons, and a Last
  completed view that remains available when the next experiment starts.
- Five-second automatic refresh that retains the last successful report if a
  refresh fails.
- Application version and codename beneath Last Refresh at the right of the
  server heading, using release metadata and matching the timestamp style.
- Smaller text in the new Experiment Status report; existing fonts are unchanged.

## [4.1.2] - 2026-11-15 @ 08:34

### Summary

Give Qwen an explicit beginning-versus-end score comparison with both averages
supplied.

### Fixed

- Compare the first and final 50-episode mean scores within the same run;
  supply both exact averages and align the prompt, example, and reference guide.

## [4.1.1] - 2026-11-15 @ 07:44

### Summary

Keep Qwen's simulation analysis focused by interpreting one chart per
conversation and loading reference guidance on demand.

### Added

- Local `kb_tool` navigation through short reference pages, installed with Ax3l.
- Durable analysis progress to resume unfinished chart sections after restart.

### Removed

- Full configuration dumps and general background from chart-analysis prompts.

### Changed

- Split run interpretation into three focused conversations, each with one
  chart, relevant facts, an example answer, and a 40-word observation limit.
- Combine all three chart observations for later parameter choices without
  another LLM conversation.

## [4.1.0] - 2026-11-15 @ 07:03

### Summary

Choose every tunable setting before executing one simulation, and use saved
visual analyses of the latest, golden, and all-time best runs to inform choices.

- Save each single/pair choice in a durable configuration draft; allow unchanged
  values and check duplicates only after the complete configuration is selected.
- Generate labeled score-timeline, episode-distribution, and Smooth L1 loss plots;
  accept a 2–3 sentence, 80-word interpretation through a run-bound MCP tool.
- Calculate exact score statistics and termination counts/percentages from
  episode records, including unrecorded outcomes, separately from interpretation.
- Deduplicate shared reference runs, preserve seed/configuration context, and
  reuse saved analyses when golden or all-time roles change.
- Recover unfinished choices, ambiguous submissions, comparisons, and analyses
  from event snapshots without automatically repeating a simulation submission.
- Count complete configuration comparisons for reporting and seed stagnation;
  include all draft conversations and vision analysis in reported LLM time.
- Show saved analyses in simulation details and shorten displayed run UUIDs to
  their first group while preserving full identifiers in storage and links.
- Update runtime/prompt documentation and tests for reset experiments; no
  migration or backward compatibility path is introduced.

## [4.0.0] - 2026-11-14 @ 20:19

### Summary

Use Snake Lab 3.0.1 for fresh experiments with a required Transformer, tunable
EpsilonNice, and 500-episode runs.

Use the standalone LlamaSrv service for shared inference and manage only
Ax3l's own application services.

- Replace the owned inference listener with a configurable `llamasrv_url`,
  defaulting to `http://127.0.0.1:51001`; exclude it from CMDB listener inventory.
- Remove model units, model constants and file checks, startup delays,
  `-model` options, and legacy inference migrations. Limit the watchdog to
  Ax3l and reporting; it never restarts the shared inference service.
- Remove the unused global MCP registration generator, obsolete inference
  setup guides, and the architecture image showing embedded inference.
  Remove the unused direct `httpx` dependency; keep per-conversation MCP
  sessions private to Ax3l.
- Reject the retired `network.llm` configuration; there is no compatibility
  migration. Both optimization entry points use LlamaSrv by default.
- Fix the model to Transformer with four attention heads; retain the existing
  five single-parameter turns and add a joint Nice probability/duration turn.
  Keep the full ordinary epsilon decay range and defaults that make Nice
  eligible at episode 227.
- Centralize simulation defaults and validation behind `SimulationConfiguration`;
  include every new setting in configuration reads, uniqueness checks, and
  comparable histories, preserving the string model type.
- Add fractional distance-reward choices and reject positive-sum pairs; keep
  validation, finite-space exhaustion, and the 55-cell report consistent.
- Explain the 24-feature vector and exploration behavior in prompts; report
  model settings, exploration counts, training rewards, and termination outcomes.
- Update bundled contract snapshots, documentation, and fresh-install tests;
  remove the unused incomplete v3 configuration schema.

## [3.2.1] - 2026-11-05 @ 03:54

- Website correction.

## [3.2.0] - 2026-11-05 @ 03:50

- Attach the pinned BMForge RCA skill for read-only production evidence collection
  and local root-cause analysis.
- Updated website.

## [3.1.2] - 2026-10-28 @ 05:00

- Updated README.

## [3.1.1] - 2026-10-20 @ 18:20

The **Yohkoh** release is named for the Japanese solar observation satellite.

- Declare Ax3l's MariaDB catalog in `DAx3l.CMDB_DATABASES` for CMDB discovery.

- Remove retired installation artifacts and environment-specific references from
  source, tests, and documentation, including obsolete setup examples in this log.
  MariaDB integration checks now use `AX3L_TEST_DB=1` and require the disposable
  `ax3l_test` database.

## [3.1.0] - 2026-10-20 @ 04:57

The **Webb** release is named for the *James Webb Space Telescope*.

### Summary

Centralize listener defaults in `CMDB_NETWORK` and preserve local network
overrides in `conf/ax3l.json`, following MyCount's configuration model.

- Rename the Qwen2.5 model option from `qwenv` to `qwen2.5` and its unit to
  `qwen2.5-server.service`; rename its constants to `DQwen25`. Upgrade and
  network restart remove the former unit. Qwen3.5 remains the default `qwen` model.

- Add `llm`, `report`, and `zmq` inventory entries to `DAx3l.CMDB_NETWORK`;
  remove the separate host, port, and endpoint constants.
- Create and validate `/opt/prod/ax3l/conf/ax3l.json` during install/upgrade,
  preserve custom files, and resolve omitted settings from defaults.
- Resolve reporting and ZeroMQ defaults through the network interface,
  including local client destinations for wildcard bindings.
- Add `scripts/restart.sh [-model qwen|phi|qwen2.5]` to validate network settings,
  regenerate listener arguments and internal URLs, and restart services without
  reinstalling dependencies. Share unit rendering with installation.

- Use one configuration for every installation; remove environment-specific
  ports, paths, service variants, and the health-only LLM stub.
- Keep local install, upgrade, uninstall, and service helpers;
  use `/opt/prod/ax3l`, `/etc/ax3l/database.env`, and the `ax3l` accounts/database.
  Deployment between machines belongs to DevOps. Database backup and reset
  utilities use this same configuration.

## [3.0.1] - 2026-10-17 @ 00:53

This release celebrates the Cree language. This is the **ayēnānēwosāp** (18) release.

- Show replacement food before the snake's digestion animation starts, keep it
  visible throughout digestion, and resume movement afterward. Regenerate cached GIFs.

## [3.0.0] - 2026-10-17 @ 00:39

This release celebrates the Cree language. This is the **tēpakohposāp** (17) release.

- Add Ax3l-owned reporting tables with automatic initial extraction and incremental
  updates. Count games, moves, and all-time high scores from completed runs only;
  preserve submitted-run and completed-experiment semantics. Keep all source
  tables and SnakeLab unchanged, and provide a reporting-only rebuild command.
- Refresh reporting counters independently of SnakeLab control-service status.

- Preserve cumulative score-distribution checkpoints when simulation IDs have
  gaps, so the #1–500 frame is shown once simulation #500 has been reached.

## [2.8.2] - 2026-10-12 @ 22:00

This release celebrates th eCree language. The number 5 in Cree is *niyānan*

- Make score-distribution frames cumulative every 500 simulations, using the
  final all-simulations axes throughout. Reduce every GIF font by another 25%.

## [2.8.1] - 2026-10-12 @ 21:43

This release celebrates the Cree language. Four in Cree is *nēwo*.

- Show 500 simulations per score-distribution frame, with a fixed Y scale based
  on the blocks and a separate all-simulations Y scale. Reduce GIF font sizes
  while preserving the size of the Number of runs label.

## [2.8.0] - 2026-10-12 @ 21:32

This release celebrates the Cree language; This is the THREE release: **Nisto**.

- Replace the Score Distribution Histogram with a looping blue-bar GIF showing
  separate complete blocks of 200 simulations and a final all-simulations frame.
  Keep axes fixed and embed simulation ranges and counts; show each block for
  two seconds and the final frame for five seconds.

## [2.7.2] - 2026-10-11 @ 16:00

This release celebrates the Cree language: This is the **nīso** (2) release.

- Use the site's logo as the favicon.

## [2.7.0] - 2026-10-11 @ 05:03

This release is in memory of **Leptictis** who died out about 30 million years ago.

- Added architecture and runtime images.

## [2.6.0] - 2026-10-11 @ 02:09

The **Huia** was a large bird native to New Zealand. The last sighting was in 1907. This release is dedicated to its memory.

- Port snake-web-code’s GIF panel with embedded simulation number, high score, and live current score. Bundle its font and regenerate cached animations.

## [2.5.7] - 2026-10-10 @ 15:33

The **Xenia** release is dedicated to [Xenia de la Ossa](https://en.wikipedia.org/wiki/Xenia_de_la_Ossa).

- Updated sidebar.

## [2.5.6] - 2026-10-10 @ 13:03

The **Tatiana** release is dedicated to **Tatiana Ehrenfest**:

*A Dutch mathematician known for her work in graph theory, particularly the mathematics of sequences and combinatorics. Tatiana contributed to the development of de Bruijn sequences.*

- Handle report HTTP connections concurrently and time out idle clients, preventing browser preconnections from blocking the homepage and health checks. Serialize access to shared background cache scheduling.

- End food digestion at the visible tail and resume directly with the next captured move, keeping that tail in place as growth appears. Prevent the previous tail square from flashing after digestion and regenerate cached GIFs.

## [2.5.4] - 2026-10-10 @ 12:41

The **Sophie** release is dedicated to [Sophie Germain](https://en.wikipedia.org/wiki/Sophie_Germain).

- Slow high-score GIF moves to an average of 75 ms and food digestion to 50 ms per segment. Round cumulative playback to GIF's 10 ms ticks and regenerate cached animations under a new renderer version.

## [2.5.3] - 2026-10-10 @ 11:59

The **Rózsa** release is dedicated to [Rózsa Péter](https://en.wikipedia.org/wiki/R%C3%B3zsa_P%C3%A9ter).

- Cache the remaining homepage status calculations in the background, including reconstruction of completed experiments.
- Limit the event list to the latest 500 events before joining messages and simulation scores. Use read-only report connections without table initialization, and log slow homepage operations.

## [2.5.2] - 2026-10-10 @ 11:48

- Animate food travelling from head to tail at 20 ms per segment while the snake holds still, then show captured growth and resume normal playback. Regenerate GIFs under a new renderer cache version.

- Slow high-score GIF playback to 40 ms per move, retaining the 1-second final pause and continuous looping.

## [2.5.1] - 2026-10-10 @ 11:28

The **Philippa** release is dedicated to [Philippa Fawcett](https://en.wikipedia.org/wiki/Philippa_Fawcett).

- Generate missing high-score GIFs in the background, showing the saved SVG until the animation is ready.
- Cache games-played and moves-made totals in memory and refresh stale totals in a separate background worker every 60 seconds while reports are viewed. Keep the last successful totals during refreshes and database outages; no database changes.

## [2.5.0] - 2026-10-10 @ 11:06

- Play high-score GIFs at 20 ms per move, pause on the final frame for 1 second, and loop forever. Use a new renderer cache version to regenerate animations with the updated timing.
- Show looping GIFs of captured high-score games in simulation reports and the current experiment panel, with saved SVG fallback when frames are unavailable.
- Cache generated GIFs on the filesystem by run ID, renderer version, and playback speed; no database changes.

## [2.4.2] - 2026-10-05 @ 18:15

- Added CMDB application metadata.
- Updated `scripts/new-release.sh` script.

## [2.4.1] - 2026-10-03 @ 05:31

- Website's project description updated.

## [2.4.0] - 2026-10-02 @ 01:50

### Changed

- Load the Qwen 3.5 4B vision projector in generated systemd services and require it before service installation.
- Document Qwen 3.5 4B vision projector conversion, installation, server loading, and capability verification.

## [2.3.14] - 2026-10-01 @ 17:20

### Changed

- Widen the Score Distribution page by 25% and show a separate bar for each integer score.

## [2.3.13] - 2026-10-01 @ 17:15

### Changed

- Reduce the Score Distribution plot height to 60% of its previous size.

## [2.3.12] - 2026-09-27 @ 09:52

- Support for the mycount project requires a refresh of this site.

## [2.3.6] - 2026-09-26 @ 17:02

- Minor tweak.

## [2.3.5] - 2026-09-24 @ 18:26

### Changed

- Stop registering SnakeLab tools with the web chat model services. Automated optimization retains its private MCP tool sessions.

## [2.3.4] - 2026-09-23 @ 17:38

### Changed

- Rename "Experiment Cycles" to "Completed Experiments" in the Report Server Status section.

## [1.6.10] - 2026-09-23 @ 17:14

### Fixed

- Handle client disconnects while sending Report Server pages or error responses without logging a broken-pipe traceback.

## [1.6.9] - 2026-09-23 @ 17:07

### Fixed

- Correct the Report Server Status label to "Games Played".

## [1.6.8] - 2026-09-23 @ 17:02

### Changed

- Format Report Server Status scores and counters with comma thousands separators.

## [1.6.7] - 2026-09-23 @ 16:58

### Changed

- Show Experiment Cycles before Simulations Submitted in Report Server status, and add Game Played and Moves Made totals from simulation episodes, including automatic refresh.

## [1.6.6] - 2026-09-22 @ 05:43

### Changed

- Calculate bucket Steps / second as the mean of individual simulation rates, giving each valid simulation equal weight.

## [1.6.5] - 2026-09-22 @ 05:25

### Added

- Add a Steps / second plot using bucket total steps divided by total simulation runtime, below the combined metrics plot in a separate bordered box with a gap between plots.

## [1.6.4] - 2026-09-22 @ 05:15

### Changed

- Combine runtime, LLM time, and Steps per Simulation in one plot, with minutes on the left axis and a distinct purple steps line on the right axis, sharing the same simulation buckets.

## [1.6.3] - 2026-09-22 @ 05:09

### Changed

- Display Simulation Runtime and LLM Time in minutes on the Simulation Metrics page.

### Added

- Add a matching Steps per Simulation plot showing mean total steps per run with the same configurable sequential buckets.

## [1.6.2] - 2026-09-22 @ 04:57

### Changed

- Thin the Simulation Metrics data:
  - Aggregate Simulation Metrics into consecutive simulation buckets (default 20, configurable), plotting mean runtime and LLM time and showing high-score and step summaries in hover details. Include every completed simulation and the final partial bucket.

## [1.6.0] - 2026-09-22 @ 04:46

### Added

- Add Simulation Metrics below Golden Configurations in the Report Server, with matching plot styling and smoothed Simulation Runtime and LLM Time lines for successfully completed simulations, numbered oldest first. LLM time sums logged prompt-to-response intervals, including proposal retries.

## [1.5.0] - 2026-09-21 @ 17:31

### Removed

- Remove Ax3l's static HTTP health endpoint and its port constants. Ax3l continues to serve tool requests over ZeroMQ.

### Added

- Make the watchdog restart inactive or failed Ax3l, reporting, and selected model services, and recover repeated LLM health failures with startup grace and journal logging limited to problems and recovery. Successful watchdog checks remain silent.

- Add coding guidelines adapted from R3el for Ax3l's architecture and development practices, including changelog updates, and direct repository agents to follow them through `AGENTS.md`.

## [1.4.2] - 2026-09-20 @ 12:30

### Changed

- Mark seed changes in the report server's Experiment Highscores plot with purple points, a hover label, and separate legend entries for the blue score line, orange accepted configurations, and purple seed changes.
- Show cumulative thirds in the score histogram: muted red for the oldest third, orange for the oldest two-thirds, and blue for all runs.

## [1.4.0] - 2026-09-20 @ 09:03

### Added

- Begin every LLM optimization conversation with the Snake tutorial context and responsibility for choosing parameters.

## [1.3.10] - 2026-09-20 @ 06:52

### Fixed

- Normalize the event run ID comparison to SnakeLab's collation so differing database collations do not break the Event Log.

## [1.3.9] - 2026-09-20 @ 06:45

### Fixed

- Read Event Log simulation high scores from the SnakeLab database instead of the Ax3l database.

## [1.3.8] - 2026-09-20 @ 06:40

### Changed

- Show each simulation's high score in the Report Server's Simulation Completed event message, including existing entries.

## [1.3.7] - 2026-09-19 @ 19:58

### Summary

- Remove unused categories from the Report Server's Event Log.
- Add static project website content.

### Added

- Add an explanation of the *golden config* and *seed changes* to the website.

### Removed

- Remove unused Metrics, Process, and System categories from the Event Log catalog and filter choices.

### Changed

- Clarify and verify that seed rotation occurs after nine complete round-robin
  cycles without improvement, including exhausted parameter skips. Regression
  coverage checks restart recovery and renewed eligibility on a different seed.

## [1.3.6] - 2026-09-19 @ 12:08

### HotFix Summary

This release addresses the scenario (reached at simulation number 885) where all legal choices for a finite parameter space, such as sequence length, have already been tried. Ax3l skips that parameter and advances to the next round-robin step. Exhaustion is checked against the current seed and otherwise identical settings, so a change to either can make choices available again.

### Fixed

- Skip exhausted finite parameter spaces before starting an LLM conversation,
  preserving round-robin progress and seed-rotation cycle counts across restarts.
- Record each skip as an INFO-level "Parameter space exhausted" entry in the
  Display Manager Event Log, including the parameter for filtering and a message
  explaining that Ax3l is advancing to the next round-robin step.

## [1.3.5] - 2026-09-19 @ 11:36

- Minor website polish.

## [1.3.3] - 2026-09-19 @ 10:58

- Additional minor website tweaks.

## [1.3.0] - 2026-09-19 @ 10:45

- Add a GitHub link.

## [1.3.0] - 2026-09-19 @ 10:42

- Complete rewrite of the website contents.

## [1.2.5] - 2026-09-19 @ 07:15

### Changed

- Widen the Golden Configurations report from 1200px to 1600px to give its columns more room.

## [1.1.0] - 2026-09-15 @ 05:27

### Added

- Add a Golden Configurations report with every baseline and promotion, newest first, including its recorded high score, parameter value change, and links to the saved configuration and the proposing LLM response's reasoning.

## [1.0.8] - 2026-09-15 @ 04:42

### Changed

- Record the Ax3l project version on simulation submission events, including default configurations, parameter proposals, and seed rotations. Seed rotation recovery preserves the version recorded before submission. Requires fresh event tables; no migration is provided.
- Record the assigned parameter on initial and retry prompt events. Replace the Event Log Source column and filter with Parameter; retain source in prompt details. The new event column requires recreating the event tables before running this version.
- Increase the number of rounds before a seed reset from 3 to 9.

## [1.0.7] - 2026-09-14 @ 04:22

### Added

- Add manual local Ax3l database backups using the configured database name.

### Changed

- Updated the English in the `ComparisonRewardPair` prompt.

## [1.0.6] - 2026-09-13 @ 19:36

### Changed

- Recover proposal monitoring after a Snake Lab restart: read stored terminal results for forgotten runs, compare completed proposals, and skip interrupted proposals while retaining the golden configuration.

## [1.0.4] - 2026-09-13 @ 17:46

### Added

- Add a Source filter when Prompt is selected in the Event Log, preserving the selected source during automatic refresh.

## [1.0.3] - 2026-09-13 @ 17:28

### Changed

- Narrow Event Log event choices by category using the shared event catalog, and show prompt sources when the Prompt filter is selected.

## [1.0.2] - 2026-09-13 @ 17:06

### Changed

- Connect Experiment Highscores points with a smooth curve instead of steps.

- Fix SnakeLab MCP startup permissions by creating service files with umask 022 and granting the service group access to existing Python virtual environments during install or upgrade.

## [1.0.1] - 2026-09-13 @ 16:26

### Changed

- Increased epochs from 500 to 1500.

## [1.0.0] - 2026-09-13 @ 16:20

### Added

- Add Experiment Highscores, a Plotly step chart of accepted config scores against simulation count, including lower baselines after seed rotation. Store score snapshots atomically with golden creation events in the fresh database.

- Store prompt module names in `events.source_name` and show them in prompt detail titles, including correction prompts. Requires a clean database reinstall; no upgrade migration.

- Integrate epsilon and reward pair tuning into the seven-entry round robin, with pair reports, bound MCP calls, retry feedback, and complete-cycle seed rotation. Existing experiment events must be reset before using the new order.

- Show the last successful dashboard refresh date/time in UTC beside the Snake Lab server status, using the same font size as Current Highscore.

### Changed

- Increase histogram bar borders to 4 pixels and match the Experiment Highscores chart to the histogram styling, with a 4-pixel highscore line and a centered bottom legend with matching spacing.

### Removed

- Remove `simulation_runs.config` from the fresh-install schema and read configuration values from `configurations` for lookups, duplicate detection, and tuning reports. Requires the matching SnakeLab writer update and a clean database reinstall.

## [0.99.13] - 2026-09-13 @ 14:11

### Changed

- Style the score histogram in dark blue and orange with outlined bars, a chart border, and a bottom legend inside the border.

## [0.99.11] - 2026-09-13 @ 14:03

### Changed

- Run the report server as root to resolve deployment file permission errors.

## [0.99.10] - 2026-09-13 @ 13:59

### Changed

- Run the report server with the deployment virtual environment's Python so it can load Plotly and the other installed application dependencies.

## [0.99.9] - 2026-09-13 @ 13:53

### Added

- Add a Score Distribution Histogram link under Experiment Status, showing all run high scores with the oldest half overlaid in shared bins using an interactive, self-contained Plotly chart.

## [0.99.7] - 2026-09-13 @ 13:28

### Changed

- Put the experiment highscore on its own line and show total submitted simulations and completed round-robin cycles, including automatic refresh.

- Reset event and SnakeLab simulation auto-increment counters after a successful database wipe, so new IDs start at 1.

## [0.99.6] - 2026-09-13 @ 13:01

### Added

- Add Category and Event dropdown filters beneath the event log headers, defaulting to `*` (all) and preserving selections during automatic refresh.

- Add an automatically refreshed Experiment Status section showing the highest recorded Snake Lab score across all runs, independent of the current golden configuration.

### Changed

- Replace automatic dashboard refresh with a dropdown defaulting to No Refresh, with intervals of 5 seconds, 30 seconds, 1 minute, 5 minutes, and 30 minutes.

- Size event log columns to fit their full content without shrinking, leaving Message to use the remaining width.

## [0.99.5] - 2026-09-13 @ 11:50

### Changed

- Restore FirstContact's experiment background and guidance to explore apparently poor choices for useful data and potential higher scores.

## [0.99.3] - 2026-09-13 @ 11:42

### Changed

- Move the HTTP request timeout to `DAx3l.HTTP_TIMEOUT_SECONDS`, retaining the 300-second value.

- Bind each conversation’s MCP tool to Ax3l’s round-robin parameter and accept only a value. Limit tool instructions, baseline data, and history to that parameter; correct unexpected parameter arguments without submitting them.

## [0.99.2] - 2026-09-13 @ 10:58

### Added

- Persist the single-parameter round-robin position in the event DB before each conversation. Restart interrupted thinking on the same parameter and advance after accepted submissions, including lost MCP replies.

### Changed

- Rotate the seed after 3 complete stagnant round-robin cycles instead of counting individual comparisons. Reset on a new golden high score and preserve accounting across restarts.

- Configure Qwen3.5 with `DQwen.CONTEXT_SIZE` (8196 tokens) and a 5-second startup delay, matching the existing QwenV settings. Pass the context size to llama-server on installation and upgrade.

- Reduced number of epochs to 500 to support a fast smoke test.

### Removed

- Remove the original Haiku POC loop, prompt, constants, and unused first-iteration helper with their obsolete tests. Rename optional capture directories to `snakelab`; retain the active optimization entry point.

## [0.99.1] - 2026-09-13 @ 10:18

### Removed

- Remove the Qwen2.5-VL custom tool chat template, missing-tool reminder retries, and extra prose-response warnings in the initial prompt. Use bundled model templates and standard required-tool metadata; missing tool calls now end the conversation with a logged error. Keep validation feedback and submission safety checks.

## [0.99.0] - 2026-09-13 @ 10:12

### Changed

- Rename `LearningRateLoop.py` to `SnakeLabLoop.py` and expand proposals to hidden size, sequence length, batch size, learning rate, and gamma. Keep reward-distance and epsilon pairs out of this iteration; use schema-backed single-parameter prompts, tool validation, per-parameter comparison histories, and actual configuration changes in comparison logs.

## [0.99.0] - 2026-09-13 @ 09:58

### Changed

- Restore Qwen3.5 (`qwen`) as the default for installation, upgrade, and service startup for text-only prompt development. Explicit `-model phi|qwenv` selections remain supported.

### Removed

- Make Snake Lab optimization conversations text-only by removing `LossPlot` and `ComparisonPlot` from initial, comparison, restart, and seed-baseline prompts, including the first-iteration helper. Update proposal instructions to use comparison history without loss curves and document the active prompts in `pages/snake-lab-propts.md`.

## [0.98.12] - 2026-09-12 @ 16:34

### Changed

- Increased num epochs to 1500

## [0.98.11] - 2026-09-12 @ 16:21

### Added

- Add `scripts/wipe-db.sh` to stop Ax3l and SnakeLab and clear both event and simulation data in one transaction. Schemas and accounts remain intact; services remain stopped.

## [0.98.10] - 2026-09-12 @ 16:02

## [0.98.9] - 2026-09-12 @ 15:56

### Changed

- Doubled the plot width

## [0.98.8] - 2026-09-12 @ 15:30

### Changed

- Supply QwenV with an explicit chat template combining vision inputs and Qwen tool definitions, calls, and results. The bundled model template omitted tools, causing prose replies despite required tool calls.

## [0.98.7] - 2026-09-12 @ 15:19

### Changed

- Reduce a missing-tool retry to “Please submit using the submit_single_value tool”. Do not resend the model’s prose response or original prompt material.

- When the LLM replies without a tool call, send only its latest response and a short `UseTool` reminder on the next request. Original prompts and plots are not resent; reminders remain linked to the same logged conversation.

- Make the first single-parameter prompt explicitly require one numeric `submit_single_value` tool call, include constraints from the JSON spec, and limit the change to the selected parameter.

- Explicitly enable llama-server’s Jinja tool-calling support for all models. Unexpected tool responses now report the received function names, finish reason, and captured reply event ID.

## [0.98.6] - 2026-09-12 @ 15:05

### Changed

- Give Chrome writable config/cache paths in Ax3l’s systemd runtime directory. This fixes the browser exiting during plot rendering when home directories are hidden and the filesystem is read-only. Verified headless PNG rendering under the service’s filesystem restrictions.

## [0.98.5] - 2026-09-12 @ 14:55

### Changed

- Provision Chrome for Kaleido inside the application directory, configure its path for Ax3l’s service, and verify PNG rendering during installation. This avoids relying on a browser download in a home directory hidden by systemd.

## [0.98.3] - 2026-09-12 @ 14:39

### Added

- Load external SnakeLab database settings from `snakelab.env` beside Ax3l’s `database.env`. Upgrades validate the required settings before stopping services; the existing Ax3l credentials file remains unchanged.

### Changed

- Grant Ax3l’s database user read-only (`SELECT`) access to `snakelab` during installation and reuse its `DB_*` credentials for simulation reads. Removed the separate `snakelab.env` requirement.

- Give the model service group access to the configuration directory and MCP registration on install/upgrade, fixing the root-only directory created during provisioning. Database credential file permissions are preserved.

## [0.98.2] - 2026-09-12 @ 14:23

### Changed

- Run `ax3l-server` as root to address the reported permission denial executing its installed virtual-environment Python.

## [0.98.1] - 2026-09-12 @ 14:19

### Added

- Prompt log entries link to detail views that display the captured text and embedded PNG plots, without regenerating images from simulation data.

## [0.9.0] - 2026-09-12 @ 14:14

### Added

- Ax3l logs each decoded MCP tool request as `tool_request_received`, including its sender, target, method, protocol version, and payload, before dispatch or validation. Unknown methods are logged too; logging failure prevents execution.

- Ax3l now runs a shared ZeroMQ listener and handles single-value proposals: JSON-spec legality checks return `InvalidValue`, duplicate golden or historical configurations return `NoDupesSingle`, and legal unique candidates are submitted once. Added `is_config_unique()` to the SnakeLab DAL using full JSON equality across all runs. Deployment installs the JSON spec and runs Ax3l from its provisioned virtual environment.

- Added the SnakeLab `submit_single_value` MCP tool and shared `ZMQMsg`/`ZMQClient` boundary. The tool forwards the parameter and numeric value to Ax3l and returns its reply without domain validation or automatic retries. The Ax3l handler remains a separate step.

- Added the SnakeLab stdio MCP entry point and generated `mcp.json` registration. Qwen, Phi, and QwenV launches pass that config to llama-server; installation provisions the MCP SDK in the application's virtual environment. Domain tools will be registered in the new server module.

- The active first iteration seeds an empty Snake Lab database, waits for idle, and sends FirstContact, GoldenConfig, LossPlot, and the learning-rate introduction in one request. Each exact message snapshot is logged as a conversation-linked prompt event; the reply ends the iteration.

- Added `LossPlot`, a dynamic PNG prompt reading per-episode losses from Snake Lab through the DAL. It embeds the PNG in the LLM message and uses `GoldenConfig.run_id` to keep both snippets tied to the same simulation.

- Added Plotly and Kaleido dependencies for dynamic PNG chart generation.

- Added the `GoldenConfig` dynamic prompt. Initialization and explicit refresh read the latest golden creation's run, reason, and stored Snake Lab configuration for use in an LLM conversation.

- Added `golden_config_created` in the Configuration category with a reason. Initial creation uses `Seeded database with default config.`; subsequent creations supply the parameter comparison.

- The Snake Lab main loop submits defaults from the JSON spec when the simulation database is empty, logs the run reference without copying its configuration, and polls every five seconds through completion. It logs the start once and the final outcome to close the cycle. The submission's config link reads its detail page directly from Snake Lab's database through the DAL.

- Added `SnakeLab.get_num_sims()` to count all stored Snake Lab runs through MariaDB, using separate `SNAKELAB_DB_*` credentials without initializing external tables.

### Changed

- Default installation, upgrade, and service startup to `qwenv`, with its vision projector for PNG prompts. Explicit `-model qwen|phi|qwenv` selections remain supported.

- Reduced loss plot PNGs to 750×450 pixels, configured through `DLossPlot.WIDTH`, `HEIGHT`, and `SCALE`.

- `FirstContactSingle` now accepts a JSON parameter key and builds its introduction from a readable name and the simulation spec's description.

- Centralized log categories, event names, and display labels in `DEventCategory`, using a shared `EventCategory` class. The main loop and reporting use the catalog; existing stored event names and categories are preserved.

## [0.8.1] - 2026-09-12 @ 11:14

### Added

- Installed the system Python ZeroMQ dependency. Services using `/usr/bin/python3` require Debian's `python3-zmq` package (`sudo apt-get install python3-zmq`) for the Snake Lab status query; listing `pyzmq` in `requirements.txt` alone does not install it.

## [0.8.0] - 2026-09-12 @ 11:10

### Added

- Added a matching Snake Lab Server status bar above the event log, showing running simulation or idle and updating with automatic refresh.

- Added the SnakeLab ZeroMQ interface to query whether the local server has an active or queued simulation, with strict response validation and bounded waits.

### Changed

- Keep the event log available when Snake Lab is down: its status bar shows unavailable on ZeroMQ transport failures and checks again on each refresh.

- Replaced the event log Refresh button with automatic refresh every 30 seconds, configurable through `DReportMgr.REFRESH_SECONDS`. Updates preserve scroll position and keep the current entries visible if refresh fails.

## [0.7.10] - 2026-09-12 @ 10:26

### Added

- Added `DConversation` definitions for the conversation category and event names, shared by the main loop, reporting, and display-label mapping.

### Changed

- Each haiku request now uses a fresh random integer from 0 through 30 in the prompt: `Write a haiku based on the number X.`

## [0.7.9] - 2026-09-12 @ 10:10

### Changed

- Split the event log timestamp into Date (`YYYY-MM-DD`) and Time (`HH:MM:SS`) columns, omitting fractional seconds from the display.

## [0.7.7] - 2026-09-12 @ 10:06

### Changed

- Reduced the Event column width from `23ch` to `12ch` to give the Message column more room.

## [0.7.6] - 2026-09-12 @ 10:02

### Changed

- Changed the `reply_received` display label to `Response`.

## [0.7.5] - 2026-09-12 @ 10:01

### Changed

- Shortened the `wait_ended` display label to `Sleep`.

- Shortened the `prompt_sent` display label to `Prompt`.

- Shortened conversation lifecycle display labels to `Started` and `Ended`; the Category column already identifies them as conversation events.

## [0.7.4] - 2026-09-12 @ 09:57

### Added

- Added shared event display labels in `DEventDisplay`. The loop logs `wait_started`, displayed as `Sleep`; existing `sleep` events receive the same label. Hovering a label shows its raw event name. New sleep messages record `Sleep for seconds: (x)` using the configured interval.

### Changed

- Expanded the development guidance for the fixed platform, clear module responsibilities, strict DAL, and thin slices without speculative defensive code. Moved it into `README.md` and updated the homepage and architecture links.

## [0.7.3] - 2026-09-12 @ 09:42

### Added

- Added the global `DAx3l.RAW_LOGS_ENABLED` flag, defaulting to `False`. The haiku loop creates no capture directories or files while disabled; database events and normal console/journal status remain available. Set it to `True` to restore raw captures. Existing captures are not deleted.

- Conversation replies now link from their assistant message text to a detail page showing the event envelope and every captured response field, including usage and timings.

## [0.7.2] - 2026-09-12 @ 09:25

### Changed

- Gave the event log separate Time, ID, Level, Category, Event, and Message columns while retaining single-line striped rows.

## [0.7.1] - 2026-09-12 @ 09:20

### Changed

- Made event log entries single-line rows with alternating dark/light backgrounds. Long entries truncate with an ellipsis; hover reveals the full entry.

- Styled the event log with a dark background, green monospace lettering, and bordered sections, controls, and log entries.

- The reporting event log now shows the newest entries first.

## [0.7.0] - 2026-09-12 @ 09:06

### Changed

- Reporting now listens on `0.0.0.0` by default, including under systemd. The event log is available at `http://neuromancer.osoyalce.com:28870/`. Use `--host 127.0.0.1` for local-only access.

## [0.6.0] - 2026-09-12 @ 09:00

### Added

- Added `DSnakeLab.HAIKU_SLEEP_SECONDS` (default: 5) to configure the delay between haiku requests and their logged wait messages.

### Changed

- The haiku request count defaults to `DSnakeLab.HAIKU_COUNT` in `ax3l/constants/DSnakeLab.py` for manual and service runs. It is initially `0` (repeat until stopped); `--count` overrides it for manual runs.

#### Service startup

- `ax3l-server` now starts the haiku loop against the local LLM while serving `/health`. Systemd supplies database credentials and a writable capture directory at `/var/lib/ax3l/haiku`. Stopping the service interrupts the loop and records conversation end.

## [0.5.0] - 2026-09-12 @ 08:52

### Added

#### Reporting

- Added a Jinja2 event-log page at `/` with chronological log lines and a Refresh button, showing the latest 500 events. `/health` remains available. Deployment includes the HTML template; the Python environment needs `Jinja2` from `requirements.txt`.

- Integrated `DbMgr.log()` into the haiku loop for linked conversation, prompt, full response, wait, and failure events. Load `DB_*` credentials before running; file capture remains available.

- Added `DbMgr.log()` to atomically store an event envelope and message, returning the event ID with optional process and parent-event links.

## [0.4.1] - 2026-09-12 @ 07:24

### Added

- Added `DbMgr` with MariaDB connection ownership, generic parameterized SQL methods, and transaction support. Initialization creates shared event envelope, message, list-item, and key/value tables. Verified against a disposable database.

- Added a minimal SnakeLab haiku loop with a shared prompt class and LLM HTTP interface. Saves requests, complete response bodies, headers, and a run log; waits five seconds between requests.

#### Running the haiku loop

From the project root, run:

```bash
set -a
. /etc/ax3l/database.env
set +a
python3 -m ax3l.app.snakelab.main-loop --url http://neuromancer.osoyalce.com:27770
```

The loop asks the running model to write a haiku, captures the response, sleeps
five seconds, and repeats. Each request starts with fresh context. Press Ctrl-C
to stop, or append `--count 2` to stop after two requests.

Output is saved in a timestamped directory under `tmp/haiku/`, printed at startup.
It includes request JSON, exact response bodies, HTTP headers and status, and
`run.log` containing output and errors. Use `--output /tmp/haiku` to change the
output root. HTTP or transport errors are logged and stop the loop.

## [0.4.0] - 2026-09-12 @ 06:13

### Added

- Added `qwenv-server` and `-model qwenv` for Qwen2.5-VL, including its vision projector and 4096-token context. All model services are installed and upgraded together.

### Removed

- Removed model service conflicts and automatic stopping/disabling of other models. Starting a model leaves existing model processes alone.

## [0.3.0] - 2026-09-12 @ 05:13

### Added

- Added `phi-server` alongside the renamed `qwen-server`, sharing the LLM port with mutually exclusive systemd units. Service control, installation, and upgrade accept `-model qwen|phi` (default Qwen); upgrade removes legacy `llm-server` units.

- Added `scripts/upgrade.sh` to update application modules and systemd units from the current checkout while preserving the database, credentials, and accounts.

### Changed

- Service installation uses the shared `DLlama.MODEL_DIR` for the model path, keeping `DLlama.BASE_DIR` for llama.cpp.

- Service installation validates generated units and stops services before replacing application files.

## [0.2.2] - 2026-09-12 @ 04:25

### Added

- Added `--metrics` switch to `llama-server` to enable it

## [0.2.1] - 2026-09-12 @ 03:28

### Changed

- `install.sh` now installs, enables, and starts all four systemd services after provisioning the database and Linux account, so uninstall/install restores the service units without a separate command.

## [0.2.0] - 2026-09-12 @ 03:23

### Changed

- LLM now binds to `DLlama.HOST` (`0.0.0.0`) to allow connections from another machine.

- Model services launch the real server using the executable and model paths from `DLlama` and `DQwen`.

## [0.1.1] - 2026-09-12 @ 03:15

### Changed

- Moved LLM, Ax3l, reporting, and MariaDB port numbers into their constants classes. Installers read the constants; existing port assignments are unchanged.

## [0.1.0] - 2026-09-12 @ 03:01

### Added

- Added a Scripts reference page, linked from the project home page, covering setup, service control, uninstall, and release commands.

- Added `scripts/services.sh start|stop`: starts the LLM, waits `DQwen.STARTUP_SECONDS` (7 seconds), then starts reporting, Ax3l, and watchdog. Shutdown uses the reverse order; service installation and uninstall follow the same ordering.

- Added four systemd services: LLM, Ax3l, reporting, and watchdog. The watchdog reports Ax3l systemd state and LLM health to the journal.

- Added `scripts/install-services.sh` to render unit templates, copy Python modules, and enable/start services. Uninstall now stops, disables, and removes those units.

- Added `scripts/uninstall.sh` to remove the installation, credentials, MariaDB database/account, and Linux service account/group.

- Added `scripts/install.sh` to create installation directories, provision the local MariaDB database and account, and generate owner-only credentials. Existing credentials are reused and database login is verified.

- Installation creates a Linux system user and group if absent, with no home directory or interactive login, and assigns application-directory ownership to that account and group.

### Changed

- Excluded local installation artifacts and credentials from Git.

## [0.0.4] - 2026-09-12 @ 01:11

### Changed

- Updated *Ax3l* logo!

- Site name in `_config.yml`

## [0.0.3] - 2026-09-12 @ 00:53

### Added

- GitHub Actions workflow to build and deploy the Jekyll site with GitHub Pages dependencies on pushes to `main` or manual runs, without requiring local Ruby.

## [0.0.2] - 2026-09-12 @ 00:29

## [0.0.1] - 2026-09-12 @ 00:21

### Added

- Initial release.

# Events

The source of truth is `ax3l/constants/DEventCategory.py`. Each category extends
`EventCategory` and defines its stored `CATEGORY`, event-name constants, and
`LABELS` mapping. For example, `DEventCategory.Conversation.RESPONSE` is
`reply_received`, and its label is `Response`. Logging and reporting share this
catalog. Add or change definitions there.

Prompt text is stored in `event_messages`, linked to a `prompt_sent` row in
`events`. The nullable `events.source_name` column records the originating Python
module name without its package or `.py` suffix, for example `GoldenConfig` or
`NoDupes`. The prompt detail heading and browser title include this source as
`Prompt (GoldenConfig): #123`. Inline argument correction prompts use
`ToolConversation`. This column is created on fresh installation; no upgrade
migration is provided.

| Event | Category |
| --- | --- |
| `service_started` | System |
| `service_stopped` | System |
| `service_failed` | System |
| `conversation_started` | Conversation |
| `conversation_ended` | Conversation |
| `prompt_sent` | Conversation |
| `reply_received` | Conversation |
| `llm_request_failed` | LLM |
| `llm_usage_recorded` | Metrics |
| `tool_execution_started` | Tool |
| `tool_request_received` | Tool |
| `tool_execution_completed` | Tool |
| `tool_execution_failed` | Tool |
| `wait_started` | Process |
| `wait_ended` | Process |
| `simulation_submitted` | SnakeLab |
| `simulation_queued` | SnakeLab |
| `simulation_started` | SnakeLab |
| `simulation_completed` | SnakeLab |
| `simulation_cancelled` | SnakeLab |
| `simulation_failed` | SnakeLab |
| `simulation_restarted` | SnakeLab |
| `proposal_accepted` | Configuration |
| `proposal_rejected_invalid` | Configuration |
| `proposal_rejected_duplicate` | Configuration |
| `configuration_compared` | Configuration |
| `golden_config_created` | Configuration |
| `golden_config_replaced` | Configuration |
| `golden_config_retained` | Configuration |
| `golden_config_seed_incremented` | Configuration |

`golden_config_created` is recorded through `ConfigurationLog.golden_config_created`.
Its message is the supplied reason, for example `Parameter x: 2 > 4`.
The initial creation after successfully submitting defaults to an empty simulation
database uses `Seeded database with default config.` as the reason.
The event references the configuration's run through `process_id`; the
initial event links to `simulation_submitted` through `parent_event_id`.
The comparison flow must supply its reason when it records subsequent creations.

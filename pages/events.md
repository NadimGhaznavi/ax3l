# Events

The source of truth is `ax3l/constants/DEventCategory.py`. Each category extends
`EventCategory` and defines its stored `CATEGORY`, event-name constants, and
`LABELS` mapping. For example, `DEventCategory.Conversation.RESPONSE` is
`reply_received`, and its label is `Response`. Logging and reporting share this
catalog. Add or change definitions there.

The Event Log's Category filter narrows Event choices using this catalog, including
valid events with no entries in the latest 500 rows. Historical events present in
those rows remain selectable. Changing category resets an incompatible Event
selection to `*`. Selecting the Prompt event shows a Source column; other Event
selections hide it.

Prompt text is stored in `event_messages`, linked to a `prompt_sent` row in
`events`. The nullable `events.source_name` column records the originating Python
module name without its package or `.py` suffix. The prompt detail heading
and browser title include the recorded source, for example
`Prompt (ExamplePrompt): #123`.

The event catalog and rendering infrastructure remain available while the
replacement conversation workflow is designed. Retired draft, chart-task,
validation, and seed-rotation event definitions have been removed.

| Event | Category |
| --- | --- |
| `conversation_started` | Conversation |
| `conversation_ended` | Conversation |
| `prompt_sent` | Conversation |
| `reply_received` | Conversation |
| `llm_request_failed` | LLM |
| `tool_execution_started` | Tool |
| `tool_request_received` | Tool |
| `tool_execution_completed` | Tool |
| `tool_execution_failed` | Tool |
| `simulation_submitted` | SnakeLab |
| `simulation_queued` | SnakeLab |
| `simulation_started` | SnakeLab |
| `simulation_completed` | SnakeLab |
| `simulation_cancelled` | SnakeLab |
| `simulation_failed` | SnakeLab |
| `simulation_restarted` | SnakeLab |
| `proposal_accepted` | Configuration |
| `configuration_compared` | Configuration |
| `golden_config_created` | Configuration |

`golden_config_created` is recorded through `ConfigurationLog.golden_config_created`.
Its message is the supplied reason, for example `Parameter x: 2 > 4`.
The event references the configuration's run through `process_id` and can link
to the originating event through `parent_event_id`.

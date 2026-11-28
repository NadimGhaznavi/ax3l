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

The four-view loop uses the shared conversation, inference, tool, simulation,
and comparison events. `view_experiment_state_saved` records a durable snapshot
of the shuffled view order, proposals, and simulation progress. A view name is
stored as the prompt's source and parameter metadata. Native `submit_view` calls
and their validated results use the Tool category.

| Event | Category |
| --- | --- |
| `conversation_started` | Conversation |
| `conversation_ended` | Conversation |
| `prompt_sent` | Conversation |
| `reply_received` | Conversation |
| `llm_request_started` | LLM |
| `llm_response_captured` | LLM |
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
| `view_experiment_state_saved` | Configuration |
| `proposal_accepted` | Configuration |
| `configuration_compared` | Configuration |
| `golden_config_created` | Configuration |

Each inference request creates one `llm_response_captured` event, shown as
**Captured output**. Its JSON message holds the accumulated streamed reasoning,
assistant text, and tool-call fragments, plus the request event ID, capture
status, received-chunk count, and UTC time of the last chunk. The first chunk is
committed immediately; later chunks update that event at most every five seconds.
Completion, timeout, connection failure, or a handled interruption flushes the
latest received output and marks the capture completed or interrupted. An abrupt
process termination preserves the last committed snapshot, which can remain
marked in progress and may omit the most recent five seconds of output.

The event links to its captured output and, when available, Reasoning. Selection
and Evaluation show the current capture until a complete `reply_received` event
is saved. Incomplete tool calls are retained for diagnosis and never executed.

`golden_config_created` is recorded through `ConfigurationLog.golden_config_created`.
Its message is the supplied reason, for example `Parameter x: 2 > 4`.
The event references the configuration's run through `process_id` and can link
to the originating event through `parent_event_id`.

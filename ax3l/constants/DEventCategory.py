"""The shared catalog of log categories and their events."""

from ax3l.entities.EventCategory import EventCategory


class DEventCategory:
    class System(EventCategory):
        CATEGORY = "System"
        STARTED = "service_started"
        STOPPED = "service_stopped"
        FAILED = "service_failed"
        LABELS = {
            STARTED: "Service started",
            STOPPED: "Service stopped",
            FAILED: "Service failed",
        }

    class Conversation(EventCategory):
        CATEGORY = "Conversation"
        STARTED = "conversation_started"
        ENDED = "conversation_ended"
        PROMPT = "prompt_sent"
        RESPONSE = "reply_received"
        LABELS = {
            STARTED: "Started",
            ENDED: "Ended",
            PROMPT: "Prompt",
            RESPONSE: "Response",
        }

    class LLM(EventCategory):
        CATEGORY = "LLM"
        REQUEST_FAILED = "llm_request_failed"
        LABELS = {
            REQUEST_FAILED: "LLM request failed",
        }

    class Metrics(EventCategory):
        CATEGORY = "Metrics"
        USAGE_RECORDED = "llm_usage_recorded"
        LABELS = {
            USAGE_RECORDED: "LLM usage",
        }

    class Tool(EventCategory):
        CATEGORY = "Tool"
        RECEIVED = "tool_request_received"
        STARTED = "tool_execution_started"
        COMPLETED = "tool_execution_completed"
        FAILED = "tool_execution_failed"
        LABELS = {
            RECEIVED: "Tool request received",
            STARTED: "Tool started",
            COMPLETED: "Tool completed",
            FAILED: "Tool failed",
        }

    class Process(EventCategory):
        CATEGORY = "Process"
        WAIT_STARTED = "wait_started"
        WAIT_ENDED = "wait_ended"
        SLEEP = "sleep"
        LABELS = {
            WAIT_STARTED: "Sleep",
            WAIT_ENDED: "Sleep",
            SLEEP: "Sleep",
        }

    class SnakeLab(EventCategory):
        CATEGORY = "SnakeLab"
        SUBMITTED = "simulation_submitted"
        QUEUED = "simulation_queued"
        STARTED = "simulation_started"
        COMPLETED = "simulation_completed"
        CANCELLED = "simulation_cancelled"
        FAILED = "simulation_failed"
        RESTARTED = "simulation_restarted"
        LABELS = {
            SUBMITTED: "Simulation submitted",
            QUEUED: "Simulation queued",
            STARTED: "Simulation started",
            COMPLETED: "Simulation completed",
            CANCELLED: "Simulation cancelled",
            FAILED: "Simulation failed",
            RESTARTED: "Simulation restarted",
        }
        TERMINAL_EVENTS = {"completed": COMPLETED, "cancelled": CANCELLED, "failed": FAILED}

    class Configuration(EventCategory):
        CATEGORY = "Configuration"
        PROPOSAL_ACCEPTED = "proposal_accepted"
        PROPOSAL_INVALID = "proposal_rejected_invalid"
        PROPOSAL_DUPLICATE = "proposal_rejected_duplicate"
        COMPARED = "configuration_compared"
        GOLDEN_CREATED = "golden_config_created"
        GOLDEN_REPLACED = "golden_config_replaced"
        GOLDEN_RETAINED = "golden_config_retained"
        SEED_ROTATION_STARTED = "seed_rotation_started"
        GOLDEN_SEED_INCREMENTED = "golden_config_seed_incremented"
        LABELS = {
            PROPOSAL_ACCEPTED: "Proposal accepted",
            PROPOSAL_INVALID: "Invalid proposal",
            PROPOSAL_DUPLICATE: "Duplicate proposal",
            COMPARED: "Configuration compared",
            GOLDEN_CREATED: "Golden configuration created",
            GOLDEN_REPLACED: "Golden configuration replaced",
            GOLDEN_RETAINED: "Golden configuration retained",
            SEED_ROTATION_STARTED: "Seed rotation started",
            GOLDEN_SEED_INCREMENTED: "Golden configuration seed incremented",
        }

    ALL = (System, Conversation, LLM, Metrics, Tool, Process, SnakeLab, Configuration)
    BY_NAME = {category.CATEGORY: category for category in ALL}

    @classmethod
    def label(cls, category: str, name: str) -> str:
        """Show unrecognized stored events by their raw name."""
        definition = cls.BY_NAME.get(category)
        return definition.LABELS.get(name, name) if definition else name

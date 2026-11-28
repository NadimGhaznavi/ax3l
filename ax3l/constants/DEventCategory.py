"""The shared catalog of log categories and their events."""

from ax3l.entities.EventCategory import EventCategory


class DEventCategory:
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
        REQUEST_STARTED = "llm_request_started"
        REQUEST_FAILED = "llm_request_failed"
        RESPONSE_CAPTURED = "llm_response_captured"
        LABELS = {
            REQUEST_STARTED: "Request started",
            REQUEST_FAILED: "Request failed",
            RESPONSE_CAPTURED: "Captured output",
        }

    class Tool(EventCategory):
        CATEGORY = "Tool"
        RECEIVED = "tool_request_received"
        STARTED = "tool_execution_started"
        COMPLETED = "tool_execution_completed"
        FAILED = "tool_execution_failed"
        LABELS = {
            RECEIVED: "Request received",
            STARTED: "Started",
            COMPLETED: "Completed",
            FAILED: "Failed",
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
        COMPARED = "configuration_compared"
        GOLDEN_CREATED = "golden_config_created"
        STATE_SAVED = "view_experiment_state_saved"
        LABELS = {
            PROPOSAL_ACCEPTED: "Proposal accepted",
            COMPARED: "Compared",
            GOLDEN_CREATED: "Golden created",
            STATE_SAVED: "View experiment saved",
        }

    ALL = (Conversation, LLM, Tool, SnakeLab, Configuration)
    BY_NAME = {category.CATEGORY: category for category in ALL}

    @classmethod
    def label(cls, category: str, name: str) -> str:
        """Show unrecognized stored events by their raw name."""
        definition = cls.BY_NAME.get(category)
        return definition.LABELS.get(name, name) if definition else name

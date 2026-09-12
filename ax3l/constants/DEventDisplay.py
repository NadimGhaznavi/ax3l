"""Human-readable labels for stored event names."""


class DEventDisplay:
    LABELS = {
        "service_started": "Service started",
        "service_stopped": "Service stopped",
        "service_failed": "Service failed",
        "conversation_started": "Started",
        "conversation_ended": "Ended",
        "prompt_sent": "Prompt",
        "reply_received": "Reply received",
        "llm_request_failed": "LLM request failed",
        "llm_usage_recorded": "LLM usage",
        "tool_execution_started": "Tool started",
        "tool_execution_completed": "Tool completed",
        "tool_execution_failed": "Tool failed",
        "wait_started": "Sleep",
        "sleep": "Sleep",  # Events stored before display labels were introduced.
        "wait_ended": "Sleep",
        "simulation_submitted": "Simulation submitted",
        "simulation_queued": "Simulation queued",
        "simulation_started": "Simulation started",
        "simulation_completed": "Simulation completed",
        "simulation_cancelled": "Simulation cancelled",
        "simulation_failed": "Simulation failed",
        "simulation_restarted": "Simulation restarted",
        "proposal_accepted": "Proposal accepted",
        "proposal_rejected_invalid": "Invalid proposal",
        "proposal_rejected_duplicate": "Duplicate proposal",
        "configuration_compared": "Configuration compared",
        "golden_config_replaced": "Golden configuration replaced",
        "golden_config_retained": "Golden configuration retained",
        "golden_config_seed_incremented": "Golden configuration seed incremented",
    }

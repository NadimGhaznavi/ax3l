from typing import Final


class DConversation:
    CATEGORY: Final[str] = "Conversation"

    STARTED: Final[str] = "conversation_started"
    ENDED: Final[str] = "conversation_ended"
    PROMPT: Final[str] = "prompt_sent"
    RESPONSE: Final[str] = "reply_received"

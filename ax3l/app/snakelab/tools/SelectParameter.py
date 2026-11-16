"""Forward Qwen's selected setting to Ax3l."""

import asyncio
import json

from ax3l.interface.Network import Network
from ax3l.zmq.ZMQClient import ZMQClient
from ax3l.zmq.ZMQMsg import ZMQMsg


class SelectParameter:
    def __init__(self, endpoint: str | None = None):
        self._client = ZMQClient(endpoint if endpoint is not None else Network.endpoint(destination=True))

    async def submit(self, draft_id: str, parameter: str) -> str:
        response = await asyncio.to_thread(
            self._client.request,
            ZMQMsg(sender="mcp-snakelab", target="snakelab", method="select_parameter",
                   payload={"draft_id": draft_id, "parameter": parameter}),
        )
        return json.dumps(response.payload, ensure_ascii=False, allow_nan=False)

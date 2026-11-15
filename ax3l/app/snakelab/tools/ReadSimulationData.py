"""Forward a small data-page request with its private draft binding."""

import asyncio
import json

from ax3l.interface.Network import Network
from ax3l.zmq.ZMQClient import ZMQClient
from ax3l.zmq.ZMQMsg import ZMQMsg


class ReadSimulationData:
    def __init__(self, endpoint: str | None = None):
        self._client = ZMQClient(endpoint if endpoint is not None else Network.endpoint(destination=True))

    async def read(self, draft_id: str, url: str) -> str:
        response = await asyncio.to_thread(
            self._client.request,
            ZMQMsg(sender="mcp-snakelab", target="snakelab", method="read_simulation_data",
                   payload={"draft_id": draft_id, "url": url}),
        )
        return json.dumps(response.payload, ensure_ascii=False, allow_nan=False)

"""Forward the bound run's interpretation through Ax3l's tool transport."""

import asyncio
import json

from ax3l.interface.Network import Network
from ax3l.zmq.ZMQClient import ZMQClient
from ax3l.zmq.ZMQMsg import ZMQMsg


class SubmitSimulationSummary:
    def __init__(self, endpoint: str | None = None):
        self._client = ZMQClient(endpoint if endpoint is not None else Network.endpoint(destination=True))

    async def submit(self, run_id: str, summary: str) -> str:
        response = await asyncio.to_thread(
            self._client.request,
            ZMQMsg(sender="mcp-snakelab", target="snakelab", method="submit_simulation_summary",
                   payload={"run_id": run_id, "summary": summary}),
        )
        return json.dumps(response.payload, ensure_ascii=False, allow_nan=False)

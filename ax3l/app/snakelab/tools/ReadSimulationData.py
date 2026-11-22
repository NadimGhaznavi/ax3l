"""Forward data-page requests with a private draft or analysis-run binding."""

import asyncio

from ax3l.interface.Network import Network
from ax3l.zmq.ZMQClient import ZMQClient
from ax3l.zmq.ZMQMsg import ZMQMsg


class ReadSimulationData:
    def __init__(self, endpoint: str | None = None):
        self._client = ZMQClient(endpoint if endpoint is not None else Network.endpoint(destination=True))

    async def read(self, draft_id: str, url: str) -> dict:
        return await self._read("read_simulation_data", {"draft_id": draft_id, "url": url})

    async def read_run(self, run_id: str, url: str) -> dict:
        return await self._read("read_analysis_data", {"run_id": run_id, "url": url})

    async def _read(self, method: str, payload: dict) -> dict:
        response = await asyncio.to_thread(
            self._client.request,
            ZMQMsg(sender="mcp-snakelab", target="snakelab", method=method, payload=payload),
        )
        return response.payload

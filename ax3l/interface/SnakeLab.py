"""Query the local Snake Lab control interface over ZeroMQ."""

from uuid import uuid4

import zmq

from ax3l.constants.DSnakeLab import DSnakeLab


class SnakeLab:
    def __init__(self, endpoint: str = DSnakeLab.ENDPOINT):
        self.endpoint = endpoint

    def is_simulation_running(self) -> bool:
        """Return whether work is running, paused, cancelling, or queued.

        This synchronous call does not retry. Transport and protocol errors
        propagate; an unavailable server is not an idle server.
        """
        request_id = str(uuid4())
        request = {
            "protocol_version": DSnakeLab.PROTOCOL_VERSION,
            "request_id": request_id,
            "method": "simulation.active",
            "payload": {},
        }
        with zmq.Context() as context:
            with context.socket(zmq.REQ) as socket:
                socket.setsockopt(zmq.LINGER, 0)
                socket.setsockopt(zmq.SNDTIMEO, DSnakeLab.TIMEOUT_MS)
                socket.setsockopt(zmq.RCVTIMEO, DSnakeLab.TIMEOUT_MS)
                socket.connect(self.endpoint)
                socket.send_json(request)
                response = socket.recv_json()

        if not isinstance(response, dict):
            raise ValueError("Snake Lab response must be an object")
        version = response.get("protocol_version")
        if type(version) is not int or version != DSnakeLab.PROTOCOL_VERSION:
            raise ValueError("Snake Lab response has an unsupported protocol version")
        if response.get("request_id") != request_id:
            raise ValueError("Snake Lab response request_id does not match")
        if response.get("status") == "error":
            raise RuntimeError(f"Snake Lab query failed: {response.get('error')}")
        if response.get("status") != "ok":
            raise ValueError("Snake Lab response has an invalid status")
        payload = response.get("payload")
        if not isinstance(payload, dict) or "run" not in payload:
            raise ValueError("Snake Lab response payload must contain run")
        run = payload["run"]
        if run is None:
            return False
        if not isinstance(run, dict) or run.get("state") not in (
            "running", "paused", "cancelling", "queued"
        ):
            raise ValueError("Snake Lab response has an invalid active run state")
        return True

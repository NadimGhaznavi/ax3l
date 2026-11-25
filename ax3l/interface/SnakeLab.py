"""Query Snake Lab through its control interface and MariaDB database."""

from contextlib import contextmanager
from collections.abc import Iterator
from uuid import UUID, uuid4

from ax3l.zmq.ZMQClient import ZMQClient

from ax3l.constants.DSnakeLab import DSnakeLab
from ax3l.interface.database.DbMgr import DbMgr
from ax3l.interface.database.SnakeLabDb import SnakeLabDb


class SnakeLabQueryError(RuntimeError):
    def __init__(self, error):
        super().__init__(f"Snake Lab query failed: {error}")
        self.code = error.get("code") if isinstance(error, dict) else None


class SimulationUnavailable(RuntimeError):
    """A run has left the server without a durable terminal result."""


class SnakeLab:
    def __init__(self, endpoint: str = DSnakeLab.ENDPOINT):
        self.endpoint = endpoint

    @contextmanager
    def _data(self) -> Iterator[SnakeLabDb]:
        """Own a read connection for one external-data operation."""
        db = DbMgr(database=DSnakeLab.DATABASE, initialize_event_tables=False)
        try:
            yield SnakeLabDb(db)
        finally:
            db.close()

    def get_num_sims(self) -> int:
        """Return the total stored run count using Ax3l’s DB credentials.

        Database errors propagate. The connection is closed after each query,
        and no tables are initialized in the Snake Lab database.
        """
        with self._data() as simulations:
            return simulations.get_num_sims()

    def get_episode_totals(self) -> dict[str, int]:
        """Return total games and moves recorded by Snake Lab."""
        with self._data() as simulations:
            return simulations.get_episode_totals()

    def get_high_score(self) -> int | None:
        """Return the experiment's highest recorded score across configs and seeds."""
        with self._data() as simulations:
            return simulations.get_high_score()

    def get_run_scores(self) -> dict[int, int | None]:
        """Return the latest score per simulation ID, oldest submissions first."""
        with self._data() as simulations:
            return simulations.get_run_scores()

    def get_episode_scores(self, run_id: str) -> list[dict]:
        """Read a run's recorded scores for its training progress chart."""
        UUID(run_id)
        with self._data() as simulations:
            return simulations.get_episode_scores(run_id)


    def get_latest_completed_run_id(self) -> str | None:
        with self._data() as simulations:
            return simulations.get_latest_completed_run_id()

    def get_all_time_best_run_id(self) -> str | None:
        with self._data() as simulations:
            return simulations.get_all_time_best_run_id()

    def is_simulation_running(self) -> bool:
        """Return whether work is running, paused, cancelling, or queued.

        This synchronous call does not retry. Transport and protocol errors
        propagate; an unavailable server is not an idle server.
        """
        payload = self._request("simulation.active", {})
        if "run" not in payload:
            raise ValueError("Snake Lab response payload must contain run")
        run = payload["run"]
        if run is None:
            return False
        if not isinstance(run, dict) or run.get("state") not in (
            "running", "paused", "cancelling", "queued"
        ):
            raise ValueError("Snake Lab response has an invalid active run state")
        return True

    def get_config(self, run_id: str) -> dict | None:
        UUID(run_id)
        with self._data() as simulations:
            return simulations.get_config(run_id)

    def get_run_summary(self, run_id: str) -> dict | None:
        UUID(run_id)
        with self._data() as simulations:
            return simulations.get_run_summary(run_id)

    def get_run_result(self, run_id: str) -> dict | None:
        UUID(run_id)
        with self._data() as simulations:
            return simulations.get_run_result(run_id)

    def get_highscore_frames(self, run_id: str) -> list[dict] | None:
        """Retrieve and validate a complete captured game; None means no capture."""
        UUID(run_id)
        try:
            payload = self._request("simulation.highscore_frames", {"run_id": run_id})
        except SnakeLabQueryError as error:
            if error.code == "frames_unavailable":
                return None
            raise
        frames = payload.get("frames")
        if payload.get("run_id") != run_id or not isinstance(frames, list) or not frames:
            raise ValueError("Snake Lab response has invalid high-score frames")
        episode = None
        grid_size = None
        for step, frame in enumerate(frames):
            if (not isinstance(frame, dict) or type(frame.get("version")) is not int
                    or frame["version"] != 1 or type(frame.get("step")) is not int
                    or frame["step"] != step or type(frame.get("episode")) is not int
                    or frame["episode"] < 1):
                raise ValueError("Snake Lab response has invalid frame metadata")
            board = frame.get("board")
            if not isinstance(board, dict) or set(board) != {
                "grid_size", "snake_head", "snake_body", "food", "direction", "score"
            }:
                raise ValueError("Snake Lab response has invalid board fields")
            size = board["grid_size"]
            if (not isinstance(size, list) or len(size) != 2
                    or any(type(n) is not int or n <= 0 for n in size)):
                raise ValueError("Snake Lab response has invalid grid dimensions")
            if step == 0:
                episode, grid_size = frame["episode"], size
            if frame["episode"] != episode or size != grid_size:
                raise ValueError("Snake Lab response mixes games or grid dimensions")
            if not isinstance(board["snake_body"], list):
                raise ValueError("Snake Lab response has invalid snake body")
            positions = [board["snake_head"], *board["snake_body"]]
            if board["food"] is not None:
                positions.append(board["food"])
            for position in positions:
                if (not isinstance(position, list) or len(position) != 2
                        or any(type(n) is not int for n in position)
                        or not (0 <= position[0] < size[0] and 0 <= position[1] < size[1])):
                    raise ValueError("Snake Lab response has invalid board coordinates")
            direction = board["direction"]
            if (not isinstance(direction, list) or len(direction) != 2
                    or any(type(n) is not int for n in direction)
                    or direction not in ([1, 0], [-1, 0], [0, 1], [0, -1])
                    or type(board["score"]) is not int or board["score"] < 0):
                raise ValueError("Snake Lab response has invalid direction or score")
        return frames


    def find_config_run(self, config: dict) -> str | None:
        with self._data() as simulations:
            return simulations.find_config_run(config)


    def get_episode_diagnostics(self, run_id: str) -> dict:
        UUID(run_id)
        with self._data() as simulations:
            return simulations.get_episode_diagnostics(run_id)


    def submit_simulation(self, config: dict) -> str:
        """Submit once and return the queued run ID; never retry a submission."""
        payload = self._request("simulation.submit", {"config": config})
        if payload.get("state") != "queued" or not isinstance(payload.get("run_id"), str):
            raise ValueError("Snake Lab response has an invalid submission")
        UUID(payload["run_id"])
        return payload["run_id"]

    def get_simulation_status(self, run_id: str) -> str:
        UUID(run_id)
        try:
            payload = self._request("simulation.status", {"run_id": run_id})
        except SnakeLabQueryError as error:
            if error.code != "run_not_found":
                raise
            # The control server only remembers runs from its current process.
            result = self.get_run_result(run_id)
            if result is not None and result["status"] in ("completed", "failed", "cancelled"):
                return result["status"]
            raise SimulationUnavailable(
                f"Simulation {run_id} is unknown to the current Snake Lab server "
                "and has no stored terminal result."
            ) from error
        if payload.get("run_id") != run_id or payload.get("state") not in (
            "queued", "running", "paused", "cancelling", "completed", "failed", "cancelled"
        ):
            raise ValueError("Snake Lab response has an invalid run status")
        return payload["state"]

    def _request(self, method: str, payload: dict) -> dict:
        request_id = str(uuid4())
        request = {
            "protocol_version": DSnakeLab.PROTOCOL_VERSION,
            "request_id": request_id,
            "method": method,
            "payload": payload,
        }
        response = ZMQClient(self.endpoint, DSnakeLab.TIMEOUT_MS / 1000).request_json(request)

        if not isinstance(response, dict):
            raise ValueError("Snake Lab response must be an object")
        version = response.get("protocol_version")
        if type(version) is not int or version != DSnakeLab.PROTOCOL_VERSION:
            raise ValueError("Snake Lab response has an unsupported protocol version")
        if response.get("request_id") != request_id:
            raise ValueError("Snake Lab response request_id does not match")
        if response.get("status") == "error":
            raise SnakeLabQueryError(response.get("error"))
        if response.get("status") != "ok":
            raise ValueError("Snake Lab response has an invalid status")
        payload = response.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("Snake Lab response payload must be an object")
        return payload

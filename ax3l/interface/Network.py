"""Resolve network defaults and production overrides once per process."""

from functools import cache
from pathlib import Path

from ax3l.constants.DAx3l import DAx3l
from ax3l.interface.Configuration import Configuration


class Network:
    @staticmethod
    def binding(use: str) -> tuple[str, int]:
        path = Path(DAx3l.BASE_DIR) / DAx3l.CONFIG_FILE
        return Network._bindings(path, DAx3l.CMDB_NETWORK)[use]

    @staticmethod
    def destination(use: str) -> tuple[str, int]:
        interface, port = Network.binding(use)
        return ('127.0.0.1' if interface == '0.0.0.0' else interface, port)

    @staticmethod
    def endpoint(*, destination: bool = False) -> str:
        host, port = Network.destination('zmq') if destination else Network.binding('zmq')
        return f'tcp://{host}:{port}'

    @staticmethod
    @cache
    def _bindings(path: Path, defaults: tuple[tuple[str, str, int], ...]) -> dict[str, tuple[str, int]]:
        return Configuration.read(path, defaults)

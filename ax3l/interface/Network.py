"""Expose configured listeners and the outbound LlamaSrv URL."""

from functools import cache

from ax3l.interface.Configuration import Configuration


class Network:
    @staticmethod
    def binding(use: str) -> tuple[str, int]:
        return Network._configuration().network[use]

    @staticmethod
    def llamasrv_url() -> str:
        return Network._configuration().llamasrv_url

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
    def _configuration() -> Configuration:
        return Configuration()

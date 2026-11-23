"""Resolve Ax3l listeners and its LlamaSrv dependency."""

from ipaddress import IPv4Address
import json
from pathlib import Path
from urllib.parse import urlsplit

from ax3l.constants.DAx3l import DAx3l


class Configuration:
    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else Path(DAx3l.BASE_DIR) / DAx3l.CONFIG_FILE
        self.network = {use: (interface, port) for use, interface, port in DAx3l.CMDB_NETWORK}
        self.llamasrv_url = DAx3l.LLAMASRV_URL
        try:
            text = self.path.read_text()
        except FileNotFoundError:
            return
        try:
            values = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f'{self.path}: invalid JSON: {error}') from error
        if not isinstance(values, dict) or values.keys() - {'network', 'llamasrv_url'}:
            raise ValueError(f'{self.path}: expected an object containing network and/or llamasrv_url settings.')
        self.llamasrv_url = self.validate_llamasrv_url(values.get('llamasrv_url', self.llamasrv_url))
        network = values.get('network', {})
        if not isinstance(network, dict):
            raise ValueError(f'{self.path}: network must be an object.')
        for use, settings in network.items():
            field = f'{self.path}: network.{use}'
            if use not in self.network:
                raise ValueError(f'{field}: unknown network use.')
            if not isinstance(settings, dict) or settings.keys() - {'interface', 'port'}:
                raise ValueError(f'{field}: expected interface and/or port settings.')
            interface = settings.get('interface', self.network[use][0])
            port = settings.get('port', self.network[use][1])
            try:
                if not isinstance(interface, str):
                    raise ValueError('expected a string')
                IPv4Address(interface)
            except ValueError as error:
                raise ValueError(f'{field}.interface: expected an IPv4 address.') from error
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError(f'{field}.port: expected an integer between 1 and 65535.')
            self.network[use] = (interface, port)

    @staticmethod
    def validate_llamasrv_url(value: object) -> str:
        message = 'llamasrv_url: expected an HTTP(S) base URL without credentials, path, query, or fragment.'
        if not isinstance(value, str) or any(character.isspace() or ord(character) < 32 for character in value):
            raise ValueError(message)
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as error:
            raise ValueError(message) from error
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.hostname in ('0.0.0.0', '::')
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or port is not None and not 1 <= port <= 65535):
            raise ValueError(message)
        return value.rstrip('/')

    @staticmethod
    def install() -> None:
        configuration = Configuration()
        path = configuration.path
        path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        values = {
            'network': {use: {'interface': interface, 'port': port}
                        for use, (interface, port) in configuration.network.items()},
            'llamasrv_url': configuration.llamasrv_url,
        }
        try:
            stream = path.open('x')
        except FileExistsError:
            pass
        else:
            with stream:
                stream.write(json.dumps(values, indent=2) + '\n')
            path.chmod(0o644)

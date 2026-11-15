"""Verify local configuration creation, validation, and restart semantics."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from ax3l.constants.DAx3l import DAx3l
from ax3l.interface.Configuration import Configuration
from ax3l.interface.Network import Network


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        base = patch.object(DAx3l, 'BASE_DIR', str(self.root))
        base.start()
        self.addCleanup(base.stop)
        Network._configuration.cache_clear()
        self.addCleanup(Network._configuration.cache_clear)
        self.path = self.root / DAx3l.CONFIG_FILE
        self.path.parent.mkdir()

    def write(self, values):
        self.path.write_text(json.dumps(values))

    def read(self):
        return Configuration(self.path).network

    def test_install_creates_defaults_and_readable_permissions(self):
        self.path.parent.rmdir()
        Configuration.install()
        self.assertEqual(self.read(), {use: (interface, port) for use, interface, port in DAx3l.CMDB_NETWORK})
        values = json.loads(self.path.read_text())
        self.assertEqual(set(values['network']), {'report', 'zmq'})
        self.assertEqual(values['llamasrv_url'], 'http://127.0.0.1:51001')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o755)

    def test_reinstall_preserves_custom_file_bytes(self):
        self.write({'network': {'report': {'interface': '127.0.0.2', 'port': 62000}}})
        original = self.path.read_bytes()
        Configuration.install()
        Configuration.install()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.read()['report'], ('127.0.0.2', 62000))

    def test_partial_overrides_and_missing_file_use_independent_defaults(self):
        defaults = self.read()
        self.write({'network': {'report': {'port': 62000}}})
        configured = self.read()
        self.assertEqual(configured['report'], ('0.0.0.0', 62000))
        self.assertEqual(defaults['report'], ('0.0.0.0', 28870))
        self.assertEqual(configured['zmq'], defaults['zmq'])
        configured['zmq'] = ('127.0.0.2', 12345)
        self.assertEqual(self.read()['zmq'], defaults['zmq'])

    def test_wildcard_binding_has_loopback_destinations(self):
        self.write({'network': {'zmq': {'interface': '0.0.0.0'}}})
        self.assertEqual(Network.binding('zmq'), ('0.0.0.0', 61970))
        self.assertEqual(Network.destination('zmq'), ('127.0.0.1', 61970))
        self.assertEqual(Network.endpoint(), 'tcp://0.0.0.0:61970')
        self.assertEqual(Network.endpoint(destination=True), 'tcp://127.0.0.1:61970')
        self.assertEqual(Network.llamasrv_url(), 'http://127.0.0.1:51001')

    def test_changes_are_loaded_on_process_restart(self):
        self.write({'network': {'report': {'port': 62000}}})
        self.assertEqual(Network.binding('report')[1], 62000)
        self.write({'network': {'report': {'port': 62001}}})
        self.assertEqual(Network.binding('report')[1], 62000)
        Network._configuration.cache_clear()  # A new service process starts with an empty cache.
        self.assertEqual(Network.binding('report')[1], 62001)

    def test_invalid_configurations_identify_field(self):
        cases = [([], 'expected an object'), ({'netwrok': {}}, 'expected an object'),
                 ({'network': []}, 'network must be an object'),
                 ({'network': {'llm': {'port': 27770}}}, 'network.llm'),
                 ({'network': {'typo': {}}}, 'network.typo'),
                 ({'network': {'report': []}}, 'network.report'),
                 ({'network': {'report': {'host': '127.0.0.1'}}}, 'network.report')]
        for interface in (None, 123, '', 'localhost', '999.0.0.1', '::1'):
            cases.append(({'network': {'report': {'interface': interface}}}, 'network.report.interface'))
        for port in (None, True, '1234', 0, -1, 65536, 1.5):
            cases.append(({'network': {'report': {'port': port}}}, 'network.report.port'))
        for values, field in cases:
            with self.subTest(values=values):
                self.write(values)
                with self.assertRaisesRegex(ValueError, field):
                    self.read()

    def test_invalid_existing_file_is_preserved_and_rejected_by_install(self):
        self.path.write_text('{bad json')
        with self.assertRaisesRegex(ValueError, 'invalid JSON'):
            Configuration.install()
        self.assertEqual(self.path.read_text(), '{bad json')

    def test_llamasrv_url_is_an_outbound_dependency_and_survives_reinstall(self):
        self.write({'llamasrv_url': 'http://wintermute:51001/'})
        original = self.path.read_bytes()
        Configuration.install()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(Network.llamasrv_url(), 'http://wintermute:51001')
        self.assertEqual(set(self.read()), {'report', 'zmq'})
        self.write({'llamasrv_url': 'https://inference.example:51443'})
        self.assertEqual(Network.llamasrv_url(), 'http://wintermute:51001')
        Network._configuration.cache_clear()
        self.assertEqual(Network.llamasrv_url(), 'https://inference.example:51443')

    def test_invalid_llamasrv_url_identifies_field(self):
        for value in (None, True, 51001, '', 'wintermute:51001', 'ftp://wintermute',
                      'http://', 'http://wintermute:bad', 'http://wintermute:0',
                      'http://wintermute:65536', 'http://[invalid]', 'http://0.0.0.0:51001',
                      'http://user:password@wintermute:51001', 'http://wintermute/v1',
                      'http://wintermute?setting=1', 'http://wintermute#fragment',
                      'http://wintermute\n', 'http://winter mute'):
            with self.subTest(value=value):
                self.write({'llamasrv_url': value})
                original = self.path.read_bytes()
                with self.assertRaisesRegex(ValueError, 'llamasrv_url'):
                    Configuration.install()
                self.assertEqual(self.path.read_bytes(), original)

    def test_report_entry_point_reads_bindings_and_allows_cli_overrides(self):
        from ax3l.server.ReportingServer import main

        self.write({'network': {'report': {'interface': '127.0.0.2', 'port': 28871}}})
        for arguments, binding in (([], ('127.0.0.2', 28871)),
                                   (['--host', '127.0.0.3', '--port', '28872'], ('127.0.0.3', 28872))):
            with self.subTest(arguments=arguments), patch('ax3l.server.ReportingServer.make_server') as server, patch('builtins.print'):
                main(arguments)
                self.assertEqual(server.call_args.args[:2], binding)
                server.return_value.__enter__.return_value.serve_forever.assert_called_once()

    def test_ax3l_listener_and_mcp_default_use_resolved_endpoints(self):
        from ax3l.server.Ax3lServer import main
        from ax3l.app.snakelab.tools.SubmitSingleValue import SubmitSingleValue
        from ax3l.app.snakelab.tools.SubmitPairValues import SubmitPairValues

        self.write({'network': {'zmq': {'interface': '0.0.0.0', 'port': 61971}}})
        loop = MagicMock()
        loop.main.return_value = 0
        with patch.dict('os.environ', {}, clear=True), patch('sys.argv', ['ax3l', '--llm-url', 'http://example']), \
                patch('ax3l.server.Ax3lServer.ZMQServer') as server, \
                patch('ax3l.server.Ax3lServer.import_module', return_value=loop):
            server.return_value.__enter__.return_value.endpoint = 'tcp://0.0.0.0:61971'
            self.assertEqual(main(), 0)
            self.assertEqual(server.call_args.args[0], 'tcp://0.0.0.0:61971')
            self.assertEqual(loop.main.call_args.args[0][-1], 'tcp://127.0.0.1:61971')
        for module, submitter in (('SubmitSingleValue', SubmitSingleValue), ('SubmitPairValues', SubmitPairValues)):
            with patch(f'ax3l.app.snakelab.tools.{module}.ZMQClient') as client:
                submitter()
                client.assert_called_once_with('tcp://127.0.0.1:61971')
                client.reset_mock()
                submitter('tcp://127.0.0.2:12345')
                client.assert_called_once_with('tcp://127.0.0.2:12345')

    def test_ax3l_uses_configured_llamasrv_by_default(self):
        from ax3l.server.Ax3lServer import main

        self.write({'llamasrv_url': 'http://wintermute:51001'})
        loop = MagicMock()
        loop.main.return_value = 0
        with patch.dict('os.environ', {}, clear=True), patch('sys.argv', ['ax3l']), \
                patch('ax3l.server.Ax3lServer.ZMQServer') as server, \
                patch('ax3l.server.Ax3lServer.import_module', return_value=loop):
            server.return_value.__enter__.return_value.endpoint = 'tcp://127.0.0.1:61970'
            self.assertEqual(main(), 0)
            self.assertEqual(loop.main.call_args.args[0][:2], ['--url', 'http://wintermute:51001'])

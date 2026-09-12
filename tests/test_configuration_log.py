import unittest
from unittest.mock import Mock

from ax3l.app.ConfigurationLog import ConfigurationLog
from ax3l.constants.DEventCategory import DEventCategory


class ConfigurationLogTests(unittest.TestCase):
    def test_creation_records_reason_and_run_reference(self):
        db = Mock()
        db.log.return_value = 42
        for reason in ("Parameter x: 2 > 4", "Seeded database with default config."):
            with self.subTest(reason=reason):
                db.reset_mock()
                self.assertEqual(ConfigurationLog(db).golden_config_created(
                    "run-id", reason=reason, parent_event_id=12,
                ), 42)
                db.log.assert_called_once_with(
                    "golden_config_created", "Configuration", "INFO", reason,
                    process_id="run-id", parent_event_id=12,
                )
        self.assertEqual(DEventCategory.label("Configuration", "golden_config_created"),
                         "Golden configuration created")

    def test_empty_reason_does_not_write_an_event(self):
        db = Mock()
        for reason in (None, "", "   "):
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                ConfigurationLog(db).golden_config_created("run-id", reason=reason)
        db.log.assert_not_called()

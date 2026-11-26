"""Recover stopped Ax3l application services."""

import logging
import subprocess

from ax3l.interface.Systemd import Systemd


class CheckServices:
    def __init__(self):
        self._systemd = Systemd()

    def run(self, ax3l_unit: str, report_unit: str) -> None:
        for unit in (ax3l_unit, report_unit):
            try:
                state = self._systemd.state(unit)
                if state in ("inactive", "failed"):
                    self._restart(unit, f"systemd state is {state}")
            except (subprocess.SubprocessError, OSError):
                logging.exception("Could not check or recover %s; will retry next poll", unit)

    def _restart(self, unit: str, reason: str) -> None:
        logging.warning("Restarting %s: %s", unit, reason)
        self._systemd.restart(unit)
        logging.info("Restart requested for %s", unit)

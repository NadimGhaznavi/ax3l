"""Recover stopped application services and an unhealthy model server."""

import logging
import subprocess
import time

from ax3l.interface.LLMHealth import LLMHealth
from ax3l.interface.Systemd import Systemd


class CheckServices:
    def __init__(self, startup_seconds: float = 60):
        self._systemd = Systemd()
        self._health = LLMHealth()
        self._startup_seconds = startup_seconds
        self._llm_ready_after = time.monotonic() + startup_seconds
        self._health_failures = 0

    def run(self, ax3l_unit: str, llm_unit: str, report_unit: str, health_url: str) -> None:
        for unit in (llm_unit, ax3l_unit, report_unit):
            try:
                state = self._systemd.state(unit)
                if state in ("inactive", "failed"):
                    self._restart(unit, f"systemd state is {state}")
                    if unit == llm_unit:
                        self._reset_llm()
                elif unit == llm_unit:
                    if state != "active":
                        self._reset_llm()
                    elif time.monotonic() >= self._llm_ready_after:
                        health = self._health.status(health_url)
                        if health["healthy"]:
                            self._health_failures = 0
                        else:
                            self._health_failures += 1
                            logging.warning("%s health check failed (%s/3): %s", unit, self._health_failures, health)
                            if self._health_failures >= 3:
                                self._restart(unit, "three consecutive health checks failed")
                                self._reset_llm()
            except (subprocess.SubprocessError, OSError):
                logging.exception("Could not check or recover %s; will retry next poll", unit)

    def _restart(self, unit: str, reason: str) -> None:
        logging.warning("Restarting %s: %s", unit, reason)
        self._systemd.restart(unit)
        logging.info("Restart requested for %s", unit)

    def _reset_llm(self) -> None:
        self._health_failures = 0
        self._llm_ready_after = time.monotonic() + self._startup_seconds

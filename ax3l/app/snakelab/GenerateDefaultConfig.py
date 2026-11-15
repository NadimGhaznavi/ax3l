"""Build a simulation configuration from the defaults in the JSON spec."""

from ax3l.interface.SimulationConfiguration import SimulationConfiguration


class GenerateDefaultConfig:
    def run(self) -> dict:
        return SimulationConfiguration.defaults()

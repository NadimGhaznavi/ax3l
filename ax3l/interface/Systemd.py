import subprocess


class Systemd:
    def state(self, unit: str) -> str:
        result = subprocess.run(
            ["systemctl", "show", unit, "--property=ActiveState", "--value"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()

    def restart(self, unit: str) -> None:
        subprocess.run(
            ["systemctl", "--no-block", "restart", unit],
            check=True, capture_output=True, text=True, timeout=10,
        )

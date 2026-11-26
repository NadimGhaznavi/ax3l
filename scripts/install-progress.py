"""Report elapsed time while an installer command runs, preserving its output."""

import argparse
import subprocess
from threading import Event, Thread
from time import monotonic


def run_step(label: str, command: list[str], *, interval: float = 5) -> int:
    started = monotonic()
    finished = Event()
    print(f'{label}...', flush=True)

    def report():
        while not finished.wait(interval):
            print(f'{label}: still working ({int(monotonic() - started)}s elapsed)', flush=True)

    reporter = Thread(target=report, daemon=True)
    reporter.start()
    try:
        result = subprocess.run(command)
        status = result.returncode if result.returncode >= 0 else 128 - result.returncode
    except KeyboardInterrupt:
        print(f'{label}: interrupted.', flush=True)
        return 130
    finally:
        finished.set()
        reporter.join()
    outcome = 'complete' if status == 0 else f'FAILED (exit {status})'
    print(f'{label}: {outcome} ({int(monotonic() - started)}s elapsed)', flush=True)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('provide a command after --')
    return run_step(args.label, command)


if __name__ == '__main__':
    raise SystemExit(main())

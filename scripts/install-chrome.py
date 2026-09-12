"""Provision Kaleido's Chrome inside the app and verify PNG rendering."""

import argparse
import os
from pathlib import Path
import struct

import plotly.graph_objects as go
from plotly.io import get_chrome


def install(app: Path) -> None:
    directory = app.resolve() / '.chrome'
    directory.mkdir(parents=True, exist_ok=True)
    executable = Path(get_chrome(path=directory))
    browser = directory / 'browser'
    if browser.is_symlink():
        browser.unlink()
    browser.symlink_to(executable.relative_to(directory))
    os.environ['BROWSER_PATH'] = str(browser)
    png = go.Figure(go.Scatter(x=[1, 2], y=[2, 1])).to_image(format='png', width=100, height=100)
    if png[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', png[16:24]) != (100, 100):
        raise RuntimeError('Chrome PNG rendering verification failed')
    print(f'Chrome installed and PNG rendering verified: {browser}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', required=True, type=Path)
    install(parser.parse_args().app)

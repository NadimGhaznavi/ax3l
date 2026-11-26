#!/usr/bin/env python3
"""Run all tests against private MariaDB and loopback service fixtures."""

import os
from pathlib import Path
import pwd
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep

import pymysql


def main() -> int:
    server_binary = shutil.which("mariadbd") or "/usr/sbin/mariadbd"
    initializer = shutil.which("mariadb-install-db")
    if not Path(server_binary).is_file() or initializer is None:
        raise SystemExit("Install MariaDB server and client tools before running the integration suite.")
    root = Path(__file__).resolve().parents[1]
    with TemporaryDirectory(prefix="ax3l-tests-") as directory:
        temporary = Path(directory)
        # Reserve a loopback port; the server's startup check detects bind failures.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        data = temporary / "data"
        with (temporary / "mariadb.log").open("w+") as log:
            subprocess.run([
                initializer, "--no-defaults", f"--datadir={data}",
                "--auth-root-authentication-method=normal", "--skip-test-db",
            ], stdout=log, stderr=log, check=True, timeout=60)
            process = subprocess.Popen([
                server_binary, "--no-defaults", f"--datadir={data}",
                f"--socket={temporary / 'mariadb.sock'}", f"--pid-file={temporary / 'mariadb.pid'}",
                "--bind-address=127.0.0.1", f"--port={port}",
                f"--user={pwd.getpwuid(os.getuid()).pw_name}",
                "--innodb-buffer-pool-size=32M", "--skip-log-bin",
            ], stdout=log, stderr=log)
            try:
                deadline = monotonic() + 30
                while True:
                    try:
                        connection = pymysql.connect(host="127.0.0.1", port=port, user="root",
                                                     password="", connect_timeout=1, autocommit=True)
                        break
                    except pymysql.OperationalError:
                        if process.poll() is not None or monotonic() >= deadline:
                            log.seek(0)
                            raise RuntimeError("Private MariaDB did not start:\n" + log.read())
                        sleep(.1)
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("CREATE DATABASE ax3l_test CHARACTER SET utf8mb4")
                        cursor.execute("CREATE DATABASE snakelab CHARACTER SET utf8mb4")
                        # Cross-database event reports need an empty external source.
                        # Individual tests create temporary tables or their own run data.
                        cursor.execute("""CREATE TABLE snakelab.simulation_runs (
                            run_id CHAR(36) COLLATE utf8mb4_unicode_ci, high_score INT
                        )""")
                finally:
                    connection.close()
                environment = dict(os.environ, DB_HOST="127.0.0.1", DB_PORT=str(port), DB_USER="root",
                                   DB_PASSWORD="", DB_NAME="ax3l_test", AX3L_TEST_DB="1", AX3L_TEST_INSTALL_DB="1")
                return subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", *sys.argv[1:]],
                                      cwd=root, env=environment).returncode
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    raise SystemExit(main())

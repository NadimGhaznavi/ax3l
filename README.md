This project is on [https://ax3l.osoyalce.com/](https://ax3l.osoyalce.com/).

If you like this project, please give it a star (top right corner)! :)

## First experiment

A fresh history runs the default baseline, then tunes one view at a time in
shuffled four-view rounds. Each selection runs its own simulation and evaluation.
Candidates that match or beat the golden score become golden. After 16 consecutive
strictly lower scores, Ax3l increments the seed and runs the golden settings to
establish a fresh baseline. See [runtime behavior](pages/runtime-behaviour.md).

## Tests

For the full suite with a private, disposable MariaDB server, run:

```sh
.venv/bin/python scripts/test.py
```

This requires MariaDB server and client tools. The runner supplies its own test
credentials and uses local HTTP/ZeroMQ fixtures. It does not use deployed services.
Pass unittest options such as `-v` or `-p test_view_cycle_integration.py` to focus a run.

Run the normal suite from the checkout with `.venv/bin/python -m unittest discover -s tests`.
HTTP and ZeroMQ fixtures bind only to loopback. Database integration tests are
opt-in and require a disposable MariaDB database named `ax3l_test`.

Load its `DB_HOST`, `DB_PORT`, `DB_USER`, and `DB_PASSWORD` environment variables,
then set `DB_NAME=ax3l_test` and `AX3L_TEST_DB=1`. The test account needs permission
to create and drop tables in that disposable database.

Run the four-view end-to-end checks with:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_view_cycle_integration.py' -v
```

These checks use real MariaDB persistence and local HTTP/ZeroMQ fixture servers.
They do not call deployed inference or SnakeLab services. They require an
otherwise empty set of simulation source tables in `ax3l_test`; the fixtures
create and remove those tables and their own event records.

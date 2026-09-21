# ax3l
Another AI Project

Run `sudo scripts/backup-db.sh` for a manual backup of the local Ax3l database.
It reads the database name from `prod_etc/ax3l/database.env` in the checkout
for DEV, or `/etc/ax3l/database.env` for PROD, and writes a private,
timestamped `*-db.dump` SQL file in the current directory. SnakeLab is not included.

## Development Style

Read and follow the [Coding Guidelines](pages/coding-guidelines.md) for the
full development guidance, including changelog updates.

- Develop for our fixed platform: Ax3l, the locally hosted LLM, SnakeLab, MariaDB, and systemd. No third-party API or vendor integrations, portability layers, or abstractions for hypothetical platforms. This does not exclude the libraries we use to build the application.
- Run one LLM model at a time. Model evaluation and generic harness support are established; do not design for concurrent models.
- Work in short iterations with thin, working slices. Implement only the data and behavior the current slice needs.
- Favor clarity over compactness. Use small, clearly named modules with one responsibility, explicit data structures, and database tables where they make data easier to understand and query.
- Follow the Common Unified Development Process class roles: interfaces communicate with other systems, entities hold data (including prompts), and activities transform data without storing state—the T in ETL. Control flow sequences the work and makes decisions.
- Keep shared application features, such as event logging and reporting, separate from domain-specific processes and prompts. Introduce shared abstractions for actual reuse.
- Enforce the DAL: `DbMgr` alone connects to MariaDB and owns connections, cursors, SQL execution, and transactions. Its initialization creates the shared logging tables. Database modules own their queries and call its generic SQL methods; application code calls named operations on those modules.
- Lean on MariaDB for both application data and the application's own state. Persist enough state to delete partial data on restart and continue LLM workflows.
- Separate stored event names and data from presentation labels and descriptions. Reporting should make the conversation and overall process readable as a story.
- Use explicit contracts and correct types. Validate at interfaces; fail fast and hard with a clear error when a contract or type is wrong, then fix the cause.
- No fallback parsing, silent defaults, repair prompts, or retries for contract violations.
- Avoid defensive programming, speculative configuration, and dead code. Add error handling only for observed failures or an explicit requirement.
- Use the real, disposable DEV MariaDB database for database development and integration checks. Test meaningful behavior appropriate to the change.

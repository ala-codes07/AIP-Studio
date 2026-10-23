# Architecture and engineering trade-offs

## Layer boundaries

- **Frontend:** statically served JavaScript UI (no build chain). Uses same-origin REST API and browser session storage. `esc()` escapes external strings before injecting into HTML. Auth tokens are never placed in generated reports.
- **API:** FastAPI route modules and Pydantic request/response models. All website, audit, job, and search-evidence routes resolve tenant membership before returning data.
- **Persistence:** SQLAlchemy 2 models and Alembic migrations, with SQLite for single-developer use and optional PostgreSQL for multi-user use.
- **Worker:** separate process reads `scan_jobs`, conditionally claims a queued row, runs the bounded scanner, commits audit/findings and marks job completed or failed. Workers should be monitored; SQLite is not an ideal high-concurrency queue backend.
- **Scanner:** DNS/IP validation and pinned public network sockets, limited redirect/response/page budgets, `robots.txt` permission checks, sitemap URL sampling, HTML metadata extraction, and explainable checks.
- **Search evidence:** uploaded user-owned Search Console Queries CSV with parsed and validated metrics. No unlicensed SERP scraping, unverifiable rankings, or fabricated keyword traffic.
- **Free intelligence:** local rules engine synthesizes findings into a prioritized plan. Optional Ollama uses a loopback-only inference endpoint. Prompt-injection defenses are best-effort; LLM output is never an authoritative audit fact.

## Trust boundaries

User-provided site URL -> public DNS validation -> pinned socket -> untrusted remote HTML -> size-constrained parser -> stored evidence -> escaped dashboard presentation. The site owner is **not** automatically proven by adding a URL; a public launch needs consent policy and further scanning safeguards.

Uploaded CSV -> capped file size, row count, numeric range validation -> website membership check -> JSON storage -> only organization members may view -> bounded opportunity ranking. The CSV's claimed dates and underlying Search Console ownership cannot be validated offline.

## Why a persisted job queue?

Synchronous scan endpoints create long-lived HTTP requests and contention. Jobs are saved first, processed in a separate worker, and polled via authenticated endpoints. Job failure is explicit, no false successful audit is produced. The legacy synchronous audit route remains for **development/tests** only and is disabled in production mode.

The local queue is intentionally inexpensive, but it is not a substitute for a distributed queue plus full observability at large scale. A production deployment should set explicit worker concurrency, timeouts and egress restrictions.

## Why not automatically estimate keyword volume and rank?

Website HTML doesn't contain Google search demand, impressions, clicks or SERP positions. A transparent system must not infer these from word frequency. For real values, owners can supply an official Search Console CSV at no subscription cost. Comparisons between data windows require user-provided matching date periods.

## Known engineering debt before commercial deployment

1. Distributed and edge rate limits for login, uploads and crawl jobs; scanner account abuse prevention.
2. Ownership / scan authorization verification for domains under analysis.
3. HTTPS termination, operational secrets management, backups/restore drills and PostgreSQL maintenance.
4. More comprehensive accessibility, performance and browser-rendered JavaScript analysis.
5. Automated live Search Console API OAuth integration and auditing of external service terms.
6. Integration testing with **real** SMTP, a representative live site, actual Ollama installation and penetration tests.

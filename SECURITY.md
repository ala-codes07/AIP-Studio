# Security posture and disclosure

**This is an educational/open-source website intelligence application, not an audited hosted security service.** Please report vulnerabilities privately to the repository maintainer, rather than in public issues. Never include secrets or user data in a security report.

## Implemented safeguards

- bcrypt password hashing (installed from project requirements), JWT claim validation, rotating persisted refresh sessions, access-token invalidation on password changes; logout revokes provided refresh token (issued access token continues until expiry).
- Six-digit single-use email codes kept as HMAC digests; 10-minute expiry, attempt limits and resend cooldown; emails sent through owner-configured SMTP or displayed locally only in development.
- Workspace membership and role checks applied to sites, GSC imports, scan jobs, reports and CSV exports.
- Bounded public-only crawling, DNS address rejection for private/reserved IPs, pinned IP connections, HTTPS certificate validation, redirects re-validated, robot rules fail closed on uncertainty, response size/page quotas.
- Security headers including CSP, denial of framing and MIME sniffing; browser strings escaped in the UI; local production auth request throttling (defense in depth, not a distributed control).
- No API key is required for default local analysis; optional Ollama endpoint bound to local loopback.
- `.env`, local DBs, tokens, caches and logs excluded from Git through `.gitignore`.

## Public deployment still requires

- HTTPS reverse proxy, strict forwarded-header/trusted-proxy configuration, edge rate limits by actual user IP, abuse reporting and outbound firewall rules for the crawler.
- Production SMTP sender validation and SPF/DKIM/DMARC, monitoring for failed mail delivery.
- PostgreSQL for multi-user concurrency, worker health checks/restart alerts, database backups, tested restore procedures, operational metrics and incident playbooks.
- Real privacy policy and permission to crawl target sites; consider domain-control verification or owner consent before serving strangers.
- Independent threat modeling / dependency scanning and end-to-end integration tests. A local test result alone does **not** certify public production readiness.

AIP performs untrusted HTML and CSV parsing, so keep dependencies patched and run with minimal OS permissions. Use a dedicated sandbox/network segment for any internet-facing crawler.

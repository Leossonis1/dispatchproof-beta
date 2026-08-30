# DispatchProof IT Upgrade Plan

## Phase 1 — Launch / 0 to 5 paying companies

Architecture: **isolated company deployments**.

Each unrelated customer has its own Render web service, SQLite database, persistent disk, users, jobs, and uploads.

Current recommended per-customer baseline:
- Render web: 0.5 CPU / 512 MB (`0.5c-512mb`)
- 1 Gunicorn worker / 4 threads
- 1 GB persistent disk
- SQLite with WAL/busy timeout

Operational triggers:
- Keep disk below ~70–80% utilization.
- Investigate repeated 5xx/timeouts, database lock errors, memory pressure, or persistent high CPU.

## Phase 2 — SaaS foundation trigger

Trigger this work at **3–5 paying companies**, or earlier if managing isolated deployments becomes the main operational burden.

Required engineering:
1. Add true Company/Organization accounts and tenant ownership.
2. Put every customer-owned record behind a company boundary.
3. Create automated tests proving Company A cannot read/write Company B data, including direct URLs, exports, public links, documents, crew/subcontractors, training administration, and backups.
4. Build a controlled data-migration path from each isolated customer deployment.

Do not simply add a `company_id` column and assume isolation is complete. Every query, write, export, background process, token/public link, and file lookup must be tenant-aware.

## Phase 3 — PostgreSQL conversion

Perform alongside or immediately after the true tenant layer.

Goals:
- Move concurrency-sensitive relational data off SQLite.
- Use managed PostgreSQL backups/recovery.
- Add connection pooling appropriate to Render.
- Convert SQLite-specific SQL (`PRAGMA`, `AUTOINCREMENT`, `COLLATE NOCASE`, `?` placeholders, backup/restore assumptions) deliberately rather than through string replacement.
- Run migration tests using a copy of real beta data before production cutover.

## Phase 4 — Object storage

Move customer-uploaded photos/documents/audio/logos from the Render persistent disk to S3-compatible object storage such as Cloudflare R2.

Design requirements:
- Tenant-prefixed object keys.
- Private objects by default.
- Time-limited/signed access where appropriate.
- Database keeps metadata/object key, not a local filesystem dependency.
- Backups include database metadata plus a documented object-storage recovery process.

This step removes the shared-filesystem limitation and makes multiple web instances practical.

## Phase 5 — 25 to 100+ companies

When measured load requires it:
- Upgrade web compute (for example 1 CPU / 2 GB).
- Add multiple web instances only after local-disk dependencies are removed.
- Move long-running work to background jobs/workers.
- Add centralized monitoring/error reporting.
- Track request latency, CPU, memory, DB connections, queue depth, storage, 5xx rate, and email/API failures.

## Phase 6 — acquisition-grade operations

As meaningful recurring revenue develops:
- Automated tenant provisioning
- Subscription/billing automation
- Automated backups and restore drills
- Security/audit logging review
- Incident/runbook documentation
- Dependency/security update process
- Customer data export/deletion procedures
- Load tests and documented capacity envelope

## What not to do now

Do not destabilize the approved product by forcing a rushed shared-database multi-tenant rewrite before real customers exist. Early isolated deployments are a valid bridge and give excellent customer separation while product-market fit is being proven.

# DispatchProof V2.46.12 — Launch & Operations Baseline

V2.46.12 is the commercial-launch operations baseline built from the approved V2.46.11 release.

## What changed

- Public launch price is locked at **$50/month per company** (initial offer: up to 10 office users; all core features included).
- Corrected Render Blueprint from `free` to the current `0.5c-512mb` production compute plan.
- Blueprint now documents a 1 GB persistent disk at `/var/data` and `DISPATCHPROOF_DATA_DIR=/var/data/dispatchproof` for new isolated-company deployments.
- Added `DISPATCHPROOF_DEPLOYMENT_MODE=isolated-company` metadata so the intended early-customer architecture is explicit.
- Centralized app version metadata at `2.46.12`; `/health` now reports the correct version plus deployment mode and public monthly price.
- Replaced stale user-visible **Free Beta** email wording with **Email Outbox Mode** / testing wording. Email behavior itself is unchanged.
- Added launch marketing, customer deployment, and IT scaling documents.

## Architecture decision

This release intentionally remains **one company per deployment/database**. Do not place unrelated customer companies into one V2.46.12 database. Early customers should receive isolated deployments.

True shared multi-tenant/PostgreSQL/object-storage architecture is a planned scaling milestone after real customer traction proves the need. See `IT_UPGRADE_PLAN_V2_46_12.md`.

## No behavior migration

No job, crew, readiness, permissions, training, document, integration, or mobile workflow logic was changed in this release.

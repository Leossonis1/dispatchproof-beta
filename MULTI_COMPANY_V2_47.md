# DispatchProof V2.47.0 — Multi-Company Architecture

## Storage model

DispatchProof now supports multiple unrelated customer companies in one Render service while keeping each company physically separated:

- Primary/upgraded company: existing `dispatchproof.db` + `uploads/` remain in place.
- Additional companies: `companies/<company-id>/dispatchproof.db` + `companies/<company-id>/uploads/`.
- Platform registry: `dispatchproof-platform.db` stores only company workspace metadata (company ID, display name, active status, time zone).
- No customer jobs, documents, crew, users, or client records are stored in the platform registry.

## Login

The sign-in screen now accepts a Company ID. Leaving it blank opens the primary upgraded company for backward compatibility. New customers use the Company ID assigned when their workspace is created.

The permanent Render-backed Owner can use **Companies** to create a company, open its workspace, deactivate/reactivate it, and see basic counts. Each new company receives its own first Administrator account and company-specific time zone.

## Public links

New public tokens are prefixed with the company ID (for example `acme.<random-token>`), allowing readiness, arrival, client-report, field-update, and portfolio links to resolve the correct isolated database without a login. Existing pre-V2.47 public tokens remain routed to the primary company.

## Backups

Backup & Restore remains company-scoped because database and upload paths resolve to the currently signed-in company. A restore cannot overwrite another company's database through the normal UI.

## Render settings

Recommended:

- `DISPATCHPROOF_DEPLOYMENT_MODE=multi-company`
- `DISPATCHPROOF_DATA_DIR=/var/data/dispatchproof`
- `DISPATCHPROOF_DEFAULT_COMPANY_SLUG=default` (or a short ID you choose before first V2.47 deploy)
- Keep a persistent disk at `/var/data`.

Do **not** change `DISPATCHPROOF_DEFAULT_COMPANY_SLUG` after production data is established unless you intentionally migrate the primary workspace.

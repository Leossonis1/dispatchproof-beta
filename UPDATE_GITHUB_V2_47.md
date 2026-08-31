# DispatchProof V2.47.0 — Multi-Company Baseline

V2.47.0 converts the V2.46.12 isolated-deployment baseline into a single-service, multiple-company architecture while preserving separate customer storage.

## What changed

- Existing primary company upgrades in place with no database move/reset.
- Added a small platform company registry (`dispatchproof-platform.db`).
- Every additional company gets its own SQLite database and uploads folder under `companies/<company-id>/`.
- Added Company ID to sign-in and pins authenticated sessions to one company.
- Added permanent Owner-only **Companies** page to create/open/deactivate company workspaces.
- New company provisioning creates an isolated database plus an initial Administrator account.
- New public tokens include the Company ID prefix so readiness, arrival, reports, portfolio links, and field links select the correct company database without requiring login.
- Existing pre-V2.47 public tokens remain valid for the primary company.
- Backup filenames, manifests, and workspace exports include Company ID.
- Full restore and workspace restore reject files belonging to another company.
- Company timezone is stored per company and used for dashboard dates/display timestamps.
- Company name/timezone metadata is kept in the company database and platform registry.
- Registry recovery can rediscover existing `companies/<id>/dispatchproof.db` folders if the small platform registry ever has to be recreated.
- Reminder throttling is tracked per company rather than globally.
- Company email sender display name follows the active company's branding while retaining the configured SMTP account.
- `/health` reports `2.47.0`, `multi-company`, and `isolated-database-per-company`.

## Storage layout

```text
/var/data/dispatchproof/
  dispatchproof.db
  uploads/
  dispatchproof-platform.db
  companies/
    acme/
      dispatchproof.db
      uploads/
```

The root database/uploads remain the primary upgraded company. New unrelated companies are never added as rows inside that database.

## Validation completed in this build

- Python source compiles successfully.
- All Jinja templates parse successfully.
- Runtime storage test created primary + second-company databases and verified user/job isolation.
- Public token tenant resolver selected the correct company.
- Existing no-prefix token behavior continues to route to the primary company.
- Company-specific timezone resolution passed.
- Company backup contained the correct tenant database.
- Cross-company restore validation rejected the wrong company's backup.
- Platform registry contained no jobs/users/clients operational tables.

## Deploy sequence

1. Download a V2.46.12 backup before deployment.
2. Keep the same persistent disk and `DISPATCHPROOF_DATA_DIR`.
3. Deploy V2.47.0.
4. Leave Company ID blank for the existing primary company login.
5. Confirm existing data and branding.
6. Open **Companies** as the permanent Owner and create one throwaway test company.
7. Verify that company's admin login and a public readiness link.
8. Verify the primary company cannot see the test company's records.
9. Test one backup/download and wrong-company restore rejection before onboarding a real second company.

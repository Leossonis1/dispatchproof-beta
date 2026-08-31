# DispatchProof V2.47.0 — Multi-Company Baseline

DispatchProof V2.47.0 upgrades the V2.46.12 launch baseline from one-company-per-deployment to a multi-company service with **isolated storage per company**.

## What changed

- One Render service can host multiple unrelated customer companies.
- The existing/primary company keeps the current root `dispatchproof.db` and `uploads/` paths, so this is a non-destructive upgrade.
- Each additional company gets `companies/<company-id>/dispatchproof.db` and its own `uploads/` folder.
- The permanent Owner gets a **Companies** page for provisioning/opening/deactivating company workspaces.
- Company users sign in with Company ID + username + password.
- New public readiness/arrival/report/field links contain a company prefix so unauthenticated links resolve the correct isolated database. Existing V2.46.12 public links continue to route to the primary company.
- Full backups and user workspace exports are stamped with Company ID and cannot be restored into a different company.
- Company time zone is now company-specific.

See `MULTI_COMPANY_V2_47.md` for architecture details and `DEPLOY_RENDER.md` for deployment settings.

# Deploy DispatchProof V2.47.0

## Render baseline

Use the included `render.yaml` or verify these settings manually:

- Plan: `0.5c-512mb`
- Persistent disk: 1 GB mounted at `/var/data`
- `DISPATCHPROOF_DATA_DIR=/var/data/dispatchproof`
- `DISPATCHPROOF_DEPLOYMENT_MODE=multi-company`
- `DISPATCHPROOF_DEFAULT_COMPANY_SLUG=default`
- unique `DISPATCHPROOF_SECRET_KEY`
- private `DISPATCHPROOF_ADMIN_PASSWORD`

**Important:** choose the default company slug before the first V2.47 production deploy and do not change it later without migrating the primary workspace. Leaving it as `default` is safe.

## Upgrade check

1. Back up the existing V2.46.12 company before deploy.
2. Deploy V2.47.0 using the same persistent disk/data directory.
3. Open `/health`; confirm version `2.47.0`, deployment mode `multi-company`, and storage model `isolated-database-per-company`.
4. Sign in to the primary company (Company ID can be left blank). Confirm existing jobs, users, documents, crew, and branding are unchanged.
5. As the permanent Owner, open **Companies** and create one test company.
6. Sign out and sign in to the test company using its Company ID and new Administrator account.
7. Create a test job/public readiness link and verify it opens correctly while signed out.
8. Confirm the primary company does not show the test company's jobs, clients, users, crew, or documents.
9. Download a backup from the test company and confirm DispatchProof refuses to restore that backup while the primary company is open.

## Storage layout

```text
/var/data/dispatchproof/
  dispatchproof.db                 # primary/upgraded company
  uploads/                         # primary/upgraded company
  dispatchproof-platform.db        # company registry only
  companies/
    acme/
      dispatchproof.db
      uploads/
    another-company/
      dispatchproof.db
      uploads/
```

The platform registry does not contain customer jobs, documents, clients, crew, or user passwords.

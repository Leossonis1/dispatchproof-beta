# Deploy DispatchProof V2.46.12

V2.46.12 is the commercial-launch operations baseline.

## Existing production deployment

If your current Render service already has the paid 0.5 CPU / 512 MB plan and persistent disk configured, deploy the code normally. Do **not** delete/recreate the service or disk.

Confirm these environment/storage settings in Render:

- Compute: `0.5c-512mb` (legacy Starter equivalent)
- Persistent disk mounted at `/var/data` (1 GB is sufficient for the early-customer stage)
- `DISPATCHPROOF_DATA_DIR=/var/data/dispatchproof`
- `DISPATCHPROOF_DEPLOYMENT_MODE=isolated-company`
- `DISPATCHPROOF_SECRET_KEY` remains private
- `DISPATCHPROOF_ADMIN_PASSWORD` remains private

`render.yaml` now reflects the intended settings for a *new* deployment. Existing manually configured Render services should be changed carefully so the current persistent data is never detached or replaced.

## Post-deploy smoke test

1. Open `/health` and confirm version `2.46.12`.
2. Sign in as Owner/Admin.
3. Confirm Dashboard, Jobs, Schedule, Crew, Clients & Projects, Documents, Training, Settings, Integrations, and mobile navigation still open normally.
4. Confirm existing jobs/documents are present.
5. If Email Outbox Mode is enabled, generate one test message and confirm it appears in Email Outbox.
6. Create/delete a harmless test job only if desired; do not perform a workspace restore as part of a routine deploy.

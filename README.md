# DispatchProof V1.7 — Backup & Branding

V1.7 adds a portable beta-data backup system so free Render resets no longer
have to erase test history permanently.

## Backup & Restore

Admin navigation now includes **Backup & Restore**.

Download Backup ZIP includes:

- `dispatchproof.db`
- all uploaded readiness photos
- all uploaded arrival photos
- jobs
- readiness confirmations
- mobilization history
- failed mobilization report data
- Email Outbox history
- a backup manifest

Restore validates and stages the backup before replacing current beta data.

## Recommended Free Render routine

1. Before a deploy/restart, download a backup.
2. Let Render redeploy.
3. If the dashboard returns empty, open Backup & Restore.
4. Upload the saved ZIP.
5. Continue testing.

## Branding polish

- DispatchProof favicon
- cleaner branded admin login
- consistent DispatchProof naming
- beta label removed from generated email header
- sidebar tagline driven from product branding constants

## Important

This backup approach is meant for the current free beta. It is not a replacement
for durable hosted storage. Later we should move to PostgreSQL/object storage or
a persistent disk.


## V1.7.1 — Field Photo Capture

Phone users now get two clear photo actions:

- **Take Photo** — requests the device camera, preferring the rear/environment camera
- **Choose Existing Photos** — selects one or more images already on the device

Selected images are accumulated into the same form submission and display:

- live thumbnail previews
- individual Remove buttons
- photo-count status
- "requirement met" state when the minimum is satisfied

Site readiness requires at least 2 photos.

Installer Arrival keeps photos optional when Site Ready is selected, but dynamically
changes to a 2-photo minimum when Site Not Ready / failed mobilization is selected.

No native mobile app is required; this uses standard browser camera/file capabilities.

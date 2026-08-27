# Upgrade Existing Render Beta to V1.7.1

You already saved a V1.7 backup before this deployment.

Upload/replace these paths in the existing `dispatchproof-beta` GitHub repository:

- `app.py`
- `README.md`
- `VERSION.txt`
- `static/app.css`
- `static/photo_capture.js`
- `templates/public_readiness.html`
- `templates/arrival.html`

Commit the changes. Render should auto-deploy.

After deployment:

1. Sign in and confirm the sidebar says Version 1.7.1.
2. If the dashboard is empty, use Backup & Restore to restore your saved V1.7 ZIP.
3. Open a public readiness link on a phone.
4. Tap **Take Photo** — the device should offer/open the camera.
5. Take two photos; verify thumbnails and "requirement met".
6. Remove one photo; verify the count drops and submission is blocked until 2 are present.
7. Test **Choose Existing Photos**.
8. On Installer Arrival, verify photos are optional for Site Ready and 2 are required for Site Not Ready.

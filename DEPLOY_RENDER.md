# V2.43 Render note

For **Find a Subcontractor**, add this environment variable to the DispatchProof Render service:

`FOURSQUARE_SERVICE_API_KEY=<your existing Foursquare service API key>`

You may reuse the same key already used by Leosson Contractor Finder. The feature remains disabled with a clear setup message when no key is configured.

No database reset is required.

---


# DispatchProof V1.5 — Render Beta Deployment

This build is prepared for a first public end-to-end test on Render.

## What V1.5 changes

- production web server: Gunicorn
- binds correctly to Render's `$PORT`
- `/health` endpoint for Render health checks
- uses Render's public HTTPS URL for readiness links
- supports a custom public URL later via `DISPATCHPROOF_PUBLIC_BASE_URL`
- trusts Render proxy headers for HTTPS URL generation
- configurable data folder via `DISPATCHPROOF_DATA_DIR`
- SQLite busy timeout/WAL settings for the single-instance beta

## Important: free Render storage is temporary

The Render free web-service filesystem is ephemeral. For this first public
workflow test, that is acceptable, but do not treat the free deployment as
permanent storage.

A restart/redeploy can remove:
- jobs stored in SQLite
- uploaded readiness photos
- uploaded arrival photos
- email outbox history

The V1.5 app automatically uses `/tmp/dispatchproof` when it detects Render.

### Later: persistent disk

When you are ready for durable beta data:

1. Upgrade the Render web service to a plan that supports a persistent disk.
2. Add a disk with mount path `/var/data`.
3. Add this environment variable:

   `DISPATCHPROOF_DATA_DIR=/var/data/dispatchproof`

No code change is required.

For a larger production product, we should eventually move structured data to
PostgreSQL and photos to object storage.

---

# Fastest deployment path

## 1. Put this folder in GitHub

Create a repository such as:

`dispatchproof-beta`

Upload the CONTENTS of `DispatchProof_V1_5_RENDER_BETA` so that `app.py`,
`requirements.txt`, and `render.yaml` are at the repository root.

Do not upload a real `.env` file or SMTP passwords.

## 2. Create the Render Blueprint

In Render:

1. Click **New +**
2. Choose **Blueprint**
3. Connect the GitHub repository
4. Render reads `render.yaml`
5. Create/apply the Blueprint

The Blueprint creates a free Python web service named:

`dispatchproof-beta`

The actual public URL depends on availability and will be shown by Render.

## 3. Wait for deployment

A successful deploy should show Gunicorn starting and Render marking the
`/health` check healthy.

Open:

`https://YOUR-RENDER-URL/health`

Expected result includes:

- `"status": "ok"`
- `"version": "1.5"`

Then open the root app URL.

## 4. First public test

Because the online beta starts with a new temporary database:

1. Create a fresh test job.
2. Use your own email address as the Site Contact Email.
3. Open its **Readiness Link** screen.
4. Before SMTP is configured, confirm the displayed confirmation link begins
   with `https://...onrender.com/`, NOT `127.0.0.1`.
5. Open the external link on your phone using cellular data or another device.
6. Complete the readiness form and upload two test photos.
7. Confirm the hosted dashboard updates.

That proves the public web workflow before email delivery is enabled.

---

# Real email after the public link test

Once the hosted link works, add SMTP environment variables in Render.

Do NOT commit passwords to GitHub.

For Gmail:

- `DISPATCHPROOF_SMTP_HOST=smtp.gmail.com`
- `DISPATCHPROOF_SMTP_PORT=587`
- `DISPATCHPROOF_SMTP_USERNAME=your-email@gmail.com`
- `DISPATCHPROOF_SMTP_PASSWORD=<Google App Password>`
- `DISPATCHPROOF_SMTP_FROM_EMAIL=your-email@gmail.com`
- `DISPATCHPROOF_SMTP_FROM_NAME=DispatchProof`
- `DISPATCHPROOF_SMTP_USE_TLS=true`

Then redeploy/restart and send the first live readiness email to yourself.

## Custom domain later

When a custom domain is attached, set:

`DISPATCHPROOF_PUBLIC_BASE_URL=https://your-domain.example`

This makes every readiness email/link use the custom domain.

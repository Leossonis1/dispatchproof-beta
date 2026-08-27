# Upgrade Existing Render Beta to V1.6

## BEFORE uploading the code

In Render → dispatchproof-beta → Environment, add:

- Key: `DISPATCHPROOF_ADMIN_USERNAME`
  Value: `admin`

- Key: `DISPATCHPROOF_ADMIN_PASSWORD`
  Value: choose a new unique password

Save the environment variables.

Do NOT use your Gmail password or Google App Password.

## Then update GitHub

Replace/upload these paths in the existing `dispatchproof-beta` repository:

- `app.py`
- `render.yaml`
- `README.md`
- `VERSION.txt`
- `static/app.css`
- `templates/base.html`
- `templates/login.html`
- `templates/email_outbox_detail.html`
- `templates/submitted.html`

Commit the changes. Render should auto-deploy.

## Expected result

Opening the main DispatchProof URL sends you to `/login`.

The public `/r/...` readiness link still opens directly without login.

After sign-in, the sidebar shows the admin username and a Sign Out control.

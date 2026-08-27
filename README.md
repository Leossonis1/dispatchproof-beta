# DispatchProof V1.6 — Admin Login

V1.6 protects the hosted internal application while keeping individual
site-readiness links public.

## Public without login

- `/r/<secure-token>` readiness confirmation pages
- `/health`
- static assets needed by the public page

## Admin login required

- Dashboard
- New Job
- Readiness Request management
- Job details
- Installer Arrival
- Failed Mobilization reports
- Archived reports/history
- Email Outbox
- Uploaded evidence photos

## Render setup before deploying V1.6

In Render → `dispatchproof-beta` → Environment, add:

`DISPATCHPROOF_ADMIN_USERNAME=admin`

`DISPATCHPROOF_ADMIN_PASSWORD=<choose a new unique password>`

Do not use your Gmail password or Google App Password.

The password stays in Render Environment and is never committed to GitHub.

If the password is missing on Render, DispatchProof fails closed: the internal
app remains locked and the login page explains that admin login is not configured.

## Other V1.6 cleanup

- Copy Link added to Email Outbox detail
- Public confirmation-complete page no longer contains a Dashboard link
- secure HttpOnly/Lax session cookie
- secure cookie enforced on Render HTTPS
- admin session expires after 12 hours

# DispatchProof V2.40.6

## V2.40.6 global Copy Link fix

- All Copy Link / Copy Report Link / Copy Installer Link controls now use one shared handler in `templates/base.html`.
- Fixes Readiness and Email Outbox buttons whose page-level scripts were placed outside the Jinja content block and therefore never rendered.
- Uses the matching Open Link `href` where available so copied links are identical to the link that opens successfully.
- Copy fallback order is synchronous legacy copy first, then Clipboard API, then a manual copy prompt only if both automatic methods fail.
- No database migration or reset is required.



## V2.40.5 readiness Copy Link fix

- Readiness Copy Link now copies the exact same URL used by Open External Page.
- No database migration/reset required.

## V2.40.4 readiness public-link fix

- Secure public links generated during a live request now prefer the current app hostname.
- Prevents a stale `DISPATCHPROOF_PUBLIC_BASE_URL` from sending readiness recipients to another deployment/database where the token does not exist.
- Public readiness URLs tolerate an optional trailing slash.
- Missing readiness tokens now log the request host and configured public-base values for diagnosis.
- Existing emailed links are unchanged; resend the readiness request after deploying V2.40.4.

Operator Workspace Restore button reliability fix.

Use the patch-only ZIP when upgrading an existing V2.40.2 installation. No database reset is required.


## V2.40.7 — Client Report Mobilization Clarity
Client Installation Reports now clearly separate the current mobilization cycle from preserved prior attempts and show fuller archived readiness/arrival evidence.

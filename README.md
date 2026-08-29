# DispatchProof V2.40.4


## V2.40.4 readiness public-link fix

- Secure public links generated during a live request now prefer the current app hostname.
- Prevents a stale `DISPATCHPROOF_PUBLIC_BASE_URL` from sending readiness recipients to another deployment/database where the token does not exist.
- Public readiness URLs tolerate an optional trailing slash.
- Missing readiness tokens now log the request host and configured public-base values for diagnosis.
- Existing emailed links are unchanged; resend the readiness request after deploying V2.40.4.

Operator Workspace Restore button reliability fix.

Use the patch-only ZIP when upgrading an existing V2.40.2 installation. No database reset is required.

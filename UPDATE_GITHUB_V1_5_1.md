# Update Existing Render Beta to V1.5.1

In the existing `dispatchproof-beta` GitHub repository, replace these files:

- app.py
- render.yaml
- README.md
- VERSION.txt
- templates/readiness_request.html
- templates/email_outbox.html

Commit the changes.

Render should auto-deploy the commit. After deployment:

1. The sidebar should show Version 1.5.1.
2. Job → Readiness Link should show **Free Beta · Outbox Mode**.
3. **Generate Readiness Email** should create an OUTBOX entry without attempting SMTP.
4. No `Network is unreachable` SMTP error should occur.

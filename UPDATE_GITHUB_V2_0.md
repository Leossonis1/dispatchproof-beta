# Upgrade Existing Render Beta to V2.0

Save a fresh V1.9 backup before deploying.

Upload/replace:

- app.py
- README.md
- VERSION.txt
- static/app.css
- templates/base.html
- templates/login.html
- templates/public_readiness.html
- templates/public_arrival.html
- templates/public_arrival_submitted.html
- templates/public_arrival_unavailable.html
- templates/public_job_closed.html
- templates/failed_mobilization_report.html
- templates/company_settings.html

Commit and let Render deploy.

After deployment:

1. Confirm the sidebar says Version 2.0.
2. Restore your latest backup if Render resets.
3. Open **Company Settings**.
4. Enter a test company name, tagline, and optional logo.
5. Save.
6. Confirm the sidebar and login page use the company identity.
7. Open a public readiness link and installer link.
8. Confirm both show the company identity and "Powered by DispatchProof".
9. Open a failed-mobilization report and confirm company branding appears.
10. Generate a readiness email preview and confirm the company name/accent appear.
11. Save a fresh backup after branding is configured.

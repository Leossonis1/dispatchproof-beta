# Upgrade V2.16 to V2.17 — Action Button UI Polish

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_17.md
- static/app.css
- templates/client_detail.html
- templates/project_detail.html
- templates/users_access.html
- templates/public_client_report.html
- templates/public_portfolio_report.html
- templates/client_report.html
- templates/email_outbox_detail.html
- templates/dashboard.html
- templates/job_detail.html
- templates/readiness_request.html
- templates/portfolio_report.html

Only upload a template from this list if it appears in the patch ZIP.

## After Render deploys

1. Confirm Version 2.17.
2. Restore the latest validated V2.16 backup if Render resets.
3. Open Dashboard and confirm **Export CSV** is now solid blue while **Clear All** remains outlined.
4. Open a job and confirm **Edit Job Details**, **Duplicate Job**, and other meaningful job actions are solid blue.
5. Confirm **Cancel**, back/navigation controls, and **Clear All** remain outlined.
6. Confirm destructive actions still use red.
7. Spot-check Clients & Projects and a report page for the same action-button consistency.
8. Save a fresh V2.17 backup after validation.

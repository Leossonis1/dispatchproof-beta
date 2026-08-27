# Upgrade Existing Render Beta to V2.6

Start from the verified V2.5 code + live-data checkpoint.

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_6.md
- static/app.css
- templates/client_detail.html
- templates/project_detail.html
- templates/email_outbox.html
- templates/email_outbox_detail.html
- templates/portfolio_report.html
- templates/public_portfolio_report.html

After deployment:

1. Confirm Version 2.6.
2. Restore the latest V2.5 backup if Render resets.
3. Open Bob Construction and confirm **Combined Client Report** appears.
4. Open Bob Retail Rollout and confirm **Combined Project Report** appears.
5. Open the Client combined report in a private/incognito window.
6. Confirm both existing test jobs appear under Bob Construction.
7. Confirm Bob Retail Rollout's combined report shows the same two jobs currently assigned to that project.
8. Confirm the report shows status, readiness/arrival details, evidence, and Job Activity.
9. Generate a combined client report email and confirm Email Outbox labels it as Bob Construction.
10. Rotate the combined Client report link; confirm old URL fails and new URL works.
11. Repeat the link-rotation check for Bob Retail Rollout.
12. Sign in as Operations and confirm combined reports remain available.
13. Save a fresh V2.6 live-data backup after validation.

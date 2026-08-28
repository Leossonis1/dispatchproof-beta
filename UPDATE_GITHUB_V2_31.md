# Upgrade V2.30 to V2.31 — Report Close + Missing Page Guard

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_31.md
- static/app.css
- templates/public_client_report.html
- templates/public_portfolio_report.html
- templates/help.html
- templates/404.html

## After Render deploys

1. Confirm Version 2.31.
2. Restore the latest validated V2.30 backup only if Render resets.
3. Open **Bob Project Test 2 → Preview Client Report**.
4. Confirm **Close Report** appears beside **Print / Save PDF**.
5. Click **Close Report** and confirm it closes/returns cleanly.
6. Open **Bob Construction → Combined Client Report → Preview/Open Combined Report**.
7. Confirm **Close Report** also appears on the combined report.
8. Test a definitely missing job URL such as `/jobs/999999`.
9. Confirm a friendly **This DispatchProof page is no longer available** page appears instead of a 500 error.
10. Open Help & Tutorials and search `close report`.
11. Save a fresh V2.31 backup after validation.

# Upgrade V2.19 to V2.20 — Needs Attention

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_20.md
- static/app.css
- templates/dashboard.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.20.
2. Restore the latest validated V2.19 backup if Render resets.
3. Open Dashboard.
4. Confirm the new **Needs Attention** panel appears above the status cards.
5. With the current test data, the near-term No Response job should appear in Needs Attention.
6. Confirm the later No Response job is not included unless its date moves into the next 7 days.
7. Click **Open Job** and confirm it opens the correct installation.
8. Open Help & Tutorials and search `attention`; confirm **Use Needs Attention** appears.
9. Save a fresh V2.20 backup after validation.

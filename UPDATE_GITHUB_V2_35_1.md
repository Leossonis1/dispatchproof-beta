# Upgrade V2.35 to V2.35.1 — Crew Availability Profile Fix

This is a small corrective deployment patch.

Upload/replace:

- app.py
- VERSION.txt
- UPDATE_GITHUB_V2_35_1.md
- static/app.css
- templates/edit_crew_member.html

## What this fixes

The V2.35 backend availability logic was deployed, but the Crew Member profile could still render the older template without the **Crew Availability** section. V2.35.1 re-deploys that profile template and its V2.35 styling.

## Test

1. Confirm Version 2.35.1.
2. Open Crew → Mike Davis → View/Edit.
3. Confirm **Crew Availability** appears below **Crew Member Details**.
4. Continue V2.35 availability testing from there.

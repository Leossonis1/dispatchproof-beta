# Update GitHub — V2.43

Replace the files from the V2.43 patch ZIP, commit, and deploy normally.

Changed files:
- `app.py`
- `templates/find_subcontractor.html`
- `templates/job_detail.html`
- `templates/crew_directory.html`
- `templates/edit_crew_member.html`
- `templates/help.html`
- `static/app.css`
- `README.md`

Render environment: add `FOURSQUARE_SERVICE_API_KEY` if it is not already present on the DispatchProof service.

No database reset is required. V2.43 adds nullable source fields to `crew_members` automatically.

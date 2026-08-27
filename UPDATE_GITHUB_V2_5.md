# Upgrade Existing Render Beta to V2.5

You have a verified V2.4 code + live-data checkpoint.

Upload/replace:

- app.py
- README.md
- VERSION.txt
- static/app.css
- templates/base.html
- templates/new_job.html
- templates/job_detail.html
- templates/backup_restore.html
- templates/public_client_report.html
- templates/clients.html
- templates/client_form.html
- templates/client_detail.html
- templates/project_form.html
- templates/project_detail.html

After deployment:

1. Confirm Version 2.5.
2. Restore the latest V2.4 backup if Render resets.
3. Confirm **Clients & Projects** appears for Owner and Operations.
4. Create a test client.
5. Create a project under that client.
6. Assign the existing test job to that client/project.
7. Confirm it appears on both Client and Project pages.
8. Confirm Job Activity records **Job Assignment Changed**.
9. Open the V2.4 Client Report and confirm Client / Project appear.
10. From the Project page click **+ New Job** and confirm Client/Project are preselected.
11. Create that job and confirm it appears under the project immediately.
12. Save a fresh V2.5 live-data backup after validation.

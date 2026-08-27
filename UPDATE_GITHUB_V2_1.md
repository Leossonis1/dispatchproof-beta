# Upgrade Existing Render Beta to V2.1

You already saved a V2.0.1 branding backup before this deployment.

Upload/replace:

- app.py
- README.md
- VERSION.txt
- static/app.css
- templates/base.html
- templates/login.html
- templates/backup_restore.html
- templates/users_access.html

Commit and let Render deploy.

After deployment:

1. Confirm Version 2.1.
2. Restore the latest backup if Render resets.
3. Sign in with the existing Owner/admin login.
4. Open **Users & Access**.
5. Add a test Operations user with a password of at least 8 characters.
6. Sign out and sign in as that user.
7. Confirm jobs and Email Outbox are available.
8. Confirm Company Settings, Users & Access, and Backup & Restore are hidden.
9. Try opening `/settings/company` directly and confirm DispatchProof returns to the dashboard with an Administrator access message.
10. Sign back in as Owner and test Disable Access / Enable Access.
11. Add an Administrator test user and confirm the management pages are available.
12. Save a new backup after testing.

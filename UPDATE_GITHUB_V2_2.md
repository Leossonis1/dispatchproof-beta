# Upgrade Existing Render Beta to V2.2

You already saved a V2.1 data backup.

Upload/replace:

- app.py
- README.md
- VERSION.txt
- static/app.css
- templates/base.html
- templates/users_access.html
- templates/my_account.html
- templates/edit_user.html

Commit and let Render deploy.

After deployment:

1. Confirm Version 2.2.
2. Restore the latest backup if Render resets.
3. Sign in as the Operations test user.
4. Open **My Account**.
5. Change the user's password using the current password.
6. Sign out and confirm the old password fails and the new password works.
7. Sign in as Owner/admin.
8. Open **Users & Access → Edit User**.
9. Change the user's Full Name or Username and save.
10. Confirm the edited login works and permissions remain correct.
11. Verify an Operations user still cannot access admin settings directly.

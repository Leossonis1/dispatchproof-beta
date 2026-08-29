# DispatchProof V2.40 Patch Only

Apply this patch over V2.39.2.

Replace/add:
- `app.py`
- `VERSION.txt`
- `templates/my_account.html`
- `templates/workspace_restore_preview.html`

The app automatically creates the additive `workspace_restore_items` table on startup. No database reset is required.

After deploy, sign in as an Operator and open **My Account → Restore / Import My Workspace**. Upload a ZIP created by **Download My Workspace ZIP**, review the preview, then confirm restore.

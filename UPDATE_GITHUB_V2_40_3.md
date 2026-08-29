# DispatchProof V2.40.3

## Restore button reliability fix
- Removes the browser JavaScript confirm dependency from Operator workspace restore.
- Adds an explicit required confirmation checkbox on the preview page.
- Restore My Workspace now submits with a plain HTML POST.
- Server verifies the confirmation and logs when a restore commit request is received.
- No database migration or reset is required.

# DispatchProof V2.40.2 — Crew Delete

Replace the current app files with this release and deploy normally. No database migration or reset is required.

## Changes
- Crew Directory now includes a **Delete** action.
- Crew Member detail pages include **Delete Crew Member**.
- A crew member can be permanently deleted only if they have no linked job assignment history.
- If linked job history exists, deletion is blocked and Deactivate should be used instead.
- Unavailability/time-off rows are cleaned up automatically for a successfully deleted unused crew member.

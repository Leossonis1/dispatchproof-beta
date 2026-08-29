# DispatchProof V2.40.2 — Patch Only

Apply this patch over V2.40.1.

Changes:
- Adds permanent Delete to Crew Directory and Crew Member detail pages.
- Permanent deletion is allowed only when the crew member has no linked job history.
- If job history exists, DispatchProof blocks deletion and directs the user to Deactivate instead.
- Availability/time-off records are removed automatically for successfully deleted unused crew.
- No database migration or reset is required.

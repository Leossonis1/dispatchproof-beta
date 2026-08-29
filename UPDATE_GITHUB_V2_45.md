# DispatchProof V2.45 — Training / Simulation Mode

Deploy this version after V2.44.3.

## What changed
- Adds an isolated Training area for office users.
- Admin can assign one scenario or the complete starter track.
- Trainees work through guided operational decisions using fake data only.
- Wrong choices provide coaching and can be retried; there is no punitive score.
- Admin can review progress, reset scenarios, or remove assignments.
- Includes scenarios for PM basics, blocked readiness, crew conflicts/staffing, failed mobilization/return visits, multi-day progress, subcontractor sourcing, and rollout route planning.
- Training tables are separate from production jobs/crew/email/routing/search data.

## Database
Automatic additive migration only. No manual database work.

## Safety
Training routes do not call production email, readiness, arrival, field-link, contractor-search, or route-provider functions.

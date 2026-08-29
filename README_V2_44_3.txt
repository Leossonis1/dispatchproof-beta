DispatchProof V2.44.3 — Bulk Rollout Job Import

Deploy this patch on top of V2.44.2.
No database migration or new environment variable is required.

New workflow:
Project > Route Optimization > Download Job Import Template > fill/paste rollout list > Upload Completed CSV > Import Jobs into This Project.

Required CSV columns:
- Job Name
- Route / Site Address
- Installation Date

Optional:
- Site Contact Name
- Site Contact Email
- Site Contact Phone

Imported jobs are Personal to the signed-in workspace by default.
- Route page now clearly displays capacity limits before download/import: up to 250 jobs per CSV and up to 40 active jobs per optimized route.


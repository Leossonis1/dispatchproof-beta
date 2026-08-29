# DispatchProof V2.44.3 — Bulk Rollout Job Import

## What changed
- Adds **Download Job Import Template** to Project Route Optimization.
- Adds **Upload Completed CSV / Import Jobs into This Project**.
- Creates rollout jobs in bulk instead of requiring 30–40 individual New Job forms.
- Template is project-specific, so Client and Project do not need to be repeated on every row.
- Required columns: **Job Name**, **Route / Site Address**, **Installation Date**.
- Optional contact columns may be completed later.
- Accepts `YYYY-MM-DD`, `MM/DD/YYYY`, `MM/DD/YY`, or `MM-DD-YYYY` dates and normalizes them internally.
- Imports are validated before saving; a bad row prevents a partial import and reports the row number.
- Exact duplicates (same project + job name + address + installation date) are skipped safely.
- Imported jobs default to **Personal** access for the signed-in workspace. Team access can be assigned later.
- The example row in the downloaded template is ignored automatically if it is left in the file.
- Maximum 250 jobs per import file; Route Optimization remains capped at 40 jobs per route plan.

## Database
No migration is required. This feature uses the existing jobs table.
- Route page now clearly displays capacity limits before download/import: up to 250 jobs per CSV and up to 40 active jobs per optimized route.


# Update GitHub — V2.44

Project-level Route Optimization.

## Replace
- `app.py`
- `static/app.css`
- `templates/project_detail.html`
- `templates/help.html`
- `templates/backup_restore.html`
- `VERSION.txt`
- `README.md`
- `DEPLOY_RENDER.md`

## Add
- `templates/route_optimizer.html`
- `UPDATE_GITHUB_V2_44.md`

## Render
Add `OPENROUTESERVICE_API_KEY` (or `DISPATCHPROOF_ORS_API_KEY`).

## Database
Automatic additive migration. Adds saved route-plan, route-stop, and geocode-cache tables.

## Core behavior
- Optimize 2–40 visible active jobs in one Project.
- Start location + optional return to start.
- Editable routing addresses do not modify job Site / Project values.
- Road-optimized sequence, mileage, drive time, interactive map.
- Manual reorder followed by one explicit recalculation call.
- Route plans are creator-private to protect PM job isolation.
- Full Owner/Admin database backups include the new route tables.

# DispatchProof V2.44.2 — Route Polish + Download

## What changed
- Makes **Crew Starting Location** unmistakably labeled and explains what belongs there.
- Keeps browser required validation and adds a specific popup message when the starting location is blank.
- Keeps the server-side validation as a fallback if browser validation is bypassed.
- Adds **Download Route CSV** for every saved route.
- The CSV includes client/project, start/return setting, total mileage, estimated drive time, numbered stop order, job names, route addresses, installation dates/status, and per-leg mileage/time.
- No database migration.
- No routing API key changes.

## Deploy
Apply this patch over V2.44.1 and deploy normally.

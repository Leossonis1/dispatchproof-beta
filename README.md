# DispatchProof V2.44

Project-level Route Optimization for retail rollouts and other multi-location work.

V2.44 keeps the existing DispatchProof job lifecycle intact and adds a focused routing tool inside **Clients & Projects → Project**. It is intentionally a planning feature, not a separate logistics application.

## What changed

- Added **Route Optimization** to each Project page.
- Select 2–40 active jobs from the current project.
- Enter the crew's starting location and optionally return to that location after the final stop.
- Each selected job's route address is editable for planning without changing the job's saved Site / Project field.
- Uses road-routing optimization to calculate an efficient stop sequence.
- Saves total road mileage and estimated drive time.
- Displays the saved route on an interactive OpenStreetMap/Leaflet map.
- Saves a numbered stop list with mileage and drive time from the prior stop.
- Manual up/down reordering is local until **Save Manual Order & Recalculate** is clicked, avoiding unnecessary routing calls.
- Saved route plans are private to the user who creates them, preventing route data from leaking another PM's private job access.
- Route plans and stops are included in Owner/Admin full-system database backups.
- Existing readiness, arrival, failed mobilization, Field Updates, Daily Progress, subcontractor search, Schedule, and Client Reports are unchanged.

## One-time Render setup

Create an openrouteservice / HeiGIT API key and add either of these environment variables to the DispatchProof Render service:

- `OPENROUTESERVICE_API_KEY` (recommended)
- `DISPATCHPROOF_ORS_API_KEY` (DispatchProof-specific override)

This is separate from `FOURSQUARE_SERVICE_API_KEY`; route optimization does not consume Contractor Finder/Foursquare credits.

V2.44 uses the current HeiGIT endpoints (`api.heigit.org`) rather than the deprecated `api.openrouteservice.org` host.

## Database migration

Automatic and additive. V2.44 creates:

- `project_route_plans`
- `project_route_stops`
- `route_geocode_cache`

No reset is required.

## First QA pass

1. Open a Project with at least 3 active jobs.
2. Click **Route Optimization**.
3. Confirm only jobs visible to the signed-in user appear.
4. Enter a real starting address.
5. Select 3 jobs and verify/correct each route address.
6. Leave **Return to starting location** off and click **Optimize Selected Jobs**.
7. Confirm a numbered stop order, total mileage, drive time, and route map appear.
8. Move one stop with the arrow buttons and click **Save Manual Order & Recalculate**.
9. Confirm the new order persists and mileage/time refresh.
10. Return to the Project, reopen Route Optimization, and confirm the saved route remains.
11. As a second normal PM, confirm the first PM's private saved route is not visible.

## Design limits in V2.44

- One saved route plan per user per Project.
- One crew / one route at a time.
- Maximum 40 selected jobs, intentionally below the routing provider's 50-waypoint directions limit.
- Route Optimization does not automatically rewrite installation dates. It plans the recommended sequence; scheduling stays under PM control.

# V2.44 Render Deploy

Deploy normally over V2.43.2.

## New environment variable

Add one routing key to the DispatchProof Render service:

`OPENROUTESERVICE_API_KEY=<your key>`

`DISPATCHPROOF_ORS_API_KEY` is accepted as an alternate DispatchProof-specific variable.

Do not change `FOURSQUARE_SERVICE_API_KEY`; subcontractor discovery continues using Foursquare separately.

## Migration

Automatic/additive on first request after deployment. No database reset is required.

## Verify after deploy

1. Footer shows Version 2.44.
2. Open Clients & Projects → a Project.
3. Click Route Optimization.
4. The yellow setup warning disappears once the routing key is configured.
5. Optimize a small 3-stop route first.

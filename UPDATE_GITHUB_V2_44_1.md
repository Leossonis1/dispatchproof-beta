# DispatchProof V2.44.1 — Route HTTP Fix

## What changed
- Fixes a Render/Python 3.14 `http.client.BadStatusLine` crash during live HeiGIT/openrouteservice calls.
- Route API calls now use `requests`/urllib3 instead of `urllib.request`.
- Adds one short retry for transient connection and 502/503/504 gateway failures.
- Routing provider errors now return a friendly DispatchProof message instead of a raw 500 page.
- No database migration.
- No change to the `OPENROUTESERVICE_API_KEY` environment variable.

## Deploy
Replace the listed patch files in the repository and deploy normally. Render will install the added `requests` dependency from `requirements.txt` during the build.

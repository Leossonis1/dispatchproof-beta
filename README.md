# DispatchProof V2.43

Find a Subcontractor. DispatchProof now includes a lightweight contractor-discovery feature inside the existing job and Crew workflows. Search nearby businesses by trade/location/radius, save a result as a normal Subcontractor directory record, and optionally assign it directly to the current job.

## What changed

- Added **Find a Subcontractor** from Field Assignment and Crew & Subcontractors.
- Reuses the Foursquare Places service-key approach from Leosson Contractor Finder.
- Supports United States, Canada, United Kingdom, Australia, Ireland, and New Zealand.
- Search uses Strict / Balanced / Broad trade matching and a small process cache to reduce provider calls.
- Search Match is explicitly a trade-fit score, not a contractor quality/qualification rating.
- Save discovered businesses into the existing Subcontractor Directory.
- **Save & Assign to This Job** adds the saved subcontractor through the existing crew assignment structure.
- Existing scheduling, conflict, availability, Field Update, and Daily Progress workflows automatically apply after assignment.
- Captures discovery address/website/source on the Subcontractor record.
- Existing V2.42 jobs, crew, readiness, arrival, reports, Field Updates, and Daily Progress are unchanged.

## Render setup

Add `FOURSQUARE_SERVICE_API_KEY` to the DispatchProof Render service environment. If you already have the service API key used by Leosson Contractor Finder, reuse that same value. `DISPATCHPROOF_FOURSQUARE_API_KEY` is also accepted as an override.

The database migration is additive and automatic. No reset is required.

## First QA pass

1. Open an active job and click **Find a Subcontractor** in Field Assignment.
2. Verify location is prefilled when the assigned Project has a location.
3. Search one trade with Balanced tolerance.
4. Save one result with **Save & Assign to This Job**.
5. Return to the job and confirm the subcontractor appears under Field Assignment as `SUB`.
6. Open Crew & Subcontractors and confirm the saved result is reusable there.
7. Run the same search again and confirm it shows `SAVED` instead of creating a duplicate record.

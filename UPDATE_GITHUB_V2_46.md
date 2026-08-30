# DispatchProof V2.46 — Subcontractor Compliance + Field Access + Voice Updates

## What changed
- Added subcontractor document storage with optional expiration dates, per-document warning windows, required flags, notes, and Expired / Expiring Soon alerts.
- Added **Snow Plowing / Snow Removal** to Find a Subcontractor with service-focused search/filter signals.
- Expanded the existing secure field link into **Field Access & Daily Progress**. PMs can expose only selected Job/Project/Client documents and optionally site-contact information.
- Added secure token-scoped document viewing/downloading for field recipients.
- Added phone voice recording/audio attachment to Field Responses and Daily Progress. Original audio is retained with the job.
- Added optional automatic transcription using `OPENAI_API_KEY` or `DISPATCHPROOF_OPENAI_API_KEY`; audio submissions still succeed when transcription is unavailable.
- Added voice/subcontractor-document support to Operator workspace backup/restore, including remapping selected Field Access document references on restore.
- Updated Dashboard, Crew & Subcontractors, Job Detail, Field Access, and Help UI.

## Database migration
Automatic/additive. No reset required.

## Render
No new setting is required for the document/audio features themselves. Optional automatic transcription requires an OpenAI API key in Render Environment settings. Keep existing persistent disk, Foursquare, and route-provider settings unchanged.

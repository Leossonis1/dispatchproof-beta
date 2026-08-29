# DispatchProof V2.40.7

## Client Report Mobilization Clarity

This patch makes the client-facing Installation Report clearly distinguish the current mobilization cycle from archived prior attempts.

### What changed

- Renamed the top summary fields to **Current Readiness** and **Current Arrival**.
- When a new mobilization cycle is waiting for a response, the report now says **Awaiting response** instead of implying no response was ever received.
- Added a clear Current Mobilization note when prior attempts exist.
- Current readiness/arrival empty states now point the reader to preserved Mobilization History.
- Expanded archived mobilization cards to show readiness result, confirmer, arrival result, failed-mobilization details, crew/hours lost, equipment, report number, issues, notes, and evidence photos.
- Newest archived attempt is shown first.

### Deployment

No database migration or reset is required. Deploy the patch files and restart the service.

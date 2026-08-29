# DispatchProof V2.40.6

## Global Copy Link fix

This patch fixes the shared-link copy controls across DispatchProof.

### What changed

- Moved copy behavior into one global handler in `templates/base.html`.
- Fixed Readiness Request → Copy Link.
- Fixed Email Outbox → Copy Link.
- Standardized Copy Installer Link, Copy Client Report Link, and Copy Combined Report Link on the same handler.
- Where an Open Link button exists, Copy Link reads that exact browser-resolved `href`.
- Automatic copy now tries the synchronous browser copy path while the click still has user activation, then the Clipboard API, then a manual prompt only as a last resort.

### Deployment

No database migration or reset is required. Deploy the patch files and restart the service.

# DispatchProof V2.40.4

## Readiness Public Link Fix

This patch fixes newly generated site-readiness links that could open the friendly "This DispatchProof page is no longer available" screen when `DISPATCHPROOF_PUBLIC_BASE_URL` pointed at an older/different deployment.

### Changes
- Public links generated from the live app now prefer the current request hostname.
- Environment-configured public URLs remain fallback values for non-request contexts.
- `/r/<token>` accepts an optional trailing slash.
- A failed readiness-token lookup now writes a diagnostic warning to Render logs showing the request host and configured public URL values.

### After deploy
1. Open the affected job.
2. Go to Readiness Request.
3. Click Open External Page and confirm it opens the public readiness form.
4. Resend the readiness email.
5. Open the newly received email link in a private/incognito browser.

Previously sent emails keep their old URL and should not be used for this verification.

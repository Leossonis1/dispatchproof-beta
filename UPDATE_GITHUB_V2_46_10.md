# DispatchProof V2.46.10 — Mobile Browser Usability

Based on the frozen V2.46.9 release candidate.

## What changed
- Added a responsive phone/tablet top bar.
- Added a slide-out navigation drawer so the full app remains navigable below 900 px.
- Added backdrop, close button, Escape-key close, and automatic menu close after navigation.
- Increased touch targets on mobile.
- Uses 16 px form controls on phones to avoid browser auto-zoom behavior.
- Stacks form actions, detail rows, cards, and headings where needed.
- Keeps wide data tables readable with contained horizontal scrolling instead of page-level overflow.
- Constrains job action menus to the phone viewport.
- Tightened small-screen padding and typography while preserving the desktop layout.

## What did not change
- No feature behavior changes.
- No database/schema changes.
- No permissions changes.
- No job/crew/conflict logic changes.
- No Training logic changes.
- No native iOS/Android app or app-store packaging.

## Files changed
- `templates/base.html`
- `static/app.css`
- `app.py` (version display only)
- `VERSION.txt`

## Deploy
Replace the files above (or deploy the full package), commit, push, and let Render redeploy normally. No environment-variable changes are required.

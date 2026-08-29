# DispatchProof V2.40.5

## Readiness Copy Link fix

- Fixes Readiness Request → Copy Link.
- Copy Link now reads the exact browser-resolved `href` used by the working Open External Page button.
- Removes the separate `data-copy-url` value and inline click handler so the two actions cannot drift apart.
- Keeps Clipboard API + legacy copy fallback, with manual copy prompt only as a last resort.
- No database migration or reset required.

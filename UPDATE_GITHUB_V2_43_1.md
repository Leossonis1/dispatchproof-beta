# Update GitHub — V2.43.1

Search-quality polish for Find a Subcontractor.

## Replace
- `app.py`
- `VERSION.txt`

No database migration is required.

## What changed
- Filters obvious cabinet/flooring/etc. stores, showrooms, suppliers, sales galleries, liquidators, and similar retail false positives.
- Keeps legitimate contractor/install businesses when their name/categories clearly indicate field service.
- Balanced and Strict searches stay focused on actual subcontractor candidates.
- Existing Foursquare key, cache, radius, save, and assignment behavior are unchanged.

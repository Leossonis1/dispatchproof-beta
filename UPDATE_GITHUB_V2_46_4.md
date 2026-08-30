# DispatchProof V2.46.4 — Snow Landscaper Matching

- Expanded Snow Plowing / Snow Removal discovery to include landscapers/lawn-care/grounds-maintenance contractors when Foursquare matches them to snow, plowing, ice-management, or winter-service content.
- Generic landscapers do not qualify without a snow/winter signal.
- Retail/supply/equipment/hardware/garden-center/nursery categories are hard-blocked from the snow section, even if another service category is also present.
- Adds a targeted `landscaper snow removal` fallback search only when the primary snow searches return too few usable contractors.
- No database migration.
- No Render environment changes.

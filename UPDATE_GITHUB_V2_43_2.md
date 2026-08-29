# Update GitHub — V2.43.2

Search-precision follow-up for Find a Subcontractor.

## Replace
- `app.py`
- `VERSION.txt`

No database migration is required.

## What changed
- Millwork / Carpentry now searches for **finish carpenter** first and **millwork installer** as fallback instead of leading with cabinet-installer wording.
- Ambiguous cabinet/cabinetry/kitchen/closet companies are excluded unless the business name itself clearly advertises installation, contracting, carpentry, construction, remodeling, service, repair, or handyman field work.
- Store/shop/showroom/gallery/sales/warehouse/liquidator/outlet/supply/design/distributor names receive the same stricter field-service requirement for Millwork / Carpentry.
- This intentionally favors **fewer, more actionable subcontractor candidates** over a longer list of cabinet retailers or manufacturers.
- Provider cache, credit-saving fallback behavior, radius, save, and assignment logic are unchanged.

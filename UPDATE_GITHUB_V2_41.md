# DispatchProof V2.41 — Subcontractor Support

## What changed
- Crew Directory now supports two reusable record types: **Internal Crew** and **Subcontractor**.
- Subcontractor records can store an optional **Company Name** plus the existing role/trade, email, phone, notes, availability, assignment history, and active/inactive status.
- Crew Directory adds a **Type** filter and separate active Internal Crew / Subcontractor counts.
- Job crew pickers show the record type and subcontractor company so PMs can assign subs through the same proven scheduling workflow.
- Subcontractors participate in the existing crew conflict and availability logic automatically because they use the same structured assignment table.
- Existing Crew Directory records migrate safely to **Internal Crew**.
- Workspace/system backups remain compatible: new fields export automatically, old backups restore with the Internal Crew default.

## Database migration
Automatic and additive. V2.41 adds `member_type` and `company_name` to `crew_members` when missing. Existing records and job assignments are preserved.

## Deploy
Use the patch ZIP on top of V2.40.9.2, or deploy the full V2.41 build. No manual database work is required.

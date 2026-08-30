# DispatchProof V2.46.1 — Subcontractor Document Upload Fix

## Fix
- Fixes a `NameError` when uploading subcontractor compliance documents.
- Restores the shared document-extension validation helper used by subcontractor, Client, Project, and Job document uploads.
- No database migration. No Render environment changes.

## QA
1. Open Crew & Subcontractors and edit a subcontractor.
2. Upload a PDF or other supported document.
3. Confirm the upload returns to the subcontractor profile and the document appears in the compliance list.

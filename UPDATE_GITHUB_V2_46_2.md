# DispatchProof V2.46.2 — Subcontractor Document Viewer

- Splits the subcontractor document action into separate **View** and **Download** buttons.
- Adds an authenticated in-app viewer for PDFs, images, CSV files, and text files.
- CSV previews are safely rendered in DispatchProof instead of relying on browser CSV behavior.
- Unsupported formats such as DOCX/XLSX/DWG/DXF show a clear preview-unavailable message with a Download button.
- Download now always sends the file as an attachment.
- No database migration or Render setting changes.

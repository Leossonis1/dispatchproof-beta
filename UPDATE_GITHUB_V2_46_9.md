# DispatchProof V2.46.9 — Workspace Visibility

- Owner/Admin continues to see all Clients, Projects, Jobs, and company data.
- Operations users now see only Clients and Projects they own or that contain a Job they are authorized to access through job ownership/team sharing.
- Client/Project direct URLs, documents, Document Center results, assignment dropdowns, route tools, and workspace exports follow the same visibility rules.
- New Clients/Projects created by an Operations user are owned by that user so they remain visible before the first Job is created.
- The Crew/Subcontractor directory remains company-wide and shared, including subcontractor documents, so PMs can share contractor resources.
- Existing Client/Project records remain Owner/Admin-only for an Operations user until that user gains access through an authorized Job.
- No destructive database reset. Existing databases receive nullable owner_user_id columns automatically.

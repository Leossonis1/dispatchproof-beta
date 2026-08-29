# Upgrade V2.36 to V2.37 — Private PM Jobs + Optional Team Sharing

V2.37 adds user-owned job workspaces and optional PM collaboration teams.

## Upload / replace

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_37.md
- templates/users_access.html
- templates/new_job.html
- templates/edit_job.html
- templates/job_detail.html
- templates/client_detail.html
- templates/project_detail.html

## What changes

### Private by default

- Every new job created by an Operations user is automatically owned by that user.
- Operations users see only:
  - jobs they own; and
  - jobs assigned to a team they belong to while that team's sharing toggle is ON.
- A newly created Operations account starts with a blank job workspace.
- Owner and Administrator accounts continue to see all jobs.

### Existing V2.36 jobs

Existing jobs are intentionally left with no PM owner during the automatic database migration.

That means:

- Owner / Administrator can still see the existing jobs.
- Newly created Operations users cannot see those legacy jobs.
- An Owner / Administrator can open an existing job and assign it to a PM Team when collaboration is needed.

This avoids guessing which existing user should own historical data.

### PM Teams

In **Settings → Users & Access → PM Teams**, an Owner / Administrator can:

1. Create a team.
2. Add active users to the team.
3. Turn team job sharing ON or OFF.
4. Remove a user from the team.

Personal jobs remain private even when their owner belongs to a team.

### Personal vs Team jobs

New Job and Edit Job now include **Job Access**:

- **Personal** — only the job owner plus Owner / Administrators can access it.
- **Team — [Team Name]** — team members can access it while that team's sharing toggle is ON.

Only the original job owner or an Owner / Administrator can change a job's Personal / Team access setting.

### Privacy across the app

Job visibility is enforced in:

- Dashboard
- Schedule
- Completed Jobs
- Clients & Projects job lists/counts
- Document Center job documents
- Email Outbox
- Crew Directory assignment history/counts
- Active and Completed CSV exports
- direct internal job URLs
- Document Center quick job upload

Crew Directory remains company-wide so the same field crew can be scheduled by multiple PMs.

If a shared crew member is double-booked across two private PM jobs, each affected PM still receives a crew-conflict warning, but the inaccessible job name is shown only as **another private job**.

### Combined Client / Project Reports

Combined Client and Project Reports aggregate company-wide job data, so V2.37 limits those combined reports to Owner / Administrator accounts. Operations users can continue using the normal per-job client report for jobs they are allowed to access.

## Database migration

No manual SQL is required.

On first startup V2.37 automatically:

- adds `owner_user_id` and `team_id` to jobs;
- creates `teams`;
- creates `team_members`;
- creates supporting indexes;
- leaves existing jobs as Owner / Administrator-only legacy jobs.

Take a fresh DispatchProof backup before deploying, as with any database-changing release.

## Recommended validation

1. Confirm the footer / Health endpoint reports **Version 2.37**.
2. Sign in as Owner / Administrator and confirm the existing V2.36 jobs are still present.
3. Create two Operations test users: PM1 and PM2.
4. Sign in as PM1. Confirm the Jobs/Dashboard/Schedule workspace contains no existing Owner jobs.
5. Create **PM1 Personal Test** as PM1.
6. Sign in as PM2. Confirm PM1 Personal Test is not visible.
7. Create **PM2 Personal Test** as PM2.
8. Sign back in as PM1. Confirm PM2 Personal Test is not visible.
9. As Owner / Administrator, create a PM Team and add PM1 + PM2.
10. Make sure **Sharing ON** is displayed for that team.
11. As PM1, create **Team Test Job** and choose that team under Job Access.
12. Sign in as PM2. Confirm Team Test Job is visible and editable, while PM1 Personal Test is still hidden.
13. As Owner / Administrator, turn that team's sharing OFF.
14. Sign in as PM2. Confirm Team Test Job created by PM1 is no longer visible.
15. Turn sharing back ON and confirm it returns.
16. Assign the same Crew Directory person to PM1 and PM2 private jobs on the same installation date. Confirm the conflict warning appears without exposing the other private job name.
17. Sign in as Owner / Administrator and confirm all PM1, PM2, team, and legacy jobs remain visible.
18. Save a fresh V2.37 backup after validation.

# DispatchProof V1.7 — Backup & Branding

V1.7 adds a portable beta-data backup system so free Render resets no longer
have to erase test history permanently.

## Backup & Restore

Admin navigation now includes **Backup & Restore**.

Download Backup ZIP includes:

- `dispatchproof.db`
- all uploaded readiness photos
- all uploaded arrival photos
- jobs
- readiness confirmations
- mobilization history
- failed mobilization report data
- Email Outbox history
- a backup manifest

Restore validates and stages the backup before replacing current beta data.

## Recommended Free Render routine

1. Before a deploy/restart, download a backup.
2. Let Render redeploy.
3. If the dashboard returns empty, open Backup & Restore.
4. Upload the saved ZIP.
5. Continue testing.

## Branding polish

- DispatchProof favicon
- cleaner branded admin login
- consistent DispatchProof naming
- beta label removed from generated email header
- sidebar tagline driven from product branding constants

## Important

This backup approach is meant for the current free beta. It is not a replacement
for durable hosted storage. Later we should move to PostgreSQL/object storage or
a persistent disk.


## V1.7.1 — Field Photo Capture

Phone users now get two clear photo actions:

- **Take Photo** — requests the device camera, preferring the rear/environment camera
- **Choose Existing Photos** — selects one or more images already on the device

Selected images are accumulated into the same form submission and display:

- live thumbnail previews
- individual Remove buttons
- photo-count status
- "requirement met" state when the minimum is satisfied

Site readiness requires at least 2 photos.

Installer Arrival keeps photos optional when Site Ready is selected, but dynamically
changes to a 2-photo minimum when Site Not Ready / failed mobilization is selected.

No native mobile app is required; this uses standard browser camera/file capabilities.


## V1.7.2 — Beta Polish

### Stay signed in

The Admin Sign In page now includes **Stay signed in on this device**.

- unchecked: browser-session login only
- checked: admin session can remain signed in for up to 30 days
- Sign Out always clears the session
- Render continues to use Secure + HttpOnly cookies

### Backup visibility

Backup & Restore now shows the record counts that will be preserved:

- Jobs
- Readiness Responses
- Mobilization Attempts
- Outbox Messages
- Uploaded Files

This makes it possible to confirm that meaningful test data is actually aboard the backup before downloading it.

### Failed mobilization impact

When **Site Not Ready** is selected:

- Crew Affected is required and must be at least 1
- Hours Lost is required and must be greater than 0
- at least one failure reason is required
- at least two arrival photos are still required

Equipment / Tools Affected and Notes remain optional.


## V1.7.2.1 — Restore Fix

The restore routine now removes stale SQLite WAL/SHM/journal files before
replacing the live database. This prevents an empty post-deploy WAL from
masking or overwriting a restored database.

Restore now verifies the live job count against the backup before reporting
success and rolls back if verification fails.

New backups also store record counts in the backup manifest.


## V1.8 — Secure Installer Arrival Link

When a job is **READY** and arrival has not yet been recorded, the protected job
page now shows an **Installer Arrival Link**.

The office can:

- Copy Installer Link
- Open External Page
- Record Internally

The installer link:

- uses a separate high-entropy token from the site-readiness link
- opens without an admin login
- exposes only the current job's installer-arrival form
- cannot access the dashboard, reports, Email Outbox, backups, or other jobs
- only accepts an arrival while the current job is READY
- locks after the first successful arrival submission
- automatically rotates whenever a new confirmation/mobilization starts

The public installer form supports:

- Site Ready / Site Not Ready
- installer/reporter name
- failure reasons
- required Crew Affected + Hours Lost on failed mobilizations
- optional equipment/tools and notes
- Take Photo
- Choose Existing Photos
- two-photo minimum for Site Not Ready

This is the first field-crew workflow that does not require sharing the DispatchProof
admin password.


## V1.8.1 — Installer Copy Link Fix

The V1.8 Installer Arrival Link button rendered correctly, but its JavaScript
was accidentally inserted inside the HTML title block and therefore never
executed.

V1.8.1:

- moves the copy script into the page body where it executes normally
- copies directly from the secure installer URL stored on the button
- uses the modern Clipboard API when available
- falls back to the legacy browser copy method
- shows "Copied!" after success
- falls back to a manual copy prompt only if both browser copy methods fail


## V1.9 — Job Lifecycle

DispatchProof now carries a job beyond pre-dispatch readiness.

### Active lifecycle

- **NO RESPONSE** — waiting for the site contact
- **REVIEW** — readiness needs office review
- **READY** — safe to dispatch
- **BLOCKED** — site is not ready / failed mobilization
- **ON SITE** — installer confirmed a successful Site Ready arrival

A successful arrival now changes the job from **READY** to **ON SITE** instead
of leaving it incorrectly marked Ready to Dispatch.

### Completion

An ON SITE job gets a **Mark Job Complete** action.

Completing the job:

- changes status to **COMPLETED**
- records the completion timestamp
- removes the job from Upcoming Installations
- moves it into **Completed Jobs**
- preserves readiness answers/photos
- preserves arrival answers/photos
- preserves mobilization and confirmation history
- revokes the shared installer-arrival link
- closes the public readiness form for that completed job

Completed jobs are view-only evidence records. They are not deleted.

### Compatibility

Older successful V1.8 arrivals that were stored as READY are migrated to
ON SITE automatically when V1.9 initializes the database.


## V2.0 — Company Settings & Branding

DispatchProof now has a protected **Company Settings** page where an admin can set:

- company name
- tagline / department label
- contact email
- contact phone
- website
- accent color
- company logo

The company identity is shown in the internal sidebar/login and on the public
readiness/installer workflow. DispatchProof remains visible as the product
attribution ("Powered by DispatchProof").

The failed-mobilization report uses the configured company name/logo as well.

The settings record lives in the same SQLite database as jobs, and the logo lives
in DispatchProof's managed uploads folder. Existing Backup & Restore therefore
preserves both the company settings and company logo.

The logo is exposed publicly through a dedicated `/branding/logo` endpoint only.
The general evidence/upload folder remains protected by the existing admin login.


## V2.0.1 — Sidebar Brand Polish

Long company names in the left sidebar now wrap naturally instead of being
truncated with an ellipsis.

The company identity remains compact by:

- using a slightly smaller brand-name type size
- aligning the logo/checkmark with the first line
- allowing multi-line company names
- keeping the DispatchProof attribution smaller beneath the company name
- preserving the full company name in the hover title


## V2.1 — Users & Access

DispatchProof now supports multiple internal office logins.

### Permanent Owner

The existing Render Environment login remains the permanent **Owner** account:

- username: `DISPATCHPROOF_ADMIN_USERNAME`
- password: `DISPATCHPROOF_ADMIN_PASSWORD`

The Owner cannot be disabled from inside DispatchProof, so the application always
has a recovery administrator.

### Additional users

Administrators can open **Users & Access** to:

- add users
- create a temporary password
- choose Operations or Administrator access
- enable / disable access
- change a user's role
- reset a user's password
- see the user's last sign-in time

Passwords for additional users are stored as one-way Werkzeug password hashes,
never plain text.

### Permissions

**Operations**
- Dashboard
- New Job
- Completed Jobs
- readiness workflow
- installer arrival workflow
- reports
- Email Outbox

**Administrator**
- everything Operations can do
- Company Settings
- Users & Access
- Backup & Restore

**Owner**
- permanent environment-backed administrator
- cannot be disabled from inside the application

Company Settings, user management, and Backup & Restore are hidden from Operations
users and server-side permission checks prevent direct URL access.

The existing **Stay signed in on this device** option works for all internal users.

### Backups

Additional users and their password hashes live in SQLite, so normal DispatchProof
backups preserve them automatically. The permanent Owner credentials remain in
Render Environment and are not stored in the backup.


## V2.2 — User Account & Admin Editing

### My Account

Every signed-in internal user now has a **My Account** page.

Database-backed Operations and Administrator users can change their own password by:

1. entering the current password
2. choosing a new password of at least 8 characters
3. confirming the new password

DispatchProof verifies the existing hashed password before changing it and refuses
to reuse the current password.

The permanent Owner account remains controlled by Render Environment, so its
My Account page clearly explains that the Owner password must be changed through
`DISPATCHPROOF_ADMIN_PASSWORD`.

### Edit User

Administrators can now open a proper **Edit User** screen from Users & Access.

Editable fields:

- Full Name
- Username
- Role
- Enabled / Disabled access

Protection rules remain in place:

- the permanent Owner username cannot be reused
- usernames remain unique
- an administrator cannot disable their own current account
- an administrator cannot demote their own current account while using it

The existing administrator password-reset control remains available for account
recovery, while users can now handle normal password changes themselves.


## V2.3 — Activity Log

DispatchProof now records an audit trail so multi-user actions have clear
accountability.

### Global Activity Log

Owners and Administrators have a new **Activity Log** page showing the latest
300 events with:

- action
- date/time
- actor name
- actor type / access level
- job link when the event belongs to a job
- human-readable description

Operations users do not receive access to the global administrative log.

### Per-job activity

Every internal user can see **Job Activity** on a job detail page. This timeline
shows who acted on that job and when, while the existing confirmation and
mobilization histories continue to preserve the actual evidence.

### Tracked V2.3 actions

The audit trail records important changes including:

- job created
- readiness request generated
- readiness reminder generated
- site-contact readiness submitted
- site ready on arrival
- failed mobilization recorded
- job completed
- new confirmation / next mobilization started
- user added or edited
- user access enabled / disabled
- user role changed
- administrator password reset
- self-service password change
- company settings changed
- backup downloaded
- backup restored

Passwords, secret values, and public tokens are never written to the activity
description.

### Upgrade history

V2.3 begins tracking at the time it is installed. It does not invent activity
records for older actions. Existing pre-V2.3 readiness confirmations,
mobilization attempts, reports, email events, photos, and completion evidence
remain preserved exactly as before.

Activity records live in SQLite and are automatically included in normal
DispatchProof backups.


## V2.4 — Client Reports

DispatchProof can now turn a running installation record into a branded,
client-facing report.

### Client Report & Email

Every job has an **Installation Report** panel with:

- Client Report & Email
- Preview Client Report

The internal Client Report page lets the office:

- enter any client recipient name and email
- generate/send a branded client-report email
- copy the secure report link
- open the report for preview
- rotate the secure link to revoke previously shared access

While Free Beta Outbox Mode is active, client-report emails are generated and
logged in Email Outbox but are not sent externally.

### Secure live report

The client receives a high-entropy no-login URL that exposes only that job's
client report. It does not expose DispatchProof dashboard, users, backups,
company settings, Email Outbox, or other jobs.

The report includes:

- current job status and install date
- site contact
- readiness confirmation and checklist
- pre-dispatch evidence photos
- installer arrival result
- failed mobilization details when applicable
- mobilization history
- job-specific audit trail
- company branding/contact information

Client-report evidence photos use a dedicated token-protected evidence route.
The route verifies that the requested photo actually belongs to the job before
serving it.

### Link rotation

The report token is separate from the readiness token and installer-arrival
token. **Rotate Secure Link** immediately invalidates the old client report URL
without changing readiness or installer links.

### Audit trail

V2.4 records:

- Client Report Generated
- Client Report Link Rotated

No client-report token or email content is written into the activity
description.

### Print / Save PDF

The public report has a **Print / Save PDF** button using the browser's native
print workflow. This keeps the beta lightweight while still giving a client or
office user a clean PDF-style copy when needed.


## V2.5 — Clients & Projects

DispatchProof now supports **Client → Project → Installation Job** organization.

- Create and edit clients.
- Create projects under a client.
- View active/completed install counts by client.
- View every project and job belonging to a client.
- View running and completed jobs inside a project.
- Assign existing jobs from Job Detail.
- Select client/project when creating a new job.
- Jobs may remain unassigned.
- Selecting a project automatically enforces that project's client.
- Creating a new job from a Project page preselects that client/project.
- V2.4 single-job Client Reports show the assigned Client and Project.
- Activity Log records client/project creation, edits, and job assignment changes.
- Backups include client/project tables and counts.
- The relationship is designed for a future combined multi-job client/project report.


## V2.6 — Combined Client & Project Reports

V2.6 turns the V2.5 Client → Project → Job structure into a client-facing
multi-install reporting workflow.

### Combined Client Report

Every Client page now has **Combined Client Report**. The secure report covers
every job assigned to the client, including jobs that are currently active and
jobs that have been completed.

### Combined Project Report

Every Project page now has **Combined Project Report**. It uses the same secure
report workflow but only includes installations assigned to that project.

### Report contents

Each combined report includes:

- total / active / completed job counts
- Ready, On Site, Blocked/Review, and No Response counts
- job name, site, install date, and site contact
- current readiness confirmation
- installer arrival result
- failed mobilization crew/hours/issues when applicable
- pre-dispatch and arrival evidence photos
- prior mobilization attempts
- each installation's complete V2.3+ Job Activity audit trail

The public combined report is branded and has **Print / Save PDF**.

### Secure sharing

Client and Project records receive their own independent high-entropy report
tokens. These tokens are separate from job readiness, installer-arrival, and
single-job client-report tokens.

The office can:

- copy the secure combined-report link
- preview it without a DispatchProof login
- rotate the link to revoke prior access immediately

Evidence photos are served through scope-specific protected routes that verify
the requested job belongs to the client/project and that the file belongs to
that job.

### Email / Outbox

Combined reports use the same email workflow as single-job reports. In Free
Beta Outbox Mode, the message is generated and logged but not delivered
externally.

Email Outbox now displays the Client or Project report name instead of
mislabeling a combined report as its internal anchor job.

### Upgrade behavior

Existing V2.5 Client and Project records are migrated in place. V2.6 adds and
backfills secure report tokens without changing existing client/project/job
relationships.

Backups automatically preserve the new report tokens and combined-report email
metadata because they are stored in the existing SQLite database.


## V2.7 — Help & Tutorials

DispatchProof now includes an in-app **Help & Tutorials** center for all signed-in office users.

### Help Center

The new page includes searchable step-by-step walkthroughs for:

- Getting Started
- Create a Job
- Job Status
- Readiness Requests
- Installer Arrival
- Failed Mobilization
- Complete a Job
- Job Activity
- Email Outbox
- Clients & Projects
- Assign Existing Jobs
- Create Jobs from Projects
- Single-Job Client Reports
- Secure Report Link Rotation
- Combined Client Reports
- Combined Project Reports
- Combined Report Link Rotation
- My Account / Password Changes

### Administrator-only tutorials

Owner and Administrator accounts additionally see help for:

- Users & Access
- Company Settings
- Global Activity Log
- Downloading Backups
- Restoring After a Render Reset

Operations users do not see tutorials for areas they cannot access.

### Search

The Help Center includes a local in-page search. Typing terms such as
`arrival`, `report`, `backup`, `client`, or `password` filters the tutorial cards
immediately without a server request.

### Quick workflow map

A Start Here panel provides the basic DispatchProof lifecycle:

**Create Job → Readiness → Arrival → Complete → Report**


## V2.8 — Internal Job Notes

V2.8 adds an internal office communication timeline to every installation job.

### Office Notes

Every Job Detail page now includes **Office Notes**.

Signed-in Operations, Administrator, and Owner users can add a private note for:

- client or GC phone-call updates
- scheduling changes
- material / access coordination
- internal follow-up reminders
- field or office context that should not be client-facing

Each note is permanently stamped with:

- signed-in user's display name
- signed-in user's role
- date and time
- note text

### Privacy

Internal Job Notes are intentionally separate from the public Job Activity trail.

They are **not included** in:

- single-job client reports
- combined client reports
- combined project reports
- readiness links
- installer arrival links
- any public evidence route

### Backup & Restore

Job notes live in the DispatchProof SQLite database, so they are included automatically in normal Backup & Restore ZIPs.

The Backup & Restore page now displays an **Internal Job Notes** record count.

Restoring a V2.7.1-or-earlier backup into V2.8 automatically creates the new notes table without changing existing jobs, users, reports, or evidence.

### Help Center

Help & Tutorials now includes **Add an Internal Job Note** under Everyday Workflows.


## V2.9 — Dashboard Search & Filters

V2.9 makes the active-installation Dashboard easier to use as job volume grows.

### Search

The Dashboard can now search active jobs by:

- Job Name
- Project / Site
- Site Contact Name
- Site Contact Email
- Client Name
- Project Name
- Project Number

Search is case-insensitive.

### Filters

Active jobs can be narrowed by:

- Client
- Project
- Status

Client and Project filters work together. When a Client is selected, the Project dropdown only shows projects belonging to that client.

The existing status summary tiles remain usable and now preserve the current Search / Client / Project filters.

### Active filter summary

When any filter is active, DispatchProof shows how many active jobs match and provides a **Clear All** control.

### No database migration

V2.9 changes only Dashboard querying and presentation. It does not add or change database tables, so restoring the latest V2.8 backup remains compatible.

### Help Center

Help & Tutorials now includes **Find a Job on the Dashboard** under Getting Started.


## V2.10 — Duplicate Job

V2.10 adds a fast way to create repeat installations without retyping the same setup.

### Duplicate Job

Every Job Detail page now has a **Duplicate Job** button.

The duplicate form copies:

- Client
- Project
- Job Name
- Project / Site
- Site Contact Name
- Site Contact Email
- Site Contact Phone
- Readiness Checklist
- Automatic Reminder setting
- Reminder window

The Installation Date is intentionally left blank so the office must choose the date for the new install.

### Fresh lifecycle

A duplicated job is always a brand-new installation with new secure tokens and **NO RESPONSE** status.

DispatchProof does **not** copy:

- readiness responses
- readiness photos
- arrival records
- failed mobilization details
- arrival photos
- client report links
- combined-report history
- activity history
- Office Notes

This prevents old evidence or private communication from being accidentally attached to a new installation.

### Audit trail

The new job receives its normal **Job Created** activity plus a **Job Duplicated** activity that identifies the source job without copying its history.

### No database migration

V2.10 does not change the database schema, so the latest V2.9 backup remains compatible.

### Help Center

Help & Tutorials now includes **Duplicate a Job** under Getting Started.


## V2.11 — Edit Job Details

V2.11 adds a safe way to correct or reschedule an active installation without rebuilding the job.

### Editable fields

From Job Detail, click **Edit Job Details** to change:

- Job Name
- Project / Site
- Installation Date
- Site Contact Name
- Site Contact Email
- Site Contact Phone
- Automatic Reminder enabled/disabled
- Reminder Window (24 / 48 / 72 hours)

### Preserved job records

Editing Job Details does **not** change:

- Client / Project assignment
- readiness checklist
- readiness response
- readiness photos
- arrival / failed mobilization records
- evidence
- client report links
- combined reports
- Office Notes
- existing Job Activity

Completed jobs remain locked.

### Audit trail

When any editable value changes, DispatchProof writes a **Job Details Updated** event to that job's audit trail.

The event records each changed field as:

`Old Value → New Value`

If the form is saved without changing anything, no update event is created.

### No database migration

V2.11 does not add or change database tables. The latest V2.10 backup is fully compatible.

### Help Center

Help & Tutorials now includes **Edit Job Details** under Getting Started.


## V2.12 — Completed Jobs Search & Filters

V2.12 gives completed installation history the same find-fast behavior as the active Dashboard.

### Search completed history

Completed Jobs can now be searched by Job Name, Project / Site, Site Contact Name or Email, Client Name, Project Name, and Project Number.

### Client and Project filters

Completed history can be narrowed by Client and Project. When a Client is selected, the Project dropdown only shows projects belonging to that client.

### Result count and organization context

When filters are active, DispatchProof shows the number of matching completed jobs compared with the full history. Completed-job rows now also show Client / Project under the Job Name when assigned.

### No database migration

V2.12 does not change the database schema. The latest V2.11 backup remains fully compatible.

### Help Center

Help & Tutorials now includes **Find a Completed Job** under Everyday Workflows.


## V2.13 — Reopen Completed Job

V2.13 adds a safe recovery path when an installation is marked complete by mistake.

### Reopen Job

Owner and Administrator accounts can open a completed installation and click **Reopen Job**.

Reopening changes only:

- Status: `COMPLETED` → `ON SITE`
- Completed timestamp: cleared

The job immediately returns to the active Dashboard.

### Preserved records

Reopening does **not** change or delete:

- readiness response
- readiness photos
- installer arrival record
- arrival evidence
- failed mobilization history
- client report token/link
- combined reports
- Office Notes
- prior Job Activity

The installer link that was revoked at completion is **not restored**. Since the successful arrival record is already locked, the reopened job simply returns to the ON SITE operational state.

### Permissions

Reopening is restricted to:

- Owner
- Administrator

Operations users can view completed jobs but cannot reopen them.

### Audit trail

Every reopen writes a **Job Reopened** event to Job Activity identifying the transition from COMPLETED back to ON SITE.

### No database migration

V2.13 does not change the database schema. The latest V2.12 backup remains fully compatible.

### Help Center

Owner/Administrator Help & Tutorials now includes **Reopen a Completed Job** under Admin Tools.


## V2.14 — Backup Reminder

V2.14 adds an in-app backup freshness reminder for Owner and Administrator accounts.

### Dashboard reminder

DispatchProof tracks the most recent backup checkpoint and shows:

- **No Dashboard warning** when the latest backup is under 3 days old
- **Backup recommended** when the latest backup is 3–6 days old
- **Backup overdue** when the latest backup is 7+ days old
- **No backup recorded** when no backup date is available

The banner includes **Back Up Now**, which opens Backup & Restore.

Operations users do not see backup reminders because Backup & Restore is an administrator-only area.

### Backup Status

Backup & Restore now displays:

- current backup status
- most recent backup date/time
- freshness message

### Tracking

Clicking **Download Backup ZIP** records the backup checkpoint before the ZIP is created. This means the backup file itself contains the checkpoint date and activity record.

### Restore-aware reminder

The backup manifest already records when the ZIP was created. V2.14 now uses that timestamp after a restore, so restoring a recent backup does not incorrectly show “No backup recorded.”

Older databases are migrated automatically. If an older database contains a previous **Backup Downloaded** Activity Log event, DispatchProof uses that as an initial last-backup date.

### Help Center

Help & Tutorials now includes **Respond to a Backup Reminder**.

### No destructive migration

V2.14 adds only one nullable settings field (`last_backup_at`) and migrates existing databases automatically.


## V2.14.1 — Eastern Time Display Fix

V2.14.1 corrects the timestamp display mismatch caused by Render using UTC.

### What changed

DispatchProof now converts stored timestamps to the configured display timezone before showing them in the UI.

The default timezone is:

`America/New_York`

This automatically handles:

- EST (UTC-5) during standard time
- EDT (UTC-4) during daylight saving time

### What it fixes

The shared `pretty_datetime` formatter is used throughout DispatchProof, so the correction applies to:

- Backup Status / Last Backup
- Job Activity
- Office Notes
- readiness timestamps
- arrival timestamps
- completed-job timestamps
- Email Outbox timestamps
- report view timestamps
- other formatted date/time displays

Stored database values are not rewritten, preserving backup compatibility and audit history.

### Optional future deployment setting

The display timezone can be changed later with:

`DISPATCHPROOF_TIMEZONE`

Example:

`America/Chicago`

No environment change is required for the current Eastern Time setup.


## V2.15 — Schedule Alerts & Date Filters

V2.15 makes installation dates operationally visible on the active Dashboard.

### Schedule buckets

Every active job is classified by Installation Date as **Overdue**, **Today**, **Next 7 Days**, or **Later**. Date classification uses the configured DispatchProof timezone (`America/New_York` by default).

### Quick schedule chips

The Dashboard shows live counts for the four schedule windows. Clicking a chip filters the active job list, and clicking the selected chip again clears that schedule filter.

### Combined filters

Schedule works together with Search, Client, Project, and Status. The same schedule choices are also available in the Search & Filter form.

### Job list alerts

Jobs that are Overdue, Today, or Next 7 Days show a small schedule label under the Installation Date. These alerts do not change job status or workflow.

### No database migration

V2.15 does not change the database schema. The latest V2.14.1 backup remains compatible.

### Help Center

Help & Tutorials now includes **Use Schedule Alerts**.


## V2.15.1 — Dashboard Width Fix

V2.15.1 fixes horizontal page overflow introduced by the expanded V2.15 Dashboard filters.

### What changed

- Dashboard filters wrap earlier instead of forcing one oversized row.
- Schedule chips remain inside the available content width.
- Grid and panel children are allowed to shrink correctly.
- Long table content wraps or scrolls inside the table container rather than widening the entire page.
- Mobile/tablet breakpoints remain responsive.

No workflow, database, search, status, or schedule logic changed.


## V2.16 — CSV Export

V2.16 adds spreadsheet-friendly exports for both active and completed installations.

### Active Dashboard export

Click **Export CSV** from Dashboard to export the current active-job view.

The export respects the current:

- Search
- Client
- Project
- Schedule
- Status

Active CSV columns include job/client/project details, attempt, installation date, schedule bucket, status, contact information, readiness response time, arrival status, and arrival time.

### Completed Jobs export

Click **Export CSV** from Completed Jobs to export the current completed-history view.

The export respects the current:

- Search
- Client
- Project

Completed CSV columns include job/client/project details, attempt, installation date, completion time, contact information, readiness response time, arrival status, and arrival time.

### Spreadsheet compatibility

CSV downloads include a UTF-8 BOM for reliable opening in Microsoft Excel and support standard spreadsheet applications such as Google Sheets.

Displayed timestamps use the configured DispatchProof timezone.

### Permissions

Exports are available to signed-in Owner, Administrator, and Operations users because they contain the same operational job data those users can already view.

### No database migration

V2.16 does not change the database schema. V2.15.1 backups remain compatible.

### Help Center

Help & Tutorials now includes **Export Jobs to CSV**.


## V2.17 — Action Button UI Polish

V2.17 improves visual consistency so important clickable actions are easier to notice.

### Solid-blue action buttons

Important actions now use the same solid-blue treatment as DispatchProof's primary workflow buttons, including examples such as:

- Export CSV
- Edit Job Details
- Duplicate Job
- Combined Client / Project Report
- Save Client / Project Details
- Preview / Open reports
- Copy / Open secure links
- readiness and arrival actions
- Edit User / Set Password
- Create Project
- Print / Save PDF

### Controls that intentionally remain neutral

Outlined/white controls are reserved for actions that should visually step back, such as:

- Cancel
- Clear All
- Back / return navigation
- Completed Jobs navigation

### Destructive actions

Dangerous or revocation-style actions keep their existing red treatment.

### No workflow or database changes

V2.17 is a visual polish release only. No database migration is required and V2.16 backups remain compatible.

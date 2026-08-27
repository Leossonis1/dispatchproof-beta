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

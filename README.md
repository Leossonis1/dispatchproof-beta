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

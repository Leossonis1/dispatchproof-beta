
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, abort, session
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from pathlib import Path
import sqlite3
import json
import secrets
import os
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent

# Local runs default to the project folder.
# On Render's free beta tier we use /tmp, which is intentionally disposable.
# For a paid Render persistent disk later, set:
#   DISPATCHPROOF_DATA_DIR=/var/data/dispatchproof
_configured_data_dir = os.getenv("DISPATCHPROOF_DATA_DIR", "").strip()
if _configured_data_dir:
    DATA_DIR = Path(_configured_data_dir)
elif os.getenv("RENDER", "").lower() == "true":
    DATA_DIR = Path("/tmp/dispatchproof")
else:
    DATA_DIR = BASE_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "dispatchproof.db"
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

PUBLIC_BASE_URL = os.getenv("DISPATCHPROOF_PUBLIC_BASE_URL", "").strip().rstrip("/")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

# V1.4 company placeholders. Later these become company settings.
COMPANY_NAME = os.getenv("DISPATCHPROOF_COMPANY_NAME", "Your Company")
COMPANY_LOGO_URL = None

# Generic SMTP configuration.
# Example Gmail values:
#   SMTP_HOST=smtp.gmail.com
#   SMTP_PORT=587
#   SMTP_USERNAME=you@gmail.com
#   SMTP_PASSWORD=<Google App Password>
#   SMTP_FROM_EMAIL=you@gmail.com
#   SMTP_USE_TLS=true
SMTP_HOST = os.getenv("DISPATCHPROOF_SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("DISPATCHPROOF_SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("DISPATCHPROOF_SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("DISPATCHPROOF_SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("DISPATCHPROOF_SMTP_FROM_EMAIL", SMTP_USERNAME).strip()
SMTP_FROM_NAME = os.getenv("DISPATCHPROOF_SMTP_FROM_NAME", COMPANY_NAME).strip()
SMTP_USE_TLS = os.getenv("DISPATCHPROOF_SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}

# Email mode:
#   outbox = generate/log messages only; never attempt SMTP
#   smtp   = attempt real SMTP delivery
# Free Render beta defaults to outbox because outbound SMTP ports are unavailable.
EMAIL_MODE = os.getenv("DISPATCHPROOF_EMAIL_MODE", "outbox").strip().lower()
if EMAIL_MODE not in {"outbox", "smtp"}:
    EMAIL_MODE = "outbox"

# Single-admin beta login.
# Username defaults to "admin". On Render, DISPATCHPROOF_ADMIN_PASSWORD must
# be set as a private environment variable before the internal app can be used.
ADMIN_USERNAME = os.getenv("DISPATCHPROOF_ADMIN_USERNAME", "admin").strip() or "admin"
ADMIN_PASSWORD = os.getenv("DISPATCHPROOF_ADMIN_PASSWORD", "")

# Reminder defaults for new jobs.
DEFAULT_REMINDER_ENABLED = True
DEFAULT_REMINDER_HOURS_BEFORE = 48

# Local beta reminder sweep. While the Flask app is running and receiving
# requests, DispatchProof checks for due reminders at most once every 5 minutes.
REMINDER_SWEEP_INTERVAL_SECONDS = 300
LAST_REMINDER_SWEEP_AT = None

app = Flask(__name__)

# Render terminates HTTPS at its proxy. ProxyFix lets Flask generate correct
# external HTTPS URLs when it needs to use request headers.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.secret_key = os.getenv("DISPATCHPROOF_SECRET_KEY", "dev-change-me-before-production")
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("RENDER", "").lower() == "true"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)

DEFAULT_CHECKLIST = [
    "Finished flooring installed",
    "Walls complete and painted",
    "Electrical rough-in complete and inspected",
    "Ceiling work complete",
    "Installation areas cleared of debris and materials",
    "Material delivery path accessible",
    "Power available in installation areas",
]

ARRIVAL_ISSUES = [
    "Area inaccessible",
    "Other trade incomplete",
    "Missing power",
    "Materials unavailable",
    "Site conditions differ from confirmation",
    "Other",
]

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.DatabaseError:
        pass
    return conn

def ensure_columns(db):
    existing = {row["name"] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
    needed = {
        "arrival_status": "TEXT",
        "arrived_at": "TEXT",
        "arrival_reported_by": "TEXT",
        "arrival_issues_json": "TEXT",
        "crew_size": "INTEGER",
        "hours_lost": "REAL",
        "equipment_affected": "TEXT",
        "arrival_notes": "TEXT",
        "arrival_photos_json": "TEXT",
        "failed_report_number": "TEXT",
        "failed_report_generated_at": "TEXT",
        "request_sent_at": "TEXT",
        "last_reminder_sent_at": "TEXT",
        "reminder_enabled": "INTEGER DEFAULT 1",
        "reminder_hours_before": "INTEGER DEFAULT 48",
        "reminder_count": "INTEGER DEFAULT 0",
    }
    for name, sql_type in needed.items():
        if name not in existing:
            db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {sql_type}")

    db.execute("""
        CREATE TABLE IF NOT EXISTS readiness_confirmations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            response_at TEXT,
            confirmed_by TEXT,
            confirmed_title TEXT,
            response_json TEXT,
            photo_json TEXT,
            status TEXT,
            archived_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS mobilization_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            attempt_number INTEGER NOT NULL,
            checklist_json TEXT NOT NULL,
            readiness_status TEXT,
            response_at TEXT,
            confirmed_by TEXT,
            confirmed_title TEXT,
            response_json TEXT,
            photo_json TEXT,
            arrival_status TEXT,
            arrived_at TEXT,
            arrival_reported_by TEXT,
            arrival_issues_json TEXT,
            crew_size INTEGER,
            hours_lost REAL,
            equipment_affected TEXT,
            arrival_notes TEXT,
            arrival_photos_json TEXT,
            failed_report_number TEXT,
            failed_report_generated_at TEXT,
            archived_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS app_migrations (
            migration_key TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            details TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS email_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            recipient_email TEXT NOT NULL,
            recipient_name TEXT,
            subject TEXT NOT NULL,
            body_html TEXT NOT NULL,
            public_url TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
    """)

    # Backfill reminder defaults for jobs upgraded from older builds.
    db.execute("""
        UPDATE jobs
        SET reminder_enabled = COALESCE(reminder_enabled, 1),
            reminder_hours_before = COALESCE(reminder_hours_before, 48),
            reminder_count = COALESCE(reminder_count, 0)
    """)
    db.commit()

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_token TEXT UNIQUE NOT NULL,
            job_name TEXT NOT NULL,
            project_site TEXT,
            installation_date TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            contact_email TEXT NOT NULL,
            contact_phone TEXT,
            checklist_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'NO RESPONSE',
            created_at TEXT NOT NULL,
            response_at TEXT,
            confirmed_by TEXT,
            confirmed_title TEXT,
            response_json TEXT,
            photo_json TEXT,
            arrival_status TEXT,
            arrived_at TEXT,
            arrival_reported_by TEXT,
            arrival_issues_json TEXT,
            crew_size INTEGER,
            hours_lost REAL,
            equipment_affected TEXT,
            arrival_notes TEXT,
            arrival_photos_json TEXT,
            failed_report_number TEXT,
            failed_report_generated_at TEXT,
            request_sent_at TEXT,
            last_reminder_sent_at TEXT,
            reminder_enabled INTEGER DEFAULT 1,
            reminder_hours_before INTEGER DEFAULT 48,
            reminder_count INTEGER DEFAULT 0
        );
        """)
        ensure_columns(db)
        recover_v130_orphaned_mobilizations(db)

def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()

def pretty_number(value):
    if value is None or value == "":
        return "—"
    try:
        f = float(value)
        if f.is_integer():
            return str(int(f))
        return f"{f:g}"
    except Exception:
        return str(value)

def format_date(value):
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value)
    except Exception:
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
        except Exception:
            return value
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}"

def format_datetime(value):
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value)
        hour = dt.strftime("%I").lstrip("0") or "0"
        return f"{dt.strftime('%b')} {dt.day}, {dt.year} at {hour}:{dt.strftime('%M %p')}"
    except Exception:
        return value

app.jinja_env.filters["pretty_date"] = format_date
app.jinja_env.filters["pretty_datetime"] = format_datetime
app.jinja_env.filters["pretty_number"] = pretty_number

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_photos(files, prefix):
    saved = []
    for photo in files:
        if photo and photo.filename and allowed_file(photo.filename):
            safe = secure_filename(photo.filename)
            filename = f"{prefix}_{secrets.token_hex(4)}_{safe}"
            photo.save(UPLOAD_DIR / filename)
            saved.append(filename)
    return saved

def calculate_status(answers, photos):
    values = list(answers.values())
    if any(v == "no" for v in values):
        return "BLOCKED"
    if values and all(v == "yes" for v in values) and len(photos) >= 2:
        return "READY"
    return "REVIEW"

def archive_current_confirmation(db, job):
    if not job["response_at"]:
        return
    db.execute("""
        INSERT INTO readiness_confirmations (
            job_id, response_at, confirmed_by, confirmed_title,
            response_json, photo_json, status, archived_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job["id"],
        job["response_at"],
        job["confirmed_by"],
        job["confirmed_title"],
        job["response_json"],
        job["photo_json"],
        job["status"],
        now_iso(),
    ))

def archive_current_mobilization(db, job):
    count = db.execute(
        "SELECT COUNT(*) AS c FROM mobilization_attempts WHERE job_id = ?",
        (job["id"],)
    ).fetchone()["c"]
    attempt_number = count + 1

    db.execute("""
        INSERT INTO mobilization_attempts (
            job_id, attempt_number, checklist_json, readiness_status,
            response_at, confirmed_by, confirmed_title, response_json, photo_json,
            arrival_status, arrived_at, arrival_reported_by, arrival_issues_json,
            crew_size, hours_lost, equipment_affected, arrival_notes,
            arrival_photos_json, failed_report_number, failed_report_generated_at,
            archived_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job["id"],
        attempt_number,
        job["checklist_json"],
        job["status"],
        job["response_at"],
        job["confirmed_by"],
        job["confirmed_title"],
        job["response_json"],
        job["photo_json"],
        job["arrival_status"],
        job["arrived_at"],
        job["arrival_reported_by"],
        job["arrival_issues_json"],
        job["crew_size"],
        job["hours_lost"],
        job["equipment_affected"],
        job["arrival_notes"],
        job["arrival_photos_json"],
        job["failed_report_number"],
        job["failed_report_generated_at"],
        now_iso(),
    ))
    return attempt_number

def recover_v130_orphaned_mobilizations(db):
    migration_key = "v1.3.2_recover_orphaned_arrivals"

    candidates = db.execute("""
        SELECT *
        FROM jobs
        WHERE arrival_status IS NOT NULL
          AND response_at IS NULL
    """).fetchall()

    recovered = 0

    for job in candidates:
        existing = db.execute("""
            SELECT id
            FROM mobilization_attempts
            WHERE job_id = ?
              AND arrived_at = ?
            LIMIT 1
        """, (job["id"], job["arrived_at"])).fetchone()

        if existing:
            db.execute("""
                UPDATE jobs
                SET arrival_status=NULL,
                    arrived_at=NULL,
                    arrival_reported_by=NULL,
                    arrival_issues_json=NULL,
                    crew_size=NULL,
                    hours_lost=NULL,
                    equipment_affected=NULL,
                    arrival_notes=NULL,
                    arrival_photos_json=NULL,
                    failed_report_number=NULL,
                    failed_report_generated_at=NULL,
                    status='NO RESPONSE'
                WHERE id=?
            """, (job["id"],))
            continue

        archived = db.execute("""
            SELECT *
            FROM readiness_confirmations
            WHERE job_id = ?
            ORDER BY id DESC
            LIMIT 1
        """, (job["id"],)).fetchone()

        if not archived:
            continue

        answers = json.loads(archived["response_json"]) if archived["response_json"] else {}
        photos = json.loads(archived["photo_json"]) if archived["photo_json"] else []
        readiness_status = calculate_status(answers, photos) if answers else (archived["status"] or "REVIEW")

        count = db.execute(
            "SELECT COUNT(*) AS c FROM mobilization_attempts WHERE job_id = ?",
            (job["id"],)
        ).fetchone()["c"]
        attempt_number = count + 1

        db.execute("""
            INSERT INTO mobilization_attempts (
                job_id, attempt_number, checklist_json, readiness_status,
                response_at, confirmed_by, confirmed_title, response_json, photo_json,
                arrival_status, arrived_at, arrival_reported_by, arrival_issues_json,
                crew_size, hours_lost, equipment_affected, arrival_notes,
                arrival_photos_json, failed_report_number, failed_report_generated_at,
                archived_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job["id"],
            attempt_number,
            job["checklist_json"],
            readiness_status,
            archived["response_at"],
            archived["confirmed_by"],
            archived["confirmed_title"],
            archived["response_json"],
            archived["photo_json"],
            job["arrival_status"],
            job["arrived_at"],
            job["arrival_reported_by"],
            job["arrival_issues_json"],
            job["crew_size"],
            job["hours_lost"],
            job["equipment_affected"],
            job["arrival_notes"],
            job["arrival_photos_json"],
            job["failed_report_number"],
            job["failed_report_generated_at"],
            now_iso(),
        ))

        db.execute("DELETE FROM readiness_confirmations WHERE id = ?", (archived["id"],))

        db.execute("""
            UPDATE jobs
            SET status='NO RESPONSE',
                response_at=NULL,
                confirmed_by=NULL,
                confirmed_title=NULL,
                response_json=NULL,
                photo_json=NULL,
                arrival_status=NULL,
                arrived_at=NULL,
                arrival_reported_by=NULL,
                arrival_issues_json=NULL,
                crew_size=NULL,
                hours_lost=NULL,
                equipment_affected=NULL,
                arrival_notes=NULL,
                arrival_photos_json=NULL,
                failed_report_number=NULL,
                failed_report_generated_at=NULL
            WHERE id=?
        """, (job["id"],))

        recovered += 1

    db.execute("""
        INSERT OR REPLACE INTO app_migrations (migration_key, applied_at, details)
        VALUES (?, ?, ?)
    """, (
        migration_key,
        now_iso(),
        f"Recovered {recovered} orphaned mobilization attempt(s)."
    ))
    db.commit()

def make_report_number(job_id, timestamp):
    try:
        dt = datetime.fromisoformat(timestamp)
    except Exception:
        dt = datetime.now()
    return f"DP-FM-{job_id:05d}-{dt.strftime('%y%m%d')}"


def public_app_base_url():
    """Return the public base URL when hosted, otherwise fall back to Flask."""
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    if RENDER_EXTERNAL_URL:
        return RENDER_EXTERNAL_URL
    return ""

def public_readiness_url(job):
    base = public_app_base_url()
    if base:
        return f"{base}/r/{job['public_token']}"
    return url_for("public_readiness", token=job["public_token"], _external=True)

def smtp_is_configured():
    return bool(SMTP_HOST and SMTP_PORT and SMTP_FROM_EMAIL)

def email_delivery_enabled():
    return EMAIL_MODE == "smtp" and smtp_is_configured()

def build_readiness_email(job, public_url, reminder=False):
    action_word = "Reminder" if reminder else "Site Readiness Confirmation"
    subject = f"{action_word}: {job['job_name']}"

    intro = (
        "This is a reminder that a site-readiness confirmation is still needed."
        if reminder else
        "Please confirm the site is ready for the scheduled installation."
    )

    html = f"""
    <html>
      <body style="font-family:Arial,sans-serif;background:#f5f7fb;padding:28px;color:#152033;">
        <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #dfe5ee;border-radius:14px;padding:28px;">
          <div style="font-size:22px;font-weight:800;color:#0b2348;margin-bottom:4px;">{COMPANY_NAME}</div>
          <div style="font-size:12px;color:#6b7280;margin-bottom:24px;">Powered by DispatchProof</div>

          <h2 style="margin:0 0 8px;font-size:24px;">{job['job_name']}</h2>
          <p style="margin:0 0 18px;color:#6b7280;">{job['project_site'] or ''}</p>

          <div style="background:#eef4ff;border:1px solid #cadcff;border-radius:10px;padding:14px;margin-bottom:20px;">
            <strong>{intro}</strong>
            <div style="margin-top:5px;color:#475467;">Scheduled installation: {format_date(job['installation_date'])}</div>
          </div>

          <p style="line-height:1.55;">
            Please review the readiness checklist, answer the site-condition questions, and upload the required photos.
            No account or password is required.
          </p>

          <div style="margin:26px 0;">
            <a href="{public_url}" style="display:inline-block;background:#0f62fe;color:white;text-decoration:none;font-weight:700;padding:13px 18px;border-radius:9px;">
              Confirm Site Readiness
            </a>
          </div>

          <p style="font-size:12px;color:#6b7280;line-height:1.5;">
            This confirmation helps prevent unnecessary mobilization, delays, and return trips.
          </p>
        </div>
      </body>
    </html>
    """
    return subject, html

def send_smtp_message(recipient_email, recipient_name, subject, html_body):
    if EMAIL_MODE != "smtp":
        return False, "Free beta Outbox Mode is enabled. Message generated locally and not delivered."

    if not smtp_is_configured():
        return False, "SMTP mode is enabled, but SMTP is not fully configured."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    msg["To"] = f"{recipient_name} <{recipient_email}>" if recipient_name else recipient_email
    msg.set_content("Please open this message in an HTML-capable email client.")
    msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USERNAME:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        return True, None
    except Exception as exc:
        return False, str(exc)

def log_email_event(db, job_id, event_type, recipient_email, recipient_name,
                    subject, body_html, public_url, status, error_message=None):
    db.execute("""
        INSERT INTO email_events (
            job_id, event_type, recipient_email, recipient_name,
            subject, body_html, public_url, status, error_message, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_id,
        event_type,
        recipient_email,
        recipient_name,
        subject,
        body_html,
        public_url,
        status,
        error_message,
        now_iso(),
    ))

def send_readiness_email_for_job(job, public_url, reminder=False):
    subject, html = build_readiness_email(job, public_url, reminder=reminder)
    sent, error = send_smtp_message(
        job["contact_email"],
        job["contact_name"],
        subject,
        html
    )

    event_type = "REMINDER" if reminder else "READINESS_REQUEST"
    if sent:
        status = "SENT"
    elif EMAIL_MODE == "outbox":
        status = "OUTBOX"
    else:
        status = "FAILED"

    with get_db() as db:
        log_email_event(
            db,
            job["id"],
            event_type,
            job["contact_email"],
            job["contact_name"],
            subject,
            html,
            public_url,
            status,
            error
        )

        if sent:
            if reminder:
                db.execute("""
                    UPDATE jobs
                    SET last_reminder_sent_at = ?,
                        reminder_count = COALESCE(reminder_count, 0) + 1
                    WHERE id = ?
                """, (now_iso(), job["id"]))
            else:
                db.execute("""
                    UPDATE jobs
                    SET request_sent_at = ?
                    WHERE id = ?
                """, (now_iso(), job["id"]))

        db.commit()

    return status, error


def latest_request_event(job_id):
    with get_db() as db:
        return db.execute("""
            SELECT *
            FROM email_events
            WHERE job_id = ?
              AND event_type = 'READINESS_REQUEST'
            ORDER BY id DESC
            LIMIT 1
        """, (job_id,)).fetchone()

def reminder_due(job):
    if not email_delivery_enabled():
        return False
    if not job["reminder_enabled"]:
        return False
    if job["status"] != "NO RESPONSE":
        return False
    if not job["request_sent_at"]:
        return False

    try:
        install_date = datetime.strptime(job["installation_date"], "%Y-%m-%d")
    except Exception:
        return False

    due_at = install_date - timedelta(hours=int(job["reminder_hours_before"] or 48))
    now = datetime.now()

    if now < due_at:
        return False

    # One automatic reminder per mobilization attempt for V1.4.
    return not bool(job["last_reminder_sent_at"])

def run_due_reminders():
    with get_db() as db:
        jobs = db.execute("""
            SELECT *
            FROM jobs
            WHERE status = 'NO RESPONSE'
              AND reminder_enabled = 1
              AND request_sent_at IS NOT NULL
        """).fetchall()

    sent_count = 0
    outbox_count = 0
    failed_count = 0

    for job in jobs:
        if not reminder_due(job):
            continue

        public_url = public_readiness_url(job)
        status, _ = send_readiness_email_for_job(job, public_url, reminder=True)

        if status == "SENT":
            sent_count += 1
        elif status == "OUTBOX":
            outbox_count += 1
        else:
            failed_count += 1

    return sent_count, outbox_count, failed_count


def admin_login_configured():
    # Local development gets an explicit dev fallback only when NOT on Render.
    if ADMIN_PASSWORD:
        return True
    return os.getenv("RENDER", "").lower() != "true"

def effective_admin_password():
    if ADMIN_PASSWORD:
        return ADMIN_PASSWORD
    # Local-only fallback for development. Never active on Render.
    return "dispatchproof-local"

def admin_authenticated():
    return bool(session.get("dispatchproof_admin"))

def safe_next_url(value):
    if not value:
        return url_for("dashboard")
    # Only allow local absolute paths, never //host or full external URLs.
    if value.startswith("/") and not value.startswith("//"):
        return value
    return url_for("dashboard")

@app.context_processor
def inject_brand():
    return {
        "company_name": COMPANY_NAME,
        "company_logo_url": COMPANY_LOGO_URL,
        "app_version": "1.6",
        "smtp_configured": smtp_is_configured(),
        "email_mode": EMAIL_MODE,
        "email_delivery_enabled": email_delivery_enabled(),
        "admin_authenticated": admin_authenticated(),
        "admin_username": ADMIN_USERNAME,
    }

@app.before_request
def ensure_db():
    global LAST_REMINDER_SWEEP_AT
    init_db()

    public_endpoints = {"login", "health", "static", "public_readiness"}
    if request.endpoint not in public_endpoints and not admin_authenticated():
        return redirect(url_for("login", next=request.full_path if request.query_string else request.path))

    # Do not make static/public requests responsible for sending reminders.
    if request.endpoint in {"static", "health", "public_readiness"}:
        return

    now = datetime.now()
    should_sweep = (
        LAST_REMINDER_SWEEP_AT is None
        or (now - LAST_REMINDER_SWEEP_AT).total_seconds() >= REMINDER_SWEEP_INTERVAL_SECONDS
    )

    if should_sweep:
        LAST_REMINDER_SWEEP_AT = now
        try:
            run_due_reminders()
        except Exception:
            # Reminder delivery must never take down the app.
            pass



@app.route("/login", methods=["GET", "POST"])
def login():
    if admin_authenticated():
        return redirect(safe_next_url(request.args.get("next")))

    configured = admin_login_configured()
    next_url = request.args.get("next") or request.form.get("next") or ""

    if request.method == "POST":
        if not configured:
            flash("Admin login is not configured yet. Add DISPATCHPROOF_ADMIN_PASSWORD in Render Environment.")
            return render_template("login.html", configured=False, next_url=next_url), 503

        submitted_username = request.form.get("username", "").strip()
        submitted_password = request.form.get("password", "")

        username_ok = secrets.compare_digest(submitted_username, ADMIN_USERNAME)
        password_ok = secrets.compare_digest(submitted_password, effective_admin_password())

        if username_ok and password_ok:
            session.clear()
            session.permanent = True
            session["dispatchproof_admin"] = True
            session["dispatchproof_admin_username"] = ADMIN_USERNAME
            return redirect(safe_next_url(next_url))

        flash("Incorrect username or password.")

    return render_template("login.html", configured=configured, next_url=next_url)

@app.post("/logout")
def logout():
    session.clear()
    flash("Signed out.")
    return redirect(url_for("login"))

@app.route("/health")
def health():
    return {
        "status": "ok",
        "version": "1.6",
        "data_dir": str(DATA_DIR),
        "email_mode": EMAIL_MODE,
        "smtp_configured": smtp_is_configured(),
        "email_delivery_enabled": email_delivery_enabled(),
    }, 200

@app.route("/")
def dashboard():
    status_filter = (request.args.get("status") or "").strip().upper()
    valid_statuses = {"READY", "REVIEW", "BLOCKED", "NO RESPONSE"}
    if status_filter not in valid_statuses:
        status_filter = ""

    with get_db() as db:
        all_jobs = db.execute("""
            SELECT
                j.*,
                (
                    SELECT COUNT(*)
                    FROM mobilization_attempts ma
                    WHERE ma.job_id = j.id
                ) + 1 AS attempt_number
            FROM jobs j
            ORDER BY installation_date ASC, id DESC
        """).fetchall()

    counts = {"READY": 0, "REVIEW": 0, "BLOCKED": 0, "NO RESPONSE": 0}
    for job in all_jobs:
        counts[job["status"]] = counts.get(job["status"], 0) + 1

    jobs = [j for j in all_jobs if not status_filter or j["status"] == status_filter]
    due_reminder_count = sum(1 for j in all_jobs if reminder_due(j))

    return render_template(
        "dashboard.html",
        jobs=jobs,
        counts=counts,
        status_filter=status_filter,
        due_reminder_count=due_reminder_count,
    )

@app.route("/jobs/new", methods=["GET", "POST"])
def new_job():
    if request.method == "POST":
        checklist = [x.strip() for x in request.form.getlist("checklist") if x.strip()]
        if not checklist:
            checklist = DEFAULT_CHECKLIST

        reminder_enabled = 1 if request.form.get("reminder_enabled") == "on" else 0
        reminder_hours_before = int(request.form.get("reminder_hours_before") or DEFAULT_REMINDER_HOURS_BEFORE)

        token = secrets.token_urlsafe(18)
        with get_db() as db:
            cur = db.execute("""
                INSERT INTO jobs (
                    public_token, job_name, project_site, installation_date,
                    contact_name, contact_email, contact_phone, checklist_json,
                    status, created_at, reminder_enabled, reminder_hours_before,
                    reminder_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NO RESPONSE', ?, ?, ?, 0)
            """, (
                token,
                request.form["job_name"].strip(),
                request.form.get("project_site", "").strip(),
                request.form["installation_date"],
                request.form["contact_name"].strip(),
                request.form["contact_email"].strip(),
                request.form.get("contact_phone", "").strip(),
                json.dumps(checklist),
                now_iso(),
                reminder_enabled,
                reminder_hours_before,
            ))
            job_id = cur.lastrowid
        return redirect(url_for("readiness_request", job_id=job_id))

    return render_template(
        "new_job.html",
        default_checklist=DEFAULT_CHECKLIST,
        default_reminder_enabled=DEFAULT_REMINDER_ENABLED,
        default_reminder_hours=DEFAULT_REMINDER_HOURS_BEFORE,
    )

@app.route("/jobs/<int:job_id>/request")
def readiness_request(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        email_events = db.execute("""
            SELECT *
            FROM email_events
            WHERE job_id = ?
            ORDER BY id DESC
            LIMIT 10
        """, (job_id,)).fetchall()

    if not job:
        abort(404)

    public_url = public_readiness_url(job)
    subject, email_preview_html = build_readiness_email(job, public_url, reminder=False)
    request_event = latest_request_event(job_id)

    return render_template(
        "readiness_request.html",
        job=job,
        public_url=public_url,
        email_events=email_events,
        email_preview_subject=subject,
        email_preview_html=email_preview_html,
        request_event=request_event,
    )

@app.post("/jobs/<int:job_id>/send-readiness-email")
def send_readiness_email(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        abort(404)

    public_url = public_readiness_url(job)
    status, error = send_readiness_email_for_job(job, public_url, reminder=False)

    if status == "SENT":
        flash(f"Readiness request emailed to {job['contact_email']}.")
    elif status == "OUTBOX":
        flash("Readiness email generated in Outbox Mode. Nothing was sent externally.")
    else:
        flash(f"Email delivery failed: {error}")

    return redirect(url_for("readiness_request", job_id=job_id))

@app.post("/jobs/<int:job_id>/send-reminder")
def send_reminder(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        abort(404)

    if job["status"] != "NO RESPONSE":
        flash("A reminder is only needed while the readiness request has no response.")
        return redirect(url_for("readiness_request", job_id=job_id))

    public_url = public_readiness_url(job)
    status, error = send_readiness_email_for_job(job, public_url, reminder=True)

    if status == "SENT":
        flash(f"Reminder emailed to {job['contact_email']}.")
    elif status == "OUTBOX":
        flash("Reminder generated in Outbox Mode. Nothing was sent externally.")
    else:
        flash(f"Reminder delivery failed: {error}")

    return redirect(url_for("readiness_request", job_id=job_id))

@app.post("/reminders/run")
def run_reminders_now():
    sent, outbox, failed = run_due_reminders()
    flash(f"Reminder check complete: {sent} sent, {outbox} saved to outbox, {failed} failed.")
    return redirect(url_for("dashboard"))

@app.route("/email-outbox")
def email_outbox():
    with get_db() as db:
        events = db.execute("""
            SELECT e.*, j.job_name
            FROM email_events e
            JOIN jobs j ON j.id = e.job_id
            ORDER BY e.id DESC
            LIMIT 100
        """).fetchall()

    return render_template("email_outbox.html", events=events)

@app.route("/email-outbox/<int:event_id>")
def email_outbox_detail(event_id):
    with get_db() as db:
        event = db.execute("""
            SELECT e.*, j.job_name, j.project_site
            FROM email_events e
            JOIN jobs j ON j.id = e.job_id
            WHERE e.id = ?
        """, (event_id,)).fetchone()

    if not event:
        abort(404)

    return render_template("email_outbox_detail.html", event=event)

@app.route("/r/<token>", methods=["GET", "POST"])
def public_readiness(token):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE public_token = ?", (token,)).fetchone()
    if not job:
        abort(404)

    checklist = json.loads(job["checklist_json"])

    if request.method == "POST":
        answers = {item: request.form.get(f"item_{idx}", "") for idx, item in enumerate(checklist)}
        files = request.files.getlist("photos")
        valid_uploads = [f for f in files if f and f.filename and allowed_file(f.filename)]

        if len(valid_uploads) < 2:
            flash("Please upload at least 2 site photos.")
            return render_template("public_readiness.html", job=job, checklist=checklist), 400

        photos = save_photos(valid_uploads, token[:8])
        status = calculate_status(answers, photos)

        with get_db() as db:
            latest = db.execute("SELECT * FROM jobs WHERE public_token = ?", (token,)).fetchone()
            if latest["response_at"]:
                archive_current_confirmation(db, latest)

            db.execute("""
                UPDATE jobs
                SET status = ?, response_at = ?, confirmed_by = ?,
                    confirmed_title = ?, response_json = ?, photo_json = ?
                WHERE public_token = ?
            """, (
                status,
                now_iso(),
                request.form.get("confirmed_by", "").strip(),
                request.form.get("confirmed_title", "").strip(),
                json.dumps(answers),
                json.dumps(photos),
                token,
            ))
            db.commit()

        return render_template("submitted.html", job=job, status=status)

    return render_template("public_readiness.html", job=job, checklist=checklist)

@app.route("/jobs/<int:job_id>")
def job_detail(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        history = db.execute("""
            SELECT * FROM readiness_confirmations
            WHERE job_id = ?
            ORDER BY id DESC
        """, (job_id,)).fetchall()
        attempts = db.execute("""
            SELECT * FROM mobilization_attempts
            WHERE job_id = ?
            ORDER BY attempt_number DESC
        """, (job_id,)).fetchall()

    if not job:
        abort(404)

    checklist = json.loads(job["checklist_json"])
    answers = json.loads(job["response_json"]) if job["response_json"] else {}
    photos = json.loads(job["photo_json"]) if job["photo_json"] else []
    arrival_issues = json.loads(job["arrival_issues_json"]) if job["arrival_issues_json"] else []
    arrival_photos = json.loads(job["arrival_photos_json"]) if job["arrival_photos_json"] else []

    history_items = []
    for row in history:
        history_items.append({
            "response_at": row["response_at"],
            "confirmed_by": row["confirmed_by"],
            "confirmed_title": row["confirmed_title"],
            "status": row["status"],
            "answers": json.loads(row["response_json"]) if row["response_json"] else {},
            "photos": json.loads(row["photo_json"]) if row["photo_json"] else [],
        })

    mobilization_history = []
    for row in attempts:
        mobilization_history.append({
            "id": row["id"],
            "attempt_number": row["attempt_number"],
            "readiness_status": row["readiness_status"],
            "response_at": row["response_at"],
            "confirmed_by": row["confirmed_by"],
            "confirmed_title": row["confirmed_title"],
            "answers": json.loads(row["response_json"]) if row["response_json"] else {},
            "photos": json.loads(row["photo_json"]) if row["photo_json"] else [],
            "arrival_status": row["arrival_status"],
            "arrived_at": row["arrived_at"],
            "arrival_reported_by": row["arrival_reported_by"],
            "arrival_issues": json.loads(row["arrival_issues_json"]) if row["arrival_issues_json"] else [],
            "crew_size": row["crew_size"],
            "hours_lost": row["hours_lost"],
            "equipment_affected": row["equipment_affected"],
            "arrival_notes": row["arrival_notes"],
            "arrival_photos": json.loads(row["arrival_photos_json"]) if row["arrival_photos_json"] else [],
            "failed_report_number": row["failed_report_number"],
        })

    current_attempt_number = len(mobilization_history) + 1

    return render_template(
        "job_detail.html",
        job=job,
        checklist=checklist,
        answers=answers,
        photos=photos,
        arrival_issues=arrival_issues,
        arrival_photos=arrival_photos,
        history_items=history_items,
        mobilization_history=mobilization_history,
        current_attempt_number=current_attempt_number,
    )

@app.route("/jobs/<int:job_id>/arrival", methods=["GET", "POST"])
def record_arrival(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        abort(404)

    if job["arrival_status"]:
        flash("This mobilization arrival is locked as evidence. Start a new confirmation for another mobilization attempt.")
        return redirect(url_for("job_detail", job_id=job_id))

    if job["status"] != "READY":
        flash("Site arrival cannot be recorded until the current readiness request is marked READY.")
        return redirect(url_for("job_detail", job_id=job_id))

    if request.method == "POST":
        arrival_status = request.form.get("arrival_status")
        reporter = request.form.get("arrival_reported_by", "").strip()

        if arrival_status not in {"READY", "NOT READY"}:
            flash("Choose whether the site was ready on arrival.")
            return redirect(url_for("record_arrival", job_id=job_id))

        issues = request.form.getlist("issues") if arrival_status == "NOT READY" else []
        crew_size = request.form.get("crew_size") or None
        hours_lost = request.form.get("hours_lost") or None
        equipment = request.form.get("equipment_affected", "").strip()
        notes = request.form.get("arrival_notes", "").strip()

        upload_files = request.files.getlist("arrival_photos")
        valid_uploads = [f for f in upload_files if f and f.filename and allowed_file(f.filename)]

        if arrival_status == "NOT READY":
            if not issues:
                flash("Select at least one reason the site was not ready.")
                return redirect(url_for("record_arrival", job_id=job_id))
            if len(valid_uploads) < 2:
                flash("Please upload at least 2 arrival photos for a failed mobilization.")
                return redirect(url_for("record_arrival", job_id=job_id))

        photos = save_photos(valid_uploads, f"arrival_{job_id}")
        arrival_time = now_iso()

        new_status = job["status"]
        report_number = job["failed_report_number"]
        report_generated_at = job["failed_report_generated_at"]

        if arrival_status == "NOT READY":
            new_status = "BLOCKED"
            if not report_number:
                report_number = make_report_number(job_id, arrival_time)
            if not report_generated_at:
                report_generated_at = arrival_time
        elif arrival_status == "READY" and job["status"] != "BLOCKED":
            new_status = "READY"

        with get_db() as db:
            db.execute("""
                UPDATE jobs
                SET arrival_status = ?, arrived_at = ?, arrival_reported_by = ?,
                    arrival_issues_json = ?, crew_size = ?, hours_lost = ?,
                    equipment_affected = ?, arrival_notes = ?,
                    arrival_photos_json = ?, status = ?,
                    failed_report_number = ?, failed_report_generated_at = ?
                WHERE id = ?
            """, (
                arrival_status,
                arrival_time,
                reporter,
                json.dumps(issues),
                int(crew_size) if crew_size else None,
                float(hours_lost) if hours_lost else None,
                equipment,
                notes,
                json.dumps(photos),
                new_status,
                report_number,
                report_generated_at,
                job_id,
            ))
            db.commit()

        if arrival_status == "NOT READY":
            return redirect(url_for("failed_mobilization_report", job_id=job_id))

        flash("Site arrival recorded as ready.")
        return redirect(url_for("job_detail", job_id=job_id))

    return render_template("arrival.html", job=job, issues=ARRIVAL_ISSUES)

@app.route("/jobs/<int:job_id>/failed-mobilization-report")
def failed_mobilization_report(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        abort(404)
    if job["arrival_status"] != "NOT READY":
        flash("A failed mobilization report is available only after recording the site as not ready.")
        return redirect(url_for("job_detail", job_id=job_id))

    checklist = json.loads(job["checklist_json"])
    answers = json.loads(job["response_json"]) if job["response_json"] else {}
    pre_photos = json.loads(job["photo_json"]) if job["photo_json"] else []
    arrival_issues = json.loads(job["arrival_issues_json"]) if job["arrival_issues_json"] else []
    arrival_photos = json.loads(job["arrival_photos_json"]) if job["arrival_photos_json"] else []

    man_hours = None
    if job["crew_size"] is not None and job["hours_lost"] is not None:
        man_hours = job["crew_size"] * job["hours_lost"]

    return render_template(
        "failed_mobilization_report.html",
        job=job,
        checklist=checklist,
        answers=answers,
        pre_photos=pre_photos,
        arrival_issues=arrival_issues,
        arrival_photos=arrival_photos,
        man_hours=man_hours,
    )

@app.route("/jobs/<int:job_id>/attempts/<int:attempt_id>/failed-mobilization-report")
def archived_failed_mobilization_report(job_id, attempt_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        attempt = db.execute("""
            SELECT * FROM mobilization_attempts
            WHERE id = ? AND job_id = ?
        """, (attempt_id, job_id)).fetchone()

    if not job or not attempt:
        abort(404)
    if attempt["arrival_status"] != "NOT READY":
        flash("This archived mobilization did not have a failed-mobilization report.")
        return redirect(url_for("job_detail", job_id=job_id))

    checklist = json.loads(attempt["checklist_json"])
    answers = json.loads(attempt["response_json"]) if attempt["response_json"] else {}
    pre_photos = json.loads(attempt["photo_json"]) if attempt["photo_json"] else []
    arrival_issues = json.loads(attempt["arrival_issues_json"]) if attempt["arrival_issues_json"] else []
    arrival_photos = json.loads(attempt["arrival_photos_json"]) if attempt["arrival_photos_json"] else []

    man_hours = None
    if attempt["crew_size"] is not None and attempt["hours_lost"] is not None:
        man_hours = attempt["crew_size"] * attempt["hours_lost"]

    report_job = dict(job)
    report_job.update({
        "status": attempt["readiness_status"],
        "response_at": attempt["response_at"],
        "confirmed_by": attempt["confirmed_by"],
        "confirmed_title": attempt["confirmed_title"],
        "arrival_status": attempt["arrival_status"],
        "arrived_at": attempt["arrived_at"],
        "arrival_reported_by": attempt["arrival_reported_by"],
        "crew_size": attempt["crew_size"],
        "hours_lost": attempt["hours_lost"],
        "equipment_affected": attempt["equipment_affected"],
        "arrival_notes": attempt["arrival_notes"],
        "failed_report_number": attempt["failed_report_number"],
        "failed_report_generated_at": attempt["failed_report_generated_at"],
    })

    return render_template(
        "failed_mobilization_report.html",
        job=report_job,
        checklist=checklist,
        answers=answers,
        pre_photos=pre_photos,
        arrival_issues=arrival_issues,
        arrival_photos=arrival_photos,
        man_hours=man_hours,
        archived_attempt_number=attempt["attempt_number"],
    )

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.post("/jobs/<int:job_id>/reset")
def reset_job(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            abort(404)

        if job["arrival_status"]:
            attempt_number = archive_current_mobilization(db, job)
            message = f"Mobilization Attempt #{attempt_number} was archived. A new readiness confirmation can now be collected."
        elif job["response_at"]:
            archive_current_confirmation(db, job)
            message = "The previous confirmation was archived. A new readiness confirmation can now be collected."
        else:
            message = "A new readiness confirmation can now be collected."

        db.execute("""
            UPDATE jobs
            SET status='NO RESPONSE',
                response_at=NULL,
                confirmed_by=NULL,
                confirmed_title=NULL,
                response_json=NULL,
                photo_json=NULL,
                arrival_status=NULL,
                arrived_at=NULL,
                arrival_reported_by=NULL,
                arrival_issues_json=NULL,
                crew_size=NULL,
                hours_lost=NULL,
                equipment_affected=NULL,
                arrival_notes=NULL,
                arrival_photos_json=NULL,
                failed_report_number=NULL,
                failed_report_generated_at=NULL,
                request_sent_at=NULL,
                last_reminder_sent_at=NULL,
                reminder_count=0
            WHERE id=?
        """, (job_id,))
        db.commit()

    flash(message)
    return redirect(url_for("readiness_request", job_id=job_id))

if __name__ == "__main__":
    init_db()
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("RENDER", "").lower() != "true",
    )


from flask import Flask, render_template, request, redirect, url_for, send_from_directory, send_file, flash, abort, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from pathlib import Path
import sqlite3
import json
import secrets
import os
import smtplib
import shutil
import tempfile
import zipfile
import re
import html as html_lib
from email.message import EmailMessage
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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

# Display timestamps in the company's local timezone while preserving the
# existing UTC-like stored ISO values used by Render.
DISPLAY_TIMEZONE_NAME = os.getenv(
    "DISPATCHPROOF_TIMEZONE", "America/New_York"
).strip() or "America/New_York"
try:
    DISPLAY_TIMEZONE = ZoneInfo(DISPLAY_TIMEZONE_NAME)
except Exception:
    DISPLAY_TIMEZONE_NAME = "America/New_York"
    DISPLAY_TIMEZONE = ZoneInfo(DISPLAY_TIMEZONE_NAME)

PUBLIC_BASE_URL = os.getenv("DISPATCHPROOF_PUBLIC_BASE_URL", "").strip().rstrip("/")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

# V1.4 company placeholders. Later these become company settings.
COMPANY_NAME = os.getenv("DISPATCHPROOF_COMPANY_NAME", "DispatchProof")
COMPANY_LOGO_URL = None
PRODUCT_NAME = "DispatchProof"
PRODUCT_TAGLINE = "Pre-Mobilization Proof"
PRODUCT_SUBTAG = "Avoid wasted trips."

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
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

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
        "arrival_token": "TEXT",
        "client_report_token": "TEXT",
        "client_id": "INTEGER",
        "project_id": "INTEGER",
        "completed_at": "TEXT",
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
        CREATE TABLE IF NOT EXISTS job_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            note_text TEXT NOT NULL,
            actor_type TEXT NOT NULL,
            actor_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
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
            scope_type TEXT,
            scope_id INTEGER,
            scope_name TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
    """)


    # V2.14: remember the most recent successful backup creation.
    app_settings_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(app_settings)").fetchall()
    }
    if "last_backup_at" not in app_settings_columns:
        db.execute("ALTER TABLE app_settings ADD COLUMN last_backup_at TEXT")

    # Older databases may already have Backup Downloaded activity. Use the
    # newest one as a safe initial reminder date until the next V2.14 backup.
    settings_row = db.execute(
        "SELECT last_backup_at FROM app_settings WHERE id = 1"
    ).fetchone()
    if settings_row and not settings_row["last_backup_at"]:
        previous_backup = db.execute("""
            SELECT created_at
            FROM activity_log
            WHERE action = 'Backup Downloaded'
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()
        if previous_backup:
            db.execute(
                "UPDATE app_settings SET last_backup_at = ? WHERE id = 1",
                (previous_backup["created_at"],),
            )

    # V2.6: extend V2.5 client/project records and email history without
    # requiring a destructive database migration.
    for table_name, columns in {
        "clients": {"report_token": "TEXT"},
        "projects": {"report_token": "TEXT"},
        "email_events": {
            "scope_type": "TEXT",
            "scope_id": "INTEGER",
            "scope_name": "TEXT",
        },
    }.items():
        existing_columns = {
            row["name"]
            for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        for column_name, sql_type in columns.items():
            if column_name not in existing_columns:
                db.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}"
                )

    for table_name in ("clients", "projects"):
        rows_without_report_token = db.execute(
            f"""
            SELECT id FROM {table_name}
            WHERE report_token IS NULL OR TRIM(report_token) = ''
            """
        ).fetchall()

        for row in rows_without_report_token:
            while True:
                candidate = secrets.token_urlsafe(24)
                exists = db.execute(
                    f"SELECT 1 FROM {table_name} WHERE report_token = ?",
                    (candidate,),
                ).fetchone()
                if not exists:
                    db.execute(
                        f"UPDATE {table_name} SET report_token = ? WHERE id = ?",
                        (candidate, row["id"]),
                    )
                    break

    db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_report_token
        ON clients(report_token)
    """)
    db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_report_token
        ON projects(report_token)
    """)

    # Backfill a separate high-entropy installer-arrival token for older jobs.
    rows_without_arrival_token = db.execute("""
        SELECT id FROM jobs
        WHERE arrival_token IS NULL OR TRIM(arrival_token) = ''
    """).fetchall()

    for row in rows_without_arrival_token:
        while True:
            candidate = secrets.token_urlsafe(24)
            exists = db.execute(
                "SELECT 1 FROM jobs WHERE arrival_token = ?",
                (candidate,),
            ).fetchone()
            if not exists:
                db.execute(
                    "UPDATE jobs SET arrival_token = ? WHERE id = ?",
                    (candidate, row["id"]),
                )
                break

    # Backfill an independent high-entropy client-report token for older jobs.
    rows_without_client_report_token = db.execute("""
        SELECT id FROM jobs
        WHERE client_report_token IS NULL OR TRIM(client_report_token) = ''
    """).fetchall()

    for row in rows_without_client_report_token:
        while True:
            candidate = secrets.token_urlsafe(24)
            exists = db.execute(
                "SELECT 1 FROM jobs WHERE client_report_token = ?",
                (candidate,),
            ).fetchone()
            if not exists:
                db.execute(
                    "UPDATE jobs SET client_report_token = ? WHERE id = ?",
                    (candidate, row["id"]),
                )
                break

    db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_arrival_token
        ON jobs(arrival_token)
    """)

    # Backfill reminder defaults for jobs upgraded from older builds.
    db.execute("""
        UPDATE jobs
        SET reminder_enabled = COALESCE(reminder_enabled, 1),
            reminder_hours_before = COALESCE(reminder_hours_before, 48),
            reminder_count = COALESCE(reminder_count, 0)
    """)

    # V1.8 kept a successful arrival in READY. In V1.9 that state is ON SITE.
    db.execute("""
        UPDATE jobs
        SET status = 'ON SITE'
        WHERE arrival_status = 'READY'
          AND status = 'READY'
          AND completed_at IS NULL
    """)

    db.commit()

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'OPERATIONS',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_token TEXT UNIQUE,
            name TEXT NOT NULL COLLATE NOCASE,
            contact_name TEXT,
            contact_email TEXT,
            contact_phone TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_token TEXT UNIQUE,
            client_id INTEGER NOT NULL,
            name TEXT NOT NULL COLLATE NOCASE,
            project_number TEXT,
            location TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            actor_type TEXT NOT NULL,
            actor_name TEXT NOT NULL,
            action TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            company_name TEXT NOT NULL,
            company_tagline TEXT,
            contact_email TEXT,
            contact_phone TEXT,
            website TEXT,
            accent_color TEXT NOT NULL DEFAULT '#0f62fe',
            logo_filename TEXT,
            last_backup_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_token TEXT UNIQUE NOT NULL,
            arrival_token TEXT UNIQUE,
            client_report_token TEXT UNIQUE,
            client_id INTEGER,
            project_id INTEGER,
            job_name TEXT NOT NULL,
            project_site TEXT,
            installation_date TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            contact_email TEXT NOT NULL,
            contact_phone TEXT,
            checklist_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'NO RESPONSE',
            created_at TEXT NOT NULL,
            completed_at TEXT,
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

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_log_created_at
            ON activity_log(created_at DESC)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_log_job_id
            ON activity_log(job_id, created_at DESC)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_projects_client_id
            ON projects(client_id, name)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_client_id
            ON jobs(client_id, installation_date)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_project_id
            ON jobs(project_id, installation_date)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_notes_job_id
            ON job_notes(job_id, created_at DESC, id DESC)
        """)

        activity_migration = db.execute(
            "SELECT 1 FROM app_migrations WHERE migration_key = ?",
            ("v2.3_activity_log",),
        ).fetchone()
        if not activity_migration:
            db.execute("""
                INSERT INTO activity_log (
                    job_id, actor_type, actor_name, action, description, created_at
                ) VALUES (NULL, 'SYSTEM', 'DispatchProof', 'Activity Log Enabled',
                          'Audit tracking started with DispatchProof V2.3.', ?)
            """, (now_iso(),))
            db.execute("""
                INSERT INTO app_migrations (migration_key, applied_at, details)
                VALUES (?, ?, ?)
            """, (
                "v2.3_activity_log",
                now_iso(),
                "Activity Log enabled. Earlier job evidence remains available in existing histories.",
            ))

        db.execute("""
            INSERT OR IGNORE INTO app_settings (
                id, company_name, company_tagline, accent_color, updated_at
            ) VALUES (1, ?, ?, '#0f62fe', ?)
        """, (
            COMPANY_NAME,
            PRODUCT_TAGLINE,
            datetime.now().replace(microsecond=0).isoformat(),
        ))
        db.commit()

        recover_v130_orphaned_mobilizations(db)

def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()

def backup_reminder_state(last_backup_at):
    """Return display state for the admin-only backup freshness reminder."""
    if not last_backup_at:
        return {
            "level": "urgent",
            "show_dashboard": True,
            "days": None,
            "label": "No backup recorded",
            "message": "Create a backup now so the current beta data can be restored after a Render reset.",
        }

    try:
        backup_dt = datetime.fromisoformat(last_backup_at)
    except Exception:
        return {
            "level": "urgent",
            "show_dashboard": True,
            "days": None,
            "label": "Backup date unavailable",
            "message": "Create a fresh backup so DispatchProof can track backup freshness correctly.",
        }

    age = datetime.now() - backup_dt
    days = max(0, age.days)

    if days >= 7:
        level = "urgent"
        show_dashboard = True
        label = "Backup overdue"
        message = (
            f"Your last backup was {days} day{'s' if days != 1 else ''} ago. "
            "Back up before the next deploy, restart, or important test."
        )
    elif days >= 3:
        level = "recommended"
        show_dashboard = True
        label = "Backup recommended"
        message = (
            f"Your last backup was {days} day{'s' if days != 1 else ''} ago. "
            "A fresh checkpoint is recommended."
        )
    else:
        level = "current"
        show_dashboard = False
        if days == 0:
            message = "Your latest backup is less than a day old."
        else:
            message = f"Your latest backup is {days} day ago."
        label = "Backup current"

    return {
        "level": level,
        "show_dashboard": show_dashboard,
        "days": days,
        "label": label,
        "message": message,
    }

def local_today():
    return datetime.now(DISPLAY_TIMEZONE).date()

def job_schedule_bucket(installation_date):
    """Classify an installation date for Dashboard schedule attention."""
    if not installation_date:
        return "unscheduled"

    try:
        install_day = date.fromisoformat(installation_date)
    except Exception:
        return "unscheduled"

    today = local_today()
    if install_day < today:
        return "overdue"
    if install_day == today:
        return "today"
    if install_day <= today + timedelta(days=7):
        return "next7"
    return "later"

def schedule_bucket_label(bucket):
    return {
        "overdue": "Overdue",
        "today": "Today",
        "next7": "Next 7 Days",
        "later": "Later",
        "unscheduled": "No Date",
    }.get(bucket, "Later")

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

        # Existing DispatchProof timestamps created on Render are stored as
        # naive ISO values representing UTC. Treat naive values as UTC, then
        # convert only for display. Aware timestamps are converted directly.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        local_dt = dt.astimezone(DISPLAY_TIMEZONE)
        hour = local_dt.strftime("%I").lstrip("0") or "0"
        zone_label = local_dt.tzname() or "ET"
        return (
            f"{local_dt.strftime('%b')} {local_dt.day}, {local_dt.year} "
            f"at {hour}:{local_dt.strftime('%M %p')} {zone_label}"
        )
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

    # Lifecycle status may now be ON SITE or BLOCKED. Preserve the readiness
    # result that existed before the installer arrived.
    readiness_status = job["status"]
    if job["response_at"] and job["response_json"]:
        try:
            readiness_answers = json.loads(job["response_json"])
            readiness_photos = json.loads(job["photo_json"]) if job["photo_json"] else []
            readiness_status = calculate_status(readiness_answers, readiness_photos)
        except Exception:
            pass

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

        new_arrival_token = secrets.token_urlsafe(24)

        db.execute("""
            UPDATE jobs
            SET arrival_token=?,
                status='NO RESPONSE',
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
        """, (new_arrival_token, job["id"]))

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

def public_arrival_url(job):
    base = public_app_base_url()
    if base:
        return f"{base}/a/{job['arrival_token']}"
    return url_for("public_arrival", token=job["arrival_token"], _external=True)

def public_client_report_url(job):
    base = public_app_base_url()
    if base:
        return f"{base}/c/{job['client_report_token']}"
    return url_for("public_client_report", token=job["client_report_token"], _external=True)

def public_portfolio_report_url(scope_type, entity):
    token = entity["report_token"]
    base = public_app_base_url()
    if scope_type == "CLIENT":
        if base:
            return f"{base}/portfolio/client/{token}"
        return url_for(
            "public_client_portfolio_report",
            token=token,
            _external=True,
        )

    if base:
        return f"{base}/portfolio/project/{token}"
    return url_for(
        "public_project_portfolio_report",
        token=token,
        _external=True,
    )


def parse_json_list(value):
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []

def parse_json_dict(value):
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}

def client_report_data(job):
    """Build a client-safe report payload for one job."""
    with get_db() as db:
        activity_events = db.execute("""
            SELECT *
            FROM activity_log
            WHERE job_id = ?
            ORDER BY id ASC
        """, (job["id"],)).fetchall()

        attempts = db.execute("""
            SELECT *
            FROM mobilization_attempts
            WHERE job_id = ?
            ORDER BY attempt_number ASC
        """, (job["id"],)).fetchall()

    checklist = parse_json_list(job["checklist_json"])
    answers = parse_json_dict(job["response_json"])
    photos = parse_json_list(job["photo_json"])
    arrival_issues = parse_json_list(job["arrival_issues_json"])
    arrival_photos = parse_json_list(job["arrival_photos_json"])

    mobilization_history = []
    for row in attempts:
        mobilization_history.append({
            "attempt_number": row["attempt_number"],
            "readiness_status": row["readiness_status"],
            "response_at": row["response_at"],
            "confirmed_by": row["confirmed_by"],
            "confirmed_title": row["confirmed_title"],
            "answers": parse_json_dict(row["response_json"]),
            "photos": parse_json_list(row["photo_json"]),
            "arrival_status": row["arrival_status"],
            "arrived_at": row["arrived_at"],
            "arrival_reported_by": row["arrival_reported_by"],
            "arrival_issues": parse_json_list(row["arrival_issues_json"]),
            "crew_size": row["crew_size"],
            "hours_lost": row["hours_lost"],
            "equipment_affected": row["equipment_affected"],
            "arrival_notes": row["arrival_notes"],
            "arrival_photos": parse_json_list(row["arrival_photos_json"]),
            "failed_report_number": row["failed_report_number"],
        })

    return {
        "checklist": checklist,
        "answers": answers,
        "photos": photos,
        "arrival_issues": arrival_issues,
        "arrival_photos": arrival_photos,
        "activity_events": activity_events,
        "mobilization_history": mobilization_history,
    }

def job_evidence_filenames(job):
    """Return only evidence filenames that belong to this job."""
    allowed = set(parse_json_list(job["photo_json"]))
    allowed.update(parse_json_list(job["arrival_photos_json"]))

    with get_db() as db:
        confirmations = db.execute("""
            SELECT photo_json
            FROM readiness_confirmations
            WHERE job_id = ?
        """, (job["id"],)).fetchall()
        attempts = db.execute("""
            SELECT photo_json, arrival_photos_json
            FROM mobilization_attempts
            WHERE job_id = ?
        """, (job["id"],)).fetchall()

    for row in confirmations:
        allowed.update(parse_json_list(row["photo_json"]))
    for row in attempts:
        allowed.update(parse_json_list(row["photo_json"]))
        allowed.update(parse_json_list(row["arrival_photos_json"]))

    return {name for name in allowed if name}

def build_client_report_email(job, report_url, recipient_name=""):
    settings = get_app_settings()
    brand_name = settings.get("company_name") or COMPANY_NAME
    brand_tagline = settings.get("company_tagline") or PRODUCT_TAGLINE
    brand_accent = normalize_hex_color(settings.get("accent_color"))
    logo_url = company_logo_external_url(settings)

    esc_brand = html_lib.escape(str(brand_name))
    esc_tagline = html_lib.escape(str(brand_tagline))
    esc_job = html_lib.escape(str(job["job_name"]))
    esc_site = html_lib.escape(str(job["project_site"] or ""))
    esc_status = html_lib.escape(str(job["status"]))
    esc_recipient = html_lib.escape(str(recipient_name or ""))
    esc_url = html_lib.escape(str(report_url), quote=True)

    subject = f"Installation Report: {job['job_name']}"
    greeting = f"Hi {esc_recipient}," if esc_recipient else "Hello,"

    html = f"""
    <html>
      <body style="font-family:Arial,sans-serif;background:#f5f7fb;padding:28px;color:#152033;">
        <div style="max-width:660px;margin:0 auto;background:#ffffff;border:1px solid #dfe5ee;border-radius:14px;padding:28px;">
          {f'<img src="{logo_url}" alt="{esc_brand} logo" style="max-height:54px;max-width:180px;object-fit:contain;margin-bottom:10px;display:block;">' if logo_url else ''}
          <div style="font-size:22px;font-weight:800;color:#0b2348;margin-bottom:4px;">{esc_brand}</div>
          <div style="font-size:12px;color:#6b7280;margin-bottom:2px;">{esc_tagline}</div>
          <div style="font-size:11px;color:#98a2b3;margin-bottom:24px;">Powered by DispatchProof</div>

          <p style="line-height:1.55;">{greeting}</p>
          <p style="line-height:1.55;">
            A current installation report is available for <strong>{esc_job}</strong>
            {f' at {esc_site}' if esc_site else ''}.
          </p>

          <div style="background:#f8fafc;border:1px solid #dfe5ee;border-radius:10px;padding:14px;margin:18px 0;">
            <div style="font-size:12px;color:#667085;">CURRENT STATUS</div>
            <div style="font-size:20px;font-weight:800;margin-top:3px;">{esc_status}</div>
            <div style="font-size:12px;color:#667085;margin-top:5px;">Scheduled installation: {format_date(job['installation_date'])}</div>
          </div>

          <p style="line-height:1.55;color:#475467;">
            The report includes readiness confirmation, submitted evidence photos,
            installer arrival information, mobilization history when applicable,
            and the job audit trail.
          </p>

          <div style="margin:26px 0;">
            <a href="{esc_url}" style="display:inline-block;background:{brand_accent};color:white;text-decoration:none;font-weight:700;padding:13px 18px;border-radius:9px;">
              View Installation Report
            </a>
          </div>

          <p style="font-size:12px;color:#6b7280;line-height:1.5;">
            This secure report link reflects the current DispatchProof record for this job.
          </p>
        </div>
      </body>
    </html>
    """
    return subject, html


def portfolio_jobs(scope_type, scope_id):
    with get_db() as db:
        if scope_type == "CLIENT":
            jobs = db.execute("""
                SELECT j.*, p.name AS assigned_project_name
                FROM jobs j
                LEFT JOIN projects p ON p.id = j.project_id
                WHERE j.client_id = ?
                ORDER BY
                    CASE WHEN j.status = 'COMPLETED' THEN 1 ELSE 0 END,
                    j.installation_date,
                    j.id
            """, (scope_id,)).fetchall()
        else:
            jobs = db.execute("""
                SELECT j.*, p.name AS assigned_project_name
                FROM jobs j
                LEFT JOIN projects p ON p.id = j.project_id
                WHERE j.project_id = ?
                ORDER BY
                    CASE WHEN j.status = 'COMPLETED' THEN 1 ELSE 0 END,
                    j.installation_date,
                    j.id
            """, (scope_id,)).fetchall()

    return jobs

def portfolio_report_data(scope_type, scope_id):
    jobs = portfolio_jobs(scope_type, scope_id)
    items = []
    counts = {
        "total": len(jobs),
        "active": 0,
        "ready": 0,
        "on_site": 0,
        "blocked": 0,
        "no_response": 0,
        "completed": 0,
    }

    for job in jobs:
        status = job["status"]
        if status == "COMPLETED":
            counts["completed"] += 1
        else:
            counts["active"] += 1
        if status == "READY":
            counts["ready"] += 1
        elif status == "ON SITE":
            counts["on_site"] += 1
        elif status in ("BLOCKED", "REVIEW"):
            counts["blocked"] += 1
        elif status == "NO RESPONSE":
            counts["no_response"] += 1

        data = client_report_data(job)
        items.append({
            "job": job,
            "data": data,
        })

    return {
        "jobs": items,
        "counts": counts,
    }

def portfolio_evidence_allowed(scope_type, scope_id, job_id, filename):
    with get_db() as db:
        if scope_type == "CLIENT":
            job = db.execute(
                "SELECT * FROM jobs WHERE id = ? AND client_id = ?",
                (job_id, scope_id),
            ).fetchone()
        else:
            job = db.execute(
                "SELECT * FROM jobs WHERE id = ? AND project_id = ?",
                (job_id, scope_id),
            ).fetchone()

    if not job:
        return False
    return filename in job_evidence_filenames(job)

def build_portfolio_report_email(
    scope_type,
    entity,
    client,
    jobs,
    report_url,
    recipient_name="",
):
    settings = get_app_settings()
    brand_name = settings.get("company_name") or COMPANY_NAME
    brand_tagline = settings.get("company_tagline") or PRODUCT_TAGLINE
    brand_accent = normalize_hex_color(settings.get("accent_color"))
    logo_url = company_logo_external_url(settings)

    entity_name = entity["name"]
    scope_label = "Client" if scope_type == "CLIENT" else "Project"
    active_count = sum(1 for job in jobs if job["status"] != "COMPLETED")
    completed_count = sum(1 for job in jobs if job["status"] == "COMPLETED")

    esc_brand = html_lib.escape(str(brand_name))
    esc_tagline = html_lib.escape(str(brand_tagline))
    esc_entity = html_lib.escape(str(entity_name))
    esc_client = html_lib.escape(str(client["name"]))
    esc_recipient = html_lib.escape(str(recipient_name or ""))
    esc_url = html_lib.escape(str(report_url), quote=True)

    subject = f"{scope_label} Installation Report: {entity_name}"
    greeting = f"Hi {esc_recipient}," if esc_recipient else "Hello,"

    html = f"""
    <html>
      <body style="font-family:Arial,sans-serif;background:#f5f7fb;padding:28px;color:#152033;">
        <div style="max-width:660px;margin:0 auto;background:#ffffff;border:1px solid #dfe5ee;border-radius:14px;padding:28px;">
          {f'<img src="{logo_url}" alt="{esc_brand} logo" style="max-height:54px;max-width:180px;object-fit:contain;margin-bottom:10px;display:block;">' if logo_url else ''}
          <div style="font-size:22px;font-weight:800;color:#0b2348;margin-bottom:4px;">{esc_brand}</div>
          <div style="font-size:12px;color:#6b7280;margin-bottom:2px;">{esc_tagline}</div>
          <div style="font-size:11px;color:#98a2b3;margin-bottom:24px;">Powered by DispatchProof</div>

          <p style="line-height:1.55;">{greeting}</p>
          <p style="line-height:1.55;">
            A combined installation report is available for
            <strong>{esc_entity}</strong>
            {f' under {esc_client}' if scope_type == 'PROJECT' else ''}.
          </p>

          <div style="display:flex;gap:10px;margin:18px 0;flex-wrap:wrap;">
            <div style="min-width:120px;background:#f8fafc;border:1px solid #dfe5ee;border-radius:10px;padding:12px;">
              <div style="font-size:11px;color:#667085;">ACTIVE INSTALLS</div>
              <div style="font-size:22px;font-weight:800;">{active_count}</div>
            </div>
            <div style="min-width:120px;background:#f8fafc;border:1px solid #dfe5ee;border-radius:10px;padding:12px;">
              <div style="font-size:11px;color:#667085;">COMPLETED</div>
              <div style="font-size:22px;font-weight:800;">{completed_count}</div>
            </div>
            <div style="min-width:120px;background:#f8fafc;border:1px solid #dfe5ee;border-radius:10px;padding:12px;">
              <div style="font-size:11px;color:#667085;">TOTAL JOBS</div>
              <div style="font-size:22px;font-weight:800;">{len(jobs)}</div>
            </div>
          </div>

          <p style="line-height:1.55;color:#475467;">
            The live report includes each installation's current status,
            readiness confirmation, field arrival result, evidence photos,
            and job audit trail.
          </p>

          <div style="margin:26px 0;">
            <a href="{esc_url}" style="display:inline-block;background:{brand_accent};color:white;text-decoration:none;font-weight:700;padding:13px 18px;border-radius:9px;">
              View Combined Installation Report
            </a>
          </div>

          <p style="font-size:12px;color:#6b7280;line-height:1.5;">
            This secure report link reflects the current DispatchProof records in this {scope_label.lower()} report.
          </p>
        </div>
      </body>
    </html>
    """
    return subject, html

def smtp_is_configured():
    return bool(SMTP_HOST and SMTP_PORT and SMTP_FROM_EMAIL)

def email_delivery_enabled():
    return EMAIL_MODE == "smtp" and smtp_is_configured()

def build_readiness_email(job, public_url, reminder=False):
    settings = get_app_settings()
    brand_name = settings.get("company_name") or COMPANY_NAME
    brand_tagline = settings.get("company_tagline") or PRODUCT_TAGLINE
    brand_accent = normalize_hex_color(settings.get("accent_color"))
    logo_url = company_logo_external_url(settings)

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
          {f'<img src="{logo_url}" alt="{brand_name} logo" style="max-height:54px;max-width:180px;object-fit:contain;margin-bottom:10px;display:block;">' if logo_url else ''}
          <div style="font-size:22px;font-weight:800;color:#0b2348;margin-bottom:4px;">{brand_name}</div>
          <div style="font-size:12px;color:#6b7280;margin-bottom:2px;">{brand_tagline}</div>
          <div style="font-size:11px;color:#98a2b3;margin-bottom:24px;">Powered by DispatchProof</div>

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
            <a href="{public_url}" style="display:inline-block;background:{brand_accent};color:white;text-decoration:none;font-weight:700;padding:13px 18px;border-radius:9px;">
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

def log_email_event(
    db,
    job_id,
    event_type,
    recipient_email,
    recipient_name,
    subject,
    body_html,
    public_url,
    status,
    error_message=None,
    scope_type=None,
    scope_id=None,
    scope_name=None,
):
    db.execute("""
        INSERT INTO email_events (
            job_id, event_type, recipient_email, recipient_name,
            subject, body_html, public_url, status, error_message,
            scope_type, scope_id, scope_name, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        scope_type,
        scope_id,
        scope_name,
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

def user_authenticated():
    # Backward compatible with older V2.0 sessions during deploy transitions.
    return bool(session.get("dispatchproof_authenticated") or session.get("dispatchproof_admin"))

def current_username():
    return session.get("dispatchproof_username") or session.get("dispatchproof_admin_username") or ""

def current_display_name():
    return session.get("dispatchproof_display_name") or current_username()

def current_user_role():
    # Legacy owner/admin sessions are always administrators.
    if session.get("dispatchproof_owner"):
        return "OWNER"
    role = (session.get("dispatchproof_role") or "").upper()
    if role in {"ADMIN", "OPERATIONS"}:
        return role
    if session.get("dispatchproof_admin"):
        return "OWNER"
    return ""

def current_user_is_admin():
    return current_user_role() in {"OWNER", "ADMIN"}

def admin_authenticated():
    # Kept for older templates; this now means "signed in".
    return user_authenticated()


def current_db_user():
    user_id = session.get("dispatchproof_user_id")
    if not user_id:
        return None

    with get_db() as db:
        return db.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def normalize_optional_id(value):
    value = str(value or "").strip()
    return int(value) if value.isdigit() and int(value) > 0 else None

def get_clients_and_projects(db):
    clients = db.execute("""
        SELECT *
        FROM clients
        ORDER BY LOWER(name), id
    """).fetchall()
    projects = db.execute("""
        SELECT p.*, c.name AS client_name
        FROM projects p
        JOIN clients c ON c.id = p.client_id
        ORDER BY LOWER(c.name), LOWER(p.name), p.id
    """).fetchall()
    return clients, projects

def resolve_job_assignment(db, raw_client_id, raw_project_id):
    client_id = normalize_optional_id(raw_client_id)
    project_id = normalize_optional_id(raw_project_id)

    if project_id:
        project = db.execute(
            "SELECT id, client_id FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if not project:
            return None, None, "The selected project could not be found."
        return project["client_id"], project["id"], None

    if client_id:
        client = db.execute(
            "SELECT id FROM clients WHERE id = ?",
            (client_id,),
        ).fetchone()
        if not client:
            return None, None, "The selected client could not be found."

    return client_id, None, None

def activity_actor():
    if user_authenticated():
        role = current_user_role() or "USER"
        return role, current_display_name() or current_username() or "Internal User"
    return "SYSTEM", "DispatchProof"

def record_activity(db, action, description="", job_id=None, actor_type=None, actor_name=None):
    if actor_type is None or actor_name is None:
        default_type, default_name = activity_actor()
        actor_type = actor_type or default_type
        actor_name = actor_name or default_name

    db.execute("""
        INSERT INTO activity_log (
            job_id, actor_type, actor_name, action, description, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        job_id,
        str(actor_type),
        str(actor_name),
        action,
        description,
        now_iso(),
    ))

def log_activity(action, description="", job_id=None, actor_type=None, actor_name=None):
    with get_db() as db:
        record_activity(
            db,
            action,
            description,
            job_id=job_id,
            actor_type=actor_type,
            actor_name=actor_name,
        )
        db.commit()

def safe_next_url(value):
    if not value:
        return url_for("dashboard")
    # Only allow local absolute paths, never //host or full external URLs.
    if value.startswith("/") and not value.startswith("//"):
        return value
    return url_for("dashboard")


def backup_filename():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"dispatchproof_backup_{stamp}.zip"

def sqlite_sidecar_paths(db_path):
    return [
        Path(str(db_path) + "-wal"),
        Path(str(db_path) + "-shm"),
        Path(str(db_path) + "-journal"),
    ]

def clear_sqlite_sidecars(db_path):
    for sidecar in sqlite_sidecar_paths(db_path):
        try:
            if sidecar.exists():
                sidecar.unlink()
        except OSError:
            pass

def database_record_counts(db_path):
    counts = {
        "jobs": 0,
        "readiness_confirmations": 0,
        "mobilization_attempts": 0,
        "email_events": 0,
        "activity_log": 0,
        "job_notes": 0,
    }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        if quick != "ok":
            raise sqlite3.DatabaseError(f"SQLite quick_check returned: {quick}")

        for table, key in (
            ("jobs", "jobs"),
            ("readiness_confirmations", "readiness_confirmations"),
            ("mobilization_attempts", "mobilization_attempts"),
            ("email_events", "email_events"),
            ("activity_log", "activity_log"),
            ("job_notes", "job_notes"),
            ("clients", "clients"),
            ("projects", "projects"),
        ):
            try:
                counts[key] = conn.execute(
                    f"SELECT COUNT(*) AS c FROM {table}"
                ).fetchone()["c"]
            except sqlite3.DatabaseError:
                counts[key] = 0
    finally:
        conn.close()

    return counts

def create_backup_archive():
    """Create a portable backup containing SQLite data and uploaded evidence."""
    temp_dir = Path(tempfile.mkdtemp(prefix="dispatchproof_backup_"))
    archive_path = temp_dir / backup_filename()

    # Fully checkpoint the live WAL into the main DB file before copying.
    if DB_PATH.exists():
        try:
            with get_db() as db:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                db.commit()
        except Exception:
            pass

    backup_counts = {
        "jobs": 0,
        "readiness_confirmations": 0,
        "mobilization_attempts": 0,
        "email_events": 0,
        "activity_log": 0,
        "job_notes": 0,
        "uploaded_files": 0,
    }

    if DB_PATH.exists():
        try:
            backup_counts.update(database_record_counts(DB_PATH))
        except Exception:
            pass

    if UPLOAD_DIR.exists():
        backup_counts["uploaded_files"] = sum(
            1 for p in UPLOAD_DIR.rglob("*") if p.is_file()
        )

    metadata = {
        "product": PRODUCT_NAME,
        "backup_format": 2,
        "created_at": now_iso(),
        "app_version": "2.15.1",
        "database_file": "dispatchproof.db",
        "uploads_folder": "uploads",
        "counts": backup_counts,
    }

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("backup_manifest.json", json.dumps(metadata, indent=2))

        if DB_PATH.exists():
            z.write(DB_PATH, "dispatchproof.db")

        if UPLOAD_DIR.exists():
            for p in UPLOAD_DIR.rglob("*"):
                if p.is_file():
                    z.write(p, Path("uploads") / p.relative_to(UPLOAD_DIR))

    return archive_path, temp_dir

def validate_backup_zip(zip_path):
    """Validate archive layout before any current data is touched."""
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            names = set(z.namelist())

            if "backup_manifest.json" not in names:
                return False, "Backup manifest is missing."

            manifest = json.loads(z.read("backup_manifest.json").decode("utf-8"))
            if manifest.get("product") != PRODUCT_NAME:
                return False, "This does not appear to be a DispatchProof backup."

            if "dispatchproof.db" not in names:
                return False, "Backup database is missing."

            for name in names:
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    return False, "Backup contains an unsafe file path."

        return True, None
    except zipfile.BadZipFile:
        return False, "The selected file is not a valid ZIP backup."
    except Exception as exc:
        return False, f"Backup could not be validated: {exc}"

def restore_backup_archive(zip_path):
    """Stage, validate, restore, and verify a DispatchProof backup."""
    valid, error = validate_backup_zip(zip_path)
    if not valid:
        return False, error, None

    stage_dir = Path(tempfile.mkdtemp(prefix="dispatchproof_restore_"))
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(stage_dir)
            try:
                manifest = json.loads(
                    z.read("backup_manifest.json").decode("utf-8")
                )
            except Exception:
                manifest = {}

        staged_db = stage_dir / "dispatchproof.db"
        staged_uploads = stage_dir / "uploads"

        try:
            staged_counts = database_record_counts(staged_db)
        except Exception as exc:
            return False, f"Backup database is not readable: {exc}", None

        safety_dir = Path(tempfile.mkdtemp(prefix="dispatchproof_pre_restore_"))
        old_db = safety_dir / "dispatchproof.db"
        old_uploads = safety_dir / "uploads"

        try:
            # Preserve current state first.
            if DB_PATH.exists():
                try:
                    with get_db() as db:
                        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                        db.commit()
                except Exception:
                    pass

                shutil.copy2(DB_PATH, old_db)

            if UPLOAD_DIR.exists():
                shutil.copytree(UPLOAD_DIR, old_uploads)

            DATA_DIR.mkdir(parents=True, exist_ok=True)

            # Critical fix: remove stale SQLite journals before swapping DB files.
            clear_sqlite_sidecars(DB_PATH)
            if DB_PATH.exists():
                DB_PATH.unlink()

            shutil.copy2(staged_db, DB_PATH)
            clear_sqlite_sidecars(DB_PATH)

            if UPLOAD_DIR.exists():
                shutil.rmtree(UPLOAD_DIR)
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

            if staged_uploads.exists():
                for p in staged_uploads.rglob("*"):
                    if p.is_file():
                        dest = UPLOAD_DIR / p.relative_to(staged_uploads)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(p, dest)

            # Migrate restored DB forward if needed.
            init_db()

            try:
                with get_db() as db:
                    db.execute("PRAGMA wal_checkpoint(FULL)")
                    db.commit()
            except Exception:
                pass

            live_counts = database_record_counts(DB_PATH)

            expected_jobs = staged_counts.get("jobs", 0)
            actual_jobs = live_counts.get("jobs", 0)
            if actual_jobs != expected_jobs:
                raise RuntimeError(
                    f"Restore verification failed: backup had {expected_jobs} job(s), "
                    f"but live database has {actual_jobs}."
                )

            shutil.rmtree(safety_dir, ignore_errors=True)
            return True, None, {
                "backup_counts": staged_counts,
                "live_counts": live_counts,
                "manifest_counts": manifest.get("counts") or {},
                "manifest_created_at": manifest.get("created_at"),
            }

        except Exception as exc:
            # Roll back to prior live data.
            try:
                clear_sqlite_sidecars(DB_PATH)
                if DB_PATH.exists():
                    DB_PATH.unlink()

                if old_db.exists():
                    shutil.copy2(old_db, DB_PATH)

                clear_sqlite_sidecars(DB_PATH)

                if UPLOAD_DIR.exists():
                    shutil.rmtree(UPLOAD_DIR)
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

                if old_uploads.exists():
                    for p in old_uploads.rglob("*"):
                        if p.is_file():
                            dest = UPLOAD_DIR / p.relative_to(old_uploads)
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(p, dest)

                init_db()
            except Exception:
                pass

            return False, f"Restore failed; current data was preserved when possible: {exc}", None

        finally:
            shutil.rmtree(safety_dir, ignore_errors=True)

    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


def get_app_settings():
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM app_settings WHERE id = 1"
        ).fetchone()

    if row:
        return dict(row)

    return {
        "company_name": COMPANY_NAME,
        "company_tagline": PRODUCT_TAGLINE,
        "contact_email": "",
        "contact_phone": "",
        "website": "",
        "accent_color": "#0f62fe",
        "logo_filename": None,
        "last_backup_at": None,
    }

def normalize_hex_color(value):
    value = (value or "").strip()
    return value.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else "#0f62fe"

def company_logo_url(settings=None):
    settings = settings or get_app_settings()
    if not settings.get("logo_filename"):
        return None
    return url_for("company_logo")

def company_logo_external_url(settings=None):
    settings = settings or get_app_settings()
    if not settings.get("logo_filename"):
        return None

    base = public_app_base_url()
    if base:
        return f"{base}/branding/logo"

    return url_for("company_logo", _external=True)

@app.context_processor
def inject_brand():
    settings = get_app_settings()
    return {
        "company_name": settings.get("company_name") or COMPANY_NAME,
        "company_logo_url": company_logo_url(settings),
        "company_tagline": settings.get("company_tagline") or PRODUCT_TAGLINE,
        "company_contact_email": settings.get("contact_email") or "",
        "company_contact_phone": settings.get("contact_phone") or "",
        "company_website": settings.get("website") or "",
        "company_accent_color": settings.get("accent_color") or "#0f62fe",
        "product_name": PRODUCT_NAME,
        "product_tagline": PRODUCT_TAGLINE,
        "product_subtag": PRODUCT_SUBTAG,
        "app_version": "2.15.1",
        "smtp_configured": smtp_is_configured(),
        "email_mode": EMAIL_MODE,
        "email_delivery_enabled": email_delivery_enabled(),
        "admin_authenticated": user_authenticated(),
        "admin_username": current_username(),
        "current_display_name": current_display_name(),
        "current_user_role": current_user_role(),
        "current_user_is_admin": current_user_is_admin(),
    }

@app.before_request
def ensure_db():
    global LAST_REMINDER_SWEEP_AT
    init_db()

    public_endpoints = {
        "login", "health", "static", "public_readiness", "public_arrival",
        "public_client_report", "client_report_asset",
        "public_client_portfolio_report", "public_project_portfolio_report",
        "client_portfolio_asset", "project_portfolio_asset",
        "company_logo"
    }
    if request.endpoint not in public_endpoints and not user_authenticated():
        return redirect(url_for("login", next=request.full_path if request.query_string else request.path))

    admin_only_endpoints = {
        "company_settings",
        "backup_restore",
        "download_backup",
        "restore_backup",
        "users_access",
        "add_user",
        "toggle_user_access",
        "reset_user_password",
        "change_user_role",
        "edit_user",
        "activity_log",
        "reopen_job",
    }
    if request.endpoint in admin_only_endpoints and user_authenticated() and not current_user_is_admin():
        flash("Administrator access is required for that page.")
        return redirect(url_for("dashboard"))

    # Do not make static/public requests responsible for sending reminders.
    if request.endpoint in {
        "static", "health", "public_readiness", "public_arrival",
        "public_client_report", "client_report_asset",
        "public_client_portfolio_report", "public_project_portfolio_report",
        "client_portfolio_asset", "project_portfolio_asset",
        "company_logo",
    }:
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
    if user_authenticated():
        return redirect(safe_next_url(request.args.get("next")))

    configured = admin_login_configured()
    next_url = request.args.get("next") or request.form.get("next") or ""

    if request.method == "POST":
        submitted_username = request.form.get("username", "").strip()
        submitted_password = request.form.get("password", "")
        stay_signed_in = request.form.get("stay_signed_in") == "1"

        # Permanent owner account remains backed by Render Environment.
        owner_ok = False
        if configured:
            username_ok = secrets.compare_digest(submitted_username, ADMIN_USERNAME)
            password_ok = secrets.compare_digest(submitted_password, effective_admin_password())
            owner_ok = username_ok and password_ok

        if owner_ok:
            session.clear()
            session.permanent = stay_signed_in
            session["dispatchproof_authenticated"] = True
            session["dispatchproof_admin"] = True
            session["dispatchproof_owner"] = True
            session["dispatchproof_username"] = ADMIN_USERNAME
            session["dispatchproof_admin_username"] = ADMIN_USERNAME
            session["dispatchproof_display_name"] = ADMIN_USERNAME
            session["dispatchproof_role"] = "OWNER"
            session["dispatchproof_stay_signed_in"] = stay_signed_in
            return redirect(safe_next_url(next_url))

        # Additional users are stored securely in SQLite using password hashes.
        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                (submitted_username,),
            ).fetchone()

            if user and user["is_active"] and check_password_hash(user["password_hash"], submitted_password):
                db.execute(
                    "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                    (now_iso(), now_iso(), user["id"]),
                )
                db.commit()

                session.clear()
                session.permanent = stay_signed_in
                session["dispatchproof_authenticated"] = True
                session["dispatchproof_admin"] = True
                session["dispatchproof_owner"] = False
                session["dispatchproof_user_id"] = user["id"]
                session["dispatchproof_username"] = user["username"]
                session["dispatchproof_admin_username"] = user["username"]
                session["dispatchproof_display_name"] = user["full_name"]
                session["dispatchproof_role"] = user["role"]
                session["dispatchproof_stay_signed_in"] = stay_signed_in
                return redirect(safe_next_url(next_url))

        flash("Incorrect username or password.")

    return render_template("login.html", configured=True, next_url=next_url)

@app.post("/logout")
def logout():
    session.clear()
    flash("Signed out.")
    return redirect(url_for("login"))

@app.route("/health")
def health():
    return {
        "status": "ok",
        "version": "2.15.1",
        "data_dir": str(DATA_DIR),
        "email_mode": EMAIL_MODE,
        "smtp_configured": smtp_is_configured(),
        "email_delivery_enabled": email_delivery_enabled(),
    }, 200



@app.route("/branding/logo")
def company_logo():
    settings = get_app_settings()
    filename = settings.get("logo_filename")
    if not filename:
        abort(404)
    return send_from_directory(UPLOAD_DIR, filename)




@app.route("/account", methods=["GET", "POST"])
def my_account():
    owner_account = bool(session.get("dispatchproof_owner"))
    user = current_db_user()

    if request.method == "POST":
        if owner_account:
            flash("The permanent Owner password is managed in Render Environment, not inside DispatchProof.")
            return redirect(url_for("my_account"))

        if not user:
            session.clear()
            flash("Your account session could not be verified. Please sign in again.")
            return redirect(url_for("login"))

        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(user["password_hash"], current_password):
            flash("Current password is incorrect.")
            return redirect(url_for("my_account"))

        if len(new_password) < 8:
            flash("New password must be at least 8 characters.")
            return redirect(url_for("my_account"))

        if new_password != confirm_password:
            flash("New password and confirmation do not match.")
            return redirect(url_for("my_account"))

        if check_password_hash(user["password_hash"], new_password):
            flash("Choose a new password that is different from your current password.")
            return redirect(url_for("my_account"))

        with get_db() as db:
            db.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (generate_password_hash(new_password), now_iso(), user["id"]),
            )
            record_activity(
                db,
                "Password Changed",
                "Changed their own DispatchProof password.",
            )
            db.commit()

        flash("Password changed successfully.")
        return redirect(url_for("my_account"))

    return render_template(
        "my_account.html",
        owner_account=owner_account,
        user=user,
    )


@app.route("/settings/users")
def users_access():
    with get_db() as db:
        users = db.execute("""
            SELECT id, full_name, username, role, is_active, created_at, last_login_at
            FROM users
            ORDER BY
                CASE role WHEN 'ADMIN' THEN 0 ELSE 1 END,
                LOWER(full_name),
                LOWER(username)
        """).fetchall()

    return render_template(
        "users_access.html",
        users=users,
        owner_username=ADMIN_USERNAME,
    )


@app.post("/settings/users/add")
def add_user():
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "OPERATIONS").strip().upper()

    if not full_name or not username or not password:
        flash("Full Name, Username, and Temporary Password are required.")
        return redirect(url_for("users_access"))

    if role not in {"ADMIN", "OPERATIONS"}:
        role = "OPERATIONS"

    if len(username) < 3:
        flash("Username must be at least 3 characters.")
        return redirect(url_for("users_access"))

    if len(password) < 8:
        flash("Temporary Password must be at least 8 characters.")
        return redirect(url_for("users_access"))

    if username.lower() == ADMIN_USERNAME.lower():
        flash("That username belongs to the permanent Owner account.")
        return redirect(url_for("users_access"))

    try:
        with get_db() as db:
            db.execute("""
                INSERT INTO users (
                    full_name, username, password_hash, role,
                    is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
            """, (
                full_name,
                username,
                generate_password_hash(password),
                role,
                now_iso(),
                now_iso(),
            ))
            record_activity(
                db,
                "User Added",
                f"Added {full_name} (@{username}) with {role.title()} access.",
            )
            db.commit()
    except sqlite3.IntegrityError:
        flash("That username is already in use.")
        return redirect(url_for("users_access"))

    flash(f"User {username} added.")
    return redirect(url_for("users_access"))


@app.post("/settings/users/<int:user_id>/toggle-access")
def toggle_user_access(user_id):
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            abort(404)

        # Prevent an admin from disabling the account currently being used.
        if session.get("dispatchproof_user_id") == user_id:
            flash("You cannot disable the account you are currently signed in with.")
            return redirect(url_for("users_access"))

        new_active = 0 if user["is_active"] else 1

        # Never allow the final enabled DB admin to be disabled by another DB admin.
        # The ENV-backed Owner always remains available regardless.
        db.execute(
            "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
            (new_active, now_iso(), user_id),
        )
        record_activity(
            db,
            "User Access Enabled" if new_active else "User Access Disabled",
            f"{'Enabled' if new_active else 'Disabled'} access for {user['full_name']} (@{user['username']}).",
        )
        db.commit()

    flash(f"{user['username']} access {'enabled' if new_active else 'disabled'}.")
    return redirect(url_for("users_access"))


@app.post("/settings/users/<int:user_id>/reset-password")
def reset_user_password(user_id):
    new_password = request.form.get("new_password", "")

    if len(new_password) < 8:
        flash("New password must be at least 8 characters.")
        return redirect(url_for("users_access"))

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            abort(404)

        db.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (generate_password_hash(new_password), now_iso(), user_id),
        )
        record_activity(
            db,
            "User Password Reset",
            f"Administrator reset the password for {user['full_name']} (@{user['username']}).",
        )
        db.commit()

    flash(f"Password reset for {user['username']}.")
    return redirect(url_for("users_access"))


@app.post("/settings/users/<int:user_id>/role")
def change_user_role(user_id):
    role = request.form.get("role", "OPERATIONS").strip().upper()
    if role not in {"ADMIN", "OPERATIONS"}:
        flash("Invalid role.")
        return redirect(url_for("users_access"))

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            abort(404)

        if session.get("dispatchproof_user_id") == user_id and role != "ADMIN":
            flash("You cannot remove administrator access from the account you are currently using.")
            return redirect(url_for("users_access"))

        db.execute(
            "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
            (role, now_iso(), user_id),
        )
        record_activity(
            db,
            "User Role Changed",
            f"Changed {user['full_name']} (@{user['username']}) to {role.title()}.",
        )
        db.commit()

    flash(f"{user['username']} role updated.")
    return redirect(url_for("users_access"))



@app.route("/settings/users/<int:user_id>/edit", methods=["GET", "POST"])
def edit_user(user_id):
    with get_db() as db:
        user = db.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    if not user:
        abort(404)

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        role = request.form.get("role", "OPERATIONS").strip().upper()
        is_active = 1 if request.form.get("is_active") == "1" else 0

        if not full_name or not username:
            flash("Full Name and Username are required.")
            return redirect(url_for("edit_user", user_id=user_id))

        if len(username) < 3:
            flash("Username must be at least 3 characters.")
            return redirect(url_for("edit_user", user_id=user_id))

        if username.lower() == ADMIN_USERNAME.lower():
            flash("That username belongs to the permanent Owner account.")
            return redirect(url_for("edit_user", user_id=user_id))

        if role not in {"ADMIN", "OPERATIONS"}:
            flash("Invalid role.")
            return redirect(url_for("edit_user", user_id=user_id))

        is_self = session.get("dispatchproof_user_id") == user_id

        if is_self and role != "ADMIN":
            flash("You cannot remove administrator access from the account you are currently using.")
            return redirect(url_for("edit_user", user_id=user_id))

        if is_self and not is_active:
            flash("You cannot disable the account you are currently signed in with.")
            return redirect(url_for("edit_user", user_id=user_id))

        try:
            with get_db() as db:
                db.execute("""
                    UPDATE users
                    SET full_name = ?,
                        username = ?,
                        role = ?,
                        is_active = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (
                    full_name,
                    username,
                    role,
                    is_active,
                    now_iso(),
                    user_id,
                ))
                changes = []
                if user["full_name"] != full_name:
                    changes.append(f"name: {user['full_name']} → {full_name}")
                if user["username"].lower() != username.lower():
                    changes.append(f"username: @{user['username']} → @{username}")
                if user["role"] != role:
                    changes.append(f"role: {user['role'].title()} → {role.title()}")
                if int(user["is_active"]) != is_active:
                    changes.append("access enabled" if is_active else "access disabled")

                record_activity(
                    db,
                    "User Updated",
                    f"Updated {full_name} (@{username})"
                    + (": " + "; ".join(changes) if changes else "."),
                )
                db.commit()
        except sqlite3.IntegrityError:
            flash("That username is already in use.")
            return redirect(url_for("edit_user", user_id=user_id))

        # If an administrator edited their own display name/username, keep the
        # current session consistent without forcing a sign-out.
        if is_self:
            session["dispatchproof_username"] = username
            session["dispatchproof_admin_username"] = username
            session["dispatchproof_display_name"] = full_name
            session["dispatchproof_role"] = role

        flash(f"User {username} updated.")
        return redirect(url_for("users_access"))

    return render_template(
        "edit_user.html",
        user=user,
        is_self=session.get("dispatchproof_user_id") == user_id,
    )


@app.route("/settings/company", methods=["GET", "POST"])
def company_settings():
    settings = get_app_settings()

    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip() or COMPANY_NAME
        company_tagline = request.form.get("company_tagline", "").strip()
        contact_email = request.form.get("contact_email", "").strip()
        contact_phone = request.form.get("contact_phone", "").strip()
        website = request.form.get("website", "").strip()
        accent_color = normalize_hex_color(request.form.get("accent_color"))

        logo_filename = settings.get("logo_filename")
        logo = request.files.get("company_logo")

        if logo and logo.filename:
            if not allowed_file(logo.filename):
                flash("Company logo must be PNG, JPG, JPEG, or WEBP.")
                return redirect(url_for("company_settings"))

            ext = Path(secure_filename(logo.filename)).suffix.lower()
            logo_filename = f"branding_company_logo{ext}"

            for old_logo in UPLOAD_DIR.glob("branding_company_logo.*"):
                try:
                    old_logo.unlink()
                except OSError:
                    pass

            logo.save(UPLOAD_DIR / logo_filename)

        if request.form.get("remove_logo") == "1":
            if logo_filename:
                try:
                    (UPLOAD_DIR / logo_filename).unlink(missing_ok=True)
                except OSError:
                    pass
            logo_filename = None

        with get_db() as db:
            db.execute("""
                UPDATE app_settings
                SET company_name = ?,
                    company_tagline = ?,
                    contact_email = ?,
                    contact_phone = ?,
                    website = ?,
                    accent_color = ?,
                    logo_filename = ?,
                    updated_at = ?
                WHERE id = 1
            """, (
                company_name,
                company_tagline,
                contact_email,
                contact_phone,
                website,
                accent_color,
                logo_filename,
                now_iso(),
            ))
            record_activity(
                db,
                "Company Settings Updated",
                f"Updated company branding/settings for {company_name}.",
            )
            db.commit()

        flash("Company branding updated.")
        return redirect(url_for("company_settings"))

    return render_template(
        "company_settings.html",
        settings=get_app_settings(),
    )


@app.route("/backup")
def backup_restore():
    db_exists = DB_PATH.exists()
    upload_count = 0
    if UPLOAD_DIR.exists():
        upload_count = sum(1 for p in UPLOAD_DIR.rglob("*") if p.is_file())

    counts = {
        "jobs": 0,
        "completed_jobs": 0,
        "users": 0,
        "readiness_responses": 0,
        "mobilization_attempts": 0,
        "outbox_messages": 0,
        "activity_events": 0,
        "job_notes": 0,
        "clients": 0,
        "projects": 0,
    }

    if db_exists:
        with get_db() as db:
            counts["jobs"] = db.execute(
                "SELECT COUNT(*) AS c FROM jobs"
            ).fetchone()["c"]

            counts["completed_jobs"] = db.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE status = 'COMPLETED'"
            ).fetchone()["c"]

            counts["users"] = db.execute(
                "SELECT COUNT(*) AS c FROM users"
            ).fetchone()["c"] + 1  # Include permanent ENV-backed Owner.

            current_responses = db.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE response_at IS NOT NULL"
            ).fetchone()["c"]
            archived_responses = db.execute(
                "SELECT COUNT(*) AS c FROM readiness_confirmations"
            ).fetchone()["c"]
            counts["readiness_responses"] = current_responses + archived_responses

            archived_attempts = db.execute(
                "SELECT COUNT(*) AS c FROM mobilization_attempts"
            ).fetchone()["c"]
            # Every current job represents its active/current mobilization attempt.
            counts["mobilization_attempts"] = archived_attempts + counts["jobs"]

            counts["outbox_messages"] = db.execute(
                "SELECT COUNT(*) AS c FROM email_events WHERE status = 'OUTBOX'"
            ).fetchone()["c"]

            counts["activity_events"] = db.execute(
                "SELECT COUNT(*) AS c FROM activity_log"
            ).fetchone()["c"]
            counts["job_notes"] = db.execute(
                "SELECT COUNT(*) AS c FROM job_notes"
            ).fetchone()["c"]
            counts["clients"] = db.execute(
                "SELECT COUNT(*) AS c FROM clients"
            ).fetchone()["c"]
            counts["projects"] = db.execute(
                "SELECT COUNT(*) AS c FROM projects"
            ).fetchone()["c"]

    settings = get_app_settings()
    backup_status = backup_reminder_state(settings.get("last_backup_at"))

    return render_template(
        "backup_restore.html",
        db_exists=db_exists,
        upload_count=upload_count,
        counts=counts,
        data_dir=str(DATA_DIR),
        last_backup_at=settings.get("last_backup_at"),
        backup_status=backup_status,
    )

@app.get("/backup/download")
def download_backup():
    backup_at = now_iso()

    # Record the checkpoint before creating the archive so the ZIP itself
    # remembers when it was made after a future restore.
    with get_db() as db:
        db.execute(
            "UPDATE app_settings SET last_backup_at = ? WHERE id = 1",
            (backup_at,),
        )
        record_activity(
            db,
            "Backup Downloaded",
            "Created a fresh DispatchProof data backup.",
        )
        db.commit()

    archive_path, temp_dir = create_backup_archive()
    response = send_file(
        archive_path,
        as_attachment=True,
        download_name=archive_path.name,
        mimetype="application/zip",
        max_age=0,
    )

    # Flask sends lazily, so cleanup after response closes.
    response.call_on_close(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
    return response

@app.post("/backup/restore")
def restore_backup():
    uploaded = request.files.get("backup_file")
    if not uploaded or not uploaded.filename:
        flash("Choose a DispatchProof backup ZIP first.")
        return redirect(url_for("backup_restore"))

    if not uploaded.filename.lower().endswith(".zip"):
        flash("Restore requires a DispatchProof ZIP backup.")
        return redirect(url_for("backup_restore"))

    temp_dir = Path(tempfile.mkdtemp(prefix="dispatchproof_restore_upload_"))
    temp_zip = temp_dir / "restore.zip"
    uploaded.save(temp_zip)

    try:
        ok, error, restore_info = restore_backup_archive(temp_zip)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if not ok:
        flash(error or "Backup restore failed.")
        return redirect(url_for("backup_restore"))

    # A V2.2-or-earlier backup will not contain the V2.3 activity table.
    # Re-run migrations against the restored database before writing the restore event.
    init_db()
    restored_jobs = (restore_info or {}).get("live_counts", {}).get("jobs", 0)
    restored_backup_at = (restore_info or {}).get("manifest_created_at")

    with get_db() as db:
        if restored_backup_at:
            db.execute(
                "UPDATE app_settings SET last_backup_at = ? WHERE id = 1",
                (restored_backup_at,),
            )
        record_activity(
            db,
            "Backup Restored",
            f"Restored and verified backup containing {restored_jobs} job(s).",
        )
        db.commit()
    flash(
        f"Backup restored and verified: {restored_jobs} job(s) restored, "
        "along with history, Email Outbox data, and uploaded evidence."
    )
    return redirect(url_for("dashboard"))




def get_portfolio_scope(scope_type, scope_id):
    with get_db() as db:
        if scope_type == "CLIENT":
            entity = db.execute(
                "SELECT * FROM clients WHERE id = ?",
                (scope_id,),
            ).fetchone()
            client = entity
        else:
            entity = db.execute("""
                SELECT p.*, c.name AS client_name,
                       c.contact_name AS client_contact_name,
                       c.contact_email AS client_contact_email,
                       c.contact_phone AS client_contact_phone
                FROM projects p
                JOIN clients c ON c.id = p.client_id
                WHERE p.id = ?
            """, (scope_id,)).fetchone()
            client = db.execute(
                "SELECT * FROM clients WHERE id = ?",
                (entity["client_id"],),
            ).fetchone() if entity else None

    return entity, client

def render_portfolio_manager(scope_type, scope_id):
    entity, client = get_portfolio_scope(scope_type, scope_id)
    if not entity:
        abort(404)

    jobs = portfolio_jobs(scope_type, scope_id)
    report_url = public_portfolio_report_url(scope_type, entity)
    default_name = (
        client["contact_name"]
        if client and client["contact_name"]
        else ""
    )
    default_email = (
        client["contact_email"]
        if client and client["contact_email"]
        else ""
    )

    return render_template(
        "portfolio_report.html",
        scope_type=scope_type,
        entity=entity,
        client=client,
        jobs=jobs,
        report_url=report_url,
        default_name=default_name,
        default_email=default_email,
    )

def generate_portfolio_email(scope_type, scope_id):
    entity, client = get_portfolio_scope(scope_type, scope_id)
    if not entity or not client:
        abort(404)

    jobs = portfolio_jobs(scope_type, scope_id)
    if not jobs:
        flash("Add at least one installation before generating a combined report email.")
        return redirect(
            url_for(
                "client_combined_report" if scope_type == "CLIENT" else "project_combined_report",
                **({"client_id": scope_id} if scope_type == "CLIENT" else {"project_id": scope_id}),
            )
        )

    recipient_name = request.form.get("recipient_name", "").strip()
    recipient_email = request.form.get("recipient_email", "").strip()
    if not recipient_email or "@" not in recipient_email:
        flash("Enter a valid client email address.")
        return redirect(
            url_for(
                "client_combined_report" if scope_type == "CLIENT" else "project_combined_report",
                **({"client_id": scope_id} if scope_type == "CLIENT" else {"project_id": scope_id}),
            )
        )

    report_url = public_portfolio_report_url(scope_type, entity)
    subject, html = build_portfolio_report_email(
        scope_type,
        entity,
        client,
        jobs,
        report_url,
        recipient_name=recipient_name,
    )
    sent, error = send_smtp_message(
        recipient_email,
        recipient_name,
        subject,
        html,
    )

    if sent:
        status = "SENT"
    elif EMAIL_MODE == "outbox":
        status = "OUTBOX"
    else:
        status = "FAILED"

    anchor_job_id = jobs[0]["id"]
    scope_label = "Client" if scope_type == "CLIENT" else "Project"
    event_type = (
        "CLIENT_COMBINED_REPORT"
        if scope_type == "CLIENT"
        else "PROJECT_COMBINED_REPORT"
    )

    with get_db() as db:
        log_email_event(
            db,
            anchor_job_id,
            event_type,
            recipient_email,
            recipient_name,
            subject,
            html,
            report_url,
            status,
            error,
            scope_type=scope_type,
            scope_id=scope_id,
            scope_name=entity["name"],
        )
        record_activity(
            db,
            f"{scope_label} Combined Report Generated",
            f"Generated combined report for {entity['name']} to {recipient_email}: {status}.",
        )
        db.commit()

    if status == "SENT":
        flash(f"Combined report emailed to {recipient_email}.")
    elif status == "OUTBOX":
        flash("Combined report generated in Outbox Mode. Nothing was sent externally.")
    else:
        flash(f"Combined report delivery failed: {error}")

    return redirect(
        url_for(
            "client_combined_report" if scope_type == "CLIENT" else "project_combined_report",
            **({"client_id": scope_id} if scope_type == "CLIENT" else {"project_id": scope_id}),
        )
    )

def rotate_portfolio_token(scope_type, scope_id):
    entity, _ = get_portfolio_scope(scope_type, scope_id)
    if not entity:
        abort(404)

    table_name = "clients" if scope_type == "CLIENT" else "projects"
    while True:
        new_token = secrets.token_urlsafe(24)
        with get_db() as db:
            exists = db.execute(
                f"SELECT 1 FROM {table_name} WHERE report_token = ?",
                (new_token,),
            ).fetchone()
        if not exists:
            break

    with get_db() as db:
        db.execute(
            f"UPDATE {table_name} SET report_token = ? WHERE id = ?",
            (new_token, scope_id),
        )
        scope_label = "Client" if scope_type == "CLIENT" else "Project"
        record_activity(
            db,
            f"{scope_label} Combined Report Link Rotated",
            f"Revoked the previous combined report link for {entity['name']}.",
        )
        db.commit()

    flash("Combined report link rotated. The previous link no longer works.")
    return redirect(
        url_for(
            "client_combined_report" if scope_type == "CLIENT" else "project_combined_report",
            **({"client_id": scope_id} if scope_type == "CLIENT" else {"project_id": scope_id}),
        )
    )


@app.route("/clients/<int:client_id>/combined-report", methods=["GET", "POST"])
def client_combined_report(client_id):
    if request.method == "POST":
        return generate_portfolio_email("CLIENT", client_id)
    return render_portfolio_manager("CLIENT", client_id)


@app.post("/clients/<int:client_id>/combined-report/rotate")
def rotate_client_combined_report(client_id):
    return rotate_portfolio_token("CLIENT", client_id)


@app.route("/projects/<int:project_id>/combined-report", methods=["GET", "POST"])
def project_combined_report(project_id):
    if request.method == "POST":
        return generate_portfolio_email("PROJECT", project_id)
    return render_portfolio_manager("PROJECT", project_id)


@app.post("/projects/<int:project_id>/combined-report/rotate")
def rotate_project_combined_report(project_id):
    return rotate_portfolio_token("PROJECT", project_id)


@app.route("/portfolio/client/<token>")
def public_client_portfolio_report(token):
    with get_db() as db:
        entity = db.execute(
            "SELECT * FROM clients WHERE report_token = ?",
            (token,),
        ).fetchone()
    if not entity:
        abort(404)

    report = portfolio_report_data("CLIENT", entity["id"])
    return render_template(
        "public_portfolio_report.html",
        scope_type="CLIENT",
        entity=entity,
        client=entity,
        report=report,
        report_token=token,
        generated_at=now_iso(),
    )


@app.route("/portfolio/project/<token>")
def public_project_portfolio_report(token):
    with get_db() as db:
        entity = db.execute("""
            SELECT p.*, c.name AS client_name,
                   c.contact_email AS client_contact_email,
                   c.contact_phone AS client_contact_phone
            FROM projects p
            JOIN clients c ON c.id = p.client_id
            WHERE p.report_token = ?
        """, (token,)).fetchone()
        client = db.execute(
            "SELECT * FROM clients WHERE id = ?",
            (entity["client_id"],),
        ).fetchone() if entity else None
    if not entity:
        abort(404)

    report = portfolio_report_data("PROJECT", entity["id"])
    return render_template(
        "public_portfolio_report.html",
        scope_type="PROJECT",
        entity=entity,
        client=client,
        report=report,
        report_token=token,
        generated_at=now_iso(),
    )


@app.route("/portfolio/client/<token>/evidence/<int:job_id>/<path:filename>")
def client_portfolio_asset(token, job_id, filename):
    with get_db() as db:
        entity = db.execute(
            "SELECT * FROM clients WHERE report_token = ?",
            (token,),
        ).fetchone()
    if not entity:
        abort(404)
    if not portfolio_evidence_allowed("CLIENT", entity["id"], job_id, filename):
        abort(404)
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/portfolio/project/<token>/evidence/<int:job_id>/<path:filename>")
def project_portfolio_asset(token, job_id, filename):
    with get_db() as db:
        entity = db.execute(
            "SELECT * FROM projects WHERE report_token = ?",
            (token,),
        ).fetchone()
    if not entity:
        abort(404)
    if not portfolio_evidence_allowed("PROJECT", entity["id"], job_id, filename):
        abort(404)
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/clients")
def clients():
    with get_db() as db:
        rows = db.execute("""
            SELECT c.*,
                   COUNT(DISTINCT p.id) AS project_count,
                   COUNT(DISTINCT j.id) AS job_count,
                   COUNT(DISTINCT CASE WHEN j.status = 'COMPLETED' THEN j.id END) AS completed_job_count,
                   COUNT(DISTINCT CASE WHEN j.status != 'COMPLETED' THEN j.id END) AS active_job_count
            FROM clients c
            LEFT JOIN projects p ON p.client_id = c.id
            LEFT JOIN jobs j ON j.client_id = c.id
            GROUP BY c.id
            ORDER BY LOWER(c.name), c.id
        """).fetchall()
    return render_template("clients.html", clients=rows)


@app.route("/clients/new", methods=["GET", "POST"])
def new_client():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        contact_name = request.form.get("contact_name", "").strip()
        contact_email = request.form.get("contact_email", "").strip()
        contact_phone = request.form.get("contact_phone", "").strip()
        notes = request.form.get("notes", "").strip()

        if not name:
            flash("Client Name is required.")
            return redirect(url_for("new_client"))

        report_token = secrets.token_urlsafe(24)
        with get_db() as db:
            duplicate = db.execute(
                "SELECT id FROM clients WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            if duplicate:
                flash("A client with that name already exists.")
                return redirect(url_for("client_detail", client_id=duplicate["id"]))

            cur = db.execute("""
                INSERT INTO clients (
                    report_token, name, contact_name, contact_email, contact_phone,
                    notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report_token, name, contact_name, contact_email, contact_phone,
                notes, now_iso(), now_iso()
            ))
            client_id = cur.lastrowid
            record_activity(db, "Client Added", f"Added client {name}.")
            db.commit()

        flash(f"Client {name} added.")
        return redirect(url_for("client_detail", client_id=client_id))

    return render_template("client_form.html")


@app.route("/clients/<int:client_id>", methods=["GET", "POST"])
def client_detail(client_id):
    with get_db() as db:
        client = db.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        if not client:
            abort(404)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            contact_name = request.form.get("contact_name", "").strip()
            contact_email = request.form.get("contact_email", "").strip()
            contact_phone = request.form.get("contact_phone", "").strip()
            notes = request.form.get("notes", "").strip()

            if not name:
                flash("Client Name is required.")
                return redirect(url_for("client_detail", client_id=client_id))

            duplicate = db.execute(
                "SELECT id FROM clients WHERE name = ? COLLATE NOCASE AND id != ?",
                (name, client_id),
            ).fetchone()
            if duplicate:
                flash("Another client already uses that name.")
                return redirect(url_for("client_detail", client_id=client_id))

            db.execute("""
                UPDATE clients
                SET name = ?, contact_name = ?, contact_email = ?,
                    contact_phone = ?, notes = ?, updated_at = ?
                WHERE id = ?
            """, (name, contact_name, contact_email, contact_phone, notes, now_iso(), client_id))
            record_activity(db, "Client Updated", f"Updated client {name}.")
            db.commit()
            flash(f"Client {name} updated.")
            return redirect(url_for("client_detail", client_id=client_id))

        projects = db.execute("""
            SELECT p.*,
                   COUNT(DISTINCT j.id) AS job_count,
                   COUNT(DISTINCT CASE WHEN j.status = 'COMPLETED' THEN j.id END) AS completed_job_count,
                   COUNT(DISTINCT CASE WHEN j.status != 'COMPLETED' THEN j.id END) AS active_job_count
            FROM projects p
            LEFT JOIN jobs j ON j.project_id = p.id
            WHERE p.client_id = ?
            GROUP BY p.id
            ORDER BY LOWER(p.name), p.id
        """, (client_id,)).fetchall()

        jobs = db.execute("""
            SELECT j.*, p.name AS project_name
            FROM jobs j
            LEFT JOIN projects p ON p.id = j.project_id
            WHERE j.client_id = ?
            ORDER BY CASE WHEN j.status = 'COMPLETED' THEN 1 ELSE 0 END,
                     j.installation_date, j.id
        """, (client_id,)).fetchall()

    return render_template("client_detail.html", client=client, projects=projects, jobs=jobs)


@app.route("/clients/<int:client_id>/projects/new", methods=["GET", "POST"])
def new_project(client_id):
    with get_db() as db:
        client = db.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if not client:
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        project_number = request.form.get("project_number", "").strip()
        location = request.form.get("location", "").strip()
        notes = request.form.get("notes", "").strip()

        if not name:
            flash("Project Name is required.")
            return redirect(url_for("new_project", client_id=client_id))

        report_token = secrets.token_urlsafe(24)
        with get_db() as db:
            duplicate = db.execute("""
                SELECT id FROM projects
                WHERE client_id = ? AND name = ? COLLATE NOCASE
            """, (client_id, name)).fetchone()
            if duplicate:
                flash("That client already has a project with this name.")
                return redirect(url_for("project_detail", project_id=duplicate["id"]))

            cur = db.execute("""
                INSERT INTO projects (
                    report_token, client_id, name, project_number, location,
                    notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report_token, client_id, name, project_number, location,
                notes, now_iso(), now_iso()
            ))
            project_id = cur.lastrowid
            record_activity(db, "Project Added", f"Added project {name} for client {client['name']}.")
            db.commit()

        flash(f"Project {name} added.")
        return redirect(url_for("project_detail", project_id=project_id))

    return render_template("project_form.html", client=client)


@app.route("/projects/<int:project_id>", methods=["GET", "POST"])
def project_detail(project_id):
    with get_db() as db:
        project = db.execute("""
            SELECT p.*, c.name AS client_name
            FROM projects p
            JOIN clients c ON c.id = p.client_id
            WHERE p.id = ?
        """, (project_id,)).fetchone()
        if not project:
            abort(404)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            project_number = request.form.get("project_number", "").strip()
            location = request.form.get("location", "").strip()
            notes = request.form.get("notes", "").strip()

            if not name:
                flash("Project Name is required.")
                return redirect(url_for("project_detail", project_id=project_id))

            duplicate = db.execute("""
                SELECT id FROM projects
                WHERE client_id = ? AND name = ? COLLATE NOCASE AND id != ?
            """, (project["client_id"], name, project_id)).fetchone()
            if duplicate:
                flash("That client already has another project with this name.")
                return redirect(url_for("project_detail", project_id=project_id))

            db.execute("""
                UPDATE projects
                SET name = ?, project_number = ?, location = ?, notes = ?, updated_at = ?
                WHERE id = ?
            """, (name, project_number, location, notes, now_iso(), project_id))
            record_activity(db, "Project Updated", f"Updated project {name} for client {project['client_name']}.")
            db.commit()
            flash(f"Project {name} updated.")
            return redirect(url_for("project_detail", project_id=project_id))

        jobs = db.execute("""
            SELECT *
            FROM jobs
            WHERE project_id = ?
            ORDER BY CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END,
                     installation_date, id
        """, (project_id,)).fetchall()

    return render_template("project_detail.html", project=project, jobs=jobs)


@app.post("/jobs/<int:job_id>/assignment")
def update_job_assignment(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            abort(404)

        client_id, project_id, error = resolve_job_assignment(
            db, request.form.get("client_id"), request.form.get("project_id")
        )
        if error:
            flash(error)
            return redirect(url_for("job_detail", job_id=job_id))

        old_client = db.execute("SELECT name FROM clients WHERE id = ?", (job["client_id"],)).fetchone() if job["client_id"] else None
        old_project = db.execute("SELECT name FROM projects WHERE id = ?", (job["project_id"],)).fetchone() if job["project_id"] else None
        new_client = db.execute("SELECT name FROM clients WHERE id = ?", (client_id,)).fetchone() if client_id else None
        new_project = db.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone() if project_id else None

        db.execute("UPDATE jobs SET client_id = ?, project_id = ? WHERE id = ?", (client_id, project_id, job_id))

        old_label = "Unassigned"
        if old_client:
            old_label = old_client["name"] + (f" / {old_project['name']}" if old_project else "")
        new_label = "Unassigned"
        if new_client:
            new_label = new_client["name"] + (f" / {new_project['name']}" if new_project else "")

        record_activity(
            db, "Job Assignment Changed",
            f"Changed client/project assignment: {old_label} → {new_label}.",
            job_id=job_id
        )
        db.commit()

    flash("Client / project assignment updated.")
    return redirect(url_for("job_detail", job_id=job_id))


@app.route("/help")
def help_center():
    return render_template("help.html")


@app.route("/activity")
def activity_log():
    with get_db() as db:
        events = db.execute("""
            SELECT a.*, j.job_name, j.project_site
            FROM activity_log a
            LEFT JOIN jobs j ON j.id = a.job_id
            ORDER BY a.id DESC
            LIMIT 300
        """).fetchall()

    return render_template(
        "activity_log.html",
        events=events,
    )


@app.route("/")
def dashboard():
    status_filter = (request.args.get("status") or "").strip().upper()
    valid_statuses = {"READY", "REVIEW", "BLOCKED", "NO RESPONSE", "ON SITE"}
    if status_filter not in valid_statuses:
        status_filter = ""

    schedule_filter = (request.args.get("schedule") or "").strip().lower()
    valid_schedule_filters = {"overdue", "today", "next7", "later"}
    if schedule_filter not in valid_schedule_filters:
        schedule_filter = ""

    search_query = (request.args.get("q") or "").strip()

    def parse_filter_id(value):
        try:
            parsed = int(value)
            return parsed if parsed > 0 else None
        except (TypeError, ValueError):
            return None

    client_filter = parse_filter_id(request.args.get("client"))
    project_filter = parse_filter_id(request.args.get("project"))

    with get_db() as db:
        all_jobs = db.execute("""
            SELECT
                j.*,
                c.name AS client_name,
                p.name AS assigned_project_name,
                p.project_number AS assigned_project_number,
                (
                    SELECT COUNT(*)
                    FROM mobilization_attempts ma
                    WHERE ma.job_id = j.id
                ) + 1 AS attempt_number
            FROM jobs j
            LEFT JOIN clients c ON c.id = j.client_id
            LEFT JOIN projects p ON p.id = j.project_id
            WHERE j.status != 'COMPLETED'
            ORDER BY installation_date ASC, j.id DESC
        """).fetchall()

        clients = db.execute("""
            SELECT id, name
            FROM clients
            ORDER BY LOWER(name), id
        """).fetchall()

        projects = db.execute("""
            SELECT id, client_id, name, project_number
            FROM projects
            ORDER BY LOWER(name), id
        """).fetchall()

    counts = {"READY": 0, "REVIEW": 0, "BLOCKED": 0, "NO RESPONSE": 0, "ON SITE": 0}
    schedule_counts = {"overdue": 0, "today": 0, "next7": 0, "later": 0}
    schedule_buckets = {}

    for job in all_jobs:
        counts[job["status"]] = counts.get(job["status"], 0) + 1
        bucket = job_schedule_bucket(job["installation_date"])
        schedule_buckets[job["id"]] = bucket
        if bucket in schedule_counts:
            schedule_counts[bucket] += 1

    search_lower = search_query.lower()
    jobs = []
    for job in all_jobs:
        if status_filter and job["status"] != status_filter:
            continue
        if schedule_filter and schedule_buckets.get(job["id"]) != schedule_filter:
            continue
        if client_filter and job["client_id"] != client_filter:
            continue
        if project_filter and job["project_id"] != project_filter:
            continue
        if search_lower:
            searchable = " ".join([
                job["job_name"] or "",
                job["project_site"] or "",
                job["contact_name"] or "",
                job["contact_email"] or "",
                job["client_name"] or "",
                job["assigned_project_name"] or "",
                job["assigned_project_number"] or "",
            ]).lower()
            if search_lower not in searchable:
                continue
        jobs.append(job)

    filters_active = bool(status_filter or schedule_filter or search_query or client_filter or project_filter)
    due_reminder_count = sum(1 for j in all_jobs if reminder_due(j))

    backup_status = None
    last_backup_at = None
    if current_user_is_admin():
        settings = get_app_settings()
        last_backup_at = settings.get("last_backup_at")
        backup_status = backup_reminder_state(last_backup_at)

    return render_template(
        "dashboard.html",
        jobs=jobs,
        counts=counts,
        status_filter=status_filter,
        schedule_filter=schedule_filter,
        schedule_counts=schedule_counts,
        schedule_buckets=schedule_buckets,
        search_query=search_query,
        client_filter=client_filter,
        project_filter=project_filter,
        clients=clients,
        projects=projects,
        filters_active=filters_active,
        total_active_jobs=len(all_jobs),
        due_reminder_count=due_reminder_count,
        backup_status=backup_status,
        last_backup_at=last_backup_at,
    )


@app.route("/completed")
def completed_jobs():
    search_query = (request.args.get("q") or "").strip()

    def parse_filter_id(value):
        try:
            parsed = int(value)
            return parsed if parsed > 0 else None
        except (TypeError, ValueError):
            return None

    client_filter = parse_filter_id(request.args.get("client"))
    project_filter = parse_filter_id(request.args.get("project"))

    with get_db() as db:
        all_jobs = db.execute("""
            SELECT
                j.*,
                c.name AS client_name,
                p.name AS assigned_project_name,
                p.project_number AS assigned_project_number,
                (
                    SELECT COUNT(*)
                    FROM mobilization_attempts ma
                    WHERE ma.job_id = j.id
                ) + 1 AS attempt_number
            FROM jobs j
            LEFT JOIN clients c ON c.id = j.client_id
            LEFT JOIN projects p ON p.id = j.project_id
            WHERE j.status = 'COMPLETED'
            ORDER BY j.completed_at DESC, j.installation_date DESC, j.id DESC
        """).fetchall()

        clients = db.execute("""
            SELECT id, name
            FROM clients
            ORDER BY LOWER(name), id
        """).fetchall()

        projects = db.execute("""
            SELECT id, client_id, name, project_number
            FROM projects
            ORDER BY LOWER(name), id
        """).fetchall()

    search_lower = search_query.lower()
    jobs = []
    for job in all_jobs:
        if client_filter and job["client_id"] != client_filter:
            continue
        if project_filter and job["project_id"] != project_filter:
            continue
        if search_lower:
            searchable = " ".join([
                job["job_name"] or "",
                job["project_site"] or "",
                job["contact_name"] or "",
                job["contact_email"] or "",
                job["client_name"] or "",
                job["assigned_project_name"] or "",
                job["assigned_project_number"] or "",
            ]).lower()
            if search_lower not in searchable:
                continue
        jobs.append(job)

    filters_active = bool(search_query or client_filter or project_filter)

    return render_template(
        "completed_jobs.html",
        jobs=jobs,
        clients=clients,
        projects=projects,
        search_query=search_query,
        client_filter=client_filter,
        project_filter=project_filter,
        filters_active=filters_active,
        total_completed_jobs=len(all_jobs),
    )

@app.route("/jobs/new", methods=["GET", "POST"])
def new_job():
    if request.method == "POST":
        checklist = [x.strip() for x in request.form.getlist("checklist") if x.strip()]
        if not checklist:
            checklist = DEFAULT_CHECKLIST

        reminder_enabled = 1 if request.form.get("reminder_enabled") == "on" else 0
        reminder_hours_before = int(request.form.get("reminder_hours_before") or DEFAULT_REMINDER_HOURS_BEFORE)
        duplicate_source_id = normalize_optional_id(request.form.get("duplicate_source_id"))

        token = secrets.token_urlsafe(18)
        arrival_token = secrets.token_urlsafe(24)
        client_report_token = secrets.token_urlsafe(24)
        with get_db() as db:
            duplicate_source = None
            if duplicate_source_id:
                duplicate_source = db.execute(
                    "SELECT id, job_name FROM jobs WHERE id = ?",
                    (duplicate_source_id,),
                ).fetchone()

            client_id, project_id, assignment_error = resolve_job_assignment(
                db, request.form.get("client_id"), request.form.get("project_id")
            )
            if assignment_error:
                flash(assignment_error)
                clients, projects = get_clients_and_projects(db)
                return render_template(
                    "new_job.html",
                    default_checklist=checklist,
                    default_reminder_enabled=bool(reminder_enabled),
                    default_reminder_hours=reminder_hours_before,
                    clients=clients,
                    projects=projects,
                    selected_client_id=normalize_optional_id(request.form.get("client_id")),
                    selected_project_id=normalize_optional_id(request.form.get("project_id")),
                    duplicate_source=duplicate_source,
                    form_values={
                        "job_name": request.form.get("job_name", ""),
                        "project_site": request.form.get("project_site", ""),
                        "installation_date": request.form.get("installation_date", ""),
                        "contact_name": request.form.get("contact_name", ""),
                        "contact_email": request.form.get("contact_email", ""),
                        "contact_phone": request.form.get("contact_phone", ""),
                    },
                )

            cur = db.execute("""
                INSERT INTO jobs (
                    public_token, arrival_token, client_report_token,
                    client_id, project_id,
                    job_name, project_site, installation_date,
                    contact_name, contact_email, contact_phone, checklist_json,
                    status, created_at, reminder_enabled, reminder_hours_before,
                    reminder_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'NO RESPONSE', ?, ?, ?, 0)
            """, (
                token,
                arrival_token,
                client_report_token,
                client_id,
                project_id,
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
            record_activity(
                db,
                "Job Created",
                f"Created job {request.form['job_name'].strip()} for {request.form['installation_date']}.",
                job_id=job_id,
            )
            if duplicate_source:
                record_activity(
                    db,
                    "Job Duplicated",
                    (
                        f"Created from {duplicate_source['job_name']} (job #{duplicate_source['id']}). "
                        "Readiness responses, arrival records, evidence, reports, activity, and internal notes were not copied."
                    ),
                    job_id=job_id,
                )
        return redirect(url_for("readiness_request", job_id=job_id))

    duplicate_source = None
    form_values = {
        "job_name": "",
        "project_site": "",
        "installation_date": "",
        "contact_name": "",
        "contact_email": "",
        "contact_phone": "",
    }
    default_checklist = DEFAULT_CHECKLIST
    default_reminder_enabled = DEFAULT_REMINDER_ENABLED
    default_reminder_hours = DEFAULT_REMINDER_HOURS_BEFORE

    with get_db() as db:
        clients, projects = get_clients_and_projects(db)
        selected_client_id = normalize_optional_id(request.args.get("client_id"))
        selected_project_id = normalize_optional_id(request.args.get("project_id"))
        duplicate_from = normalize_optional_id(request.args.get("duplicate_from"))

        if duplicate_from:
            duplicate_source = db.execute(
                "SELECT * FROM jobs WHERE id = ?",
                (duplicate_from,),
            ).fetchone()
            if duplicate_source:
                selected_client_id = duplicate_source["client_id"]
                selected_project_id = duplicate_source["project_id"]
                form_values = {
                    "job_name": duplicate_source["job_name"] or "",
                    "project_site": duplicate_source["project_site"] or "",
                    "installation_date": "",
                    "contact_name": duplicate_source["contact_name"] or "",
                    "contact_email": duplicate_source["contact_email"] or "",
                    "contact_phone": duplicate_source["contact_phone"] or "",
                }
                try:
                    source_checklist = json.loads(duplicate_source["checklist_json"] or "[]")
                    if isinstance(source_checklist, list) and source_checklist:
                        default_checklist = source_checklist
                except (TypeError, ValueError, json.JSONDecodeError):
                    default_checklist = DEFAULT_CHECKLIST

                default_reminder_enabled = bool(duplicate_source["reminder_enabled"])
                default_reminder_hours = int(
                    duplicate_source["reminder_hours_before"] or DEFAULT_REMINDER_HOURS_BEFORE
                )
            else:
                flash("The job you tried to duplicate could not be found.")

        if selected_project_id:
            selected_project = db.execute(
                "SELECT id, client_id FROM projects WHERE id = ?",
                (selected_project_id,),
            ).fetchone()
            if selected_project:
                selected_client_id = selected_project["client_id"]
            else:
                selected_project_id = None

    return render_template(
        "new_job.html",
        default_checklist=default_checklist,
        default_reminder_enabled=default_reminder_enabled,
        default_reminder_hours=default_reminder_hours,
        clients=clients,
        projects=projects,
        selected_client_id=selected_client_id,
        selected_project_id=selected_project_id,
        duplicate_source=duplicate_source,
        form_values=form_values,
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

    if job["status"] == "COMPLETED":
        flash("This job is completed. Its readiness and arrival evidence are preserved.")
        return redirect(url_for("job_detail", job_id=job_id))

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

    if job["status"] == "COMPLETED":
        flash("This job is completed. No new readiness email was generated.")
        return redirect(url_for("job_detail", job_id=job_id))

    public_url = public_readiness_url(job)
    status, error = send_readiness_email_for_job(job, public_url, reminder=False)

    if status == "SENT":
        flash(f"Readiness request emailed to {job['contact_email']}.")
    elif status == "OUTBOX":
        flash("Readiness email generated in Outbox Mode. Nothing was sent externally.")
    else:
        flash(f"Email delivery failed: {error}")

    log_activity(
        "Readiness Request Generated",
        f"Readiness request for {job['contact_name']} <{job['contact_email']}>: {status}.",
        job_id=job_id,
    )
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

    log_activity(
        "Readiness Reminder Generated",
        f"Reminder for {job['contact_name']} <{job['contact_email']}>: {status}.",
        job_id=job_id,
    )
    return redirect(url_for("readiness_request", job_id=job_id))

@app.post("/reminders/run")
def run_reminders_now():
    sent, outbox, failed = run_due_reminders()
    flash(f"Reminder check complete: {sent} sent, {outbox} saved to outbox, {failed} failed.")
    return redirect(url_for("dashboard"))


@app.route("/jobs/<int:job_id>/client-report", methods=["GET", "POST"])
def client_report(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()

    if not job:
        abort(404)

    report_url = public_client_report_url(job)

    if request.method == "POST":
        recipient_name = request.form.get("recipient_name", "").strip()
        recipient_email = request.form.get("recipient_email", "").strip()

        if not recipient_email or "@" not in recipient_email:
            flash("Enter a valid client email address.")
            return redirect(url_for("client_report", job_id=job_id))

        subject, html = build_client_report_email(
            job,
            report_url,
            recipient_name=recipient_name,
        )
        sent, error = send_smtp_message(
            recipient_email,
            recipient_name,
            subject,
            html,
        )

        if sent:
            status = "SENT"
        elif EMAIL_MODE == "outbox":
            status = "OUTBOX"
        else:
            status = "FAILED"

        with get_db() as db:
            log_email_event(
                db,
                job_id,
                "CLIENT_REPORT",
                recipient_email,
                recipient_name,
                subject,
                html,
                report_url,
                status,
                error,
            )
            record_activity(
                db,
                "Client Report Generated",
                f"Client report for {recipient_email}: {status}.",
                job_id=job_id,
            )
            db.commit()

        if status == "SENT":
            flash(f"Client report emailed to {recipient_email}.")
        elif status == "OUTBOX":
            flash("Client report generated in Outbox Mode. Nothing was sent externally.")
        else:
            flash(f"Client report delivery failed: {error}")

        return redirect(url_for("client_report", job_id=job_id))

    return render_template(
        "client_report.html",
        job=job,
        report_url=report_url,
    )


@app.post("/jobs/<int:job_id>/client-report/rotate")
def rotate_client_report(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            abort(404)

        while True:
            new_token = secrets.token_urlsafe(24)
            exists = db.execute(
                "SELECT 1 FROM jobs WHERE client_report_token = ?",
                (new_token,),
            ).fetchone()
            if not exists:
                break

        db.execute(
            "UPDATE jobs SET client_report_token = ? WHERE id = ?",
            (new_token, job_id),
        )
        record_activity(
            db,
            "Client Report Link Rotated",
            "Revoked the previous client report link and generated a new secure link.",
            job_id=job_id,
        )
        db.commit()

    flash("Client report link rotated. The previous link no longer works.")
    return redirect(url_for("client_report", job_id=job_id))


@app.route("/c/<token>")
def public_client_report(token):
    with get_db() as db:
        job = db.execute(
            "SELECT * FROM jobs WHERE client_report_token = ?",
            (token,),
        ).fetchone()

    if not job:
        abort(404)

    report = client_report_data(job)
    with get_db() as db:
        report_client = db.execute(
            "SELECT * FROM clients WHERE id = ?",
            (job["client_id"],),
        ).fetchone() if job["client_id"] else None
        report_project = db.execute(
            "SELECT * FROM projects WHERE id = ?",
            (job["project_id"],),
        ).fetchone() if job["project_id"] else None

    return render_template(
        "public_client_report.html",
        job=job,
        report=report,
        report_client=report_client,
        report_project=report_project,
        report_token=token,
        generated_at=now_iso(),
    )


@app.route("/c/<token>/evidence/<path:filename>")
def client_report_asset(token, filename):
    with get_db() as db:
        job = db.execute(
            "SELECT * FROM jobs WHERE client_report_token = ?",
            (token,),
        ).fetchone()

    if not job:
        abort(404)

    allowed = job_evidence_filenames(job)
    if filename not in allowed:
        abort(404)

    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/email-outbox")
def email_outbox():
    with get_db() as db:
        events = db.execute("""
            SELECT e.*, j.job_name,
                   COALESCE(e.scope_name, j.job_name) AS display_name
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
            SELECT e.*, j.job_name, j.project_site,
                   COALESCE(e.scope_name, j.job_name) AS display_name
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

    if job["status"] == "COMPLETED":
        return render_template("public_job_closed.html", job=job)

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

        confirmed_by = request.form.get("confirmed_by", "").strip()
        confirmed_title = request.form.get("confirmed_title", "").strip()

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
                confirmed_by,
                confirmed_title,
                json.dumps(answers),
                json.dumps(photos),
                token,
            ))
            record_activity(
                db,
                "Readiness Submitted",
                f"Site readiness submitted with status {status} and {len(photos)} photo(s).",
                job_id=job["id"],
                actor_type="SITE CONTACT",
                actor_name=confirmed_by or job["contact_name"] or "Site Contact",
            )
            db.commit()

        return render_template("submitted.html", job=job, status=status)

    return render_template("public_readiness.html", job=job, checklist=checklist)


def save_arrival_submission(job, form, uploaded_files, actor_type=None, actor_name=None):
    """Validate and save one arrival record. Used by internal users and secure public link."""
    if job["arrival_status"]:
        return False, "This mobilization arrival is already locked as evidence.", None

    if job["status"] != "READY":
        return False, "Site arrival cannot be recorded until the current readiness request is marked READY.", None

    arrival_status = form.get("arrival_status")
    reporter = form.get("arrival_reported_by", "").strip()

    if arrival_status not in {"READY", "NOT READY"}:
        return False, "Choose whether the site was ready on arrival.", None

    if not reporter:
        return False, "Enter the installer / reporter name.", None

    issues = form.getlist("issues") if arrival_status == "NOT READY" else []
    crew_size = form.get("crew_size") or None
    hours_lost = form.get("hours_lost") or None
    equipment = form.get("equipment_affected", "").strip()
    notes = form.get("arrival_notes", "").strip()

    valid_uploads = [
        f for f in uploaded_files
        if f and f.filename and allowed_file(f.filename)
    ]

    if arrival_status == "NOT READY":
        if not issues:
            return False, "Select at least one reason the site was not ready.", None

        if crew_size is None or hours_lost is None:
            return False, "Crew Affected and Hours Lost are required for a failed mobilization.", None

        try:
            crew_value = int(crew_size)
            hours_value = float(hours_lost)
        except (TypeError, ValueError):
            return False, "Enter valid numbers for Crew Affected and Hours Lost.", None

        if crew_value < 1:
            return False, "Crew Affected must be at least 1.", None

        if hours_value <= 0:
            return False, "Hours Lost must be greater than 0.", None

        if len(valid_uploads) < 2:
            return False, "Please add at least 2 arrival photos for a failed mobilization.", None

    photos = save_photos(valid_uploads, f"arrival_{job['id']}")
    arrival_time = now_iso()

    new_status = job["status"]
    report_number = job["failed_report_number"]
    report_generated_at = job["failed_report_generated_at"]

    if arrival_status == "NOT READY":
        new_status = "BLOCKED"
        if not report_number:
            report_number = make_report_number(job["id"], arrival_time)
        if not report_generated_at:
            report_generated_at = arrival_time
    elif arrival_status == "READY" and job["status"] != "BLOCKED":
        new_status = "ON SITE"

    with get_db() as db:
        cur = db.execute("""
            UPDATE jobs
            SET arrival_status = ?, arrived_at = ?, arrival_reported_by = ?,
                arrival_issues_json = ?, crew_size = ?, hours_lost = ?,
                equipment_affected = ?, arrival_notes = ?,
                arrival_photos_json = ?, status = ?,
                failed_report_number = ?, failed_report_generated_at = ?
            WHERE id = ? AND arrival_status IS NULL AND status = 'READY'
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
            job["id"],
        ))
        if cur.rowcount == 1:
            event_action = "Site Ready on Arrival" if arrival_status == "READY" else "Failed Mobilization Recorded"
            event_description = (
                f"{reporter} reported the site ready on arrival."
                if arrival_status == "READY"
                else f"{reporter} reported the site not ready: {int(crew_size)} crew affected, {float(hours_lost):g} hour(s) lost."
            )
            record_activity(
                db,
                event_action,
                event_description,
                job_id=job["id"],
                actor_type=actor_type or "INSTALLER",
                actor_name=actor_name or reporter,
            )
        db.commit()

    if cur.rowcount != 1:
        # A second submission won the race; do not leave orphaned files behind.
        for filename in photos:
            try:
                (UPLOAD_DIR / filename).unlink(missing_ok=True)
            except OSError:
                pass
        return False, "This arrival was already recorded by another submission.", None

    return True, None, arrival_status


@app.route("/a/<token>", methods=["GET", "POST"])
def public_arrival(token):
    with get_db() as db:
        job = db.execute(
            "SELECT * FROM jobs WHERE arrival_token = ?",
            (token,),
        ).fetchone()

    if not job:
        abort(404)

    if request.method == "POST":
        ok, error, arrival_status = save_arrival_submission(
            job,
            request.form,
            request.files.getlist("arrival_photos"),
        )

        if not ok:
            flash(error)
            return redirect(url_for("public_arrival", token=token))

        return redirect(url_for("public_arrival", token=token, submitted="1"))

    # Fetch again so GET after POST always reflects the locked record.
    with get_db() as db:
        job = db.execute(
            "SELECT * FROM jobs WHERE arrival_token = ?",
            (token,),
        ).fetchone()

    if job["arrival_status"]:
        return render_template(
            "public_arrival_submitted.html",
            job=job,
            arrival_status=job["arrival_status"],
        )

    if job["status"] != "READY":
        return render_template(
            "public_arrival_unavailable.html",
            job=job,
        )

    return render_template(
        "public_arrival.html",
        job=job,
        issues=ARRIVAL_ISSUES,
    )



@app.post("/jobs/<int:job_id>/complete")
def complete_job(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()

        if not job:
            abort(404)

        if job["status"] == "COMPLETED":
            flash("This job is already completed.")
            return redirect(url_for("job_detail", job_id=job_id))

        if job["arrival_status"] != "READY" or job["status"] != "ON SITE":
            flash("A job can be completed after the installer records a successful Site Ready arrival.")
            return redirect(url_for("job_detail", job_id=job_id))

        # Revoke the shared installer link as soon as the job is completed.
        closed_arrival_token = secrets.token_urlsafe(24)
        completed_at = now_iso()

        db.execute("""
            UPDATE jobs
            SET status='COMPLETED',
                completed_at=?,
                arrival_token=?
            WHERE id=?
        """, (completed_at, closed_arrival_token, job_id))
        record_activity(
            db,
            "Job Completed",
            f"Marked {job['job_name']} complete and revoked the installer link.",
            job_id=job_id,
        )
        db.commit()

    flash("Job marked complete. All readiness and arrival evidence remains preserved.")
    return redirect(url_for("job_detail", job_id=job_id))


@app.post("/jobs/<int:job_id>/reopen")
def reopen_job(job_id):
    with get_db() as db:
        job = db.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()

        if not job:
            abort(404)

        if job["status"] != "COMPLETED":
            flash("Only completed jobs can be reopened.")
            return redirect(url_for("job_detail", job_id=job_id))

        # Jobs can only reach COMPLETED after a successful READY arrival.
        # Reopening restores the operational state without changing any evidence.
        db.execute("""
            UPDATE jobs
            SET status = 'ON SITE',
                completed_at = NULL
            WHERE id = ?
        """, (job_id,))

        record_activity(
            db,
            "Job Reopened",
            (
                f"Reopened {job['job_name']} from COMPLETED to ON SITE. "
                "Readiness, arrival evidence, reports, Office Notes, and prior activity were preserved."
            ),
            job_id=job_id,
        )
        db.commit()

    flash("Job reopened and returned to On Site. Existing evidence and history were preserved.")
    return redirect(url_for("job_detail", job_id=job_id))


@app.post("/jobs/<int:job_id>/notes")
def add_job_note(job_id):
    note_text = request.form.get("note_text", "").strip()

    if not note_text:
        flash("Enter a note before saving.")
        return redirect(url_for("job_detail", job_id=job_id) + "#internal-notes")

    if len(note_text) > 2000:
        flash("Internal notes can be up to 2,000 characters.")
        return redirect(url_for("job_detail", job_id=job_id) + "#internal-notes")

    with get_db() as db:
        job = db.execute(
            "SELECT id FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if not job:
            abort(404)

        db.execute("""
            INSERT INTO job_notes (
                job_id, note_text, actor_type, actor_name, created_at
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            job_id,
            note_text,
            current_user_role() or "USER",
            current_display_name() or current_username() or "Internal User",
            now_iso(),
        ))
        db.commit()

    flash("Internal job note saved.")
    return redirect(url_for("job_detail", job_id=job_id) + "#internal-notes")


@app.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
def edit_job(job_id):
    with get_db() as db:
        job = db.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if not job:
            abort(404)

        if job["status"] == "COMPLETED":
            flash("Completed jobs are locked. Reopen/reset the job before changing its setup.")
            return redirect(url_for("job_detail", job_id=job_id))

        if request.method == "POST":
            job_name = request.form.get("job_name", "").strip()
            project_site = request.form.get("project_site", "").strip()
            installation_date = request.form.get("installation_date", "").strip()
            contact_name = request.form.get("contact_name", "").strip()
            contact_email = request.form.get("contact_email", "").strip()
            contact_phone = request.form.get("contact_phone", "").strip()
            reminder_enabled = 1 if request.form.get("reminder_enabled") == "on" else 0

            try:
                reminder_hours_before = int(
                    request.form.get("reminder_hours_before") or DEFAULT_REMINDER_HOURS_BEFORE
                )
            except ValueError:
                reminder_hours_before = DEFAULT_REMINDER_HOURS_BEFORE

            if reminder_hours_before not in {24, 48, 72}:
                reminder_hours_before = DEFAULT_REMINDER_HOURS_BEFORE

            if not job_name or not installation_date or not contact_name or not contact_email:
                flash("Job Name, Installation Date, Site Contact, and Email are required.")
                return render_template(
                    "edit_job.html",
                    job=job,
                    form_values={
                        "job_name": job_name,
                        "project_site": project_site,
                        "installation_date": installation_date,
                        "contact_name": contact_name,
                        "contact_email": contact_email,
                        "contact_phone": contact_phone,
                        "reminder_enabled": reminder_enabled,
                        "reminder_hours_before": reminder_hours_before,
                    },
                )

            changes = []

            def note_change(label, old_value, new_value):
                old_text = "" if old_value is None else str(old_value)
                new_text = "" if new_value is None else str(new_value)
                if old_text != new_text:
                    changes.append(f"{label}: {old_text or '—'} → {new_text or '—'}")

            note_change("Job Name", job["job_name"], job_name)
            note_change("Project / Site", job["project_site"], project_site)
            note_change("Install Date", job["installation_date"], installation_date)
            note_change("Site Contact", job["contact_name"], contact_name)
            note_change("Contact Email", job["contact_email"], contact_email)
            note_change("Contact Phone", job["contact_phone"], contact_phone)
            note_change(
                "Automatic Reminder",
                "Enabled" if job["reminder_enabled"] else "Disabled",
                "Enabled" if reminder_enabled else "Disabled",
            )
            note_change(
                "Reminder Window",
                f"{job['reminder_hours_before']} hours" if job["reminder_hours_before"] else "—",
                f"{reminder_hours_before} hours",
            )

            if changes:
                db.execute("""
                    UPDATE jobs
                    SET job_name = ?,
                        project_site = ?,
                        installation_date = ?,
                        contact_name = ?,
                        contact_email = ?,
                        contact_phone = ?,
                        reminder_enabled = ?,
                        reminder_hours_before = ?
                    WHERE id = ?
                """, (
                    job_name,
                    project_site,
                    installation_date,
                    contact_name,
                    contact_email,
                    contact_phone,
                    reminder_enabled,
                    reminder_hours_before,
                    job_id,
                ))

                record_activity(
                    db,
                    "Job Details Updated",
                    " · ".join(changes),
                    job_id=job_id,
                )
                db.commit()
                flash("Job details updated.")
            else:
                flash("No job detail changes were made.")

            return redirect(url_for("job_detail", job_id=job_id))

        form_values = {
            "job_name": job["job_name"] or "",
            "project_site": job["project_site"] or "",
            "installation_date": job["installation_date"] or "",
            "contact_name": job["contact_name"] or "",
            "contact_email": job["contact_email"] or "",
            "contact_phone": job["contact_phone"] or "",
            "reminder_enabled": int(job["reminder_enabled"] or 0),
            "reminder_hours_before": int(
                job["reminder_hours_before"] or DEFAULT_REMINDER_HOURS_BEFORE
            ),
        }

    return render_template(
        "edit_job.html",
        job=job,
        form_values=form_values,
    )


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
        activity_events = db.execute("""
            SELECT *
            FROM activity_log
            WHERE job_id = ?
            ORDER BY id DESC
            LIMIT 100
        """, (job_id,)).fetchall()
        job_notes = db.execute("""
            SELECT *
            FROM job_notes
            WHERE job_id = ?
            ORDER BY id DESC
            LIMIT 100
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
    arrival_url = public_arrival_url(job) if job["arrival_token"] else None
    client_report_url = public_client_report_url(job) if job["client_report_token"] else None

    with get_db() as db:
        assigned_client = db.execute(
            "SELECT * FROM clients WHERE id = ?",
            (job["client_id"],),
        ).fetchone() if job["client_id"] else None
        assigned_project = db.execute(
            "SELECT * FROM projects WHERE id = ?",
            (job["project_id"],),
        ).fetchone() if job["project_id"] else None
        assignment_clients, assignment_projects = get_clients_and_projects(db)

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
        arrival_url=arrival_url,
        client_report_url=client_report_url,
        activity_events=activity_events,
        job_notes=job_notes,
        assigned_client=assigned_client,
        assigned_project=assigned_project,
        assignment_clients=assignment_clients,
        assignment_projects=assignment_projects,
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
        ok, error, arrival_status = save_arrival_submission(
            job,
            request.form,
            request.files.getlist("arrival_photos"),
            actor_type=current_user_role() or "USER",
            actor_name=current_display_name() or current_username() or "Internal User",
        )

        if not ok:
            flash(error)
            return redirect(url_for("record_arrival", job_id=job_id))

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

        if job["status"] == "COMPLETED":
            flash("Completed jobs are locked. Their evidence remains available in Completed Jobs.")
            return redirect(url_for("job_detail", job_id=job_id))

        if job["arrival_status"]:
            attempt_number = archive_current_mobilization(db, job)
            message = f"Mobilization Attempt #{attempt_number} was archived. A new readiness confirmation can now be collected."
            activity_action = "Next Mobilization Started"
            activity_description = f"Archived Mobilization Attempt #{attempt_number} and started a new readiness cycle."
        elif job["response_at"]:
            archive_current_confirmation(db, job)
            message = "The previous confirmation was archived. A new readiness confirmation can now be collected."
            activity_action = "New Confirmation Requested"
            activity_description = "Archived the current readiness confirmation and started a new confirmation cycle."
        else:
            message = "A new readiness confirmation can now be collected."
            activity_action = "Readiness Cycle Reset"
            activity_description = "Started a fresh readiness confirmation cycle."

        # Every new confirmation/mobilization gets a fresh installer-arrival link.
        # This revokes any installer link that may have been shared for the prior attempt.
        new_arrival_token = secrets.token_urlsafe(24)

        db.execute("""
            UPDATE jobs
            SET arrival_token=?,
                status='NO RESPONSE',
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
        """, (new_arrival_token, job_id))
        record_activity(
            db,
            activity_action,
            activity_description,
            job_id=job_id,
        )
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

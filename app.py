
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, send_file, flash, abort, session, has_request_context
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
import csv
import io
import hashlib
import time
import requests
from email.message import EmailMessage
from urllib.parse import urlencode, urlparse
from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError, URLError
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

# V2.43 lightweight contractor discovery. The same Foursquare service key used by
# Leosson Contractor Finder can be reused here. DispatchProof keeps this as a
# job/crew workflow feature rather than a separate contractor-management app.
CONTRACTOR_SEARCH_API_KEY = (
    os.getenv("DISPATCHPROOF_FOURSQUARE_API_KEY", "").strip()
    or os.getenv("FOURSQUARE_SERVICE_API_KEY", "").strip()
)
CONTRACTOR_SEARCH_CACHE_TTL_SECONDS = max(0, int(os.getenv("CONTRACTOR_SEARCH_CACHE_TTL_SECONDS", "600")))
CONTRACTOR_SEARCH_FALLBACK_MIN_RESULTS = max(1, int(os.getenv("CONTRACTOR_SEARCH_FALLBACK_MIN_RESULTS", "8")))
_CONTRACTOR_SEARCH_CACHE = {}

# V2.44 rollout route optimization. This uses the HeiGIT/openrouteservice
# optimization + directions services. A separate free API key is used so
# contractor-search credits remain completely independent.
ROUTE_OPTIMIZATION_API_KEY = (
    os.getenv("DISPATCHPROOF_ORS_API_KEY", "").strip()
    or os.getenv("OPENROUTESERVICE_API_KEY", "").strip()
)
ROUTE_OPTIMIZER_MAX_JOBS = max(2, min(40, int(os.getenv("ROUTE_OPTIMIZER_MAX_JOBS", "40"))))
ROUTE_GEOCODE_CACHE_TTL_DAYS = max(1, int(os.getenv("ROUTE_GEOCODE_CACHE_TTL_DAYS", "90")))


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
DOCUMENT_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "csv", "txt", "png", "jpg", "jpeg", "webp", "dwg", "dxf"}
MAX_JOB_DOCUMENT_BYTES = 20 * 1024 * 1024

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
app.config["MAX_CONTENT_LENGTH"] = 110 * 1024 * 1024
MAX_WORKSPACE_RESTORE_BYTES = 100 * 1024 * 1024
MAX_WORKSPACE_RESTORE_EXPANDED_BYTES = 300 * 1024 * 1024
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
        "crew_lead": "TEXT",
        "planned_crew_size": "INTEGER",
        "assigned_crew": "TEXT",
        "owner_user_id": "INTEGER",
        "team_id": "INTEGER",
    }
    for name, sql_type in needed.items():
        if name not in existing:
            db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {sql_type}")

    # V2.41: crew records can represent either internal crew or a subcontractor.
    # Existing records stay Internal Crew so upgrades do not change scheduling behavior.
    crew_existing = {row["name"] for row in db.execute("PRAGMA table_info(crew_members)").fetchall()}
    crew_needed = {
        "member_type": "TEXT NOT NULL DEFAULT 'INTERNAL'",
        "company_name": "TEXT",
        "source_provider": "TEXT",
        "source_place_id": "TEXT",
        "source_address": "TEXT",
        "source_website": "TEXT",
    }
    for name, sql_type in crew_needed.items():
        if name not in crew_existing:
            db.execute(f"ALTER TABLE crew_members ADD COLUMN {name} {sql_type}")
    db.execute("""
        UPDATE crew_members
        SET member_type = 'INTERNAL'
        WHERE member_type IS NULL
           OR TRIM(member_type) = ''
           OR UPPER(member_type) NOT IN ('INTERNAL', 'SUBCONTRACTOR')
    """)

    # V2.37: PM-owned jobs with optional team collaboration. Existing jobs
    # intentionally keep owner_user_id/team_id NULL so only Owner/Admin sees
    # legacy records until a new owner/team is explicitly assigned.
    db.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE,
            share_jobs INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(team_id, user_id),
            FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # V2.40: remember user-scoped workspace restore items so the same
    # exported job cannot be accidentally imported twice.
    db.execute("""
        CREATE TABLE IF NOT EXISTS workspace_restore_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source_identity TEXT NOT NULL,
            source_job_id INTEGER,
            restored_job_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, source_identity),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(restored_job_id) REFERENCES jobs(id) ON DELETE CASCADE
        )
    """)

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
        CREATE TABLE IF NOT EXISTS job_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            original_filename TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            content_type TEXT,
            actor_type TEXT NOT NULL,
            actor_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS project_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            original_filename TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            content_type TEXT,
            actor_type TEXT NOT NULL,
            actor_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS client_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            original_filename TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            content_type TEXT,
            actor_type TEXT NOT NULL,
            actor_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
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


    # V2.42: secure PM-to-field requests plus reusable daily progress evidence.
    # These tables are intentionally independent from readiness/arrival evidence so
    # field communication cannot rewrite or unlock proven mobilization records.
    db.execute("""
        CREATE TABLE IF NOT EXISTS field_update_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            crew_member_id INTEGER,
            recipient_name TEXT NOT NULL,
            recipient_email TEXT,
            request_note TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            revoked_at TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
            FOREIGN KEY(crew_member_id) REFERENCES crew_members(id) ON DELETE SET NULL
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS field_progress_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            field_link_id INTEGER,
            entry_type TEXT NOT NULL,
            submitted_by TEXT NOT NULL,
            work_date TEXT NOT NULL,
            work_completed TEXT,
            notes TEXT,
            crew_size INTEGER,
            hours_worked REAL,
            issues_delays TEXT,
            photo_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
            FOREIGN KEY(field_link_id) REFERENCES field_update_links(id) ON DELETE SET NULL
        )
    """)

    # V2.44: saved route plans are private to the creator (Owner/Admin may still
    # view all underlying jobs normally). This prevents one PM's private rollout
    # sequence from exposing job names to another PM.
    db.execute("""
        CREATE TABLE IF NOT EXISTS project_route_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            owner_key TEXT NOT NULL,
            start_address TEXT NOT NULL,
            start_lat REAL NOT NULL,
            start_lon REAL NOT NULL,
            return_to_start INTEGER NOT NULL DEFAULT 0,
            total_distance_m REAL NOT NULL DEFAULT 0,
            total_duration_s REAL NOT NULL DEFAULT 0,
            route_geometry_json TEXT,
            provider_name TEXT NOT NULL DEFAULT 'openrouteservice',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, owner_key),
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS project_route_stops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_plan_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            stop_order INTEGER NOT NULL,
            route_address TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            leg_distance_m REAL NOT NULL DEFAULT 0,
            leg_duration_s REAL NOT NULL DEFAULT 0,
            UNIQUE(route_plan_id, job_id),
            UNIQUE(route_plan_id, stop_order),
            FOREIGN KEY(route_plan_id) REFERENCES project_route_plans(id) ON DELETE CASCADE,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS route_geocode_cache (
            address_key TEXT PRIMARY KEY,
            original_address TEXT NOT NULL,
            formatted_address TEXT,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            cached_at TEXT NOT NULL
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


def normalize_crew_member_type(value):
    value = str(value or "").strip().upper()
    return value if value in {"INTERNAL", "SUBCONTRACTOR"} else "INTERNAL"


# V2.43 contractor discovery intentionally reuses only the lightweight search
# purpose of Leosson Contractor Finder. Saved results become normal DispatchProof
# subcontractor directory records and then use the existing assignment/schedule logic.
CONTRACTOR_COUNTRY_CONFIG = {
    "US": {"name": "United States", "unit": "mi"},
    "CA": {"name": "Canada", "unit": "km"},
    "GB": {"name": "United Kingdom", "unit": "km"},
    "AU": {"name": "Australia", "unit": "km"},
    "IE": {"name": "Ireland", "unit": "km"},
    "NZ": {"name": "New Zealand", "unit": "km"},
}

CONTRACTOR_TRADE_CONFIG = {
    "millwork": {"label": "Millwork / Carpentry", "terms": ["finish carpenter", "millwork installer" ]},
    "plumbing": {"label": "Plumbing", "terms": ["commercial plumber", "plumbing contractor"]},
    "electrical": {"label": "Electrical", "terms": ["commercial electrician", "electrical contractor"]},
    "hvac": {"label": "HVAC", "terms": ["commercial hvac contractor", "hvac contractor"]},
    "flooring": {"label": "Flooring", "terms": ["commercial flooring contractor", "flooring installer"]},
    "painting": {"label": "Painting", "terms": ["commercial painter", "painting contractor"]},
    "drywall": {"label": "Drywall", "terms": ["drywall contractor", "commercial drywall contractor"]},
    "fixtures": {"label": "Fixtures / Displays", "terms": ["fixture installer", "retail fixture installer"]},
    "handyman": {"label": "Handyman / Punch", "terms": ["handyman", "finish carpenter"]},
    "roofing": {"label": "Roofing", "terms": ["commercial roofer", "roofing contractor"]},
    "concrete_masonry": {"label": "Concrete / Masonry", "terms": ["commercial concrete contractor", "masonry contractor"]},
    "cleaning": {"label": "Cleaning / Janitorial", "terms": ["commercial cleaning service", "janitorial service"]},
    "low_voltage": {"label": "Data / Low Voltage", "terms": ["low voltage contractor", "data cabling contractor"]},
    "landscaping": {"label": "Landscaping", "terms": ["commercial landscaper", "landscape contractor"]},
}


class ContractorSearchError(Exception):
    pass


def contractor_country_info(code):
    return CONTRACTOR_COUNTRY_CONFIG.get(str(code or "US").upper(), CONTRACTOR_COUNTRY_CONFIG["US"])


def contractor_search_cache_get(key):
    if CONTRACTOR_SEARCH_CACHE_TTL_SECONDS <= 0:
        return None
    row = _CONTRACTOR_SEARCH_CACHE.get(key)
    if not row:
        return None
    created, value = row
    if time.monotonic() - created > CONTRACTOR_SEARCH_CACHE_TTL_SECONDS:
        _CONTRACTOR_SEARCH_CACHE.pop(key, None)
        return None
    return value


def contractor_search_cache_put(key, value, max_entries=300):
    if len(_CONTRACTOR_SEARCH_CACHE) >= max_entries:
        oldest = min(_CONTRACTOR_SEARCH_CACHE.items(), key=lambda item: item[1][0])[0]
        _CONTRACTOR_SEARCH_CACHE.pop(oldest, None)
    _CONTRACTOR_SEARCH_CACHE[key] = (time.monotonic(), value)


def contractor_http_json(url, params=None, headers=None, timeout=20):
    if params:
        url = f"{url}?{urlencode(params)}"
    req = URLRequest(url, headers=headers or {})
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body or "null")
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            body = ""
        lowered = body.lower()
        if exc.code in (402, 403) or "credit" in lowered or "billing" in lowered:
            raise ContractorSearchError("Contractor search is unavailable because the search service key or billing needs attention.")
        if exc.code == 429:
            raise ContractorSearchError("Contractor search is temporarily busy. Wait a moment and try again.")
        raise ContractorSearchError("The contractor search service returned an error. Please try again.")
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print(f"Contractor search request failed: {exc}")
        raise ContractorSearchError("Contractor search could not reach the search service. Please try again.")


def contractor_geocode(location, country="US"):
    location = str(location or "").strip()
    if not location:
        raise ContractorSearchError("Enter a city, state/province, or job location to search.")
    data = contractor_http_json(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": location,
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": str(country or "US").lower(),
        },
        headers={"User-Agent": "DispatchProof/2.44 contractor-discovery"},
        timeout=20,
    )
    if not isinstance(data, list) or not data:
        raise ContractorSearchError(f'Could not locate "{location}". Try a city plus state/province or postal code.')
    return float(data[0]["lat"]), float(data[0]["lon"])


def contractor_provider_search(query, lat, lon, radius_value, limit=50, exclude_chains=True, country="US"):
    if not CONTRACTOR_SEARCH_API_KEY:
        raise ContractorSearchError("Contractor search is not configured yet. Add the Foursquare service API key in Render first.")
    info = contractor_country_info(country)
    radius_meters = min(
        int(float(radius_value) * (1609.344 if info["unit"] == "mi" else 1000)),
        100000,
    )
    key = (
        str(query or "").strip().lower(), round(float(lat), 4), round(float(lon), 4),
        radius_meters, min(int(limit), 50), bool(exclude_chains), str(country or "US").upper(),
    )
    cached = contractor_search_cache_get(key)
    if cached is not None:
        return cached, True
    params = {
        "query": query,
        "ll": f"{lat},{lon}",
        "radius": radius_meters,
        "limit": min(int(limit), 50),
        "sort": "RELEVANCE",
        "tel_format": "NATIONAL",
    }
    if exclude_chains:
        params["exclude_all_chains"] = "true"
    data = contractor_http_json(
        "https://places-api.foursquare.com/places/search",
        params=params,
        headers={
            "Authorization": f"Bearer {CONTRACTOR_SEARCH_API_KEY}",
            "X-Places-Api-Version": "2025-06-17",
            "Accept": "application/json",
            "User-Agent": "DispatchProof/2.44 contractor-discovery",
        },
        timeout=30,
    )
    results = data if isinstance(data, list) else ((data or {}).get("results") or (data or {}).get("places") or [])
    contractor_search_cache_put(key, results)
    return results, False


def contractor_place_name(place):
    return place.get("name") or place.get("display_name") or "Unnamed contractor"


def contractor_place_id(place):
    return place.get("fsq_place_id") or place.get("fsq_id") or place.get("id") or contractor_place_name(place)


def contractor_place_phone(place):
    return place.get("tel") or place.get("telephone") or place.get("phone") or ""


def contractor_place_website(place):
    value = place.get("website") or place.get("website_url") or place.get("url") or ""
    try:
        parsed = urlparse(value)
        return value if parsed.scheme in {"http", "https"} else ""
    except Exception:
        return ""


def contractor_place_address(place):
    loc = place.get("location") or {}
    if not isinstance(loc, dict):
        return str(loc or "")
    return loc.get("formatted_address") or ", ".join(
        str(x) for x in [loc.get("address"), loc.get("locality"), loc.get("region"), loc.get("postcode")] if x
    )


def contractor_place_categories(place):
    out = []
    for category in place.get("categories") or []:
        if isinstance(category, dict):
            name = category.get("name") or category.get("short_name") or ""
        else:
            name = str(category)
        if name:
            out.append(name)
    if not out and place.get("category"):
        out.append(str(place.get("category")))
    return out


def contractor_place_country(place):
    loc = place.get("location") or {}
    if not isinstance(loc, dict):
        loc = {}
    code = str(loc.get("country_code") or place.get("country_code") or "").upper().strip()
    if code:
        return "GB" if code == "UK" else code
    country = str(loc.get("country") or place.get("country") or "").strip().lower()
    names = {
        "united states": "US", "united states of america": "US", "usa": "US", "us": "US",
        "canada": "CA", "united kingdom": "GB", "uk": "GB", "great britain": "GB",
        "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB",
        "australia": "AU", "ireland": "IE", "republic of ireland": "IE", "new zealand": "NZ",
    }
    return names.get(country, "")


def contractor_obvious_non_service_business(place, trade):
    """Reject obvious stores/showrooms/suppliers without hiding real installers.

    Foursquare sometimes gives a retail cabinet showroom a Carpenter category, so
    category matching alone is not enough. We use strong retail name phrases as a
    second guard, but allow names that clearly advertise installation/contracting.
    """
    name = contractor_place_name(place).lower()
    categories = " | ".join(contractor_place_categories(place)).lower()

    service_category_cues = [
        "carpenter", "contractor", "construction", "installer", "installation",
        "repair service", "maintenance", "home service", "home improvement",
        "plumber", "electrician", "roofer", "landscaper", "janitorial service",
        "cleaning service", "mason",
    ]
    retail_category_cues = [
        "retail store", "miscellaneous store", "furniture store", "hardware store",
        "home improvement store", "building supply", "supply store", "wholesaler",
        "showroom", "interior design", "kitchen supply", "bathroom supply",
        "lighting store", "electronics store", "computer store", "garden center",
        "nursery", "florist", "appliance store",
    ]
    if any(word in categories for word in retail_category_cues) and not any(
        word in categories for word in service_category_cues
    ):
        return True

    service_name_cues = [
        "install", "contract", "carpenter", "millwork", "casework", "construction",
        "service", "repair", "remodel", "maintenance",
    ]
    trade_retail_name_cues = {
        "millwork": [
            "cabinet sales", "cabinet gallery", "cabinet showroom", "cabinet outlet",
            "cabinet liquidator", "cabinet liquidators", "cabinet warehouse",
            "warehouse cabinet", "cabinet distributor", "cabinet distributors",
            "kitchen showroom", "kitchen gallery", "kitchen cabinet sales",
        ],
        "plumbing": ["plumbing supply", "plumbing showroom"],
        "electrical": ["electrical supply", "lighting showroom", "lighting gallery"],
        "hvac": ["hvac supply", "heating supply", "air conditioning supply"],
        "flooring": ["flooring store", "flooring showroom", "carpet store", "tile store"],
        "painting": ["paint store", "paint supply"],
        "drywall": ["drywall supply", "building supply"],
        "fixtures": ["fixture showroom", "fixture supply", "display showroom"],
        "handyman": ["hardware store", "home improvement store"],
        "roofing": ["roofing supply", "building supply"],
        "concrete_masonry": ["concrete supply", "stone supplier", "masonry supply"],
        "cleaning": ["cleaning supply", "janitorial supply", "laundromat", "dry cleaner"],
        "low_voltage": ["electronics store", "computer store", "electrical supply"],
        "landscaping": ["landscape supply", "garden center", "plant nursery"],
    }
    if any(word in name for word in trade_retail_name_cues.get(trade, [])) and not any(
        word in name for word in service_name_cues
    ):
        return True

    # Millwork searches are specifically for people who can perform field work,
    # not cabinet retailers/manufacturers that happen to carry a Carpenter tag.
    # Foursquare often labels cabinet companies as Carpenter, so for an ambiguous
    # cabinet business name we require the NAME itself to advertise field service.
    if trade == "millwork":
        field_service_name_cues = [
            "install", "installer", "installation", "contract", "contractor",
            "carpenter", "carpentry", "construction", "remodel", "service",
            "repair", "handyman",
        ]
        ambiguous_cabinet_business = any(word in name for word in [
            "cabinet", "cabinetry", "kitchen", "closet",
        ])
        shop_or_retail_name = any(word in name for word in [
            " store", "store ", " shop", "shop ", "showroom", "gallery",
            "sales", "warehouse", "liquidat", "outlet", "supply", "supplier",
            "design", "distributor",
        ])
        advertises_field_service = any(word in name for word in field_service_name_cues)
        if (ambiguous_cabinet_business or shop_or_retail_name) and not advertises_field_service:
            return True

    # Global non-contractor business types that should never surface as subs.
    global_non_service = [
        "loan", "bank", "finance", "property management", "real estate",
        "insurance agency", "employment agency",
    ]
    return any(word in (name + " | " + categories) for word in global_non_service)


def contractor_trade_match_strength(place, trade):
    name = contractor_place_name(place).lower()
    categories = " | ".join(contractor_place_categories(place)).lower()
    blob = name + " | " + categories
    if contractor_obvious_non_service_business(place, trade):
        return 0
    explicit = {
        "millwork": ["carpenter", "cabinet maker", "millwork", "casework", "woodworker", "cabinet installer"],
        "plumbing": ["plumber", "plumbing contractor", "plumbing service"],
        "electrical": ["electrician", "electrical contractor", "electrical service"],
        "hvac": ["hvac", "air conditioning contractor", "heating contractor", "mechanical contractor"],
        "flooring": ["flooring contractor", "flooring installer", "tile contractor", "tile installer", "carpet installer"],
        "painting": ["painter", "painting contractor", "commercial painter"],
        "drywall": ["drywall contractor", "drywall installer", "sheetrock", "gypsum contractor"],
        "fixtures": ["fixture installer", "fixture contractor", "retail fixture", "display installer"],
        "handyman": ["handyman", "maintenance contractor", "property maintenance", "finish carpenter"],
        "roofing": ["roofer", "roofing contractor", "roofing company", "commercial roofing"],
        "concrete_masonry": ["concrete contractor", "masonry contractor", "mason", "brick mason", "concrete construction"],
        "cleaning": ["commercial cleaning", "janitorial service", "cleaning service", "construction cleaning", "post construction cleaning"],
        "low_voltage": ["low voltage contractor", "data cabling", "structured cabling", "network cabling", "telecommunications contractor", "security system installer"],
        "landscaping": ["landscaper", "landscape contractor", "landscaping", "grounds maintenance", "landscape installation"],
    }
    name_terms = {
        "millwork": ["millwork", "cabinet", "casework", "carpentry", "carpenter", "woodwork"],
        "plumbing": ["plumb", "plumber"], "electrical": ["electric", "electrician"],
        "hvac": ["hvac", "heating", "air conditioning", "mechanical"],
        "flooring": ["floor", "flooring", "tile", "carpet"], "painting": ["paint", "painting", "painter"],
        "drywall": ["drywall", "sheetrock", "gypsum"], "fixtures": ["fixture", "display", "store fixture"],
        "handyman": ["handyman", "maintenance", "carpentry", "repair"], "roofing": ["roof", "roofing", "roofer"],
        "concrete_masonry": ["concrete", "masonry", "mason", "brick", "block"],
        "cleaning": ["cleaning", "janitorial", "cleaners", "clean"],
        "low_voltage": ["low voltage", "data", "cabling", "structured cabling", "network cabling", "security", "access control"],
        "landscaping": ["landscape", "landscaping", "lawn", "grounds", "irrigation"],
    }
    competing = {
        "plumbing": ["electrician", "electrical contractor", "hvac", "roofing", "concrete", "flooring", "painting"],
        "electrical": ["plumber", "plumbing contractor", "hvac", "roofing", "concrete", "flooring", "painting"],
        "hvac": ["plumber", "electrician", "roofing", "concrete", "flooring", "painting"],
        "flooring": ["plumber", "electrician", "hvac", "roofing", "painting contractor"],
        "painting": ["plumber", "electrician", "hvac", "roofing", "flooring contractor"],
        "drywall": ["plumber", "electrician", "hvac", "roofing", "flooring contractor"],
        "millwork": ["plumber", "electrician", "hvac", "roofing", "concrete contractor"],
        "fixtures": ["plumber", "electrician", "hvac", "roofing", "concrete contractor"],
        "handyman": [],
        "roofing": ["plumber", "electrician", "hvac", "flooring contractor", "painting contractor", "concrete contractor"],
        "concrete_masonry": ["plumber", "electrician", "hvac", "roofing contractor", "flooring contractor"],
        "cleaning": ["plumber", "electrician", "hvac", "roofing contractor", "concrete contractor"],
        "low_voltage": ["plumber", "roofing contractor", "concrete contractor", "landscaper"],
        "landscaping": ["plumber", "electrician", "hvac", "roofing contractor"],
    }
    if any(word in blob for word in competing.get(trade, [])):
        return 0
    if any(word in categories for word in explicit.get(trade, [])):
        return 3
    broad_service = any(word in categories for word in [
        "general contractor", "contractor", "construction", "home service", "home improvement", "repair service", "maintenance"
    ])
    if any(word in name for word in name_terms.get(trade, [])) and broad_service:
        return 2
    if broad_service:
        return 1
    return 0


def contractor_place_relevant(place, tolerance, trade):
    strength = contractor_trade_match_strength(place, trade)
    if tolerance == "strict":
        return strength >= 3
    if tolerance == "broad":
        return strength >= 1
    return strength >= 2


def contractor_fit_score(place, trade):
    strength = contractor_trade_match_strength(place, trade)
    score = {0: 0, 1: 42, 2: 68, 3: 82}.get(strength, 0)
    if contractor_place_phone(place):
        score += 5
    if contractor_place_website(place):
        score += 2
    name = contractor_place_name(place).lower()
    if any(word in name for word in ["service", "services", "repair", "install", "contracting"]):
        score += 3
    return max(0, min(99, round(score, 1)))


def run_contractor_search(location, country, trade, radius, tolerance, max_results=15):
    country = str(country or "US").upper()
    if country not in CONTRACTOR_COUNTRY_CONFIG:
        country = "US"
    trade = trade if trade in CONTRACTOR_TRADE_CONFIG else "handyman"
    tolerance = tolerance if tolerance in {"strict", "balanced", "broad"} else "balanced"
    unit = contractor_country_info(country)["unit"]
    max_radius = 60 if unit == "mi" else 100
    try:
        radius = max(1, min(max_radius, int(radius)))
    except (TypeError, ValueError):
        radius = 30
    lat, lon = contractor_geocode(location, country)
    terms = CONTRACTOR_TRADE_CONFIG[trade]["terms"]
    seen = {}
    provider_calls = 0
    cache_hits = 0

    def add_results(rows):
        for place in rows or []:
            seen.setdefault(str(contractor_place_id(place)), place)

    def usable_count():
        total = 0
        for place in seen.values():
            place_country = contractor_place_country(place)
            if place_country and place_country != country:
                continue
            if contractor_place_relevant(place, tolerance, trade):
                total += 1
        return total

    rows, cached = contractor_provider_search(terms[0], lat, lon, radius, 50, True, country)
    provider_calls += 0 if cached else 1
    cache_hits += 1 if cached else 0
    add_results(rows)
    target = min(max(1, int(max_results)), CONTRACTOR_SEARCH_FALLBACK_MIN_RESULTS)
    if usable_count() < target and len(terms) > 1:
        rows, cached = contractor_provider_search(terms[1], lat, lon, radius, 50, True, country)
        provider_calls += 0 if cached else 1
        cache_hits += 1 if cached else 0
        add_results(rows)
    if tolerance == "broad" and usable_count() < target:
        rows, cached = contractor_provider_search(terms[0], lat, lon, radius, 50, False, country)
        provider_calls += 0 if cached else 1
        cache_hits += 1 if cached else 0
        add_results(rows)

    results = []
    rejected = 0
    wrong_country = 0
    for place in seen.values():
        place_country = contractor_place_country(place)
        if place_country and place_country != country:
            wrong_country += 1
            continue
        if not contractor_place_relevant(place, tolerance, trade):
            rejected += 1
            continue
        rating = place.get("rating")
        try:
            rating = round(float(rating), 1) if rating is not None else None
        except Exception:
            rating = None
        categories = contractor_place_categories(place)
        results.append({
            "place_id": str(contractor_place_id(place)),
            "name": contractor_place_name(place),
            "phone": contractor_place_phone(place),
            "address": contractor_place_address(place),
            "website": contractor_place_website(place),
            "specialty": " / ".join(categories[:2]) or CONTRACTOR_TRADE_CONFIG[trade]["label"],
            "fit_score": contractor_fit_score(place, trade),
            "external_rating": rating,
        })
    results.sort(key=lambda row: (row["fit_score"], bool(row["phone"]), bool(row["website"])), reverse=True)
    return {
        "results": results[:max_results],
        "provider_calls": provider_calls,
        "cache_hits": cache_hits,
        "rejected_irrelevant": rejected,
        "rejected_wrong_country": wrong_country,
        "lat": lat,
        "lon": lon,
        "radius": radius,
        "unit": unit,
    }


class RouteOptimizationError(Exception):
    pass


def route_plan_owner_key():
    if session.get("dispatchproof_owner"):
        return "OWNER"
    user_id = current_user_id()
    return f"USER:{user_id}" if user_id else ""


def normalize_route_address(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def route_address_key(value):
    return normalize_route_address(value).lower()


def route_http_json(url, params=None, payload=None, timeout=35):
    if not ROUTE_OPTIMIZATION_API_KEY:
        raise RouteOptimizationError(
            "Route Optimization is not configured yet. Add an openrouteservice API key in Render first."
        )

    # V2.44.1: use requests/urllib3 for HeiGIT routing calls instead of
    # urllib.request. On Render/Python 3.14 the HeiGIT edge occasionally
    # produced http.client.BadStatusLine before urllib could parse a response,
    # which escaped the route error handler and caused a 500 page. Requests is
    # more tolerant here, and a short retry keeps transient edge disconnects
    # from turning into a failed route calculation.
    method = "POST" if payload is not None else "GET"
    headers = {
        "Authorization": ROUTE_OPTIMIZATION_API_KEY,
        "Accept": "application/json, application/geo+json",
        "User-Agent": "DispatchProof/2.44.3 route-optimization",
        "Connection": "close",
    }

    last_error = None
    for attempt in range(2):
        try:
            response = requests.request(
                method,
                url,
                params=params or None,
                json=payload if payload is not None else None,
                headers=headers,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.35)
                continue
            print(f"Route optimization request failed after retry: {exc}")
            raise RouteOptimizationError(
                "DispatchProof could not reach the routing service. Please try again."
            )

        body = response.text or ""
        lower = body.lower()
        if 200 <= response.status_code < 300:
            try:
                return response.json() if body else None
            except ValueError as exc:
                print(f"Route API returned invalid JSON: {body[:500]}")
                raise RouteOptimizationError(
                    "The routing service returned an unreadable response. Please try again."
                ) from exc

        # Retry transient provider/gateway errors once before showing the user
        # a friendly message. Do not retry authentication, quota, or bad input.
        if response.status_code in (502, 503, 504) and attempt == 0:
            last_error = RuntimeError(f"HTTP {response.status_code}")
            time.sleep(0.35)
            continue
        if response.status_code in (401, 403):
            raise RouteOptimizationError(
                "The routing service rejected the API key. Check the key in Render and try again."
            )
        if response.status_code == 429 or "quota" in lower or "rate limit" in lower:
            raise RouteOptimizationError(
                "The routing service quota is temporarily exhausted. Try again after the quota resets."
            )
        if response.status_code == 400:
            raise RouteOptimizationError(
                "The routing service could not calculate this route. Check the selected addresses and try again."
            )
        print(f"Route API HTTP {response.status_code}: {body[:1000]}")
        raise RouteOptimizationError("The routing service returned an error. Please try again.")

    print(f"Route optimization request failed: {last_error}")
    raise RouteOptimizationError("DispatchProof could not reach the routing service. Please try again.")


def route_geocode(db, address):
    address = normalize_route_address(address)
    if not address:
        raise RouteOptimizationError("Every selected stop needs a location/address.")
    key = route_address_key(address)
    cached = db.execute(
        "SELECT * FROM route_geocode_cache WHERE address_key = ?", (key,)
    ).fetchone()
    if cached:
        try:
            cached_day = datetime.fromisoformat(cached["cached_at"]).date()
            if (local_today() - cached_day).days <= ROUTE_GEOCODE_CACHE_TTL_DAYS:
                return float(cached["lat"]), float(cached["lon"]), cached["formatted_address"] or address, True
        except Exception:
            pass

    data = route_http_json(
        "https://api.heigit.org/pelias/v1/search",
        params={"text": address, "size": 1},
        timeout=25,
    )
    features = (data or {}).get("features") or []
    if not features:
        raise RouteOptimizationError(f'Could not locate "{address}". Enter a more complete street/city/state address.')
    feature = features[0]
    coords = ((feature.get("geometry") or {}).get("coordinates") or [])
    if len(coords) < 2:
        raise RouteOptimizationError(f'Could not locate "{address}". Enter a more complete address.')
    props = feature.get("properties") or {}
    formatted = props.get("label") or props.get("name") or address
    lon, lat = float(coords[0]), float(coords[1])
    db.execute("""
        INSERT INTO route_geocode_cache (address_key, original_address, formatted_address, lat, lon, cached_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(address_key) DO UPDATE SET
            original_address = excluded.original_address,
            formatted_address = excluded.formatted_address,
            lat = excluded.lat,
            lon = excluded.lon,
            cached_at = excluded.cached_at
    """, (key, address, formatted, lat, lon, now_iso()))
    return lat, lon, formatted, False


def route_optimize_order(start_coord, stops, return_to_start=False):
    jobs_payload = [
        {"id": int(stop["job_id"]), "location": [float(stop["lon"]), float(stop["lat"])], "description": stop["job_name"]}
        for stop in stops
    ]
    vehicle = {
        "id": 1,
        "profile": "driving-car",
        "start": [float(start_coord[1]), float(start_coord[0])],
    }
    if return_to_start:
        vehicle["end"] = [float(start_coord[1]), float(start_coord[0])]
    data = route_http_json(
        "https://api.heigit.org/vroom/v0/",
        payload={"jobs": jobs_payload, "vehicles": [vehicle]},
        timeout=45,
    )
    routes = (data or {}).get("routes") or []
    unassigned = (data or {}).get("unassigned") or []
    if not routes:
        raise RouteOptimizationError("The routing service could not produce an optimized route for those stops.")
    if unassigned:
        raise RouteOptimizationError("One or more selected jobs could not be included in the optimized route. Check their addresses and try again.")
    order = [int(step["id"]) for step in routes[0].get("steps", []) if step.get("type") == "job" and step.get("id") is not None]
    expected = {int(stop["job_id"]) for stop in stops}
    if set(order) != expected:
        raise RouteOptimizationError("The routing service returned an incomplete stop order. Please try again.")
    return order


def route_directions(start_coord, ordered_stops, return_to_start=False):
    coords = [[float(start_coord[1]), float(start_coord[0])]]
    coords.extend([[float(stop["lon"]), float(stop["lat"])] for stop in ordered_stops])
    if return_to_start:
        coords.append([float(start_coord[1]), float(start_coord[0])])
    data = route_http_json(
        "https://api.heigit.org/openrouteservice/v2/directions/driving-car/geojson",
        payload={"coordinates": coords, "instructions": False, "units": "m"},
        timeout=45,
    )
    features = (data or {}).get("features") or []
    if not features:
        raise RouteOptimizationError("The routing service optimized the stops but could not build the driving route.")
    feature = features[0]
    props = feature.get("properties") or {}
    summary = props.get("summary") or {}
    segments = props.get("segments") or []
    leg_values = []
    # Segment 0 is Start -> Stop 1, segment 1 is Stop 1 -> Stop 2, etc.
    for index in range(len(ordered_stops)):
        segment = segments[index] if index < len(segments) else {}
        leg_values.append((float(segment.get("distance") or 0), float(segment.get("duration") or 0)))
    return {
        "distance": float(summary.get("distance") or sum(x[0] for x in leg_values)),
        "duration": float(summary.get("duration") or sum(x[1] for x in leg_values)),
        "geometry": feature.get("geometry") or None,
        "legs": leg_values,
    }


def save_project_route_plan(db, project_id, start_address, start_coord, return_to_start, ordered_stops, route_data):
    owner_key = route_plan_owner_key()
    if not owner_key:
        raise RouteOptimizationError("A signed-in user is required to save a route plan.")
    existing = db.execute(
        "SELECT id FROM project_route_plans WHERE project_id = ? AND owner_key = ?",
        (project_id, owner_key),
    ).fetchone()
    actor = current_display_name() or current_username() or "DispatchProof User"
    geometry_json = json.dumps(route_data.get("geometry")) if route_data.get("geometry") else None
    if existing:
        plan_id = existing["id"]
        db.execute("""
            UPDATE project_route_plans
            SET start_address = ?, start_lat = ?, start_lon = ?, return_to_start = ?,
                total_distance_m = ?, total_duration_s = ?, route_geometry_json = ?,
                provider_name = 'openrouteservice', created_by = ?, updated_at = ?
            WHERE id = ?
        """, (
            start_address, start_coord[0], start_coord[1], 1 if return_to_start else 0,
            route_data["distance"], route_data["duration"], geometry_json, actor, now_iso(), plan_id,
        ))
        db.execute("DELETE FROM project_route_stops WHERE route_plan_id = ?", (plan_id,))
    else:
        cur = db.execute("""
            INSERT INTO project_route_plans (
                project_id, owner_key, start_address, start_lat, start_lon, return_to_start,
                total_distance_m, total_duration_s, route_geometry_json, provider_name,
                created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'openrouteservice', ?, ?, ?)
        """, (
            project_id, owner_key, start_address, start_coord[0], start_coord[1], 1 if return_to_start else 0,
            route_data["distance"], route_data["duration"], geometry_json, actor, now_iso(), now_iso(),
        ))
        plan_id = cur.lastrowid

    legs = route_data.get("legs") or []
    for index, stop in enumerate(ordered_stops, start=1):
        leg_distance, leg_duration = legs[index - 1] if index - 1 < len(legs) else (0, 0)
        db.execute("""
            INSERT INTO project_route_stops (
                route_plan_id, job_id, stop_order, route_address, lat, lon,
                leg_distance_m, leg_duration_s
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            plan_id, stop["job_id"], index, stop["address"], stop["lat"], stop["lon"],
            leg_distance, leg_duration,
        ))
    return plan_id


def load_project_route_plan(db, project_id):
    owner_key = route_plan_owner_key()
    if not owner_key:
        return None, []
    plan = db.execute(
        "SELECT * FROM project_route_plans WHERE project_id = ? AND owner_key = ?",
        (project_id, owner_key),
    ).fetchone()
    if not plan:
        return None, []
    visibility_clause, visibility_params = job_visibility_sql("j")
    stops = db.execute(f"""
        SELECT prs.*, j.job_name, j.project_site, j.installation_date, j.status
        FROM project_route_stops prs
        JOIN jobs j ON j.id = prs.job_id
        WHERE prs.route_plan_id = ? AND ({visibility_clause})
        ORDER BY prs.stop_order, prs.id
    """, (plan["id"], *visibility_params)).fetchall()
    total_stops = db.execute(
        "SELECT COUNT(*) AS n FROM project_route_stops WHERE route_plan_id = ?",
        (plan["id"],),
    ).fetchone()["n"]
    # If access to a Team job was later removed, do not render an old route
    # geometry/totals that could reveal a private location indirectly.
    if len(stops) != total_stops and not current_user_is_admin():
        return None, []
    return plan, stops


BULK_JOB_IMPORT_HEADERS = [
    "Job Name",
    "Route / Site Address",
    "Installation Date",
    "Site Contact Name",
    "Site Contact Email",
    "Site Contact Phone",
]
BULK_JOB_IMPORT_MAX_ROWS = 250


def normalize_bulk_job_header(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def parse_bulk_job_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def bulk_job_import_column_map(fieldnames):
    aliases = {
        "job_name": {"jobname", "job", "storename", "store", "sitename", "locationname"},
        "project_site": {"routesiteaddress", "routeaddress", "siteaddress", "address", "projectsite", "location"},
        "installation_date": {"installationdate", "installdate", "scheduleddate", "date"},
        "contact_name": {"sitecontactname", "contactname", "contact"},
        "contact_email": {"sitecontactemail", "contactemail", "email"},
        "contact_phone": {"sitecontactphone", "contactphone", "phone"},
    }
    normalized = {normalize_bulk_job_header(name): name for name in (fieldnames or []) if name}
    result = {}
    for key, options in aliases.items():
        for option in options:
            if option in normalized:
                result[key] = normalized[option]
                break
    return result


def route_miles(meters):
    return float(meters or 0) / 1609.344


def route_duration_label(seconds):
    total_minutes = max(0, int(round(float(seconds or 0) / 60)))
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours} hr {minutes} min"
    if hours:
        return f"{hours} hr"
    return f"{minutes} min"


def append_crew_member_to_job(db, job_id, crew_member_id):
    existing = db.execute(
        "SELECT 1 FROM job_crew_assignments WHERE job_id = ? AND crew_member_id = ?",
        (job_id, crew_member_id),
    ).fetchone()
    if existing:
        return False
    next_order = db.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM job_crew_assignments WHERE job_id = ?",
        (job_id,),
    ).fetchone()["n"]
    db.execute("""
        INSERT INTO job_crew_assignments (job_id, crew_member_id, is_lead, sort_order, created_at)
        VALUES (?, ?, 0, ?, ?)
    """, (job_id, crew_member_id, next_order, now_iso()))
    member = db.execute("SELECT name FROM crew_members WHERE id = ?", (crew_member_id,)).fetchone()
    job = db.execute("SELECT assigned_crew FROM jobs WHERE id = ?", (job_id,)).fetchone()
    names = parse_crew_names(job["assigned_crew"] if job else "")
    if member and member["name"].lower() not in {name.lower() for name in names}:
        names.append(member["name"])
        db.execute("UPDATE jobs SET assigned_crew = ? WHERE id = ?", (", ".join(names), job_id))
    return True


def parse_crew_names(value):
    """Normalize comma/semicolon/newline separated crew names without duplicates."""
    names = []
    seen = set()
    for raw in re.split(r"[,;\n]+", str(value or "")):
        name = raw.strip()
        key = name.lower()
        if name and key not in seen:
            names.append(name)
            seen.add(key)
    return names


def get_or_create_crew_member(db, name):
    name = str(name or "").strip()
    if not name:
        return None

    member = db.execute(
        "SELECT * FROM crew_members WHERE LOWER(name) = LOWER(?)",
        (name,),
    ).fetchone()
    if member:
        return member["id"]

    cur = db.execute("""
        INSERT INTO crew_members (
            name, email, phone, role_trade, notes,
            is_active, created_at, updated_at
        ) VALUES (?, '', '', '', '', 1, ?, ?)
    """, (name, now_iso(), now_iso()))
    return cur.lastrowid


def migrate_legacy_crew_directory(db):
    """
    V2.33 migration:
    convert existing text crew assignments into reusable crew members
    and structured job/member links without changing the legacy display text.
    """
    jobs = db.execute("""
        SELECT id, crew_lead, assigned_crew
        FROM jobs
        WHERE TRIM(COALESCE(crew_lead, '')) <> ''
           OR TRIM(COALESCE(assigned_crew, '')) <> ''
        ORDER BY id
    """).fetchall()

    for job in jobs:
        lead_name = (job["crew_lead"] or "").strip()
        ordered_names = parse_crew_names(job["assigned_crew"])
        if lead_name and lead_name.lower() not in {x.lower() for x in ordered_names}:
            ordered_names.insert(0, lead_name)

        lead_id = get_or_create_crew_member(db, lead_name) if lead_name else None

        for sort_order, name in enumerate(ordered_names):
            member_id = get_or_create_crew_member(db, name)
            if not member_id:
                continue
            db.execute("""
                INSERT OR IGNORE INTO job_crew_assignments (
                    job_id, crew_member_id, is_lead, sort_order, created_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                job["id"],
                member_id,
                1 if lead_id and member_id == lead_id else 0,
                sort_order,
                now_iso(),
            ))

        if lead_id:
            db.execute("""
                UPDATE job_crew_assignments
                SET is_lead = CASE WHEN crew_member_id = ? THEN 1 ELSE 0 END
                WHERE job_id = ?
            """, (lead_id, job["id"]))


def get_crew_members_for_picker(db, job_id=None):
    """Active members plus any inactive members already assigned to this job."""
    if job_id:
        return db.execute("""
            SELECT cm.*,
                   CASE WHEN jca.crew_member_id IS NULL THEN 0 ELSE 1 END AS assigned_to_job
            FROM crew_members cm
            LEFT JOIN job_crew_assignments jca
              ON jca.crew_member_id = cm.id
             AND jca.job_id = ?
            WHERE cm.is_active = 1
               OR jca.crew_member_id IS NOT NULL
            ORDER BY
                CASE WHEN cm.is_active = 1 THEN 0 ELSE 1 END,
                CASE WHEN cm.member_type = 'SUBCONTRACTOR' THEN 1 ELSE 0 END,
                LOWER(COALESCE(cm.company_name, '')),
                LOWER(cm.name),
                cm.id
        """, (job_id,)).fetchall()

    return db.execute("""
        SELECT cm.*, 0 AS assigned_to_job
        FROM crew_members cm
        WHERE cm.is_active = 1
        ORDER BY
            CASE WHEN cm.member_type = 'SUBCONTRACTOR' THEN 1 ELSE 0 END,
            LOWER(COALESCE(cm.company_name, '')),
            LOWER(cm.name),
            cm.id
    """).fetchall()


def job_crew_picker_state(db, job):
    """Return structured selections plus any remaining custom/free-text crew names."""
    if not job:
        return {
            "selected_crew_ids": [],
            "selected_lead_id": None,
            "custom_crew_lead": "",
            "custom_crew_names": "",
        }

    assignments = db.execute("""
        SELECT jca.crew_member_id, jca.is_lead, jca.sort_order, cm.name
        FROM job_crew_assignments jca
        JOIN crew_members cm ON cm.id = jca.crew_member_id
        WHERE jca.job_id = ?
        ORDER BY jca.sort_order, LOWER(cm.name), cm.id
    """, (job["id"],)).fetchall()

    selected_ids = [row["crew_member_id"] for row in assignments]
    lead_row = next((row for row in assignments if row["is_lead"]), None)
    structured_names = {row["name"].lower() for row in assignments}

    custom_names = [
        name
        for name in parse_crew_names(job["assigned_crew"])
        if name.lower() not in structured_names
    ]

    custom_lead = ""
    legacy_lead = (job["crew_lead"] or "").strip()
    if legacy_lead and not lead_row:
        custom_lead = legacy_lead

    return {
        "selected_crew_ids": selected_ids,
        "selected_lead_id": lead_row["crew_member_id"] if lead_row else None,
        "custom_crew_lead": custom_lead,
        "custom_crew_names": ", ".join(custom_names),
    }


def resolve_job_crew_form(db, form):
    """
    Resolve the directory picker + optional custom names into both:
      - structured job_crew_assignments rows
      - legacy crew_lead / assigned_crew text used elsewhere in the app
    """
    raw_ids = form.getlist("crew_member_ids")
    selected_ids = []
    seen_ids = set()
    for raw in raw_ids:
        member_id = normalize_optional_id(raw)
        if member_id and member_id not in seen_ids:
            selected_ids.append(member_id)
            seen_ids.add(member_id)

    lead_id = normalize_optional_id(form.get("crew_lead_member_id"))
    custom_lead = (form.get("custom_crew_lead") or "").strip()
    custom_names = parse_crew_names(form.get("custom_crew_names"))

    if lead_id and lead_id not in seen_ids:
        selected_ids.insert(0, lead_id)
        seen_ids.add(lead_id)

    members = []
    if selected_ids:
        placeholders = ",".join("?" for _ in selected_ids)
        rows = db.execute(
            f"SELECT id, name, is_active FROM crew_members WHERE id IN ({placeholders})",
            tuple(selected_ids),
        ).fetchall()
        by_id = {row["id"]: row for row in rows}
        selected_ids = [member_id for member_id in selected_ids if member_id in by_id]
        members = [by_id[member_id] for member_id in selected_ids]

    lead_name = ""
    if lead_id:
        lead_member = next((row for row in members if row["id"] == lead_id), None)
        if lead_member:
            lead_name = lead_member["name"]
        else:
            lead_id = None

    if not lead_name:
        lead_name = custom_lead
        lead_id = None

    assigned_names = []
    assigned_seen = set()

    def add_name(name):
        name = str(name or "").strip()
        key = name.lower()
        if name and key not in assigned_seen:
            assigned_names.append(name)
            assigned_seen.add(key)

    for member in members:
        add_name(member["name"])
    if lead_name:
        add_name(lead_name)
    for name in custom_names:
        add_name(name)

    return {
        "crew_lead": lead_name,
        "assigned_crew": ", ".join(assigned_names),
        "selected_crew_ids": selected_ids,
        "selected_lead_id": lead_id,
        "custom_crew_lead": custom_lead if not lead_id else "",
        "custom_crew_names": ", ".join(custom_names),
    }


def save_job_crew_assignments(db, job_id, selected_crew_ids, lead_id):
    db.execute("DELETE FROM job_crew_assignments WHERE job_id = ?", (job_id,))
    for sort_order, member_id in enumerate(selected_crew_ids):
        db.execute("""
            INSERT INTO job_crew_assignments (
                job_id, crew_member_id, is_lead, sort_order, created_at
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            job_id,
            member_id,
            1 if lead_id and member_id == lead_id else 0,
            sort_order,
            now_iso(),
        ))


def sync_jobs_after_crew_member_rename(db, crew_member_id, old_name):
    """Keep legacy searchable/display crew text in sync after a directory rename."""
    jobs = db.execute("""
        SELECT DISTINCT j.*
        FROM jobs j
        JOIN job_crew_assignments jca ON jca.job_id = j.id
        WHERE jca.crew_member_id = ?
    """, (crew_member_id,)).fetchall()

    for job in jobs:
        assignments = db.execute("""
            SELECT jca.crew_member_id, jca.is_lead, jca.sort_order, cm.name
            FROM job_crew_assignments jca
            JOIN crew_members cm ON cm.id = jca.crew_member_id
            WHERE jca.job_id = ?
            ORDER BY jca.sort_order, LOWER(cm.name), cm.id
        """, (job["id"],)).fetchall()

        old_structured_names = set()
        for row in assignments:
            if row["crew_member_id"] == crew_member_id:
                old_structured_names.add((old_name or "").lower())
            else:
                old_structured_names.add((row["name"] or "").lower())

        custom_names = [
            name for name in parse_crew_names(job["assigned_crew"])
            if name.lower() not in old_structured_names
        ]

        names = []
        seen = set()
        for row in assignments:
            name = row["name"].strip()
            if name.lower() not in seen:
                names.append(name)
                seen.add(name.lower())
        for name in custom_names:
            if name.lower() not in seen:
                names.append(name)
                seen.add(name.lower())

        lead_row = next((row for row in assignments if row["is_lead"]), None)
        crew_lead = lead_row["name"] if lead_row else (job["crew_lead"] or "")

        db.execute("""
            UPDATE jobs
            SET crew_lead = ?, assigned_crew = ?
            WHERE id = ?
        """, (crew_lead, ", ".join(names), job["id"]))


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
            reminder_count INTEGER DEFAULT 0,
            owner_user_id INTEGER,
            team_id INTEGER,
            FOREIGN KEY(owner_user_id) REFERENCES users(id),
            FOREIGN KEY(team_id) REFERENCES teams(id)
        );

        CREATE TABLE IF NOT EXISTS crew_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE,
            member_type TEXT NOT NULL DEFAULT 'INTERNAL',
            company_name TEXT,
            source_provider TEXT,
            source_place_id TEXT,
            source_address TEXT,
            source_website TEXT,
            email TEXT,
            phone TEXT,
            role_trade TEXT,
            notes TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS job_crew_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            crew_member_id INTEGER NOT NULL,
            is_lead INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(job_id, crew_member_id),
            FOREIGN KEY(job_id) REFERENCES jobs(id),
            FOREIGN KEY(crew_member_id) REFERENCES crew_members(id)
        );

        CREATE TABLE IF NOT EXISTS crew_unavailability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crew_member_id INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(crew_member_id) REFERENCES crew_members(id)
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
            CREATE INDEX IF NOT EXISTS idx_crew_members_active_name
            ON crew_members(is_active, name)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_crew_members_type_active_name
            ON crew_members(member_type, is_active, name)
        """)
        db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_crew_members_source_place_id
            ON crew_members(source_place_id)
            WHERE source_place_id IS NOT NULL AND TRIM(source_place_id) <> ''
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_crew_assignments_job
            ON job_crew_assignments(job_id, sort_order, crew_member_id)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_crew_assignments_member
            ON job_crew_assignments(crew_member_id, job_id)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_crew_unavailability_member_dates
            ON crew_unavailability(crew_member_id, start_date, end_date)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_owner_user_id
            ON jobs(owner_user_id, status, installation_date)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_team_id
            ON jobs(team_id, status, installation_date)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_team_members_user
            ON team_members(user_id, team_id)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_team_members_team
            ON team_members(team_id, user_id)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_notes_job_id
            ON job_notes(job_id, created_at DESC, id DESC)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_documents_job_id
            ON job_documents(job_id, created_at DESC, id DESC)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_field_update_links_job
            ON field_update_links(job_id, is_active, created_at DESC, id DESC)
        """)
        db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_field_update_links_token
            ON field_update_links(token)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_field_progress_entries_job_date
            ON field_progress_entries(job_id, work_date DESC, created_at DESC, id DESC)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_route_plans_project_owner
            ON project_route_plans(project_id, owner_key, updated_at DESC)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_route_stops_plan_order
            ON project_route_stops(route_plan_id, stop_order, job_id)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_documents_project_id
            ON project_documents(project_id, created_at DESC, id DESC)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_client_documents_client_id
            ON client_documents(client_id, created_at DESC, id DESC)
        """)

        access_migration = db.execute(
            "SELECT 1 FROM app_migrations WHERE migration_key = ?",
            ("v2.37_user_team_access",),
        ).fetchone()
        if not access_migration:
            db.execute("""
                INSERT INTO app_migrations (migration_key, applied_at, details)
                VALUES (?, ?, ?)
            """, (
                "v2.37_user_team_access",
                now_iso(),
                "Added private-by-default job ownership plus optional team job sharing. Legacy jobs remain Owner/Admin-only.",
            ))
            record_activity(
                db,
                "User Job Privacy Enabled",
                "Enabled private-by-default PM jobs and optional team collaboration. Existing legacy jobs remain Owner/Admin-only.",
                actor_type="SYSTEM",
                actor_name="DispatchProof",
            )

        crew_migration = db.execute(
            "SELECT 1 FROM app_migrations WHERE migration_key = ?",
            ("v2.33_crew_directory",),
        ).fetchone()
        if not crew_migration:
            migrate_legacy_crew_directory(db)
            db.execute("""
                INSERT INTO app_migrations (migration_key, applied_at, details)
                VALUES (?, ?, ?)
            """, (
                "v2.33_crew_directory",
                now_iso(),
                "Created Crew Directory and migrated existing named crew assignments.",
            ))
            record_activity(
                db,
                "Crew Directory Enabled",
                "Created the reusable crew directory and migrated existing named crew assignments.",
                actor_type="SYSTEM",
                actor_name="DispatchProof",
            )

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

def job_has_crew_assignment(job):
    """True when at least one named crew assignment exists."""
    return bool(
        (job["crew_lead"] or "").strip()
        or (job["assigned_crew"] or "").strip()
    )


def job_assigned_crew_names(job):
    """
    Return unique named people counted toward Planned Crew Size.

    assigned_crew normally already contains the lead, but older/custom data can
    contain a lead separately. Counting by normalized name prevents double
    counting the same person.
    """
    names = parse_crew_names(job["assigned_crew"])
    seen = {name.lower() for name in names}

    lead = (job["crew_lead"] or "").strip()
    if lead and lead.lower() not in seen:
        names.insert(0, lead)

    return names


def job_staffing_gap(job):
    """
    Return staffing-gap details when Planned Crew Size exceeds named crew.

    Jobs without Planned Crew Size are intentionally not treated as staffing
    gaps because DispatchProof has no target headcount to compare against.
    """
    try:
        planned = int(job["planned_crew_size"] or 0)
    except (TypeError, ValueError):
        planned = 0

    if planned < 1:
        return None

    assigned_names = job_assigned_crew_names(job)
    assigned = len(assigned_names)
    needed = planned - assigned

    if needed <= 0:
        return None

    return {
        "planned": planned,
        "assigned": assigned,
        "needed": needed,
        "assigned_names": assigned_names,
    }


def get_active_staffing_gaps(jobs):
    """
    Return staffing gaps for non-completed jobs.

    Returns:
      by_job: {job_id: {planned, assigned, needed, assigned_names}}
      job_count: number of active jobs with a staffing gap
      total_needed: total additional crew members needed across those jobs
    """
    by_job = {}
    total_needed = 0

    for job in jobs:
        if (job["status"] or "").upper() == "COMPLETED":
            continue

        gap = job_staffing_gap(job)
        if not gap:
            continue

        by_job[job["id"]] = gap
        total_needed += gap["needed"]

    return by_job, len(by_job), total_needed


def get_active_crew_conflicts(db, visible_job_ids=None):
    """Detect company-wide crew conflicts while respecting PM job privacy."""
    rows = db.execute("""
        SELECT j.id AS job_id, j.job_name, j.installation_date,
               cm.id AS crew_member_id, cm.name AS crew_member_name
        FROM job_crew_assignments jca
        JOIN jobs j ON j.id = jca.job_id
        JOIN crew_members cm ON cm.id = jca.crew_member_id
        WHERE j.status <> 'COMPLETED'
          AND TRIM(COALESCE(j.installation_date, '')) <> ''
        ORDER BY j.installation_date, cm.id, j.id
    """).fetchall()

    visible = None if visible_job_ids is None else set(visible_job_ids)
    groups = {}
    for row in rows:
        groups.setdefault((row["installation_date"], row["crew_member_id"]), []).append(row)

    by_job = {}
    group_count = 0
    for (install_date, _member_id), group_rows in groups.items():
        if len({row["job_id"] for row in group_rows}) < 2:
            continue
        target_rows = group_rows if visible is None else [row for row in group_rows if row["job_id"] in visible]
        if not target_rows:
            continue
        group_count += 1
        for row in target_rows:
            others = []
            for other in group_rows:
                if other["job_id"] == row["job_id"]:
                    continue
                label = other["job_name"] if visible is None or other["job_id"] in visible else "another private job"
                if label not in others:
                    others.append(label)
            by_job.setdefault(row["job_id"], []).append({
                "crew_member_name": row["crew_member_name"],
                "installation_date": install_date,
                "other_jobs": others,
            })
    return by_job, group_count


def get_active_crew_unavailability_issues(db):
    """
    Return active jobs whose assigned Crew Directory members are unavailable
    on the job's installation date. Completed jobs are intentionally excluded.

    Returns:
      by_job: {job_id: [{crew_member_name, installation_date, periods:[...]}]}
      group_count: number of unique crew-member/date availability issues
    """
    rows = db.execute("""
        SELECT
            j.id AS job_id,
            j.job_name,
            j.installation_date,
            cm.id AS crew_member_id,
            cm.name AS crew_member_name,
            cu.id AS unavailability_id,
            cu.start_date,
            cu.end_date,
            cu.reason
        FROM job_crew_assignments jca
        JOIN jobs j ON j.id = jca.job_id
        JOIN crew_members cm ON cm.id = jca.crew_member_id
        JOIN crew_unavailability cu ON cu.crew_member_id = cm.id
        WHERE j.status <> 'COMPLETED'
          AND TRIM(COALESCE(j.installation_date, '')) <> ''
          AND cu.start_date <= j.installation_date
          AND cu.end_date >= j.installation_date
        ORDER BY j.installation_date, cm.id, cu.start_date, cu.id
    """).fetchall()

    grouped = {}
    for row in rows:
        key = (row["job_id"], row["crew_member_id"])
        issue = grouped.setdefault(key, {
            "job_id": row["job_id"],
            "job_name": row["job_name"],
            "crew_member_id": row["crew_member_id"],
            "crew_member_name": row["crew_member_name"],
            "installation_date": row["installation_date"],
            "periods": [],
        })
        issue["periods"].append({
            "id": row["unavailability_id"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "reason": (row["reason"] or "Unavailable").strip() or "Unavailable",
        })

    by_job = {}
    for issue in grouped.values():
        by_job.setdefault(issue["job_id"], []).append(issue)

    group_count = len(grouped)
    return by_job, group_count


def get_member_unavailability_for_date(db, crew_member_id, install_date):
    if not install_date:
        return []
    return db.execute("""
        SELECT *
        FROM crew_unavailability
        WHERE crew_member_id = ?
          AND start_date <= ?
          AND end_date >= ?
        ORDER BY start_date, end_date, id
    """, (crew_member_id, install_date, install_date)).fetchall()


def job_attention_reason(
    job,
    schedule_bucket,
    has_crew_conflict=False,
    has_availability_issue=False,
    has_staffing_gap=False,
):
    """Return the highest-priority office action for an active job."""
    status = (job["status"] or "").upper()

    if schedule_bucket == "overdue":
        return {
            "priority": 1,
            "level": "critical",
            "label": "Overdue install",
            "message": "The installation date has passed and the job is still active.",
        }

    if schedule_bucket == "today":
        return {
            "priority": 2,
            "level": "urgent",
            "label": "Install today",
            "message": "This installation is scheduled for today.",
        }

    if has_crew_conflict:
        return {
            "priority": 3,
            "level": "conflict",
            "label": "Crew conflict",
            "message": "One or more assigned crew members are booked on another active install the same day.",
        }

    if has_availability_issue:
        return {
            "priority": 4,
            "level": "availability",
            "label": "Crew unavailable",
            "message": "An assigned crew member is marked unavailable on this installation date.",
        }

    if status == "BLOCKED":
        return {
            "priority": 5,
            "level": "critical",
            "label": "Blocked",
            "message": "The site is not ready and needs office follow-up.",
        }

    if status == "REVIEW":
        return {
            "priority": 6,
            "level": "review",
            "label": "Needs review",
            "message": "A readiness response is waiting for office review.",
        }

    if status == "NO RESPONSE" and schedule_bucket == "next7":
        return {
            "priority": 7,
            "level": "warning",
            "label": "No response · Next 7 Days",
            "message": "The install is approaching and readiness has not been confirmed.",
        }

    if schedule_bucket == "next7" and not job_has_crew_assignment(job):
        return {
            "priority": 8,
            "level": "crew",
            "label": "Crew unassigned · Next 7 Days",
            "message": "No crew lead or installer has been assigned to this upcoming install.",
        }

    if has_staffing_gap:
        return {
            "priority": 9,
            "level": "staffing",
            "label": "Staffing gap",
            "message": "Planned Crew Size is larger than the number of named crew members assigned.",
        }

    return None

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

def pretty_bytes(value):
    try:
        size = int(value or 0)
    except (TypeError, ValueError):
        size = 0

    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"

app.jinja_env.filters["pretty_bytes"] = pretty_bytes

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_document(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in DOCUMENT_EXTENSIONS

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
    """Return the base URL for secure public links.

    V2.40.4 prefers the hostname of the live request that generated the link.
    This prevents a stale DISPATCHPROOF_PUBLIC_BASE_URL from sending a site
    contact to another DispatchProof deployment/database where the token does
    not exist. Environment URLs remain fallbacks for non-request contexts.
    """
    if has_request_context():
        live_base = (request.url_root or "").strip().rstrip("/")
        if live_base:
            return live_base
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

def public_field_update_url(field_link):
    base = public_app_base_url()
    token = field_link["token"]
    if base:
        return f"{base}/f/{token}"
    return url_for("public_field_update", token=token, _external=True)

def field_progress_data(job_id, newest_first=False):
    order = "work_date DESC, created_at DESC, id DESC" if newest_first else "work_date ASC, created_at ASC, id ASC"
    with get_db() as db:
        rows = db.execute(f"""
            SELECT *
            FROM field_progress_entries
            WHERE job_id = ?
            ORDER BY {order}
        """, (job_id,)).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["photos"] = parse_json_list(row["photo_json"])
        items.append(item)
    return items

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

        progress_rows = db.execute("""
            SELECT *
            FROM field_progress_entries
            WHERE job_id = ? AND entry_type = 'DAILY_PROGRESS'
            ORDER BY work_date ASC, created_at ASC, id ASC
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

    progress_entries = []
    for row in progress_rows:
        item = dict(row)
        item["photos"] = parse_json_list(row["photo_json"])
        progress_entries.append(item)

    return {
        "checklist": checklist,
        "answers": answers,
        "photos": photos,
        "arrival_issues": arrival_issues,
        "arrival_photos": arrival_photos,
        "activity_events": activity_events,
        "mobilization_history": mobilization_history,
        "progress_entries": progress_entries,
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
        progress = db.execute("""
            SELECT photo_json
            FROM field_progress_entries
            WHERE job_id = ? AND entry_type = 'DAILY_PROGRESS'
        """, (job["id"],)).fetchall()

    for row in confirmations:
        allowed.update(parse_json_list(row["photo_json"]))
    for row in attempts:
        allowed.update(parse_json_list(row["photo_json"]))
        allowed.update(parse_json_list(row["arrival_photos_json"]))
    for row in progress:
        allowed.update(parse_json_list(row["photo_json"]))

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


def build_field_update_email(job, field_link, public_url):
    settings = get_app_settings()
    brand_name = settings.get("company_name") or COMPANY_NAME
    brand_tagline = settings.get("company_tagline") or PRODUCT_TAGLINE
    brand_accent = normalize_hex_color(settings.get("accent_color"))
    logo_url = company_logo_external_url(settings)

    esc_brand = html_lib.escape(str(brand_name))
    esc_tagline = html_lib.escape(str(brand_tagline))
    esc_job = html_lib.escape(str(job["job_name"]))
    esc_site = html_lib.escape(str(job["project_site"] or ""))
    esc_name = html_lib.escape(str(field_link["recipient_name"] or "Field Crew"))
    esc_note = html_lib.escape(str(field_link["request_note"] or ""))
    esc_url = html_lib.escape(str(public_url), quote=True)

    subject = f"Field Update Request: {job['job_name']}"
    html = f"""
    <html>
      <body style="font-family:Arial,sans-serif;background:#f5f7fb;padding:28px;color:#152033;">
        <div style="max-width:660px;margin:0 auto;background:#ffffff;border:1px solid #dfe5ee;border-radius:14px;padding:28px;">
          {f'<img src="{logo_url}" alt="{esc_brand} logo" style="max-height:54px;max-width:180px;object-fit:contain;margin-bottom:10px;display:block;">' if logo_url else ''}
          <div style="font-size:22px;font-weight:800;color:#0b2348;margin-bottom:4px;">{esc_brand}</div>
          <div style="font-size:12px;color:#6b7280;margin-bottom:2px;">{esc_tagline}</div>
          <div style="font-size:11px;color:#98a2b3;margin-bottom:24px;">Powered by DispatchProof</div>
          <p>Hi {esc_name},</p>
          <h2 style="margin-bottom:4px;">{esc_job}</h2>
          {f'<div style="color:#667085;margin-bottom:18px;">{esc_site}</div>' if esc_site else ''}
          <div style="background:#f8fafc;border-left:4px solid {brand_accent};padding:14px 16px;margin:18px 0;line-height:1.5;">
            <strong>PM Request</strong><br>{esc_note}
          </div>
          <p style="line-height:1.55;">Open the secure field link to respond with a note or photos. You can also use the same link to submit daily progress photos while this job is active. No DispatchProof account is required.</p>
          <div style="margin:26px 0;">
            <a href="{esc_url}" style="display:inline-block;background:{brand_accent};color:white;text-decoration:none;font-weight:700;padding:13px 18px;border-radius:9px;">Open Field Update</a>
          </div>
          <p style="font-size:12px;color:#6b7280;line-height:1.5;">This secure link is tied only to this job and can be revoked by the project manager.</p>
        </div>
      </body>
    </html>
    """
    return subject, html


def send_field_update_email(job, field_link, public_url):
    email = (field_link["recipient_email"] or "").strip()
    if not email:
        return None, None
    subject, html = build_field_update_email(job, field_link, public_url)
    sent, error = send_smtp_message(email, field_link["recipient_name"], subject, html)
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
            "FIELD_UPDATE_REQUEST",
            email,
            field_link["recipient_name"],
            subject,
            html,
            public_url,
            status,
            error,
        )
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


def current_user_id():
    try:
        user_id = int(session.get("dispatchproof_user_id") or 0)
    except (TypeError, ValueError):
        return None
    return user_id if user_id > 0 else None


def database_user_session_is_current():
    """Validate DB-backed sessions against the live Users table.

    The permanent Owner login is environment-backed and has no users.id.
    All other sessions must still point at the same active database user that
    originally authenticated. This prevents stale browser sessions from
    carrying a deleted/recreated user id into foreign-keyed job records.
    """
    if not user_authenticated() or session.get("dispatchproof_owner"):
        return True

    user_id = current_user_id()
    session_username = (current_username() or "").strip()
    if not user_id or not session_username:
        return False

    with get_db() as db:
        user = db.execute(
            "SELECT id, full_name, username, role, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    if not user or not user["is_active"]:
        return False
    if (user["username"] or "").strip().lower() != session_username.lower():
        return False

    # Keep display/role information synchronized with live account settings.
    session["dispatchproof_authenticated"] = True
    session["dispatchproof_admin"] = True
    session["dispatchproof_owner"] = False
    session["dispatchproof_user_id"] = user["id"]
    session["dispatchproof_username"] = user["username"]
    session["dispatchproof_admin_username"] = user["username"]
    session["dispatchproof_display_name"] = user["full_name"]
    session["dispatchproof_role"] = user["role"]
    return True


def job_visibility_sql(alias="j"):
    """Return a SQL predicate + params for jobs visible to this signed-in user."""
    if current_user_is_admin():
        return "1=1", []

    user_id = current_user_id()
    if not user_id:
        return "0=1", []

    alias = re.sub(r"[^A-Za-z0-9_]", "", alias or "j") or "j"
    clause = f"""(
        {alias}.owner_user_id = ?
        OR (
            {alias}.team_id IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM team_members tm
                JOIN teams t ON t.id = tm.team_id
                WHERE tm.user_id = ?
                  AND tm.team_id = {alias}.team_id
                  AND t.share_jobs = 1
            )
        )
    )"""
    return clause, [user_id, user_id]


def user_can_access_job(db, job_id):
    if current_user_is_admin():
        return True
    clause, params = job_visibility_sql("j")
    row = db.execute(
        f"SELECT 1 FROM jobs j WHERE j.id = ? AND ({clause})",
        (job_id, *params),
    ).fetchone()
    return bool(row)


def user_team_options(db, include_disabled=False):
    """Teams the current user may choose for a job."""
    if current_user_is_admin():
        return db.execute("""
            SELECT t.*, COUNT(tm.user_id) AS member_count
            FROM teams t
            LEFT JOIN team_members tm ON tm.team_id = t.id
            GROUP BY t.id
            ORDER BY LOWER(t.name), t.id
        """).fetchall()

    user_id = current_user_id()
    if not user_id:
        return []
    sharing_filter = "" if include_disabled else "WHERE t.share_jobs = 1"
    return db.execute(f"""
        SELECT t.*, COUNT(all_tm.user_id) AS member_count
        FROM teams t
        JOIN team_members mine ON mine.team_id = t.id AND mine.user_id = ?
        LEFT JOIN team_members all_tm ON all_tm.team_id = t.id
        {sharing_filter}
        GROUP BY t.id
        ORDER BY LOWER(t.name), t.id
    """, (user_id,)).fetchall()


def resolve_job_team_id(db, raw_team_id, allow_disabled=False):
    team_id = normalize_optional_id(raw_team_id)
    if not team_id:
        return None, None

    if current_user_is_admin():
        team = db.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    else:
        user_id = current_user_id()
        sharing_sql = "" if allow_disabled else "AND t.share_jobs = 1"
        team = db.execute(f"""
            SELECT t.*
            FROM teams t
            JOIN team_members tm ON tm.team_id = t.id
            WHERE t.id = ? AND tm.user_id = ? {sharing_sql}
        """, (team_id, user_id)).fetchone() if user_id else None

    if not team:
        return None, "That team is not available for job sharing."
    return team_id, None


def can_manage_job_access(job):
    if current_user_is_admin():
        return True
    user_id = current_user_id()
    return bool(user_id and job and job["owner_user_id"] == user_id)


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

def stored_upload_file_count():
    if not UPLOAD_DIR.exists():
        return 0
    return sum(1 for p in UPLOAD_DIR.rglob("*") if p.is_file())

def stored_job_document_file_count():
    """Count the actual internal job-document files that a backup can preserve."""
    if not UPLOAD_DIR.exists():
        return 0
    return sum(
        1
        for p in UPLOAD_DIR.rglob("*")
        if p.is_file() and p.name.startswith("jobdoc_")
    )

def stored_project_document_file_count():
    """Count the actual internal project-document files that a backup can preserve."""
    if not UPLOAD_DIR.exists():
        return 0
    return sum(
        1
        for p in UPLOAD_DIR.rglob("*")
        if p.is_file() and p.name.startswith("projdoc_")
    )

def stored_client_document_file_count():
    """Count the actual internal client-document files that a backup can preserve."""
    if not UPLOAD_DIR.exists():
        return 0
    return sum(
        1
        for p in UPLOAD_DIR.rglob("*")
        if p.is_file() and p.name.startswith("clientdoc_")
    )

def database_record_counts(db_path):
    counts = {
        "jobs": 0,
        "readiness_confirmations": 0,
        "mobilization_attempts": 0,
        "email_events": 0,
        "activity_log": 0,
        "job_notes": 0,
        "job_documents": 0,
        "field_update_links": 0,
        "field_progress_entries": 0,
        "project_route_plans": 0,
        "project_route_stops": 0,
        "project_documents": 0,
        "client_documents": 0,
        "crew_members": 0,
        "job_crew_assignments": 0,
        "crew_unavailability": 0,
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
            ("job_documents", "job_documents"),
            ("field_update_links", "field_update_links"),
            ("field_progress_entries", "field_progress_entries"),
            ("project_route_plans", "project_route_plans"),
            ("project_route_stops", "project_route_stops"),
            ("project_documents", "project_documents"),
            ("client_documents", "client_documents"),
            ("clients", "clients"),
            ("projects", "projects"),
            ("crew_members", "crew_members"),
            ("job_crew_assignments", "job_crew_assignments"),
            ("crew_unavailability", "crew_unavailability"),
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
        "job_documents": 0,
        "field_update_links": 0,
        "field_progress_entries": 0,
        "project_route_plans": 0,
        "project_route_stops": 0,
        "project_documents": 0,
        "client_documents": 0,
        "crew_members": 0,
        "job_crew_assignments": 0,
        "crew_unavailability": 0,
        "uploaded_files": 0,
    }

    if DB_PATH.exists():
        try:
            backup_counts.update(database_record_counts(DB_PATH))
        except Exception:
            pass

    # File-based counts should reflect what will actually be written into the ZIP.
    backup_counts["uploaded_files"] = stored_upload_file_count()
    backup_counts["job_documents"] = max(
        backup_counts.get("job_documents", 0),
        stored_job_document_file_count(),
    )
    backup_counts["project_documents"] = max(
        backup_counts.get("project_documents", 0),
        stored_project_document_file_count(),
    )

    backup_counts["client_documents"] = max(
        backup_counts.get("client_documents", 0),
        stored_client_document_file_count(),
    )

    metadata = {
        "product": PRODUCT_NAME,
        "backup_format": 2,
        "created_at": now_iso(),
        "app_version": "2.44.3",
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

def workspace_export_filename():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    username = secure_filename(current_username()) or "user"
    return f"dispatchproof_workspace_{username}_{stamp}.zip"


def _rows_as_dicts(rows):
    return [dict(row) for row in rows]


def _select_for_job_ids(db, table, job_ids, order_by="id ASC"):
    if not job_ids:
        return []
    placeholders = ",".join("?" for _ in job_ids)
    return _rows_as_dicts(db.execute(
        f"SELECT * FROM {table} WHERE job_id IN ({placeholders}) ORDER BY {order_by}",
        tuple(job_ids),
    ).fetchall())


def _csv_text(rows):
    if not rows:
        return ""
    fieldnames = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def build_workspace_export_data(db):
    """Build an Operator-safe workspace snapshot.

    Private job data remains limited by job_visibility_sql(). Shared setup masters
    (Clients, Projects, Crew and their shared documents) are included because
    Operators can already access and maintain those company-wide records in the UI.
    This lets a workspace backup preserve useful setup progress even before a job
    has successfully been created.
    """
    visibility_clause, visibility_params = job_visibility_sql("j")
    jobs = _rows_as_dicts(db.execute(f"""
        SELECT j.*
        FROM jobs j
        WHERE ({visibility_clause})
        ORDER BY j.installation_date, j.id
    """, visibility_params).fetchall())
    job_ids = [row["id"] for row in jobs]

    readiness = _select_for_job_ids(db, "readiness_confirmations", job_ids)
    mobilizations = _select_for_job_ids(db, "mobilization_attempts", job_ids, "job_id ASC, attempt_number ASC, id ASC")
    notes = _select_for_job_ids(db, "job_notes", job_ids, "job_id ASC, created_at ASC, id ASC")
    documents = _select_for_job_ids(db, "job_documents", job_ids, "job_id ASC, created_at ASC, id ASC")
    field_links = _select_for_job_ids(db, "field_update_links", job_ids, "job_id ASC, created_at ASC, id ASC")
    field_progress = _select_for_job_ids(db, "field_progress_entries", job_ids, "job_id ASC, work_date ASC, created_at ASC, id ASC")
    emails = _select_for_job_ids(db, "email_events", job_ids, "job_id ASC, created_at ASC, id ASC")
    activity = _select_for_job_ids(db, "activity_log", job_ids, "job_id ASC, created_at ASC, id ASC")
    crew_assignments = _select_for_job_ids(db, "job_crew_assignments", job_ids, "job_id ASC, sort_order ASC, id ASC")

    team_ids = sorted({row["team_id"] for row in jobs if row.get("team_id")})

    def select_ids(table, ids, columns="*"):
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        return _rows_as_dicts(db.execute(
            f"SELECT {columns} FROM {table} WHERE id IN ({placeholders}) ORDER BY id ASC",
            tuple(ids),
        ).fetchall())

    # Clients, Projects and Crew are shared company setup records in DispatchProof.
    # Including them does not expose another PM's private jobs, and it protects work
    # done before the first job exists.
    clients = _rows_as_dicts(db.execute("SELECT * FROM clients ORDER BY LOWER(name), id").fetchall())
    projects = _rows_as_dicts(db.execute("SELECT * FROM projects ORDER BY client_id, LOWER(name), id").fetchall())
    crew_members = _rows_as_dicts(db.execute("SELECT * FROM crew_members ORDER BY LOWER(name), id").fetchall())
    crew_unavailability = _rows_as_dicts(db.execute("SELECT * FROM crew_unavailability ORDER BY crew_member_id, start_date, id").fetchall())
    client_documents = _rows_as_dicts(db.execute("SELECT * FROM client_documents ORDER BY client_id, created_at, id").fetchall())
    project_documents = _rows_as_dicts(db.execute("SELECT * FROM project_documents ORDER BY project_id, created_at, id").fetchall())

    data = {
        "jobs": jobs,
        "clients": clients,
        "projects": projects,
        "teams": select_ids("teams", team_ids, "id, name, share_jobs, created_at, updated_at"),
        "readiness_confirmations": readiness,
        "mobilization_attempts": mobilizations,
        "job_notes": notes,
        "job_documents": documents,
        "field_update_links": field_links,
        "field_progress_entries": field_progress,
        "client_documents": client_documents,
        "project_documents": project_documents,
        "email_events": emails,
        "activity_log": activity,
        "job_crew_assignments": crew_assignments,
        "crew_members": crew_members,
        "crew_unavailability": crew_unavailability,
    }
    return data

def workspace_export_stats(db):
    data = build_workspace_export_data(db)
    evidence = set()
    for job in data["jobs"]:
        evidence.update(parse_json_list(job.get("photo_json")))
        evidence.update(parse_json_list(job.get("arrival_photos_json")))
    for row in data["readiness_confirmations"]:
        evidence.update(parse_json_list(row.get("photo_json")))
    for row in data["mobilization_attempts"]:
        evidence.update(parse_json_list(row.get("photo_json")))
        evidence.update(parse_json_list(row.get("arrival_photos_json")))
    for row in data.get("field_progress_entries") or []:
        evidence.update(parse_json_list(row.get("photo_json")))
    return {
        "jobs": len(data["jobs"]),
        "job_documents": len(data["job_documents"]),
        "evidence_files": len({name for name in evidence if name}),
        "team_jobs": sum(1 for job in data["jobs"] if job.get("team_id")),
        "clients": len(data["clients"]),
        "projects": len(data["projects"]),
        "crew_members": len(data["crew_members"]),
        "shared_documents": len(data["client_documents"]) + len(data["project_documents"]),
    }

def create_workspace_export_archive():
    """Create a non-destructive, user-scoped backup/export ZIP.

    This is intentionally not a restorable full-system database backup. It contains
    only jobs the current user may access at export time and files attached to
    those jobs, preventing one PM from exporting another PM's private workspace.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="dispatchproof_workspace_"))
    archive_path = temp_dir / workspace_export_filename()

    with get_db() as db:
        data = build_workspace_export_data(db)

    job_by_id = {row["id"]: row for row in data["jobs"]}
    file_index = []
    missing_files = []
    included_uploads = set()

    def add_upload(z, stored_filename, archive_name, job_id, kind, original_filename=None, entity_type=None, entity_id=None, document_id=None):
        if not stored_filename:
            return
        stored_filename = str(stored_filename)
        if stored_filename in included_uploads:
            return
        source = UPLOAD_DIR / stored_filename
        if not source.is_file():
            missing_files.append({
                "job_id": job_id,
                "kind": kind,
                "stored_filename": stored_filename,
                "original_filename": original_filename,
            })
            return
        z.write(source, archive_name)
        included_uploads.add(stored_filename)
        entry = {
            "job_id": job_id,
            "kind": kind,
            "stored_filename": stored_filename,
            "original_filename": original_filename or stored_filename,
            "archive_path": str(archive_name).replace("\\", "/"),
        }
        if entity_type:
            entry["entity_type"] = entity_type
        if entity_id is not None:
            entry["entity_id"] = entity_id
        if document_id is not None:
            entry["document_id"] = document_id
        file_index.append(entry)

    manifest = {
        "product": PRODUCT_NAME,
        "export_format": 2,
        "export_type": "user_workspace",
        "created_at": now_iso(),
        "app_version": "2.44.3",
        "exported_for": {
            "username": current_username(),
            "display_name": current_display_name(),
            "role": current_user_role(),
        },
        "scope_note": "Contains this account's authorized jobs plus shared Clients, Projects, Crew, and shared setup documents visible to Operators. It never includes another PM's private jobs. Full-system restore remains Owner/Administrator-only.",
        "counts": {key: len(rows) for key, rows in data.items()},
    }

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("workspace_manifest.json", json.dumps(manifest, indent=2))
        z.writestr("workspace_data.json", json.dumps(data, indent=2))
        z.writestr(
            "README.txt",
            "DispatchProof Workspace Export\n"
            "==============================\n\n"
            "This ZIP is a personal/team workspace backup for reference and file recovery.\n"
            "It contains jobs this account was authorized to access plus shared Clients, Projects, Crew and setup documents visible to Operators.\n"
            "It does not contain other PMs' private jobs, user passwords, or the full company database.\n"
            "Only Owner/Administrator full-system backups can be restored over DispatchProof.\n\n"
            "Store this ZIP securely because it may contain customer contact information, job history, and site evidence.\n"
        )

        for table, rows in data.items():
            z.writestr(f"data/{table}.csv", _csv_text(rows))

        # Internal job documents.
        for doc in data["job_documents"]:
            safe_original = secure_filename(doc.get("original_filename") or "") or doc["stored_filename"]
            archive_name = Path("files") / f"job_{doc['job_id']}" / "documents" / f"{doc['id']}_{safe_original}"
            add_upload(
                z,
                doc["stored_filename"],
                archive_name,
                doc["job_id"],
                "job_document",
                doc.get("original_filename"),
            )

        # Shared Client / Project documents. These records are already visible to
        # Operators in the shared setup areas, and are restored additively only.
        for doc in data.get("client_documents") or []:
            safe_original = secure_filename(doc.get("original_filename") or "") or doc["stored_filename"]
            archive_name = Path("files") / "shared" / "clients" / f"client_{doc['client_id']}" / f"{doc['id']}_{safe_original}"
            add_upload(
                z, doc["stored_filename"], archive_name, None, "client_document",
                doc.get("original_filename"), entity_type="client", entity_id=doc.get("client_id"), document_id=doc.get("id"),
            )

        for doc in data.get("project_documents") or []:
            safe_original = secure_filename(doc.get("original_filename") or "") or doc["stored_filename"]
            archive_name = Path("files") / "shared" / "projects" / f"project_{doc['project_id']}" / f"{doc['id']}_{safe_original}"
            add_upload(
                z, doc["stored_filename"], archive_name, None, "project_document",
                doc.get("original_filename"), entity_type="project", entity_id=doc.get("project_id"), document_id=doc.get("id"),
            )

        # Readiness / arrival evidence, including archived attempts.
        evidence_by_job = {job_id: set() for job_id in job_by_id}
        for job in data["jobs"]:
            evidence_by_job[job["id"]].update(parse_json_list(job.get("photo_json")))
            evidence_by_job[job["id"]].update(parse_json_list(job.get("arrival_photos_json")))
        for row in data["readiness_confirmations"]:
            evidence_by_job.setdefault(row["job_id"], set()).update(parse_json_list(row.get("photo_json")))
        for row in data["mobilization_attempts"]:
            evidence_by_job.setdefault(row["job_id"], set()).update(parse_json_list(row.get("photo_json")))
            evidence_by_job.setdefault(row["job_id"], set()).update(parse_json_list(row.get("arrival_photos_json")))
        for row in data.get("field_progress_entries") or []:
            evidence_by_job.setdefault(row["job_id"], set()).update(parse_json_list(row.get("photo_json")))

        for job_id, filenames in evidence_by_job.items():
            for filename in sorted(name for name in filenames if name):
                archive_name = Path("files") / f"job_{job_id}" / "evidence" / secure_filename(filename)
                add_upload(z, filename, archive_name, job_id, "site_evidence")

        z.writestr("file_index.json", json.dumps(file_index, indent=2))
        z.writestr("missing_files.json", json.dumps(missing_files, indent=2))

    return archive_path, temp_dir, manifest, len(file_index), len(missing_files)



def _workspace_source_identity(manifest, job):
    exported_for = manifest.get("exported_for") or {}
    stable = "|".join([
        str(exported_for.get("username") or "").lower(),
        str(job.get("id") or ""),
        str(job.get("created_at") or ""),
        str(job.get("public_token") or ""),
    ])
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _workspace_restore_stage_dir():
    path = DATA_DIR / "workspace_restore_staging"
    path.mkdir(parents=True, exist_ok=True)
    # Best-effort cleanup of abandoned previews older than two hours.
    cutoff = datetime.now().timestamp() - 7200
    for item in path.glob("*"):
        try:
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
        except OSError:
            pass
    return path


def inspect_workspace_restore_zip(zip_path):
    """Validate and summarize a user workspace ZIP without changing live data."""
    try:
        if Path(zip_path).stat().st_size > MAX_WORKSPACE_RESTORE_BYTES:
            return False, "Workspace ZIP is larger than the 100 MB restore limit.", None
        with zipfile.ZipFile(zip_path, "r") as z:
            names = set(z.namelist())
            for name in names:
                pp = Path(name)
                if pp.is_absolute() or ".." in pp.parts:
                    return False, "Workspace ZIP contains an unsafe file path.", None
            required = {"workspace_manifest.json", "workspace_data.json", "file_index.json"}
            if not required.issubset(names):
                return False, "This is not a complete DispatchProof workspace ZIP.", None
            expanded = sum(info.file_size for info in z.infolist())
            if expanded > MAX_WORKSPACE_RESTORE_EXPANDED_BYTES:
                return False, "Workspace ZIP expands beyond the 300 MB safety limit.", None
            manifest_raw = z.read("workspace_manifest.json")
            data_raw = z.read("workspace_data.json")
            manifest = json.loads(manifest_raw.decode("utf-8"))
            data = json.loads(data_raw.decode("utf-8"))
            file_index = json.loads(z.read("file_index.json").decode("utf-8"))
            if manifest.get("product") != PRODUCT_NAME or manifest.get("export_type") != "user_workspace":
                return False, "This is not a DispatchProof user workspace backup.", None
            export_format = int(manifest.get("export_format") or 0)
            if export_format not in {1, 2}:
                return False, "This workspace backup format is not supported by this version of DispatchProof.", None
            backup_user = ((manifest.get("exported_for") or {}).get("username") or "").strip()
            if backup_user.lower() != (current_username() or "").strip().lower():
                return False, f"This workspace backup belongs to {backup_user or 'a different user'}. Sign in as that user or ask an Administrator for help.", None
            if not isinstance(data, dict) or not isinstance(data.get("jobs"), list) or not isinstance(file_index, list):
                return False, "Workspace backup data is malformed.", None
            fingerprint = hashlib.sha256(data_raw).hexdigest()
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError):
        return False, "The selected file is not a valid DispatchProof workspace ZIP.", None

    jobs = data.get("jobs") or []
    clients = data.get("clients") or []
    projects = data.get("projects") or []
    crew_members = data.get("crew_members") or []
    user_id = current_user_id()
    source_ids = {job.get("id"): _workspace_source_identity(manifest, job) for job in jobs}
    already = set()

    with get_db() as db:
        if user_id and source_ids:
            placeholders = ",".join("?" for _ in source_ids.values())
            rows = db.execute(
                f"SELECT source_identity FROM workspace_restore_items WHERE user_id = ? AND source_identity IN ({placeholders})",
                (user_id, *source_ids.values()),
            ).fetchall()
            already = {row["source_identity"] for row in rows}

        live_clients = {str(r["name"] or "").strip().lower(): r["id"] for r in db.execute("SELECT id, name FROM clients").fetchall()}
        live_projects = {(r["client_id"], str(r["name"] or "").strip().lower()) for r in db.execute("SELECT client_id, name FROM projects").fetchall()}
        live_crew = {str(r["name"] or "").strip().lower(): r["id"] for r in db.execute("SELECT id, name FROM crew_members").fetchall()}

        backup_client_names = {r.get("id"): str(r.get("name") or "").strip().lower() for r in clients}
        new_clients = [r for r in clients if backup_client_names.get(r.get("id")) and backup_client_names.get(r.get("id")) not in live_clients]

        new_projects = []
        for row in projects:
            pname = str(row.get("name") or "").strip().lower()
            cname = backup_client_names.get(row.get("client_id"))
            live_client_id = live_clients.get(cname) if cname else None
            if pname and (not live_client_id or (live_client_id, pname) not in live_projects):
                new_projects.append(row)

        new_crew = [r for r in crew_members if str(r.get("name") or "").strip().lower() and str(r.get("name") or "").strip().lower() not in live_crew]

        # Preview shared documents as new only when an equivalent original filename + size
        # is not already attached to the matched live entity.
        new_client_docs = 0
        for row in data.get("client_documents") or []:
            cname = backup_client_names.get(row.get("client_id"))
            live_client_id = live_clients.get(cname) if cname else None
            if not live_client_id:
                new_client_docs += 1
                continue
            exists = db.execute(
                "SELECT 1 FROM client_documents WHERE client_id = ? AND original_filename = ? COLLATE NOCASE AND file_size = ? LIMIT 1",
                (live_client_id, row.get("original_filename") or "", int(row.get("file_size") or 0)),
            ).fetchone()
            if not exists:
                new_client_docs += 1

        backup_projects = {r.get("id"): r for r in projects}
        new_project_docs = 0
        for row in data.get("project_documents") or []:
            project = backup_projects.get(row.get("project_id"))
            cname = backup_client_names.get(project.get("client_id")) if project else None
            live_client_id = live_clients.get(cname) if cname else None
            pname = str(project.get("name") or "").strip().lower() if project else ""
            live_project = None
            if live_client_id and pname:
                live_project = db.execute(
                    "SELECT id FROM projects WHERE client_id = ? AND name = ? COLLATE NOCASE",
                    (live_client_id, project.get("name")),
                ).fetchone()
            if not live_project:
                new_project_docs += 1
                continue
            exists = db.execute(
                "SELECT 1 FROM project_documents WHERE project_id = ? AND original_filename = ? COLLATE NOCASE AND file_size = ? LIMIT 1",
                (live_project["id"], row.get("original_filename") or "", int(row.get("file_size") or 0)),
            ).fetchone()
            if not exists:
                new_project_docs += 1

    new_jobs = [job for job in jobs if source_ids.get(job.get("id")) not in already]
    new_ids = {job.get("id") for job in new_jobs}
    available_job_files = [f for f in file_index if f.get("job_id") in new_ids and f.get("archive_path")]
    shared_file_count = sum(1 for f in file_index if f.get("kind") in {"client_document", "project_document"} and f.get("archive_path"))
    restorable_items = len(new_jobs) + len(new_clients) + len(new_projects) + len(new_crew) + new_client_docs + new_project_docs

    preview = {
        "manifest": manifest,
        "data": data,
        "file_index": file_index,
        "fingerprint": fingerprint,
        "source_identities": source_ids,
        "total_jobs": len(jobs),
        "new_jobs": len(new_jobs),
        "already_restored": len(jobs) - len(new_jobs),
        "team_jobs_as_personal": sum(1 for job in new_jobs if job.get("team_id")),
        "available_files": len(available_job_files) + shared_file_count,
        "job_documents": sum(1 for row in (data.get("job_documents") or []) if row.get("job_id") in new_ids),
        "crew_assignments": sum(1 for row in (data.get("job_crew_assignments") or []) if row.get("job_id") in new_ids),
        "new_clients": len(new_clients),
        "new_projects": len(new_projects),
        "new_crew": len(new_crew),
        "new_shared_documents": new_client_docs + new_project_docs,
        "setup_records_in_zip": len(clients) + len(projects) + len(crew_members),
        "restorable_items": restorable_items,
        "export_format": export_format,
        "skipped_email_events": sum(1 for row in (data.get("email_events") or []) if row.get("job_id") in new_ids),
        "skipped_activity": sum(1 for row in (data.get("activity_log") or []) if row.get("job_id") in new_ids),
    }
    return True, None, preview

def _restore_insert_row(db, table, row, exclude=None, overrides=None):
    exclude = set(exclude or ())
    overrides = dict(overrides or {})
    columns = {r["name"] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    payload = {k: v for k, v in dict(row).items() if k in columns and k not in exclude}
    payload.update({k: v for k, v in overrides.items() if k in columns})
    if not payload:
        raise ValueError(f"No restorable columns for {table}")
    keys = list(payload)
    sql = f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})"
    cur = db.execute(sql, tuple(payload[k] for k in keys))
    return cur.lastrowid


def _rewrite_filename_json(value, file_map):
    if not value:
        return value
    try:
        items = json.loads(value) if isinstance(value, str) else list(value)
    except (json.JSONDecodeError, TypeError, ValueError):
        return value
    if not isinstance(items, list):
        return value
    return json.dumps([file_map.get(str(item), str(item)) for item in items])


def restore_workspace_archive(zip_path):
    ok, error, preview = inspect_workspace_restore_zip(zip_path)
    if not ok:
        return False, error, None
    if current_user_is_admin() or not current_user_id():
        return False, "Workspace restore is available to Operator accounts only.", None

    data = preview["data"]
    identities = preview["source_identities"]
    user_id = current_user_id()
    created_files = []
    stats = {
        "jobs": 0, "files": 0, "already_restored": preview["already_restored"], "team_copies": 0,
        "clients": 0, "projects": 0, "crew": 0, "shared_documents": 0, "unavailability": 0,
    }

    with zipfile.ZipFile(zip_path, "r") as z, get_db() as db:
        try:
            import_jobs = []
            for job in data.get("jobs") or []:
                identity = identities.get(job.get("id"))
                exists = db.execute(
                    "SELECT 1 FROM workspace_restore_items WHERE user_id = ? AND source_identity = ?",
                    (user_id, identity),
                ).fetchone()
                if not exists:
                    import_jobs.append(job)
            source_job_ids = {job.get("id") for job in import_jobs}

            # Shared setup masters are restored additively by natural name. Existing
            # records are reused and never overwritten.
            client_map = {}
            clients_by_id = {row.get("id"): row for row in (data.get("clients") or [])}
            for old_id, row in clients_by_id.items():
                if not row.get("name"):
                    continue
                existing = db.execute("SELECT id FROM clients WHERE name = ? COLLATE NOCASE", (row["name"],)).fetchone()
                if existing:
                    client_map[old_id] = existing["id"]
                else:
                    client_map[old_id] = _restore_insert_row(
                        db, "clients", row, exclude={"id", "report_token"},
                        overrides={"report_token": secrets.token_urlsafe(24), "created_at": row.get("created_at") or now_iso(), "updated_at": now_iso()},
                    )
                    stats["clients"] += 1

            project_map = {}
            projects_by_id = {row.get("id"): row for row in (data.get("projects") or [])}
            for old_id, row in projects_by_id.items():
                if not row.get("name"):
                    continue
                live_client_id = client_map.get(row.get("client_id"))
                if not live_client_id:
                    continue
                existing = db.execute(
                    "SELECT id FROM projects WHERE client_id = ? AND name = ? COLLATE NOCASE",
                    (live_client_id, row["name"]),
                ).fetchone()
                if existing:
                    project_map[old_id] = existing["id"]
                else:
                    project_map[old_id] = _restore_insert_row(
                        db, "projects", row, exclude={"id", "report_token", "client_id"},
                        overrides={"report_token": secrets.token_urlsafe(24), "client_id": live_client_id, "created_at": row.get("created_at") or now_iso(), "updated_at": now_iso()},
                    )
                    stats["projects"] += 1

            crew_map = {}
            crew_by_id = {row.get("id"): row for row in (data.get("crew_members") or [])}
            for old_id, row in crew_by_id.items():
                if not row.get("name"):
                    continue
                existing = db.execute("SELECT id FROM crew_members WHERE name = ? COLLATE NOCASE", (row["name"],)).fetchone()
                if existing:
                    crew_map[old_id] = existing["id"]
                else:
                    crew_map[old_id] = _restore_insert_row(
                        db, "crew_members", row, exclude={"id"},
                        overrides={"created_at": row.get("created_at") or now_iso(), "updated_at": now_iso()},
                    )
                    stats["crew"] += 1

            for row in data.get("crew_unavailability") or []:
                live_crew_id = crew_map.get(row.get("crew_member_id"))
                if not live_crew_id:
                    continue
                exists = db.execute(
                    "SELECT 1 FROM crew_unavailability WHERE crew_member_id = ? AND start_date = ? AND end_date = ? AND COALESCE(reason,'') = COALESCE(?, '') LIMIT 1",
                    (live_crew_id, row.get("start_date"), row.get("end_date"), row.get("reason")),
                ).fetchone()
                if not exists:
                    _restore_insert_row(db, "crew_unavailability", row, exclude={"id", "crew_member_id"}, overrides={"crew_member_id": live_crew_id})
                    stats["unavailability"] += 1

            names = set(z.namelist())
            file_index = preview["file_index"]

            def restore_file(item, fallback_name="restored_file"):
                archive_path = item.get("archive_path")
                if not archive_path or archive_path not in names:
                    return None
                info = z.getinfo(archive_path)
                if info.file_size > MAX_JOB_DOCUMENT_BYTES:
                    return None
                original = secure_filename(item.get("original_filename") or item.get("stored_filename") or fallback_name) or fallback_name
                new_name = f"restore_{secrets.token_hex(10)}_{original}"
                target = UPLOAD_DIR / new_name
                target.write_bytes(z.read(archive_path))
                created_files.append(target)
                stats["files"] += 1
                return new_name

            file_by_stored = {str(item.get("stored_filename") or ""): item for item in file_index if item.get("stored_filename")}

            # Restore shared Client / Project documents additively.
            for row in data.get("client_documents") or []:
                live_client_id = client_map.get(row.get("client_id"))
                if not live_client_id:
                    continue
                exists = db.execute(
                    "SELECT 1 FROM client_documents WHERE client_id = ? AND original_filename = ? COLLATE NOCASE AND file_size = ? LIMIT 1",
                    (live_client_id, row.get("original_filename") or "", int(row.get("file_size") or 0)),
                ).fetchone()
                if exists:
                    continue
                item = file_by_stored.get(str(row.get("stored_filename") or ""))
                new_stored = restore_file(item) if item else None
                if not new_stored:
                    continue
                restored = dict(row)
                restored["stored_filename"] = new_stored
                restored["file_size"] = (UPLOAD_DIR / new_stored).stat().st_size
                _restore_insert_row(db, "client_documents", restored, exclude={"id", "client_id"}, overrides={"client_id": live_client_id})
                stats["shared_documents"] += 1

            for row in data.get("project_documents") or []:
                live_project_id = project_map.get(row.get("project_id"))
                if not live_project_id:
                    continue
                exists = db.execute(
                    "SELECT 1 FROM project_documents WHERE project_id = ? AND original_filename = ? COLLATE NOCASE AND file_size = ? LIMIT 1",
                    (live_project_id, row.get("original_filename") or "", int(row.get("file_size") or 0)),
                ).fetchone()
                if exists:
                    continue
                item = file_by_stored.get(str(row.get("stored_filename") or ""))
                new_stored = restore_file(item) if item else None
                if not new_stored:
                    continue
                restored = dict(row)
                restored["stored_filename"] = new_stored
                restored["file_size"] = (UPLOAD_DIR / new_stored).stat().st_size
                _restore_insert_row(db, "project_documents", restored, exclude={"id", "project_id"}, overrides={"project_id": live_project_id})
                stats["shared_documents"] += 1

            # Restore job-linked files under fresh storage names before rewriting JSON references.
            file_map = {}
            job_file_index = [f for f in file_index if f.get("job_id") in source_job_ids]
            for item in job_file_index:
                old_name = str(item.get("stored_filename") or "")
                if not old_name:
                    continue
                new_name = restore_file(item)
                if new_name:
                    file_map[old_name] = new_name

            job_map = {}
            job_by_old_id = {job.get("id"): job for job in import_jobs}
            for old_id, job in job_by_old_id.items():
                restored_job = dict(job)
                for field in ("photo_json", "arrival_photos_json"):
                    restored_job[field] = _rewrite_filename_json(restored_job.get(field), file_map)
                new_job_id = _restore_insert_row(
                    db, "jobs", restored_job,
                    exclude={"id", "public_token", "arrival_token", "client_report_token", "client_id", "project_id", "owner_user_id", "team_id"},
                    overrides={
                        "public_token": secrets.token_urlsafe(24),
                        "arrival_token": secrets.token_urlsafe(24),
                        "client_report_token": secrets.token_urlsafe(24),
                        "client_id": client_map.get(job.get("client_id")),
                        "project_id": project_map.get(job.get("project_id")),
                        "owner_user_id": user_id,
                        "team_id": None,
                    },
                )
                job_map[old_id] = new_job_id
                identity = identities.get(old_id)
                db.execute(
                    "INSERT INTO workspace_restore_items (user_id, source_identity, source_job_id, restored_job_id, created_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, identity, old_id, new_job_id, now_iso()),
                )
                stats["jobs"] += 1
                if job.get("team_id"):
                    stats["team_copies"] += 1

            field_link_map = {}
            for row in data.get("field_update_links") or []:
                old_job_id = row.get("job_id")
                if old_job_id not in job_map:
                    continue
                restored = dict(row)
                old_link_id = row.get("id")
                new_link_id = _restore_insert_row(
                    db, "field_update_links", restored,
                    exclude={"id", "job_id", "token", "crew_member_id"},
                    overrides={
                        "job_id": job_map[old_job_id],
                        "token": secrets.token_urlsafe(24),
                        "crew_member_id": crew_map.get(row.get("crew_member_id")),
                    },
                )
                if old_link_id is not None:
                    field_link_map[old_link_id] = new_link_id

            for row in data.get("field_progress_entries") or []:
                old_job_id = row.get("job_id")
                if old_job_id not in job_map:
                    continue
                restored = dict(row)
                restored["photo_json"] = _rewrite_filename_json(restored.get("photo_json"), file_map)
                _restore_insert_row(
                    db, "field_progress_entries", restored,
                    exclude={"id", "job_id", "field_link_id"},
                    overrides={
                        "job_id": job_map[old_job_id],
                        "field_link_id": field_link_map.get(row.get("field_link_id")),
                    },
                )

            for table in ("readiness_confirmations", "mobilization_attempts", "job_notes"):
                for row in data.get(table) or []:
                    old_job_id = row.get("job_id")
                    if old_job_id not in job_map:
                        continue
                    restored = dict(row)
                    for field in ("photo_json", "arrival_photos_json"):
                        if field in restored:
                            restored[field] = _rewrite_filename_json(restored.get(field), file_map)
                    _restore_insert_row(db, table, restored, exclude={"id", "job_id"}, overrides={"job_id": job_map[old_job_id]})

            assignments = [r for r in (data.get("job_crew_assignments") or []) if r.get("job_id") in source_job_ids]
            for row in assignments:
                if row.get("job_id") not in job_map or row.get("crew_member_id") not in crew_map:
                    continue
                _restore_insert_row(
                    db, "job_crew_assignments", row,
                    exclude={"id", "job_id", "crew_member_id"},
                    overrides={"job_id": job_map[row["job_id"]], "crew_member_id": crew_map[row["crew_member_id"]]},
                )

            for row in data.get("job_documents") or []:
                old_job_id = row.get("job_id")
                new_stored = file_map.get(str(row.get("stored_filename") or ""))
                if old_job_id not in job_map or not new_stored:
                    continue
                restored = dict(row)
                restored["stored_filename"] = new_stored
                target = UPLOAD_DIR / new_stored
                restored["file_size"] = target.stat().st_size if target.exists() else int(row.get("file_size") or 0)
                _restore_insert_row(db, "job_documents", restored, exclude={"id", "job_id"}, overrides={"job_id": job_map[old_job_id]})

            total_changes = stats["jobs"] + stats["clients"] + stats["projects"] + stats["crew"] + stats["shared_documents"] + stats["unavailability"]
            if total_changes:
                record_activity(
                    db,
                    "Workspace Restored",
                    f"Restored {stats['jobs']} job(s), {stats['clients']} client(s), {stats['projects']} project(s), {stats['crew']} crew record(s), and {stats['files']} linked file(s) from a workspace ZIP.",
                )
            db.commit()
        except Exception:
            db.rollback()
            for path in created_files:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
    return True, None, stats

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

PAGE_HELP_ANCHORS = {
    "dashboard": "help-dashboard",
    "schedule_board": "help-schedule",
    "crew_directory": "help-crew-directory",
    "find_subcontractor": "help-find-subcontractor",
    "edit_crew_member": "help-crew-directory",
    "new_job": "help-create-job",
    "edit_job": "help-edit-job",
    "job_detail": "everyday-workflows",
    "field_updates": "help-field-updates",
    "readiness_request": "help-readiness-request",
    "arrival": "help-arrival",
    "completed_jobs": "help-completed-jobs",
    "email_outbox": "help-email-outbox",
    "email_outbox_detail": "help-email-outbox",
    "clients": "clients-projects",
    "new_client": "help-create-client",
    "client_detail": "clients-projects",
    "new_project": "help-create-project",
    "project_detail": "clients-projects",
    "project_route_optimizer": "help-route-optimization",
    "document_center": "documents",
    "my_account": "account-access",
    "company_settings": "help-company-settings",
    "users_access": "help-users-access",
    "edit_user": "help-users-access",
    "activity_log": "help-activity-log",
    "backup_restore": "backup-restore",
}

def page_help_anchor_for_request():
    endpoint = request.endpoint or ""
    return PAGE_HELP_ANCHORS.get(endpoint)


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
        "app_version": "2.44.3",
        "smtp_configured": smtp_is_configured(),
        "email_mode": EMAIL_MODE,
        "email_delivery_enabled": email_delivery_enabled(),
        "admin_authenticated": user_authenticated(),
        "admin_username": current_username(),
        "current_display_name": current_display_name(),
        "current_user_role": current_user_role(),
        "current_user_is_admin": current_user_is_admin(),
        "page_help_anchor": page_help_anchor_for_request(),
    }

@app.before_request
def ensure_db():
    global LAST_REMINDER_SWEEP_AT
    init_db()

    public_endpoints = {
        "login", "health", "static", "public_readiness", "public_arrival",
        "public_field_update", "public_field_update_submitted",
        "public_client_report", "client_report_asset",
        "public_client_portfolio_report", "public_project_portfolio_report",
        "client_portfolio_asset", "project_portfolio_asset",
        "company_logo"
    }
    if request.endpoint not in public_endpoints and not user_authenticated():
        return redirect(url_for("login", next=request.full_path if request.query_string else request.path))

    # V2.39.2: a signed browser cookie is not enough for DB-backed users.
    # Confirm the referenced user still exists, is active, and is the same
    # username before allowing any internal work. This closes a stale-session
    # path that could surface later as FOREIGN KEY constraint failed on jobs.
    if request.endpoint not in public_endpoints and user_authenticated() and not session.get("dispatchproof_owner"):
        if not database_user_session_is_current():
            next_url = request.full_path if request.query_string else request.path
            session.clear()
            flash("Your user session is no longer current. Please sign in again before continuing.")
            return redirect(url_for("login", next=next_url))

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
        "add_team",
        "toggle_team_sharing",
        "add_team_member",
        "remove_team_member",
        "client_combined_report",
        "rotate_client_combined_report",
        "project_combined_report",
        "rotate_project_combined_report",
        "activity_log",
        "reopen_job",
        "delete_job_document",
        "delete_project_document",
        "delete_client_document",
    }
    if request.endpoint in admin_only_endpoints and user_authenticated() and not current_user_is_admin():
        flash("Administrator access is required for that page.")
        return redirect(url_for("dashboard"))

    # V2.37: central direct-URL protection for every authenticated internal
    # route carrying a job_id. Public token/evidence routes are excluded above.
    job_id = (request.view_args or {}).get("job_id") if request.view_args else None
    if job_id and request.endpoint not in public_endpoints:
        with get_db() as db:
            exists = db.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not exists:
                abort(404)
            if not user_can_access_job(db, job_id):
                abort(404)

    # Do not make static/public requests responsible for sending reminders.
    if request.endpoint in {
        "static", "health", "public_readiness", "public_arrival",
        "public_field_update", "public_field_update_submitted",
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

@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


@app.route("/health")
def health():
    return {
        "status": "ok",
        "version": "2.40.2",
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

    workspace_stats = None
    if not current_user_is_admin():
        with get_db() as db:
            workspace_stats = workspace_export_stats(db)

    return render_template(
        "my_account.html",
        owner_account=owner_account,
        user=user,
        workspace_stats=workspace_stats,
    )


@app.get("/account/export")
def export_my_workspace():
    if current_user_is_admin():
        flash("Owner and Administrator accounts can use the full Backup & Restore page.")
        return redirect(url_for("backup_restore"))

    archive_path, temp_dir, manifest, file_count, missing_count = create_workspace_export_archive()
    job_count = manifest.get("counts", {}).get("jobs", 0)

    with get_db() as db:
        record_activity(
            db,
            "Workspace Export Downloaded",
            f"Exported {job_count} accessible job(s) and {file_count} linked file(s).",
        )
        db.commit()

    response = send_file(
        archive_path,
        as_attachment=True,
        download_name=archive_path.name,
        mimetype="application/zip",
        max_age=0,
    )
    if missing_count:
        response.headers["X-DispatchProof-Missing-Files"] = str(missing_count)
    response.call_on_close(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
    return response


@app.post("/account/restore/preview")
def preview_my_workspace_restore():
    if current_user_is_admin():
        flash("Owner and Administrator accounts should use the full Backup & Restore page.")
        return redirect(url_for("backup_restore"))
    uploaded = request.files.get("workspace_file")
    if not uploaded or not uploaded.filename:
        flash("Choose a DispatchProof workspace ZIP first.")
        return redirect(url_for("my_account") + "#workspace-restore")
    if not uploaded.filename.lower().endswith(".zip"):
        flash("Workspace restore requires a .zip file created by Download My Workspace ZIP.")
        return redirect(url_for("my_account") + "#workspace-restore")

    stage_dir = _workspace_restore_stage_dir()
    token = secrets.token_urlsafe(24)
    zip_path = stage_dir / f"{token}.zip"
    meta_path = stage_dir / f"{token}.json"
    uploaded.save(zip_path)
    ok, error, preview = inspect_workspace_restore_zip(zip_path)
    if not ok:
        zip_path.unlink(missing_ok=True)
        flash(error or "Workspace ZIP could not be validated.")
        return redirect(url_for("my_account") + "#workspace-restore")
    meta_path.write_text(json.dumps({"user_id": current_user_id(), "created_at": now_iso()}), encoding="utf-8")
    return render_template("workspace_restore_preview.html", preview=preview, restore_token=token)


@app.post("/account/restore/commit")
def commit_my_workspace_restore():
    if current_user_is_admin():
        flash("Owner and Administrator accounts should use the full Backup & Restore page.")
        return redirect(url_for("backup_restore"))
    token = (request.form.get("restore_token") or "").strip()
    app.logger.info("Workspace restore commit requested user_id=%r token_prefix=%s", current_user_id(), token[:8] if token else "")
    if request.form.get("confirm_restore") != "yes":
        flash("Confirm that you want to restore the previewed workspace before continuing.")
        return redirect(url_for("my_account") + "#workspace-restore")
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", token):
        flash("That workspace restore preview is no longer valid. Please upload the ZIP again.")
        return redirect(url_for("my_account") + "#workspace-restore")
    stage_dir = _workspace_restore_stage_dir()
    zip_path = stage_dir / f"{token}.zip"
    meta_path = stage_dir / f"{token}.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        flash("That workspace restore preview has expired. Please upload the ZIP again.")
        return redirect(url_for("my_account") + "#workspace-restore")
    if int(meta.get("user_id") or 0) != int(current_user_id() or 0) or not zip_path.is_file():
        abort(404)
    try:
        ok, error, stats = restore_workspace_archive(zip_path)
    except Exception:
        app.logger.exception("Workspace restore failed for user_id=%r", current_user_id())
        flash("Workspace restore could not be completed. Nothing from this restore was committed. Please try again or contact an Administrator.")
        return redirect(url_for("my_account") + "#workspace-restore")
    finally:
        zip_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
    if not ok:
        flash(error or "Workspace restore could not be completed.")
    else:
        total_changes = sum(int(stats.get(key, 0) or 0) for key in ("jobs", "clients", "projects", "crew", "shared_documents", "unavailability"))
        if total_changes == 0:
            flash("Nothing new was restored. The records in that backup are already present in this workspace.")
        else:
            extra = f" {stats['team_copies']} Team job(s) were restored as private personal copies." if stats.get("team_copies") else ""
            flash(
                f"Workspace restored: {stats.get('jobs', 0)} job(s), {stats.get('clients', 0)} client(s), "
                f"{stats.get('projects', 0)} project(s), {stats.get('crew', 0)} crew record(s), and "
                f"{stats.get('files', 0)} linked file(s).{extra}"
            )
    return redirect(url_for("my_account") + "#workspace-restore")



@app.route("/crew/find-subcontractor", methods=["GET", "POST"])
@app.route("/jobs/<int:job_id>/find-subcontractor", methods=["GET", "POST"])
def find_subcontractor(job_id=None):
    job = None
    assigned_project = None
    if job_id:
        with get_db() as db:
            job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not job:
                abort(404)
            if job["project_id"]:
                assigned_project = db.execute("SELECT * FROM projects WHERE id = ?", (job["project_id"],)).fetchone()

    default_location = ""
    if assigned_project and (assigned_project["location"] or "").strip():
        default_location = assigned_project["location"].strip()
    elif job and (job["project_site"] or "").strip():
        default_location = job["project_site"].strip()

    location = (request.form.get("location") if request.method == "POST" else request.args.get("location")) or default_location
    location = location.strip()
    country = ((request.form.get("country") if request.method == "POST" else request.args.get("country")) or "US").upper().strip()
    if country not in CONTRACTOR_COUNTRY_CONFIG:
        country = "US"
    trade = ((request.form.get("trade") if request.method == "POST" else request.args.get("trade")) or "handyman").strip()
    if trade not in CONTRACTOR_TRADE_CONFIG:
        trade = "handyman"
    tolerance = ((request.form.get("tolerance") if request.method == "POST" else request.args.get("tolerance")) or "balanced").strip().lower()
    if tolerance not in {"strict", "balanced", "broad"}:
        tolerance = "balanced"
    try:
        radius = int((request.form.get("radius") if request.method == "POST" else request.args.get("radius")) or 30)
    except ValueError:
        radius = 30
    max_radius = 60 if contractor_country_info(country)["unit"] == "mi" else 100
    radius = max(1, min(max_radius, radius))

    results = []
    search_meta = None
    search_error = None
    search_performed = request.method == "POST"
    if search_performed:
        try:
            search_meta = run_contractor_search(location, country, trade, radius, tolerance, max_results=15)
            results = search_meta["results"]
        except ContractorSearchError as exc:
            search_error = str(exc)

    if results:
        with get_db() as db:
            assigned_ids = set()
            if job_id:
                assigned_ids = {
                    row["crew_member_id"] for row in db.execute(
                        "SELECT crew_member_id FROM job_crew_assignments WHERE job_id = ?", (job_id,)
                    ).fetchall()
                }
            for row in results:
                existing = db.execute(
                    """SELECT * FROM crew_members
                       WHERE source_place_id = ?
                          OR (source_place_id IS NULL AND name = ? COLLATE NOCASE)
                       ORDER BY CASE WHEN source_place_id = ? THEN 0 ELSE 1 END, id
                       LIMIT 1""",
                    (row["place_id"], row["name"], row["place_id"]),
                ).fetchone()
                row["existing_member"] = dict(existing) if existing else None
                row["already_assigned"] = bool(existing and existing["id"] in assigned_ids)

    return render_template(
        "find_subcontractor.html",
        job=job,
        assigned_project=assigned_project,
        location=location,
        country=country,
        trade=trade,
        radius=radius,
        tolerance=tolerance,
        country_config=CONTRACTOR_COUNTRY_CONFIG,
        trade_config=CONTRACTOR_TRADE_CONFIG,
        results=results,
        search_meta=search_meta,
        search_error=search_error,
        search_performed=search_performed,
        search_configured=bool(CONTRACTOR_SEARCH_API_KEY),
        distance_unit=contractor_country_info(country)["unit"],
    )


@app.post("/subcontractors/save-found")
def save_found_subcontractor():
    job_id = normalize_optional_id(request.form.get("job_id"))
    action = (request.form.get("action") or "save").strip().lower()
    source_place_id = (request.form.get("place_id") or "").strip()
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    address = (request.form.get("address") or "").strip()
    website = contractor_place_website({"website": (request.form.get("website") or "").strip()})
    trade = (request.form.get("trade") or "handyman").strip()
    trade_label = CONTRACTOR_TRADE_CONFIG.get(trade, CONTRACTOR_TRADE_CONFIG["handyman"])["label"]

    if not source_place_id or not name:
        flash("That contractor result is incomplete. Run the search again before saving it.")
        return redirect(url_for("find_subcontractor", job_id=job_id) if job_id else url_for("find_subcontractor"))

    with get_db() as db:
        job = None
        if job_id:
            job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not job or not user_can_access_job(db, job_id):
                abort(404)

        existing = db.execute(
            "SELECT * FROM crew_members WHERE source_place_id = ? LIMIT 1",
            (source_place_id,),
        ).fetchone()
        if not existing:
            existing = db.execute(
                "SELECT * FROM crew_members WHERE name = ? COLLATE NOCASE LIMIT 1",
                (name,),
            ).fetchone()

        created = False
        if existing:
            if existing["member_type"] != "SUBCONTRACTOR":
                flash(f'{name} already exists as Internal Crew. Edit that record first if it should become a subcontractor.')
                return redirect(url_for("edit_crew_member", crew_member_id=existing["id"]))
            crew_member_id = existing["id"]
            db.execute("""
                UPDATE crew_members
                SET source_provider = COALESCE(NULLIF(source_provider, ''), 'FOURSQUARE'),
                    source_place_id = COALESCE(NULLIF(source_place_id, ''), ?),
                    source_address = CASE WHEN TRIM(COALESCE(source_address, '')) = '' THEN ? ELSE source_address END,
                    source_website = CASE WHEN TRIM(COALESCE(source_website, '')) = '' THEN ? ELSE source_website END,
                    phone = CASE WHEN TRIM(COALESCE(phone, '')) = '' THEN ? ELSE phone END,
                    role_trade = CASE WHEN TRIM(COALESCE(role_trade, '')) = '' THEN ? ELSE role_trade END,
                    updated_at = ?
                WHERE id = ?
            """, (source_place_id, address, website, phone, trade_label, now_iso(), crew_member_id))
            existing = db.execute("SELECT * FROM crew_members WHERE id = ?", (crew_member_id,)).fetchone()
        else:
            cur = db.execute("""
                INSERT INTO crew_members (
                    name, member_type, company_name, source_provider, source_place_id,
                    source_address, source_website, email, phone, role_trade, notes,
                    is_active, created_at, updated_at
                ) VALUES (?, 'SUBCONTRACTOR', '', 'FOURSQUARE', ?, ?, ?, '', ?, ?, '', 1, ?, ?)
            """, (name, source_place_id, address, website, phone, trade_label, now_iso(), now_iso()))
            crew_member_id = cur.lastrowid
            created = True
            record_activity(
                db,
                "Subcontractor Saved",
                f"Saved {name} from Find a Subcontractor ({trade_label}).",
                job_id=job_id,
            )

        assigned = False
        inactive_blocked = False
        completed_blocked = False
        already_assigned = False
        if action == "save_assign" and job_id:
            current = db.execute("SELECT * FROM crew_members WHERE id = ?", (crew_member_id,)).fetchone()
            if job["status"] == "COMPLETED":
                completed_blocked = True
            elif not current["is_active"]:
                inactive_blocked = True
            else:
                assigned = append_crew_member_to_job(db, job_id, crew_member_id)
                already_assigned = not assigned
                if assigned:
                    record_activity(
                        db,
                        "Crew Assignment Updated",
                        f"Added subcontractor {name} to the field assignment from Find a Subcontractor.",
                        job_id=job_id,
                    )
        db.commit()

    if action == "save_assign" and job_id:
        if completed_blocked:
            flash(f"{name} was saved to the Subcontractor Directory, but completed jobs cannot receive new assignments.")
            return redirect(url_for("find_subcontractor", job_id=job_id))
        if inactive_blocked:
            flash(f"{name} is currently inactive. Reactivate the subcontractor before assigning it to a job.")
            return redirect(url_for("edit_crew_member", crew_member_id=crew_member_id))
        if assigned:
            flash(f"{name} saved and assigned to this job.")
        elif already_assigned:
            flash(f"{name} is already assigned to this job. No duplicate assignment was created.")
        return redirect(url_for("job_detail", job_id=job_id) + "#field-assignment")

    if created:
        flash(f"{name} saved to Crew & Subcontractors.")
    else:
        flash(f"{name} is already in Crew & Subcontractors; available source details were refreshed.")
    if job_id:
        return redirect(url_for("find_subcontractor", job_id=job_id))
    return redirect(url_for("edit_crew_member", crew_member_id=crew_member_id))


@app.route("/crew")
def crew_directory():
    search_query = (request.args.get("q") or "").strip()
    status_filter = (request.args.get("status") or "active").strip().lower()
    type_filter = (request.args.get("type") or "all").strip().lower()
    if status_filter not in {"active", "inactive", "all"}:
        status_filter = "active"
    if type_filter not in {"all", "internal", "subcontractor"}:
        type_filter = "all"

    today = local_today().isoformat()
    next7 = (local_today() + timedelta(days=7)).isoformat()

    where = []
    params = []
    if status_filter == "active":
        where.append("cm.is_active = 1")
    elif status_filter == "inactive":
        where.append("cm.is_active = 0")

    if type_filter == "internal":
        where.append("cm.member_type = 'INTERNAL'")
    elif type_filter == "subcontractor":
        where.append("cm.member_type = 'SUBCONTRACTOR'")

    if search_query:
        where.append("""
            LOWER(
                COALESCE(cm.name, '') || ' ' ||
                COALESCE(cm.company_name, '') || ' ' ||
                COALESCE(cm.member_type, '') || ' ' ||
                COALESCE(cm.email, '') || ' ' ||
                COALESCE(cm.phone, '') || ' ' ||
                COALESCE(cm.role_trade, '') || ' ' ||
                COALESCE(cm.source_address, '') || ' ' ||
                COALESCE(cm.source_website, '') || ' ' ||
                COALESCE(cm.notes, '')
            ) LIKE ?
        """)
        params.append(f"%{search_query.lower()}%")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with get_db() as db:
        visibility_clause, visibility_params = job_visibility_sql("j")
        members = db.execute(f"""
            SELECT
                cm.*,
                COUNT(DISTINCT CASE
                    WHEN j.status <> 'COMPLETED' THEN j.id
                END) AS active_job_count,
                COUNT(DISTINCT CASE
                    WHEN j.status <> 'COMPLETED'
                     AND j.installation_date >= ?
                     AND j.installation_date <= ?
                    THEN j.id
                END) AS next7_job_count,
                (
                    SELECT COUNT(*)
                    FROM crew_unavailability cu
                    WHERE cu.crew_member_id = cm.id
                      AND cu.end_date >= ?
                ) AS upcoming_time_off_count
            FROM crew_members cm
            LEFT JOIN job_crew_assignments jca
              ON jca.crew_member_id = cm.id
            LEFT JOIN jobs j
              ON j.id = jca.job_id AND ({visibility_clause})
            {where_sql}
            GROUP BY cm.id
            ORDER BY
                CASE WHEN cm.is_active = 1 THEN 0 ELSE 1 END,
                CASE WHEN cm.member_type = 'SUBCONTRACTOR' THEN 1 ELSE 0 END,
                LOWER(COALESCE(cm.company_name, '')),
                LOWER(cm.name),
                cm.id
        """, (today, next7, today, *visibility_params, *params)).fetchall()

        counts = {
            "active": db.execute(
                "SELECT COUNT(*) AS c FROM crew_members WHERE is_active = 1"
            ).fetchone()["c"],
            "active_internal": db.execute(
                "SELECT COUNT(*) AS c FROM crew_members WHERE is_active = 1 AND member_type = 'INTERNAL'"
            ).fetchone()["c"],
            "active_subcontractors": db.execute(
                "SELECT COUNT(*) AS c FROM crew_members WHERE is_active = 1 AND member_type = 'SUBCONTRACTOR'"
            ).fetchone()["c"],
            "inactive": db.execute(
                "SELECT COUNT(*) AS c FROM crew_members WHERE is_active = 0"
            ).fetchone()["c"],
            "assigned_active_jobs": db.execute(f"""
                SELECT COUNT(DISTINCT j.id) AS c
                FROM jobs j
                JOIN job_crew_assignments jca ON jca.job_id = j.id
                WHERE j.status <> 'COMPLETED'
                  AND ({visibility_clause})
            """, visibility_params).fetchone()["c"],
            "upcoming_time_off": db.execute("""
                SELECT COUNT(*) AS c
                FROM crew_unavailability
                WHERE end_date >= ?
            """, (today,)).fetchone()["c"],
        }

    return render_template(
        "crew_directory.html",
        members=members,
        counts=counts,
        search_query=search_query,
        status_filter=status_filter,
        type_filter=type_filter,
    )


@app.post("/crew/add")
def add_crew_member():
    name = (request.form.get("name") or "").strip()
    member_type = normalize_crew_member_type(request.form.get("member_type"))
    company_name = (request.form.get("company_name") or "").strip()
    email = (request.form.get("email") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    role_trade = (request.form.get("role_trade") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    if member_type != "SUBCONTRACTOR":
        company_name = ""

    if not name:
        flash("Name is required.")
        return redirect(url_for("crew_directory") + "#add-crew")

    try:
        with get_db() as db:
            cur = db.execute("""
                INSERT INTO crew_members (
                    name, member_type, company_name, email, phone, role_trade, notes,
                    is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (
                name, member_type, company_name, email, phone, role_trade, notes,
                now_iso(), now_iso()
            ))
            kind = "subcontractor" if member_type == "SUBCONTRACTOR" else "internal crew member"
            article = "a" if member_type == "SUBCONTRACTOR" else "an"
            company_text = f" with {company_name}" if company_name else ""
            record_activity(
                db,
                "Crew Member Added",
                f"Added {name} as {article} {kind}{company_text}"
                + (f" ({role_trade})." if role_trade else "."),
            )
            db.commit()
            member_id = cur.lastrowid
    except sqlite3.IntegrityError:
        flash("A directory record with that name already exists.")
        return redirect(url_for("crew_directory") + "#add-crew")

    flash(f"{name} added to Crew & Subcontractors.")
    return redirect(url_for("edit_crew_member", crew_member_id=member_id))


@app.route("/crew/<int:crew_member_id>/edit", methods=["GET", "POST"])
def edit_crew_member(crew_member_id):
    with get_db() as db:
        visibility_clause, visibility_params = job_visibility_sql("j")
        member = db.execute(
            "SELECT * FROM crew_members WHERE id = ?",
            (crew_member_id,),
        ).fetchone()
        if not member:
            abort(404)

        if request.method == "POST":
            name = (request.form.get("name") or "").strip()
            member_type = normalize_crew_member_type(request.form.get("member_type"))
            company_name = (request.form.get("company_name") or "").strip()
            email = (request.form.get("email") or "").strip()
            phone = (request.form.get("phone") or "").strip()
            role_trade = (request.form.get("role_trade") or "").strip()
            notes = (request.form.get("notes") or "").strip()

            if member_type != "SUBCONTRACTOR":
                company_name = ""

            if not name:
                flash("Name is required.")
                return redirect(url_for("edit_crew_member", crew_member_id=crew_member_id))

            changes = []

            def crew_note_change(label, old, new):
                old_text = str(old or "")
                new_text = str(new or "")
                if old_text != new_text:
                    changes.append(f"{label}: {old_text or '—'} → {new_text or '—'}")

            crew_note_change("Name", member["name"], name)
            crew_note_change("Type", "Subcontractor" if member["member_type"] == "SUBCONTRACTOR" else "Internal Crew", "Subcontractor" if member_type == "SUBCONTRACTOR" else "Internal Crew")
            crew_note_change("Company", member["company_name"], company_name)
            crew_note_change("Role / Trade", member["role_trade"], role_trade)
            crew_note_change("Email", member["email"], email)
            crew_note_change("Phone", member["phone"], phone)
            crew_note_change("Notes", member["notes"], notes)

            try:
                db.execute("""
                    UPDATE crew_members
                    SET name = ?, member_type = ?, company_name = ?,
                        email = ?, phone = ?, role_trade = ?, notes = ?, updated_at = ?
                    WHERE id = ?
                """, (
                    name, member_type, company_name, email, phone, role_trade, notes,
                    now_iso(), crew_member_id,
                ))

                if (member["name"] or "").strip() != name:
                    sync_jobs_after_crew_member_rename(
                        db, crew_member_id, member["name"]
                    )

                if changes:
                    record_activity(
                        db,
                        "Crew Member Updated",
                        f"Updated {name}: " + " · ".join(changes),
                    )
                db.commit()
            except sqlite3.IntegrityError:
                flash("A directory record with that name already exists.")
                return redirect(url_for("edit_crew_member", crew_member_id=crew_member_id))

            flash("Directory record updated." if changes else "No directory changes were made.")
            return redirect(url_for("edit_crew_member", crew_member_id=crew_member_id))

        assignments = db.execute(f"""
            SELECT
                j.id,
                j.job_name,
                j.project_site,
                j.installation_date,
                j.status,
                jca.is_lead,
                c.name AS client_name,
                p.name AS project_name
            FROM job_crew_assignments jca
            JOIN jobs j ON j.id = jca.job_id
            LEFT JOIN clients c ON c.id = j.client_id
            LEFT JOIN projects p ON p.id = j.project_id
            WHERE jca.crew_member_id = ?
              AND ({visibility_clause})
            ORDER BY
                CASE WHEN j.status = 'COMPLETED' THEN 1 ELSE 0 END,
                j.installation_date DESC,
                j.id DESC
            LIMIT 50
        """, (crew_member_id, *visibility_params)).fetchall()

        unavailability = db.execute("""
            SELECT *
            FROM crew_unavailability
            WHERE crew_member_id = ?
            ORDER BY
                CASE WHEN end_date >= ? THEN 0 ELSE 1 END,
                start_date ASC,
                id ASC
        """, (crew_member_id, local_today().isoformat())).fetchall()

    return render_template(
        "edit_crew_member.html",
        member=member,
        assignments=assignments,
        unavailability=unavailability,
        today_iso=local_today().isoformat(),
    )


@app.post("/crew/<int:crew_member_id>/availability/add")
def add_crew_unavailability(crew_member_id):
    start_date = (request.form.get("start_date") or "").strip()
    end_date = (request.form.get("end_date") or "").strip()
    reason = (request.form.get("reason") or "Unavailable").strip() or "Unavailable"

    try:
        start_day = date.fromisoformat(start_date)
        end_day = date.fromisoformat(end_date)
    except ValueError:
        flash("Enter valid start and end dates for crew availability.")
        return redirect(url_for("edit_crew_member", crew_member_id=crew_member_id) + "#availability")

    if end_day < start_day:
        flash("End Date cannot be before Start Date.")
        return redirect(url_for("edit_crew_member", crew_member_id=crew_member_id) + "#availability")

    with get_db() as db:
        member = db.execute(
            "SELECT * FROM crew_members WHERE id = ?",
            (crew_member_id,),
        ).fetchone()
        if not member:
            abort(404)

        db.execute("""
            INSERT INTO crew_unavailability (
                crew_member_id, start_date, end_date, reason, created_at
            ) VALUES (?, ?, ?, ?, ?)
        """, (crew_member_id, start_date, end_date, reason, now_iso()))
        record_activity(
            db,
            "Crew Availability Added",
            f"Marked {member['name']} unavailable {start_date} through {end_date}: {reason}.",
        )
        db.commit()

    flash(f"Availability saved for {member['name']}.")
    return redirect(url_for("edit_crew_member", crew_member_id=crew_member_id) + "#availability")


@app.post("/crew/<int:crew_member_id>/availability/<int:availability_id>/delete")
def delete_crew_unavailability(crew_member_id, availability_id):
    with get_db() as db:
        member = db.execute(
            "SELECT * FROM crew_members WHERE id = ?",
            (crew_member_id,),
        ).fetchone()
        if not member:
            abort(404)

        row = db.execute("""
            SELECT *
            FROM crew_unavailability
            WHERE id = ? AND crew_member_id = ?
        """, (availability_id, crew_member_id)).fetchone()
        if not row:
            abort(404)

        db.execute(
            "DELETE FROM crew_unavailability WHERE id = ? AND crew_member_id = ?",
            (availability_id, crew_member_id),
        )
        record_activity(
            db,
            "Crew Availability Removed",
            f"Removed {member['name']} availability {row['start_date']} through {row['end_date']} ({row['reason'] or 'Unavailable'}).",
        )
        db.commit()

    flash(f"Availability removed for {member['name']}.")
    return redirect(url_for("edit_crew_member", crew_member_id=crew_member_id) + "#availability")


@app.post("/crew/<int:crew_member_id>/delete")
def delete_crew_member(crew_member_id):
    with get_db() as db:
        member = db.execute(
            "SELECT * FROM crew_members WHERE id = ?",
            (crew_member_id,),
        ).fetchone()
        if not member:
            abort(404)

        assignment = db.execute(
            "SELECT 1 FROM job_crew_assignments WHERE crew_member_id = ? LIMIT 1",
            (crew_member_id,),
        ).fetchone()
        if assignment:
            flash(
                f"{member['name']} is linked to existing job history and cannot be permanently deleted. "
                "Deactivate this crew member instead so past job records stay intact."
            )
            return redirect(url_for("crew_directory", status="all"))

        try:
            db.execute(
                "DELETE FROM crew_unavailability WHERE crew_member_id = ?",
                (crew_member_id,),
            )
            db.execute(
                "DELETE FROM crew_members WHERE id = ?",
                (crew_member_id,),
            )
            record_activity(
                db,
                "Crew Member Deleted",
                f"Permanently deleted {member['name']} from Crew Directory. The crew member had no linked job history.",
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            flash(
                f"{member['name']} could not be deleted because the crew member is linked to existing records. "
                "Deactivate this crew member instead."
            )
            return redirect(url_for("crew_directory", status="all"))

    flash(f"{member['name']} permanently deleted from Crew Directory.")
    return redirect(url_for("crew_directory", status="all"))


@app.post("/crew/<int:crew_member_id>/toggle")
def toggle_crew_member(crew_member_id):
    with get_db() as db:
        member = db.execute(
            "SELECT * FROM crew_members WHERE id = ?",
            (crew_member_id,),
        ).fetchone()
        if not member:
            abort(404)

        new_active = 0 if member["is_active"] else 1
        db.execute("""
            UPDATE crew_members
            SET is_active = ?, updated_at = ?
            WHERE id = ?
        """, (new_active, now_iso(), crew_member_id))

        record_activity(
            db,
            "Crew Member Reactivated" if new_active else "Crew Member Deactivated",
            f"{'Reactivated' if new_active else 'Deactivated'} {member['name']} in Crew Directory.",
        )
        db.commit()

    flash(
        f"{member['name']} {'reactivated' if new_active else 'deactivated'}. "
        "Existing job assignments were preserved."
    )
    return redirect(url_for("crew_directory", status="all"))



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
        teams = db.execute("""
            SELECT t.*, COUNT(tm.user_id) AS member_count
            FROM teams t
            LEFT JOIN team_members tm ON tm.team_id = t.id
            GROUP BY t.id
            ORDER BY LOWER(t.name), t.id
        """).fetchall()
        team_cards = []
        for team in teams:
            members = db.execute("""
                SELECT u.id, u.full_name, u.username, u.role, u.is_active
                FROM team_members tm
                JOIN users u ON u.id = tm.user_id
                WHERE tm.team_id = ?
                ORDER BY LOWER(u.full_name), LOWER(u.username)
            """, (team["id"],)).fetchall()
            team_cards.append({"team": team, "members": members})

    return render_template(
        "users_access.html",
        users=users,
        teams=team_cards,
        owner_username=ADMIN_USERNAME,
    )


@app.post("/settings/teams/add")
def add_team():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Team Name is required.")
        return redirect(url_for("users_access") + "#teams")

    try:
        with get_db() as db:
            cur = db.execute("""
                INSERT INTO teams (name, share_jobs, created_at, updated_at)
                VALUES (?, 1, ?, ?)
            """, (name, now_iso(), now_iso()))
            record_activity(db, "Team Added", f"Created collaboration team {name} with job sharing enabled.")
            db.commit()
            team_id = cur.lastrowid
    except sqlite3.IntegrityError:
        flash("A team with that name already exists.")
        return redirect(url_for("users_access") + "#teams")

    flash(f"Team {name} created. Add the PMs who should collaborate.")
    return redirect(url_for("users_access") + f"#team-{team_id}")


@app.post("/settings/teams/<int:team_id>/toggle-sharing")
def toggle_team_sharing(team_id):
    with get_db() as db:
        team = db.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        if not team:
            abort(404)
        new_value = 0 if team["share_jobs"] else 1
        db.execute("UPDATE teams SET share_jobs = ?, updated_at = ? WHERE id = ?", (new_value, now_iso(), team_id))
        record_activity(
            db,
            "Team Job Sharing Enabled" if new_value else "Team Job Sharing Disabled",
            f"{'Enabled' if new_value else 'Disabled'} shared-job access for team {team['name']}.",
        )
        db.commit()
    flash(f"{team['name']} job sharing {'enabled' if new_value else 'disabled'}.")
    return redirect(url_for("users_access") + f"#team-{team_id}")


@app.post("/settings/teams/<int:team_id>/members/add")
def add_team_member(team_id):
    user_id = normalize_optional_id(request.form.get("user_id"))
    if not user_id:
        flash("Choose a user to add to the team.")
        return redirect(url_for("users_access") + f"#team-{team_id}")

    with get_db() as db:
        team = db.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not team or not user:
            abort(404)
        if not user["is_active"]:
            flash("Only active users can be added to a PM team.")
            return redirect(url_for("users_access") + f"#team-{team_id}")
        try:
            db.execute(
                "INSERT INTO team_members (team_id, user_id, created_at) VALUES (?, ?, ?)",
                (team_id, user_id, now_iso()),
            )
        except sqlite3.IntegrityError:
            flash(f"{user['full_name']} is already on {team['name']}.")
            return redirect(url_for("users_access") + f"#team-{team_id}")
        record_activity(db, "Team Member Added", f"Added {user['full_name']} (@{user['username']}) to {team['name']}.")
        db.commit()

    flash(f"{user['full_name']} added to {team['name']}.")
    return redirect(url_for("users_access") + f"#team-{team_id}")


@app.post("/settings/teams/<int:team_id>/members/<int:user_id>/remove")
def remove_team_member(team_id, user_id):
    with get_db() as db:
        team = db.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not team or not user:
            abort(404)
        db.execute("DELETE FROM team_members WHERE team_id = ? AND user_id = ?", (team_id, user_id))
        record_activity(db, "Team Member Removed", f"Removed {user['full_name']} (@{user['username']}) from {team['name']}.")
        db.commit()

    flash(f"{user['full_name']} removed from {team['name']}.")
    return redirect(url_for("users_access") + f"#team-{team_id}")


@app.post("/settings/users/add")
def add_user():
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "OPERATIONS").strip().upper()

    if not full_name or not username or not password:
        flash("Full Name, Username, and Temporary Password are required.")
        return redirect(url_for("users_access") + "#users-access")

    if role not in {"ADMIN", "OPERATIONS"}:
        role = "OPERATIONS"

    if len(username) < 3:
        flash("Username must be at least 3 characters.")
        return redirect(url_for("users_access") + "#users-access")

    if len(password) < 8:
        flash("Temporary Password must be at least 8 characters.")
        return redirect(url_for("users_access") + "#users-access")

    if username.lower() == ADMIN_USERNAME.lower():
        flash("That username belongs to the permanent Owner account.")
        return redirect(url_for("users_access") + "#users-access")

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
        return redirect(url_for("users_access") + "#users-access")

    flash(f"User {username} added.")
    return redirect(url_for("users_access") + "#users-access")


@app.post("/settings/users/<int:user_id>/toggle-access")
def toggle_user_access(user_id):
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            abort(404)

        # Prevent an admin from disabling the account currently being used.
        if session.get("dispatchproof_user_id") == user_id:
            flash("You cannot disable the account you are currently signed in with.")
            return redirect(url_for("users_access") + "#users-access")

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
    return redirect(url_for("users_access") + "#users-access")


@app.post("/settings/users/<int:user_id>/reset-password")
def reset_user_password(user_id):
    new_password = request.form.get("new_password", "")

    if len(new_password) < 8:
        flash("New password must be at least 8 characters.")
        return redirect(url_for("users_access") + "#users-access")

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
    return redirect(url_for("users_access") + "#users-access")


@app.post("/settings/users/<int:user_id>/role")
def change_user_role(user_id):
    role = request.form.get("role", "OPERATIONS").strip().upper()
    if role not in {"ADMIN", "OPERATIONS"}:
        flash("Invalid role.")
        return redirect(url_for("users_access") + "#users-access")

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            abort(404)

        if session.get("dispatchproof_user_id") == user_id and role != "ADMIN":
            flash("You cannot remove administrator access from the account you are currently using.")
            return redirect(url_for("users_access") + "#users-access")

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
    return redirect(url_for("users_access") + "#users-access")



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
    upload_count = stored_upload_file_count()
    stored_document_count = stored_job_document_file_count()
    stored_project_document_count = stored_project_document_file_count()
    stored_client_document_count = stored_client_document_file_count()

    counts = {
        "jobs": 0,
        "completed_jobs": 0,
        "users": 0,
        "readiness_responses": 0,
        "mobilization_attempts": 0,
        "outbox_messages": 0,
        "activity_events": 0,
        "job_notes": 0,
        "job_documents": 0,
        "field_update_links": 0,
        "field_progress_entries": 0,
        "project_route_plans": 0,
        "project_route_stops": 0,
        "project_documents": 0,
        "client_documents": 0,
        "clients": 0,
        "projects": 0,
        "crew_members": 0,
        "job_crew_assignments": 0,
        "crew_unavailability": 0,
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
            database_document_count = db.execute(
                "SELECT COUNT(*) AS c FROM job_documents"
            ).fetchone()["c"]
            counts["job_documents"] = max(
                database_document_count,
                stored_document_count,
            )
            counts["field_update_links"] = db.execute(
                "SELECT COUNT(*) AS c FROM field_update_links"
            ).fetchone()["c"]
            counts["field_progress_entries"] = db.execute(
                "SELECT COUNT(*) AS c FROM field_progress_entries"
            ).fetchone()["c"]
            counts["project_route_plans"] = db.execute(
                "SELECT COUNT(*) AS c FROM project_route_plans"
            ).fetchone()["c"]
            counts["project_route_stops"] = db.execute(
                "SELECT COUNT(*) AS c FROM project_route_stops"
            ).fetchone()["c"]
            database_project_document_count = db.execute(
                "SELECT COUNT(*) AS c FROM project_documents"
            ).fetchone()["c"]
            counts["project_documents"] = max(
                database_project_document_count,
                stored_project_document_count,
            )
            database_client_document_count = db.execute(
                "SELECT COUNT(*) AS c FROM client_documents"
            ).fetchone()["c"]
            counts["client_documents"] = max(
                database_client_document_count,
                stored_client_document_count,
            )
            counts["clients"] = db.execute(
                "SELECT COUNT(*) AS c FROM clients"
            ).fetchone()["c"]
            counts["projects"] = db.execute(
                "SELECT COUNT(*) AS c FROM projects"
            ).fetchone()["c"]
            counts["crew_members"] = db.execute(
                "SELECT COUNT(*) AS c FROM crew_members"
            ).fetchone()["c"]
            counts["job_crew_assignments"] = db.execute(
                "SELECT COUNT(*) AS c FROM job_crew_assignments"
            ).fetchone()["c"]
            counts["crew_unavailability"] = db.execute(
                "SELECT COUNT(*) AS c FROM crew_unavailability"
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
        visibility_clause, visibility_params = job_visibility_sql("j")
        rows = db.execute(f"""
            SELECT c.*,
                   COUNT(DISTINCT p.id) AS project_count,
                   COUNT(DISTINCT j.id) AS job_count,
                   COUNT(DISTINCT CASE WHEN j.status = 'COMPLETED' THEN j.id END) AS completed_job_count,
                   COUNT(DISTINCT CASE WHEN j.status != 'COMPLETED' THEN j.id END) AS active_job_count
            FROM clients c
            LEFT JOIN projects p ON p.client_id = c.id
            LEFT JOIN jobs j ON j.client_id = c.id AND ({visibility_clause})
            GROUP BY c.id
            ORDER BY LOWER(c.name), c.id
        """, visibility_params).fetchall()
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
        visibility_clause, visibility_params = job_visibility_sql("j")
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

        projects = db.execute(f"""
            SELECT p.*,
                   COUNT(DISTINCT j.id) AS job_count,
                   COUNT(DISTINCT CASE WHEN j.status = 'COMPLETED' THEN j.id END) AS completed_job_count,
                   COUNT(DISTINCT CASE WHEN j.status != 'COMPLETED' THEN j.id END) AS active_job_count
            FROM projects p
            LEFT JOIN jobs j ON j.project_id = p.id AND ({visibility_clause})
            WHERE p.client_id = ?
            GROUP BY p.id
            ORDER BY LOWER(p.name), p.id
        """, (*visibility_params, client_id)).fetchall()

        jobs = db.execute(f"""
            SELECT j.*, p.name AS project_name
            FROM jobs j
            LEFT JOIN projects p ON p.id = j.project_id
            WHERE j.client_id = ?
              AND ({visibility_clause})
            ORDER BY CASE WHEN j.status = 'COMPLETED' THEN 1 ELSE 0 END,
                     j.installation_date, j.id
        """, (client_id, *visibility_params)).fetchall()

        client_documents = db.execute("""
            SELECT *
            FROM client_documents
            WHERE client_id = ?
            ORDER BY id DESC
            LIMIT 100
        """, (client_id,)).fetchall()

    return render_template(
        "client_detail.html",
        client=client,
        projects=projects,
        jobs=jobs,
        client_documents=client_documents,
    )


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
        visibility_clause, visibility_params = job_visibility_sql("j")
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

        jobs = db.execute(f"""
            SELECT j.*
            FROM jobs j
            WHERE j.project_id = ?
              AND ({visibility_clause})
            ORDER BY CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END,
                     installation_date, id
        """, (project_id, *visibility_params)).fetchall()
        project_documents = db.execute("""
            SELECT *
            FROM project_documents
            WHERE project_id = ?
            ORDER BY id DESC
            LIMIT 100
        """, (project_id,)).fetchall()

        client_documents = db.execute("""
            SELECT *
            FROM client_documents
            WHERE client_id = ?
            ORDER BY id DESC
            LIMIT 100
        """, (project["client_id"],)).fetchall()

    return render_template(
        "project_detail.html",
        project=project,
        jobs=jobs,
        project_documents=project_documents,
        client_documents=client_documents,
    )


@app.get("/projects/<int:project_id>/bulk-jobs/template.csv")
def download_project_bulk_job_template(project_id):
    with get_db() as db:
        project = db.execute("""
            SELECT p.*, c.name AS client_name
            FROM projects p
            JOIN clients c ON c.id = p.client_id
            WHERE p.id = ?
        """, (project_id,)).fetchone()
        if not project:
            abort(404)

    rows = [
        [
            "EXAMPLE - Store 101 (delete this row)",
            "123 Main St, Akron, OH 44308",
            "09/21/2026",
            "Jane Superintendent",
            "jane@example.com",
            "330-555-0101",
        ]
    ]
    safe_project = re.sub(r"[^A-Za-z0-9_-]+", "_", project["name"]).strip("_") or "project"
    return csv_download(rows, BULK_JOB_IMPORT_HEADERS, f"dispatchproof_{safe_project}_job_import_template.csv")


@app.post("/projects/<int:project_id>/bulk-jobs/import")
def import_project_bulk_jobs(project_id):
    upload = request.files.get("job_import_file")
    if not upload or not upload.filename:
        flash("Choose a completed DispatchProof Job Import CSV first.")
        return redirect(url_for("project_route_optimizer", project_id=project_id))
    if not upload.filename.lower().endswith(".csv"):
        flash("Bulk Job Import currently accepts CSV files. Download the template, fill it in, and upload the CSV.")
        return redirect(url_for("project_route_optimizer", project_id=project_id))

    raw = upload.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        flash("That import file is too large. Keep the CSV under 2 MB.")
        return redirect(url_for("project_route_optimizer", project_id=project_id))
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("DispatchProof could not read that CSV. Save it as a standard UTF-8 CSV and try again.")
        return redirect(url_for("project_route_optimizer", project_id=project_id))

    reader = csv.DictReader(io.StringIO(text))
    column_map = bulk_job_import_column_map(reader.fieldnames)
    missing = [
        label for key, label in (
            ("job_name", "Job Name"),
            ("project_site", "Route / Site Address"),
            ("installation_date", "Installation Date"),
        ) if key not in column_map
    ]
    if missing:
        flash("Import file is missing required column(s): " + ", ".join(missing) + ". Download a fresh template and try again.")
        return redirect(url_for("project_route_optimizer", project_id=project_id))

    parsed_rows = []
    errors = []
    for sheet_row, row in enumerate(reader, start=2):
        values = {key: str(row.get(source, "") or "").strip() for key, source in column_map.items()}
        job_name = values.get("job_name", "")
        project_site = values.get("project_site", "")
        date_text = values.get("installation_date", "")
        if not any(values.values()):
            continue
        if job_name.upper().startswith("EXAMPLE -"):
            continue
        if len(parsed_rows) >= BULK_JOB_IMPORT_MAX_ROWS:
            errors.append(f"Row {sheet_row}: import limit is {BULK_JOB_IMPORT_MAX_ROWS} jobs at a time.")
            break
        if not job_name:
            errors.append(f"Row {sheet_row}: Job Name is required.")
            continue
        if not project_site:
            errors.append(f"Row {sheet_row}: Route / Site Address is required.")
            continue
        install_date = parse_bulk_job_date(date_text)
        if not install_date:
            errors.append(f"Row {sheet_row}: Installation Date '{date_text}' is not recognized. Use YYYY-MM-DD or MM/DD/YYYY.")
            continue
        parsed_rows.append({
            "job_name": job_name[:200],
            "project_site": project_site[:500],
            "installation_date": install_date,
            "contact_name": (values.get("contact_name") or "TBD")[:200],
            "contact_email": values.get("contact_email", "")[:320],
            "contact_phone": values.get("contact_phone", "")[:100],
        })

    if errors:
        preview = " ".join(errors[:6])
        if len(errors) > 6:
            preview += f" Plus {len(errors) - 6} more error(s)."
        flash("Nothing was imported. " + preview)
        return redirect(url_for("project_route_optimizer", project_id=project_id))
    if not parsed_rows:
        flash("No job rows were found in that CSV. Add jobs below the header row and try again.")
        return redirect(url_for("project_route_optimizer", project_id=project_id))

    with get_db() as db:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            abort(404)
        owner_user_id = current_user_id()
        imported = 0
        duplicates = 0
        for item in parsed_rows:
            existing = db.execute("""
                SELECT id FROM jobs
                WHERE project_id = ?
                  AND LOWER(job_name) = LOWER(?)
                  AND installation_date = ?
                  AND LOWER(COALESCE(project_site, '')) = LOWER(?)
                LIMIT 1
            """, (project_id, item["job_name"], item["installation_date"], item["project_site"])).fetchone()
            if existing:
                duplicates += 1
                continue
            cur = db.execute("""
                INSERT INTO jobs (
                    public_token, arrival_token, client_report_token,
                    client_id, project_id, job_name, project_site, installation_date,
                    contact_name, contact_email, contact_phone, checklist_json,
                    crew_lead, planned_crew_size, assigned_crew,
                    owner_user_id, team_id, status, created_at, reminder_enabled,
                    reminder_hours_before, reminder_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', NULL, '', ?, NULL, 'NO RESPONSE', ?, 1, ?, 0)
            """, (
                secrets.token_urlsafe(18),
                secrets.token_urlsafe(24),
                secrets.token_urlsafe(24),
                project["client_id"],
                project_id,
                item["job_name"],
                item["project_site"],
                item["installation_date"],
                item["contact_name"],
                item["contact_email"],
                item["contact_phone"],
                json.dumps(DEFAULT_CHECKLIST),
                owner_user_id,
                now_iso(),
                DEFAULT_REMINDER_HOURS_BEFORE,
            ))
            job_id = cur.lastrowid
            record_activity(
                db,
                "Job Created",
                f"Bulk imported job {item['job_name']} for {item['installation_date']}.",
                job_id=job_id,
            )
            imported += 1

        if imported:
            record_activity(
                db,
                "Bulk Jobs Imported",
                f"Imported {imported} job(s) into project {project['name']} from CSV."
                + (f" Skipped {duplicates} exact duplicate(s)." if duplicates else ""),
            )
        db.commit()

    message = f"Imported {imported} job{'s' if imported != 1 else ''} into this project."
    if duplicates:
        message += f" Skipped {duplicates} exact duplicate{'s' if duplicates != 1 else ''}."
    if imported:
        message += " They are Personal jobs owned by your workspace; assign Team access later if needed."
    flash(message)
    return redirect(url_for("project_route_optimizer", project_id=project_id))


@app.route("/projects/<int:project_id>/route-optimization", methods=["GET", "POST"])
def project_route_optimizer(project_id):
    with get_db() as db:
        visibility_clause, visibility_params = job_visibility_sql("j")
        project = db.execute("""
            SELECT p.*, c.name AS client_name
            FROM projects p
            JOIN clients c ON c.id = p.client_id
            WHERE p.id = ?
        """, (project_id,)).fetchone()
        if not project:
            abort(404)

        jobs = db.execute(f"""
            SELECT j.*
            FROM jobs j
            WHERE j.project_id = ?
              AND j.status != 'COMPLETED'
              AND ({visibility_clause})
            ORDER BY j.installation_date, LOWER(j.job_name), j.id
        """, (project_id, *visibility_params)).fetchall()
        visible_job_ids = {int(job["id"]) for job in jobs}

        if request.method == "POST":
            action = request.form.get("action", "optimize").strip().lower()
            owner_key = route_plan_owner_key()
            if action == "clear":
                plan = db.execute(
                    "SELECT id FROM project_route_plans WHERE project_id = ? AND owner_key = ?",
                    (project_id, owner_key),
                ).fetchone()
                if plan:
                    db.execute("DELETE FROM project_route_plans WHERE id = ?", (plan["id"],))
                    record_activity(db, "Route Plan Cleared", f"Cleared saved route for project {project['name']}.")
                    db.commit()
                flash("Saved route cleared.")
                return redirect(url_for("project_route_optimizer", project_id=project_id))

            if not ROUTE_OPTIMIZATION_API_KEY:
                flash("Route Optimization needs an openrouteservice API key before it can calculate routes.")
                return redirect(url_for("project_route_optimizer", project_id=project_id))

            start_address = normalize_route_address(request.form.get("start_address"))
            return_to_start = request.form.get("return_to_start") == "1"
            if not start_address:
                flash("Enter the crew's starting location before optimizing the route.")
                return redirect(url_for("project_route_optimizer", project_id=project_id))

            try:
                start_lat, start_lon, _, _ = route_geocode(db, start_address)
                start_coord = (start_lat, start_lon)

                if action == "manual":
                    raw_order = [x for x in (request.form.get("manual_order") or "").split(",") if x.strip().isdigit()]
                    job_ids = [int(x) for x in raw_order]
                    if not job_ids or len(job_ids) != len(set(job_ids)) or any(job_id not in visible_job_ids for job_id in job_ids):
                        raise RouteOptimizationError("The manual stop order is invalid. Reload the page and try again.")
                    address_map = {}
                    plan, prior_stops = load_project_route_plan(db, project_id)
                    for stop in prior_stops:
                        address_map[int(stop["job_id"])] = stop["route_address"]
                    selected_jobs = [next(job for job in jobs if int(job["id"]) == job_id) for job_id in job_ids]
                else:
                    selected_ids = []
                    for raw in request.form.getlist("job_ids"):
                        if str(raw).isdigit() and int(raw) in visible_job_ids:
                            selected_ids.append(int(raw))
                    selected_ids = list(dict.fromkeys(selected_ids))
                    if len(selected_ids) < 2:
                        raise RouteOptimizationError("Select at least two active jobs to optimize a route.")
                    if len(selected_ids) > ROUTE_OPTIMIZER_MAX_JOBS:
                        raise RouteOptimizationError(f"Select no more than {ROUTE_OPTIMIZER_MAX_JOBS} jobs in one route plan.")
                    selected_jobs = [job for job in jobs if int(job["id"]) in set(selected_ids)]
                    address_map = {
                        int(job["id"]): normalize_route_address(request.form.get(f"address_{job['id']}") or job["project_site"])
                        for job in selected_jobs
                    }

                stops = []
                for job in selected_jobs:
                    address = address_map.get(int(job["id"])) or normalize_route_address(job["project_site"])
                    if not address:
                        raise RouteOptimizationError(f"{job['job_name']} does not have a route address. Enter one before optimizing.")
                    lat, lon, _, _ = route_geocode(db, address)
                    stops.append({
                        "job_id": int(job["id"]), "job_name": job["job_name"], "address": address,
                        "lat": lat, "lon": lon,
                    })

                if action == "manual":
                    ordered_stops = stops
                else:
                    order = route_optimize_order(start_coord, stops, return_to_start)
                    by_id = {int(stop["job_id"]): stop for stop in stops}
                    ordered_stops = [by_id[job_id] for job_id in order]

                route_data = route_directions(start_coord, ordered_stops, return_to_start)
                save_project_route_plan(
                    db, project_id, start_address, start_coord, return_to_start,
                    ordered_stops, route_data,
                )
                action_text = "manually reordered" if action == "manual" else "optimized"
                record_activity(
                    db,
                    "Project Route Updated",
                    f"{action_text.capitalize()} {len(ordered_stops)} stops for project {project['name']} ({route_miles(route_data['distance']):.1f} mi, {route_duration_label(route_data['duration'])}).",
                )
                db.commit()
                flash(f"Route {action_text}: {len(ordered_stops)} stops · {route_miles(route_data['distance']):.1f} mi · {route_duration_label(route_data['duration'])} drive time.")
            except RouteOptimizationError as exc:
                db.rollback()
                flash(str(exc))
            return redirect(url_for("project_route_optimizer", project_id=project_id))

        plan, plan_stops = load_project_route_plan(db, project_id)
        geometry = None
        if plan and plan["route_geometry_json"]:
            try:
                geometry = json.loads(plan["route_geometry_json"])
            except Exception:
                geometry = None

    return render_template(
        "route_optimizer.html",
        project=project,
        jobs=jobs,
        route_plan=plan,
        route_stops=plan_stops,
        route_job_ids={int(stop["job_id"]) for stop in plan_stops},
        route_address_by_job={int(stop["job_id"]): stop["route_address"] for stop in plan_stops},
        route_geometry=geometry,
        route_configured=bool(ROUTE_OPTIMIZATION_API_KEY),
        route_max_jobs=ROUTE_OPTIMIZER_MAX_JOBS,
        route_miles=route_miles,
        route_duration_label=route_duration_label,
    )


@app.get("/projects/<int:project_id>/route-optimization/download.csv")
def download_project_route_csv(project_id):
    """Download the signed-in user's saved project route as a clean CSV summary."""
    with get_db() as db:
        project = db.execute("""
            SELECT p.*, c.name AS client_name
            FROM projects p
            JOIN clients c ON c.id = p.client_id
            WHERE p.id = ?
        """, (project_id,)).fetchone()
        if not project:
            abort(404)

        plan, stops = load_project_route_plan(db, project_id)
        if not plan or not stops:
            flash("Build and save a route before downloading it.")
            return redirect(url_for("project_route_optimizer", project_id=project_id))

        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["DispatchProof Route Plan"])
        writer.writerow(["Client", project["client_name"]])
        writer.writerow(["Project", project["name"]])
        writer.writerow(["Starting Location", plan["start_address"]])
        writer.writerow(["Return to Start", "Yes" if plan["return_to_start"] else "No"])
        writer.writerow(["Total Driving (mi)", f"{route_miles(plan['total_distance_m']):.1f}"])
        writer.writerow(["Estimated Drive Time", route_duration_label(plan["total_duration_s"])])
        writer.writerow(["Route Updated", plan["updated_at"]])
        writer.writerow([])
        writer.writerow([
            "Stop", "Job", "Route Address", "Installation Date", "Status",
            "Miles From Prior Stop", "Drive Time From Prior Stop",
        ])
        writer.writerow(["START", "", plan["start_address"], "", "", "0.0", ""])
        for stop in stops:
            writer.writerow([
                int(stop["stop_order"]),
                stop["job_name"],
                stop["route_address"],
                stop["installation_date"] or "",
                stop["status"] or "",
                f"{route_miles(stop['leg_distance_m']):.1f}",
                route_duration_label(stop["leg_duration_s"]),
            ])

        if plan["return_to_start"]:
            used_distance = sum(float(stop["leg_distance_m"] or 0) for stop in stops)
            used_duration = sum(float(stop["leg_duration_s"] or 0) for stop in stops)
            return_distance = max(0.0, float(plan["total_distance_m"] or 0) - used_distance)
            return_duration = max(0.0, float(plan["total_duration_s"] or 0) - used_duration)
            writer.writerow([
                "END", "Return to Start", plan["start_address"], "", "",
                f"{route_miles(return_distance):.1f}",
                route_duration_label(return_duration),
            ])

        csv_bytes = io.BytesIO(output.getvalue().encode("utf-8-sig"))
        csv_bytes.seek(0)
        base_name = secure_filename(f"{project['name']}_route") or f"project_{project_id}_route"
        return send_file(
            csv_bytes,
            mimetype="text/csv; charset=utf-8",
            as_attachment=True,
            download_name=f"{base_name}.csv",
        )


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


@app.route("/documents")
def document_center():
    search_query = (request.args.get("q") or "").strip()
    scope_filter = (request.args.get("scope") or "").strip().upper()
    if scope_filter not in {"", "CLIENT", "PROJECT", "JOB"}:
        scope_filter = ""

    client_id = normalize_optional_id(request.args.get("client_id"))
    project_id = normalize_optional_id(request.args.get("project_id"))

    with get_db() as db:
        visibility_clause, visibility_params = job_visibility_sql("j")
        clients, projects = get_clients_and_projects(db)
        jobs = db.execute(f"""
            SELECT
                j.id,
                j.job_name,
                j.project_site,
                j.status,
                j.client_id,
                j.project_id,
                c.name AS client_name,
                p.name AS project_name
            FROM jobs j
            LEFT JOIN clients c ON c.id = j.client_id
            LEFT JOIN projects p ON p.id = j.project_id
            WHERE ({visibility_clause})
            ORDER BY CASE WHEN j.status = 'COMPLETED' THEN 1 ELSE 0 END,
                     j.installation_date DESC,
                     j.job_name COLLATE NOCASE,
                     j.id DESC
        """, visibility_params).fetchall()

        # Keep these as three simple queries instead of one compound UNION.
        # This is more tolerant of restored/upgraded beta databases and avoids
        # SQLite compound-query edge cases while preserving the same result set.
        client_rows = db.execute("""
            SELECT
                'CLIENT' AS document_scope,
                cd.id AS document_id,
                cd.original_filename,
                cd.file_size,
                cd.actor_name,
                cd.created_at,
                c.id AS client_id,
                c.name AS client_name,
                NULL AS project_id,
                NULL AS project_name,
                NULL AS job_id,
                NULL AS job_name,
                NULL AS project_site
            FROM client_documents cd
            JOIN clients c ON c.id = cd.client_id
        """).fetchall()

        project_rows = db.execute("""
            SELECT
                'PROJECT' AS document_scope,
                pd.id AS document_id,
                pd.original_filename,
                pd.file_size,
                pd.actor_name,
                pd.created_at,
                c.id AS client_id,
                c.name AS client_name,
                p.id AS project_id,
                p.name AS project_name,
                NULL AS job_id,
                NULL AS job_name,
                p.location AS project_site
            FROM project_documents pd
            JOIN projects p ON p.id = pd.project_id
            JOIN clients c ON c.id = p.client_id
        """).fetchall()

        job_rows = db.execute(f"""
            SELECT
                'JOB' AS document_scope,
                jd.id AS document_id,
                jd.original_filename,
                jd.file_size,
                jd.actor_name,
                jd.created_at,
                c.id AS client_id,
                c.name AS client_name,
                p.id AS project_id,
                p.name AS project_name,
                j.id AS job_id,
                j.job_name AS job_name,
                j.project_site AS project_site
            FROM job_documents jd
            JOIN jobs j ON j.id = jd.job_id
            LEFT JOIN clients c ON c.id = j.client_id
            LEFT JOIN projects p ON p.id = j.project_id
            WHERE ({visibility_clause})
        """, visibility_params).fetchall()

        rows = list(client_rows) + list(project_rows) + list(job_rows)
        rows.sort(
            key=lambda row: (
                row["created_at"] or "",
                int(row["document_id"] or 0),
            ),
            reverse=True,
        )

    documents = []
    q_lower = search_query.lower()

    for row in rows:
        if scope_filter and row["document_scope"] != scope_filter:
            continue
        if client_id and row["client_id"] != client_id:
            continue
        if project_id and row["project_id"] != project_id:
            continue

        if q_lower:
            searchable = " ".join(
                str(value or "")
                for value in (
                    row["original_filename"],
                    row["client_name"],
                    row["project_name"],
                    row["job_name"],
                    row["project_site"],
                    row["actor_name"],
                    row["document_scope"],
                )
            ).lower()
            if q_lower not in searchable:
                continue

        documents.append(row)

    scope_counts = {
        "CLIENT": sum(1 for row in rows if row["document_scope"] == "CLIENT"),
        "PROJECT": sum(1 for row in rows if row["document_scope"] == "PROJECT"),
        "JOB": sum(1 for row in rows if row["document_scope"] == "JOB"),
    }

    return render_template(
        "documents.html",
        documents=documents,
        total_document_count=len(rows),
        scope_counts=scope_counts,
        search_query=search_query,
        scope_filter=scope_filter,
        selected_client_id=client_id,
        selected_project_id=project_id,
        clients=clients,
        projects=projects,
        jobs=jobs,
    )


@app.post("/documents/upload")
def document_center_upload():
    document_scope = (request.form.get("document_scope") or "").strip().upper()
    client_id = normalize_optional_id(request.form.get("upload_client_id"))
    project_id = normalize_optional_id(request.form.get("upload_project_id"))
    job_id = normalize_optional_id(request.form.get("upload_job_id"))
    uploaded = request.files.get("document_file")

    if document_scope not in {"CLIENT", "PROJECT", "JOB"}:
        flash("Choose whether this is a Client, Project, or Job Document.")
        return redirect(url_for("document_center") + "#quick-upload")

    if not uploaded or not uploaded.filename:
        flash("Choose a document before uploading.")
        return redirect(url_for("document_center") + "#quick-upload")

    original_filename = secure_filename(uploaded.filename)
    if not original_filename:
        flash("That document filename could not be used.")
        return redirect(url_for("document_center") + "#quick-upload")

    if not allowed_document(original_filename):
        flash("Unsupported document type. Use PDF, Word, Excel, CSV, TXT, image, DWG, or DXF files.")
        return redirect(url_for("document_center") + "#quick-upload")

    actor_type, actor_name = activity_actor()

    with get_db() as db:
        if document_scope == "CLIENT":
            if not client_id:
                flash("Choose a client for this Client Document.")
                return redirect(url_for("document_center") + "#quick-upload")

            parent = db.execute(
                "SELECT * FROM clients WHERE id = ?",
                (client_id,),
            ).fetchone()
            if not parent:
                abort(404)

            stored_filename = f"clientdoc_{client_id}_{secrets.token_hex(8)}_{original_filename}"
            destination = UPLOAD_DIR / stored_filename
            uploaded.save(destination)

            try:
                file_size = destination.stat().st_size
            except OSError:
                destination.unlink(missing_ok=True)
                flash("The client document could not be saved.")
                return redirect(url_for("document_center") + "#quick-upload")

            if file_size > MAX_JOB_DOCUMENT_BYTES:
                destination.unlink(missing_ok=True)
                flash("Documents can be up to 20 MB each.")
                return redirect(url_for("document_center") + "#quick-upload")

            try:
                db.execute("""
                    INSERT INTO client_documents (
                        client_id, stored_filename, original_filename, file_size,
                        content_type, actor_type, actor_name, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    client_id,
                    stored_filename,
                    original_filename,
                    file_size,
                    uploaded.mimetype or "",
                    actor_type,
                    actor_name,
                    now_iso(),
                ))
                record_activity(
                    db,
                    "Client Document Uploaded",
                    f"Uploaded internal client document {original_filename} to {parent['name']} from Document Center.",
                )
                db.commit()
            except Exception:
                destination.unlink(missing_ok=True)
                raise

            flash(f"Client Document uploaded to {parent['name']}.")
            return redirect(url_for("document_center", scope="CLIENT"))

        if document_scope == "PROJECT":
            if not project_id:
                flash("Choose a project for this Project Document.")
                return redirect(url_for("document_center") + "#quick-upload")

            parent = db.execute("""
                SELECT p.*, c.name AS client_name
                FROM projects p
                JOIN clients c ON c.id = p.client_id
                WHERE p.id = ?
            """, (project_id,)).fetchone()
            if not parent:
                abort(404)

            stored_filename = f"projdoc_{project_id}_{secrets.token_hex(8)}_{original_filename}"
            destination = UPLOAD_DIR / stored_filename
            uploaded.save(destination)

            try:
                file_size = destination.stat().st_size
            except OSError:
                destination.unlink(missing_ok=True)
                flash("The project document could not be saved.")
                return redirect(url_for("document_center") + "#quick-upload")

            if file_size > MAX_JOB_DOCUMENT_BYTES:
                destination.unlink(missing_ok=True)
                flash("Documents can be up to 20 MB each.")
                return redirect(url_for("document_center") + "#quick-upload")

            try:
                db.execute("""
                    INSERT INTO project_documents (
                        project_id, stored_filename, original_filename, file_size,
                        content_type, actor_type, actor_name, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    project_id,
                    stored_filename,
                    original_filename,
                    file_size,
                    uploaded.mimetype or "",
                    actor_type,
                    actor_name,
                    now_iso(),
                ))
                record_activity(
                    db,
                    "Project Document Uploaded",
                    f"Uploaded internal project document {original_filename} to "
                    f"{parent['client_name']} / {parent['name']} from Document Center.",
                )
                db.commit()
            except Exception:
                destination.unlink(missing_ok=True)
                raise

            flash(f"Project Document uploaded to {parent['name']}.")
            return redirect(url_for("document_center", scope="PROJECT"))

        if not job_id:
            flash("Choose a job for this Job Document.")
            return redirect(url_for("document_center") + "#quick-upload")

        parent = db.execute("""
            SELECT j.*, c.name AS client_name, p.name AS project_name
            FROM jobs j
            LEFT JOIN clients c ON c.id = j.client_id
            LEFT JOIN projects p ON p.id = j.project_id
            WHERE j.id = ?
        """, (job_id,)).fetchone()
        if not parent or not user_can_access_job(db, job_id):
            abort(404)

        stored_filename = f"jobdoc_{job_id}_{secrets.token_hex(8)}_{original_filename}"
        destination = UPLOAD_DIR / stored_filename
        uploaded.save(destination)

        try:
            file_size = destination.stat().st_size
        except OSError:
            destination.unlink(missing_ok=True)
            flash("The job document could not be saved.")
            return redirect(url_for("document_center") + "#quick-upload")

        if file_size > MAX_JOB_DOCUMENT_BYTES:
            destination.unlink(missing_ok=True)
            flash("Documents can be up to 20 MB each.")
            return redirect(url_for("document_center") + "#quick-upload")

        try:
            db.execute("""
                INSERT INTO job_documents (
                    job_id, stored_filename, original_filename, file_size,
                    content_type, actor_type, actor_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                stored_filename,
                original_filename,
                file_size,
                uploaded.mimetype or "",
                actor_type,
                actor_name,
                now_iso(),
            ))
            record_activity(
                db,
                "Job Document Uploaded",
                f"Uploaded internal job document {original_filename} to "
                f"{parent['job_name']} from Document Center.",
                job_id=job_id,
            )
            db.commit()
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    flash(f"Job Document uploaded to {parent['job_name']}.")
    return redirect(url_for("document_center", scope="JOB"))


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


def build_schedule_view(args):
    search_query = (args.get("q") or "").strip()
    schedule_filter = (args.get("schedule") or "").strip().lower()
    valid_schedule_filters = {"overdue", "today", "next7", "later"}
    if schedule_filter not in valid_schedule_filters:
        schedule_filter = ""

    status_filter = (args.get("status") or "").strip().upper()
    valid_statuses = {"READY", "REVIEW", "BLOCKED", "NO RESPONSE", "ON SITE", "COMPLETED"}
    if status_filter not in valid_statuses:
        status_filter = ""

    include_completed = (args.get("completed") or "").strip() == "1"
    crew_filter = (args.get("crew") or "").strip().lower()
    if crew_filter not in {"assigned", "unassigned", "conflict", "unavailable", "gap"}:
        crew_filter = ""

    crew_filter_label = {
        "assigned": "Assigned",
        "unassigned": "Unassigned",
        "conflict": "Conflicts",
        "unavailable": "Unavailable Crew",
        "gap": "Staffing Gaps",
    }.get(crew_filter, "")

    client_filter = normalize_optional_id(args.get("client"))
    project_filter = normalize_optional_id(args.get("project"))

    with get_db() as db:
        visibility_clause, visibility_params = job_visibility_sql("j")
        all_jobs = db.execute(f"""
            SELECT
                j.*,
                c.name AS client_name,
                p.name AS assigned_project_name,
                p.project_number AS assigned_project_number
            FROM jobs j
            LEFT JOIN clients c ON c.id = j.client_id
            LEFT JOIN projects p ON p.id = j.project_id
            WHERE ({visibility_clause})
            ORDER BY j.installation_date ASC, j.id ASC
        """, visibility_params).fetchall()

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

        visible_job_ids = {job["id"] for job in all_jobs}
        crew_conflicts_by_job, crew_conflict_group_count = get_active_crew_conflicts(db, visible_job_ids)
        crew_unavailability_by_job, crew_unavailability_group_count = get_active_crew_unavailability_issues(db)
        crew_unavailability_by_job = {k: v for k, v in crew_unavailability_by_job.items() if k in visible_job_ids}
        crew_unavailability_group_count = sum(len(v) for v in crew_unavailability_by_job.values())

    staffing_gaps_by_job, staffing_gap_job_count, staffing_gap_total_needed = get_active_staffing_gaps(all_jobs)

    conflict_job_ids = set(crew_conflicts_by_job.keys())
    unavailable_job_ids = set(crew_unavailability_by_job.keys())
    staffing_gap_job_ids = set(staffing_gaps_by_job.keys())
    schedule_counts = {"overdue": 0, "today": 0, "next7": 0, "later": 0}
    crew_counts = {
        "assigned": 0,
        "unassigned": 0,
        "conflict": len(conflict_job_ids),
        "unavailable": len(unavailable_job_ids),
        "gap": staffing_gap_job_count,
    }
    active_job_count = 0
    completed_job_count = 0

    for job in all_jobs:
        if job["status"] == "COMPLETED":
            completed_job_count += 1
            continue

        active_job_count += 1
        bucket = job_schedule_bucket(job["installation_date"])
        if bucket in schedule_counts:
            schedule_counts[bucket] += 1

        if job_has_crew_assignment(job):
            crew_counts["assigned"] += 1
        else:
            crew_counts["unassigned"] += 1

    search_lower = search_query.lower()
    visible_jobs = []

    for job in all_jobs:
        is_completed = job["status"] == "COMPLETED"
        if is_completed and not include_completed and status_filter != "COMPLETED":
            continue

        bucket = job_schedule_bucket(job["installation_date"])

        if schedule_filter and bucket != schedule_filter:
            continue
        if status_filter and job["status"] != status_filter:
            continue
        if crew_filter == "assigned" and not job_has_crew_assignment(job):
            continue
        if crew_filter == "unassigned" and job_has_crew_assignment(job):
            continue
        if crew_filter == "conflict" and job["id"] not in conflict_job_ids:
            continue
        if crew_filter == "unavailable" and job["id"] not in unavailable_job_ids:
            continue
        if crew_filter == "gap" and job["id"] not in staffing_gap_job_ids:
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
                job["crew_lead"] or "",
                job["assigned_crew"] or "",
            ]).lower()
            if search_lower not in searchable:
                continue

        visible_jobs.append({
            "job": job,
            "bucket": bucket,
        })

    grouped_days = []
    current_date = None
    current_group = None

    for item in visible_jobs:
        job = item["job"]
        install_date = job["installation_date"] or ""
        if install_date != current_date:
            current_date = install_date
            current_group = {
                "date": install_date,
                "bucket": item["bucket"],
                "jobs": [],
            }
            grouped_days.append(current_group)
        current_group["jobs"].append(job)

    filters_active = bool(
        search_query
        or schedule_filter
        or status_filter
        or crew_filter
        or client_filter
        or project_filter
        or include_completed
    )

    return {
        "grouped_days": grouped_days,
        "visible_jobs": visible_jobs,
        "visible_job_count": len(visible_jobs),
        "active_job_count": active_job_count,
        "completed_job_count": completed_job_count,
        "schedule_counts": schedule_counts,
        "crew_counts": crew_counts,
        "crew_conflicts_by_job": crew_conflicts_by_job,
        "crew_conflict_group_count": crew_conflict_group_count,
        "crew_unavailability_by_job": crew_unavailability_by_job,
        "crew_unavailability_group_count": crew_unavailability_group_count,
        "staffing_gaps_by_job": staffing_gaps_by_job,
        "staffing_gap_job_count": staffing_gap_job_count,
        "staffing_gap_total_needed": staffing_gap_total_needed,
        "search_query": search_query,
        "schedule_filter": schedule_filter,
        "status_filter": status_filter,
        "crew_filter": crew_filter,
        "crew_filter_label": crew_filter_label,
        "client_filter": client_filter,
        "project_filter": project_filter,
        "include_completed": include_completed,
        "clients": clients,
        "projects": projects,
        "filters_active": filters_active,
        "today_iso": local_today().isoformat(),
        "tomorrow_iso": (local_today() + timedelta(days=1)).isoformat(),
    }


@app.route("/schedule")
def schedule_board():
    schedule_data = build_schedule_view(request.args)
    return render_template("schedule.html", **schedule_data)


@app.route("/schedule/export.csv")
def schedule_export_csv():
    schedule_data = build_schedule_view(request.args)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Install Date",
        "Schedule Window",
        "Status",
        "Job",
        "Project / Site",
        "Client",
        "Project",
        "Project Number",
        "Crew Lead",
        "Planned Crew Size",
        "Crew / Installers",
        "Site Contact",
        "Contact Email",
        "Contact Phone",
    ])

    bucket_labels = {
        "overdue": "Overdue",
        "today": "Today",
        "next7": "Next 7 Days",
        "later": "Later",
    }

    for item in schedule_data["visible_jobs"]:
        job = item["job"]
        writer.writerow([
            job["installation_date"] or "",
            bucket_labels.get(item["bucket"], item["bucket"] or ""),
            job["status"] or "",
            job["job_name"] or "",
            job["project_site"] or "",
            job["client_name"] or "",
            job["assigned_project_name"] or "",
            job["assigned_project_number"] or "",
            job["crew_lead"] or "",
            job["planned_crew_size"] or "",
            job["assigned_crew"] or "",
            job["contact_name"] or "",
            job["contact_email"] or "",
            job["contact_phone"] or "",
        ])

    filename = f"dispatchproof_schedule_{local_today().isoformat()}.csv"
    csv_text = output.getvalue()

    return app.response_class(
        csv_text,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
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
        visibility_clause, visibility_params = job_visibility_sql("j")
        all_jobs = db.execute(f"""
            SELECT
                j.*,
                c.name AS client_name,
                p.name AS assigned_project_name,
                p.project_number AS assigned_project_number,
                (
                    SELECT COUNT(*)
                    FROM mobilization_attempts ma
                    WHERE ma.job_id = j.id
                ) + 1 AS attempt_number,
                (
                    SELECT COUNT(*)
                    FROM email_events ee
                    WHERE ee.job_id = j.id
                      AND ee.event_type = 'REMINDER'
                ) AS reminder_event_count,
                (
                    SELECT ee.created_at
                    FROM email_events ee
                    WHERE ee.job_id = j.id
                      AND ee.event_type = 'REMINDER'
                    ORDER BY ee.id DESC
                    LIMIT 1
                ) AS last_reminder_event_at,
                (
                    SELECT ee.status
                    FROM email_events ee
                    WHERE ee.job_id = j.id
                      AND ee.event_type = 'REMINDER'
                    ORDER BY ee.id DESC
                    LIMIT 1
                ) AS last_reminder_event_status
            FROM jobs j
            LEFT JOIN clients c ON c.id = j.client_id
            LEFT JOIN projects p ON p.id = j.project_id
            WHERE j.status != 'COMPLETED'
              AND ({visibility_clause})
            ORDER BY installation_date ASC, j.id DESC
        """, visibility_params).fetchall()

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

        visible_job_ids = {job["id"] for job in all_jobs}
        crew_conflicts_by_job, crew_conflict_group_count = get_active_crew_conflicts(db, visible_job_ids)
        crew_unavailability_by_job, crew_unavailability_group_count = get_active_crew_unavailability_issues(db)
        crew_unavailability_by_job = {k: v for k, v in crew_unavailability_by_job.items() if k in visible_job_ids}
        crew_unavailability_group_count = sum(len(v) for v in crew_unavailability_by_job.values())

    staffing_gaps_by_job, staffing_gap_job_count, staffing_gap_total_needed = get_active_staffing_gaps(all_jobs)

    counts = {"READY": 0, "REVIEW": 0, "BLOCKED": 0, "NO RESPONSE": 0, "ON SITE": 0}
    schedule_counts = {"overdue": 0, "today": 0, "next7": 0, "later": 0}
    schedule_buckets = {}

    for job in all_jobs:
        counts[job["status"]] = counts.get(job["status"], 0) + 1
        bucket = job_schedule_bucket(job["installation_date"])
        schedule_buckets[job["id"]] = bucket
        if bucket in schedule_counts:
            schedule_counts[bucket] += 1

    attention_jobs = []
    for job in all_jobs:
        job_conflicts = crew_conflicts_by_job.get(job["id"], [])
        availability_issues = crew_unavailability_by_job.get(job["id"], [])
        staffing_gap = staffing_gaps_by_job.get(job["id"])
        attention = job_attention_reason(
            job,
            schedule_buckets.get(job["id"]),
            has_crew_conflict=bool(job_conflicts),
            has_availability_issue=bool(availability_issues),
            has_staffing_gap=bool(staffing_gap),
        )
        if not attention:
            continue
        bucket = schedule_buckets.get(job["id"])
        attention_jobs.append({
            "job": job,
            "priority": attention["priority"],
            "level": attention["level"],
            "label": attention["label"],
            "message": attention["message"],
            "crew_unassigned": (
                bucket in {"overdue", "today", "next7"}
                and not job_has_crew_assignment(job)
            ),
            "crew_conflict_names": [
                conflict["crew_member_name"]
                for conflict in job_conflicts
            ],
            "crew_unavailable_names": [
                issue["crew_member_name"]
                for issue in availability_issues
            ],
            "staffing_gap": staffing_gap,
        })

    attention_jobs.sort(key=lambda item: (
        item["priority"],
        item["job"]["installation_date"] or "9999-12-31",
        item["job"]["id"],
    ))
    attention_total = len(attention_jobs)
    attention_jobs = attention_jobs[:5]

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
                job["crew_lead"] or "",
                job["assigned_crew"] or "",
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
        attention_jobs=attention_jobs,
        attention_total=attention_total,
        crew_conflict_group_count=crew_conflict_group_count,
        crew_unavailability_group_count=crew_unavailability_group_count,
        staffing_gap_job_count=staffing_gap_job_count,
        staffing_gap_total_needed=staffing_gap_total_needed,
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
        visibility_clause, visibility_params = job_visibility_sql("j")
        all_jobs = db.execute(f"""
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
              AND ({visibility_clause})
            ORDER BY j.completed_at DESC, j.installation_date DESC, j.id DESC
        """, visibility_params).fetchall()

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

def export_filter_id(value):
    try:
        parsed = int(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None

def csv_download(rows, headers, filename):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)

    # UTF-8 BOM helps Excel open names/characters cleanly.
    payload = io.BytesIO(("\ufeff" + stream.getvalue()).encode("utf-8"))
    payload.seek(0)
    return send_file(
        payload,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=filename,
    )

@app.get("/export/active.csv")
def export_active_csv():
    status_filter = (request.args.get("status") or "").strip().upper()
    if status_filter not in {"READY", "REVIEW", "BLOCKED", "NO RESPONSE", "ON SITE"}:
        status_filter = ""

    schedule_filter = (request.args.get("schedule") or "").strip().lower()
    if schedule_filter not in {"overdue", "today", "next7", "later"}:
        schedule_filter = ""

    search_query = (request.args.get("q") or "").strip()
    search_lower = search_query.lower()
    client_filter = export_filter_id(request.args.get("client"))
    project_filter = export_filter_id(request.args.get("project"))

    with get_db() as db:
        visibility_clause, visibility_params = job_visibility_sql("j")
        all_jobs = db.execute(f"""
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
              AND ({visibility_clause})
            ORDER BY j.installation_date ASC, j.id DESC
        """, visibility_params).fetchall()

    export_jobs = []
    for job in all_jobs:
        bucket = job_schedule_bucket(job["installation_date"])
        if status_filter and job["status"] != status_filter:
            continue
        if schedule_filter and bucket != schedule_filter:
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
        export_jobs.append((job, bucket))

    rows = []
    for job, bucket in export_jobs:
        rows.append([
            job["job_name"] or "",
            job["client_name"] or "",
            job["assigned_project_name"] or "",
            job["assigned_project_number"] or "",
            job["project_site"] or "",
            job["attempt_number"],
            job["installation_date"] or "",
            schedule_bucket_label(bucket),
            job["status"] or "",
            job["contact_name"] or "",
            job["contact_email"] or "",
            job["contact_phone"] or "",
            format_datetime(job["response_at"]) if job["response_at"] else "",
            job["arrival_status"] or "",
            format_datetime(job["arrived_at"]) if job["arrived_at"] else "",
        ])

    filename = f"dispatchproof_active_jobs_{local_today().isoformat()}.csv"
    return csv_download(
        rows,
        [
            "Job",
            "Client",
            "Project",
            "Project Number",
            "Project / Site",
            "Attempt",
            "Installation Date",
            "Schedule",
            "Status",
            "Site Contact",
            "Contact Email",
            "Contact Phone",
            "Readiness Response",
            "Arrival Status",
            "Arrival Time",
        ],
        filename,
    )

@app.get("/export/completed.csv")
def export_completed_csv():
    search_query = (request.args.get("q") or "").strip()
    search_lower = search_query.lower()
    client_filter = export_filter_id(request.args.get("client"))
    project_filter = export_filter_id(request.args.get("project"))

    with get_db() as db:
        visibility_clause, visibility_params = job_visibility_sql("j")
        all_jobs = db.execute(f"""
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
              AND ({visibility_clause})
            ORDER BY j.completed_at DESC, j.installation_date DESC, j.id DESC
        """, visibility_params).fetchall()

    export_jobs = []
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
        export_jobs.append(job)

    rows = []
    for job in export_jobs:
        rows.append([
            job["job_name"] or "",
            job["client_name"] or "",
            job["assigned_project_name"] or "",
            job["assigned_project_number"] or "",
            job["project_site"] or "",
            job["attempt_number"],
            job["installation_date"] or "",
            format_datetime(job["completed_at"]) if job["completed_at"] else "",
            job["contact_name"] or "",
            job["contact_email"] or "",
            job["contact_phone"] or "",
            format_datetime(job["response_at"]) if job["response_at"] else "",
            job["arrival_status"] or "",
            format_datetime(job["arrived_at"]) if job["arrived_at"] else "",
        ])

    filename = f"dispatchproof_completed_jobs_{local_today().isoformat()}.csv"
    return csv_download(
        rows,
        [
            "Job",
            "Client",
            "Project",
            "Project Number",
            "Project / Site",
            "Attempt",
            "Installation Date",
            "Completed",
            "Site Contact",
            "Contact Email",
            "Contact Phone",
            "Readiness Response",
            "Arrival Status",
            "Arrival Time",
        ],
        filename,
    )


@app.route("/jobs/new", methods=["GET", "POST"])
def new_job():
    if request.method == "POST":
        standard_checklist = [x.strip() for x in request.form.getlist("checklist") if x.strip()]
        custom_checklist = [x.strip() for x in request.form.getlist("checklist_custom") if x.strip()]
        checklist = standard_checklist + custom_checklist
        if not checklist:
            checklist = DEFAULT_CHECKLIST

        reminder_enabled = 1 if request.form.get("reminder_enabled") == "on" else 0
        reminder_hours_before = int(request.form.get("reminder_hours_before") or DEFAULT_REMINDER_HOURS_BEFORE)
        duplicate_source_id = normalize_optional_id(request.form.get("duplicate_source_id"))
        requested_team_id = normalize_optional_id(request.form.get("team_id"))
        planned_crew_size_raw = request.form.get("planned_crew_size", "").strip()
        planned_crew_size = None
        if planned_crew_size_raw:
            try:
                planned_crew_size = int(planned_crew_size_raw)
            except ValueError:
                flash("Planned Crew Size must be a whole number.")
                planned_crew_size = -1
            if planned_crew_size == 0 or planned_crew_size < -1:
                flash("Planned Crew Size must be at least 1 when entered.")
                planned_crew_size = -1

        token = secrets.token_urlsafe(18)
        arrival_token = secrets.token_urlsafe(24)
        client_report_token = secrets.token_urlsafe(24)
        if planned_crew_size == -1:
            with get_db() as db:
                clients, projects = get_clients_and_projects(db)
                crew_members = get_crew_members_for_picker(db)
                crew_state = resolve_job_crew_form(db, request.form)
                team_options = user_team_options(db)
            return render_template(
                "new_job.html",
                default_checklist=checklist,
                default_reminder_enabled=bool(reminder_enabled),
                default_reminder_hours=reminder_hours_before,
                clients=clients,
                projects=projects,
                crew_members=crew_members,
                selected_crew_ids=crew_state["selected_crew_ids"],
                selected_lead_id=crew_state["selected_lead_id"],
                custom_crew_lead=crew_state["custom_crew_lead"],
                custom_crew_names=crew_state["custom_crew_names"],
                selected_client_id=normalize_optional_id(request.form.get("client_id")),
                selected_project_id=normalize_optional_id(request.form.get("project_id")),
                duplicate_source=None,
                team_options=team_options,
                selected_team_id=requested_team_id,
                form_values={
                    "job_name": request.form.get("job_name", ""),
                    "project_site": request.form.get("project_site", ""),
                    "installation_date": request.form.get("installation_date", ""),
                    "contact_name": request.form.get("contact_name", ""),
                    "contact_email": request.form.get("contact_email", ""),
                    "contact_phone": request.form.get("contact_phone", ""),
                    "planned_crew_size": planned_crew_size_raw,
                },
            )

        with get_db() as db:
            crew_members = get_crew_members_for_picker(db)
            crew_state = resolve_job_crew_form(db, request.form)
            crew_lead = crew_state["crew_lead"]
            assigned_crew = crew_state["assigned_crew"]
            team_options = user_team_options(db)
            team_id, team_error = resolve_job_team_id(db, request.form.get("team_id"))

            duplicate_source = None
            if duplicate_source_id:
                if user_can_access_job(db, duplicate_source_id):
                    duplicate_source = db.execute(
                        "SELECT id, job_name FROM jobs WHERE id = ?",
                        (duplicate_source_id,),
                    ).fetchone()

            if team_error:
                flash(team_error)
                clients, projects = get_clients_and_projects(db)
                return render_template(
                    "new_job.html",
                    default_checklist=checklist,
                    default_reminder_enabled=bool(reminder_enabled),
                    default_reminder_hours=reminder_hours_before,
                    clients=clients,
                    projects=projects,
                    crew_members=crew_members,
                    selected_crew_ids=crew_state["selected_crew_ids"],
                    selected_lead_id=crew_state["selected_lead_id"],
                    custom_crew_lead=crew_state["custom_crew_lead"],
                    custom_crew_names=crew_state["custom_crew_names"],
                    selected_client_id=normalize_optional_id(request.form.get("client_id")),
                    selected_project_id=normalize_optional_id(request.form.get("project_id")),
                    duplicate_source=duplicate_source,
                    team_options=team_options,
                    selected_team_id=requested_team_id,
                    form_values={
                        "job_name": request.form.get("job_name", ""),
                        "project_site": request.form.get("project_site", ""),
                        "installation_date": request.form.get("installation_date", ""),
                        "contact_name": request.form.get("contact_name", ""),
                        "contact_email": request.form.get("contact_email", ""),
                        "contact_phone": request.form.get("contact_phone", ""),
                        "planned_crew_size": planned_crew_size_raw,
                    },
                )

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
                    crew_members=crew_members,
                    selected_crew_ids=crew_state["selected_crew_ids"],
                    selected_lead_id=crew_state["selected_lead_id"],
                    custom_crew_lead=crew_state["custom_crew_lead"],
                    custom_crew_names=crew_state["custom_crew_names"],
                    selected_client_id=normalize_optional_id(request.form.get("client_id")),
                    selected_project_id=normalize_optional_id(request.form.get("project_id")),
                    duplicate_source=duplicate_source,
                    team_options=team_options,
                    selected_team_id=requested_team_id,
                    form_values={
                        "job_name": request.form.get("job_name", ""),
                        "project_site": request.form.get("project_site", ""),
                        "installation_date": request.form.get("installation_date", ""),
                        "contact_name": request.form.get("contact_name", ""),
                        "contact_email": request.form.get("contact_email", ""),
                        "contact_phone": request.form.get("contact_phone", ""),
                        "planned_crew_size": planned_crew_size_raw,
                    },
                )

            owner_user_id = current_user_id()
            try:
                cur = db.execute("""
                    INSERT INTO jobs (
                        public_token, arrival_token, client_report_token,
                        client_id, project_id,
                        job_name, project_site, installation_date,
                        contact_name, contact_email, contact_phone, checklist_json,
                        crew_lead, planned_crew_size, assigned_crew,
                        owner_user_id, team_id,
                        status, created_at, reminder_enabled, reminder_hours_before,
                        reminder_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'NO RESPONSE', ?, ?, ?, 0)
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
                    crew_lead,
                    planned_crew_size,
                    assigned_crew,
                    owner_user_id,
                    team_id,
                    now_iso(),
                    reminder_enabled,
                    reminder_hours_before,
                ))
            except sqlite3.IntegrityError:
                db.rollback()
                fk_list = [dict(row) for row in db.execute("PRAGMA foreign_key_list(jobs)").fetchall()]
                parent_state = {
                    "owner_user_exists": bool(owner_user_id and db.execute("SELECT 1 FROM users WHERE id = ?", (owner_user_id,)).fetchone()) if owner_user_id else True,
                    "team_exists": bool(team_id and db.execute("SELECT 1 FROM teams WHERE id = ?", (team_id,)).fetchone()) if team_id else True,
                    "client_exists": bool(client_id and db.execute("SELECT 1 FROM clients WHERE id = ?", (client_id,)).fetchone()) if client_id else True,
                    "project_exists": bool(project_id and db.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()) if project_id else True,
                }
                app.logger.exception(
                    "Job create integrity error user_id=%r team_id=%r client_id=%r project_id=%r parent_state=%r job_fk_list=%r",
                    owner_user_id, team_id, client_id, project_id, parent_state, fk_list,
                )
                flash("The job could not be created because an account, team, client, or project link changed. Nothing was saved. Please refresh the form and try again.")
                return redirect(url_for("new_job", client_id=client_id or "", project_id=project_id or ""))
            job_id = cur.lastrowid
            save_job_crew_assignments(
                db,
                job_id,
                crew_state["selected_crew_ids"],
                crew_state["selected_lead_id"],
            )
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
        "planned_crew_size": "",
    }
    default_checklist = DEFAULT_CHECKLIST
    default_reminder_enabled = DEFAULT_REMINDER_ENABLED
    default_reminder_hours = DEFAULT_REMINDER_HOURS_BEFORE

    with get_db() as db:
        clients, projects = get_clients_and_projects(db)
        crew_members = get_crew_members_for_picker(db)
        team_options = user_team_options(db)
        selected_team_id = None
        selected_crew_ids = []
        selected_lead_id = None
        custom_crew_lead = ""
        custom_crew_names = ""
        selected_client_id = normalize_optional_id(request.args.get("client_id"))
        selected_project_id = normalize_optional_id(request.args.get("project_id"))
        duplicate_from = normalize_optional_id(request.args.get("duplicate_from"))

        if duplicate_from:
            duplicate_source = None
            if user_can_access_job(db, duplicate_from):
                duplicate_source = db.execute(
                    "SELECT * FROM jobs WHERE id = ?",
                    (duplicate_from,),
                ).fetchone()
            if duplicate_source:
                selected_client_id = duplicate_source["client_id"]
                selected_project_id = duplicate_source["project_id"]
                allowed_team_ids = {team["id"] for team in team_options}
                selected_team_id = duplicate_source["team_id"] if duplicate_source["team_id"] in allowed_team_ids else None
                form_values = {
                    "job_name": duplicate_source["job_name"] or "",
                    "project_site": duplicate_source["project_site"] or "",
                    "installation_date": "",
                    "contact_name": duplicate_source["contact_name"] or "",
                    "contact_email": duplicate_source["contact_email"] or "",
                    "contact_phone": duplicate_source["contact_phone"] or "",
                    "planned_crew_size": "",
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
        crew_members=crew_members,
        selected_crew_ids=selected_crew_ids,
        selected_lead_id=selected_lead_id,
        custom_crew_lead=custom_crew_lead,
        custom_crew_names=custom_crew_names,
        selected_client_id=selected_client_id,
        selected_project_id=selected_project_id,
        duplicate_source=duplicate_source,
        team_options=team_options,
        selected_team_id=selected_team_id,
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
        reminder_event_count = db.execute("""
            SELECT COUNT(*) AS c
            FROM email_events
            WHERE job_id = ?
              AND event_type = 'REMINDER'
        """, (job_id,)).fetchone()["c"]
        latest_reminder_event = db.execute("""
            SELECT *
            FROM email_events
            WHERE job_id = ?
              AND event_type = 'REMINDER'
            ORDER BY id DESC
            LIMIT 1
        """, (job_id,)).fetchone()

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
        reminder_event_count=reminder_event_count,
        latest_reminder_event=latest_reminder_event,
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
        if request.form.get("return_to") == "dashboard":
            return redirect(url_for("dashboard"))
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

    # Quick actions may launch from Dashboard. Only accept a known internal
    # destination instead of redirecting to an arbitrary URL.
    if request.form.get("return_to") == "dashboard":
        return redirect(url_for("dashboard"))

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


@app.route("/jobs/<int:job_id>/field-updates", methods=["GET", "POST"])
def field_updates(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            abort(404)

        if request.method == "POST":
            if job["status"] == "COMPLETED":
                flash("Completed jobs are locked. Existing field updates remain available as evidence.")
                return redirect(url_for("field_updates", job_id=job_id))

            crew_member_id = normalize_optional_id(request.form.get("crew_member_id"))
            recipient_name = (request.form.get("recipient_name") or "").strip()
            recipient_email = (request.form.get("recipient_email") or "").strip()
            request_note = (request.form.get("request_note") or "").strip()

            selected_member = None
            if crew_member_id:
                selected_member = db.execute("""
                    SELECT cm.*
                    FROM crew_members cm
                    JOIN job_crew_assignments jca ON jca.crew_member_id = cm.id
                    WHERE cm.id = ? AND jca.job_id = ?
                """, (crew_member_id, job_id)).fetchone()
                if not selected_member:
                    flash("That installer/subcontractor is not assigned to this job.")
                    return redirect(url_for("field_updates", job_id=job_id))
                recipient_name = recipient_name or selected_member["name"]
                recipient_email = recipient_email or (selected_member["email"] or "").strip()

            if not recipient_name:
                flash("Recipient Name is required.")
                return redirect(url_for("field_updates", job_id=job_id))
            if not request_note:
                flash("Type a PM request or field note before generating the link.")
                return redirect(url_for("field_updates", job_id=job_id))

            while True:
                token = secrets.token_urlsafe(24)
                if not db.execute("SELECT 1 FROM field_update_links WHERE token = ?", (token,)).fetchone():
                    break

            cur = db.execute("""
                INSERT INTO field_update_links (
                    job_id, token, crew_member_id, recipient_name, recipient_email,
                    request_note, is_active, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (
                job_id, token, crew_member_id, recipient_name, recipient_email or None,
                request_note, current_display_name() or current_username() or "Internal User", now_iso(),
            ))
            link_id = cur.lastrowid
            field_link = db.execute("SELECT * FROM field_update_links WHERE id = ?", (link_id,)).fetchone()
            record_activity(
                db,
                "Field Update Requested",
                f"Created a secure field-update request for {recipient_name}.",
                job_id=job_id,
            )
            db.commit()

            public_url = public_field_update_url(field_link)
            if recipient_email:
                status, _error = send_field_update_email(job, field_link, public_url)
                if status == "SENT":
                    flash("Field update link sent and saved to Communication History.")
                elif status == "OUTBOX":
                    flash("Field update email preview generated in Email Outbox. Copy or open the secure link below for testing.")
                else:
                    flash("Field update link created, but email delivery failed. You can still copy the secure link below.")
            else:
                flash("Field update link created. No email was supplied, so copy the secure link and send it directly.")
            return redirect(url_for("field_updates", job_id=job_id, created=link_id) + f"#field-link-{link_id}")

        assigned_crew = db.execute("""
            SELECT cm.*, jca.is_lead, jca.sort_order
            FROM job_crew_assignments jca
            JOIN crew_members cm ON cm.id = jca.crew_member_id
            WHERE jca.job_id = ?
            ORDER BY jca.sort_order, LOWER(cm.name), cm.id
        """, (job_id,)).fetchall()
        links = db.execute("""
            SELECT ful.*, cm.member_type, cm.company_name
            FROM field_update_links ful
            LEFT JOIN crew_members cm ON cm.id = ful.crew_member_id
            WHERE ful.job_id = ?
            ORDER BY ful.id DESC
        """, (job_id,)).fetchall()
        entries = db.execute("""
            SELECT fpe.*, ful.recipient_name AS link_recipient
            FROM field_progress_entries fpe
            LEFT JOIN field_update_links ful ON ful.id = fpe.field_link_id
            WHERE fpe.job_id = ?
            ORDER BY fpe.work_date DESC, fpe.created_at DESC, fpe.id DESC
        """, (job_id,)).fetchall()

    progress_entries = []
    for row in entries:
        item = dict(row)
        item["photos"] = parse_json_list(row["photo_json"])
        progress_entries.append(item)
    progress_days = len({item["work_date"] for item in progress_entries if item["entry_type"] == "DAILY_PROGRESS"})
    link_items = []
    for row in links:
        item = dict(row)
        item["public_url"] = public_field_update_url(row)
        link_items.append(item)

    return render_template(
        "field_updates.html",
        job=job,
        assigned_crew=assigned_crew,
        field_links=link_items,
        progress_entries=progress_entries,
        progress_days=progress_days,
        created_link_id=normalize_optional_id(request.args.get("created")),
    )


@app.post("/jobs/<int:job_id>/field-updates/<int:link_id>/revoke")
def revoke_field_update_link(job_id, link_id):
    with get_db() as db:
        link = db.execute("SELECT * FROM field_update_links WHERE id = ? AND job_id = ?", (link_id, job_id)).fetchone()
        if not link:
            abort(404)
        if link["is_active"]:
            db.execute("UPDATE field_update_links SET is_active = 0, revoked_at = ? WHERE id = ?", (now_iso(), link_id))
            record_activity(db, "Field Link Revoked", f"Revoked field update link for {link['recipient_name']}.", job_id=job_id)
            db.commit()
            flash("Field update link revoked. The old URL can no longer accept submissions.")
    return redirect(url_for("field_updates", job_id=job_id) + f"#field-link-{link_id}")


@app.route("/f/<token>", methods=["GET", "POST"])
def public_field_update(token):
    with get_db() as db:
        row = db.execute("""
            SELECT ful.*, j.job_name, j.project_site, j.installation_date, j.status AS job_status
            FROM field_update_links ful
            JOIN jobs j ON j.id = ful.job_id
            WHERE ful.token = ?
        """, (token,)).fetchone()
    if not row:
        abort(404)
    field_link = dict(row)
    if not field_link["is_active"]:
        return render_template("public_field_update_unavailable.html", field_link=field_link, reason="This field update link has been revoked."), 410
    if field_link["job_status"] == "COMPLETED":
        return render_template("public_field_update_unavailable.html", field_link=field_link, reason="This job has been completed and field submissions are closed."), 410

    if request.method == "POST":
        entry_type = (request.form.get("entry_type") or "").strip().upper()
        if entry_type not in {"RESPONSE", "DAILY_PROGRESS"}:
            flash("Choose a valid field update type.")
            return redirect(url_for("public_field_update", token=token))
        submitted_by = (request.form.get("submitted_by") or field_link["recipient_name"] or "Field Crew").strip()[:160]
        work_date = (request.form.get("work_date") or local_today().isoformat()).strip()
        try:
            date.fromisoformat(work_date)
        except Exception:
            work_date = local_today().isoformat()
        work_completed = (request.form.get("work_completed") or "").strip()[:4000]
        notes = (request.form.get("notes") or "").strip()[:4000]
        issues_delays = (request.form.get("issues_delays") or "").strip()[:4000]
        crew_size_raw = (request.form.get("crew_size") or "").strip()
        hours_raw = (request.form.get("hours_worked") or "").strip()
        try:
            crew_size = max(0, min(999, int(crew_size_raw))) if crew_size_raw else None
        except ValueError:
            crew_size = None
        try:
            hours_worked = max(0.0, min(24.0, float(hours_raw))) if hours_raw else None
        except ValueError:
            hours_worked = None

        files = request.files.getlist("photos")
        valid_uploads = [f for f in files if f and f.filename and allowed_file(f.filename)]
        if len(valid_uploads) > 30:
            flash("Please upload no more than 30 photos in one update.")
            return redirect(url_for("public_field_update", token=token))
        if entry_type == "DAILY_PROGRESS":
            if not work_completed:
                flash("Please describe the work completed today.")
                return redirect(url_for("public_field_update", token=token))
            if not valid_uploads:
                flash("Please upload at least 1 daily progress photo.")
                return redirect(url_for("public_field_update", token=token))
        elif not notes and not valid_uploads:
            flash("Add a response note or at least one photo before submitting.")
            return redirect(url_for("public_field_update", token=token))

        saved = save_photos(valid_uploads, f"field_{field_link['job_id']}")
        with get_db() as db:
            db.execute("""
                INSERT INTO field_progress_entries (
                    job_id, field_link_id, entry_type, submitted_by, work_date,
                    work_completed, notes, crew_size, hours_worked, issues_delays,
                    photo_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                field_link["job_id"], field_link["id"], entry_type, submitted_by,
                work_date, work_completed or None, notes or None, crew_size,
                hours_worked, issues_delays or None, json.dumps(saved), now_iso(),
            ))
            db.execute("UPDATE field_update_links SET last_used_at = ? WHERE id = ?", (now_iso(), field_link["id"]))
            action = "Daily Progress Submitted" if entry_type == "DAILY_PROGRESS" else "Field Response Submitted"
            description = (
                f"{submitted_by} submitted daily progress for {work_date} with {len(saved)} photo(s)."
                if entry_type == "DAILY_PROGRESS"
                else f"{submitted_by} responded to the PM field request with {len(saved)} photo(s)."
            )
            record_activity(db, action, description, job_id=field_link["job_id"], actor_type="FIELD", actor_name=submitted_by)
            db.commit()
        return redirect(url_for("public_field_update_submitted", token=token, kind=entry_type.lower()))

    return render_template("public_field_update.html", field_link=field_link, today=local_today().isoformat())


@app.route("/f/<token>/submitted")
def public_field_update_submitted(token):
    with get_db() as db:
        field_link = db.execute("""
            SELECT ful.*, j.job_name, j.project_site
            FROM field_update_links ful
            JOIN jobs j ON j.id = ful.job_id
            WHERE ful.token = ?
        """, (token,)).fetchone()
    if not field_link:
        abort(404)
    return render_template("public_field_update_submitted.html", field_link=field_link, kind=(request.args.get("kind") or "update"))


@app.route("/email-outbox")
def email_outbox():
    with get_db() as db:
        visibility_clause, visibility_params = job_visibility_sql("j")
        events = db.execute(f"""
            SELECT e.*, j.job_name,
                   COALESCE(e.scope_name, j.job_name) AS display_name
            FROM email_events e
            JOIN jobs j ON j.id = e.job_id
            WHERE ({visibility_clause})
            ORDER BY e.id DESC
            LIMIT 100
        """, visibility_params).fetchall()

    return render_template("email_outbox.html", events=events)

@app.route("/email-outbox/<int:event_id>")
def email_outbox_detail(event_id):
    with get_db() as db:
        visibility_clause, visibility_params = job_visibility_sql("j")
        event = db.execute(f"""
            SELECT e.*, j.job_name, j.project_site,
                   COALESCE(e.scope_name, j.job_name) AS display_name
            FROM email_events e
            JOIN jobs j ON j.id = e.job_id
            WHERE e.id = ?
              AND ({visibility_clause})
        """, (event_id, *visibility_params)).fetchone()

    if not event:
        abort(404)

    return render_template("email_outbox_detail.html", event=event)

@app.route("/r/<token>", methods=["GET", "POST"], strict_slashes=False)
def public_readiness(token):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE public_token = ?", (token,)).fetchone()
    if not job:
        app.logger.warning(
            "Public readiness token not found token_prefix=%s request_host=%s configured_public_base=%s render_external_url=%s",
            (token or "")[:8],
            (request.url_root or "").rstrip("/"),
            PUBLIC_BASE_URL or "<unset>",
            RENDER_EXTERNAL_URL or "<unset>",
        )
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
        db.execute("""
            UPDATE field_update_links
            SET is_active = 0, revoked_at = COALESCE(revoked_at, ?)
            WHERE job_id = ? AND is_active = 1
        """, (completed_at, job_id))
        record_activity(
            db,
            "Job Completed",
            f"Marked {job['job_name']} complete and revoked active installer/field links.",
            job_id=job_id,
        )
        db.commit()

    flash("Job marked complete. Readiness, arrival, and field-progress evidence remains preserved; active field links were closed.")
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
                "Readiness, arrival evidence, reports, Office Notes, field progress, and prior activity were preserved. Prior field links remain revoked."
            ),
            job_id=job_id,
        )
        db.commit()

    flash("Job reopened and returned to On Site. Existing evidence/history was preserved. Create a new Field Update link if field access is needed again.")
    return redirect(url_for("job_detail", job_id=job_id))


@app.post("/clients/<int:client_id>/documents")
def upload_client_document(client_id):
    uploaded = request.files.get("client_document")
    if not uploaded or not uploaded.filename:
        flash("Choose a client document before uploading.")
        return redirect(url_for("client_detail", client_id=client_id) + "#client-documents")

    with get_db() as db:
        client = db.execute(
            "SELECT * FROM clients WHERE id = ?",
            (client_id,),
        ).fetchone()
    if not client:
        abort(404)

    original_filename = secure_filename(uploaded.filename)
    if not original_filename:
        flash("That document filename could not be used.")
        return redirect(url_for("client_detail", client_id=client_id) + "#client-documents")

    if not allowed_document(original_filename):
        flash("Unsupported document type. Use PDF, Word, Excel, CSV, TXT, image, DWG, or DXF files.")
        return redirect(url_for("client_detail", client_id=client_id) + "#client-documents")

    stored_filename = f"clientdoc_{client_id}_{secrets.token_hex(8)}_{original_filename}"
    destination = UPLOAD_DIR / stored_filename
    uploaded.save(destination)

    try:
        file_size = destination.stat().st_size
    except OSError:
        destination.unlink(missing_ok=True)
        flash("The client document could not be saved.")
        return redirect(url_for("client_detail", client_id=client_id) + "#client-documents")

    if file_size > MAX_JOB_DOCUMENT_BYTES:
        destination.unlink(missing_ok=True)
        flash("Client documents can be up to 20 MB each.")
        return redirect(url_for("client_detail", client_id=client_id) + "#client-documents")

    actor_type, actor_name = activity_actor()
    try:
        with get_db() as db:
            db.execute("""
                INSERT INTO client_documents (
                    client_id, stored_filename, original_filename, file_size,
                    content_type, actor_type, actor_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                client_id,
                stored_filename,
                original_filename,
                file_size,
                uploaded.mimetype or "",
                actor_type,
                actor_name,
                now_iso(),
            ))
            record_activity(
                db,
                "Client Document Uploaded",
                f"Uploaded internal client document {original_filename} to {client['name']}.",
            )
            db.commit()
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    flash("Internal client document uploaded.")
    return redirect(url_for("client_detail", client_id=client_id) + "#client-documents")


@app.get("/clients/<int:client_id>/documents/<int:document_id>/download")
def download_client_document(client_id, document_id):
    with get_db() as db:
        document = db.execute("""
            SELECT *
            FROM client_documents
            WHERE id = ? AND client_id = ?
        """, (document_id, client_id)).fetchone()

    if not document:
        abort(404)

    path = UPLOAD_DIR / document["stored_filename"]
    if not path.exists():
        abort(404)

    return send_file(
        path,
        as_attachment=True,
        download_name=document["original_filename"],
        mimetype=document["content_type"] or None,
    )


@app.post("/clients/<int:client_id>/documents/<int:document_id>/delete")
def delete_client_document(client_id, document_id):
    with get_db() as db:
        document = db.execute("""
            SELECT cd.*, c.name AS client_name
            FROM client_documents cd
            JOIN clients c ON c.id = cd.client_id
            WHERE cd.id = ? AND cd.client_id = ?
        """, (document_id, client_id)).fetchone()
        if not document:
            abort(404)

        db.execute(
            "DELETE FROM client_documents WHERE id = ? AND client_id = ?",
            (document_id, client_id),
        )
        record_activity(
            db,
            "Client Document Deleted",
            f"Deleted internal client document {document['original_filename']} from "
            f"{document['client_name']}.",
        )
        db.commit()

    try:
        (UPLOAD_DIR / document["stored_filename"]).unlink(missing_ok=True)
    except OSError:
        pass

    flash("Internal client document deleted.")
    return redirect(url_for("client_detail", client_id=client_id) + "#client-documents")


@app.post("/projects/<int:project_id>/documents")
def upload_project_document(project_id):
    uploaded = request.files.get("project_document")
    if not uploaded or not uploaded.filename:
        flash("Choose a project document before uploading.")
        return redirect(url_for("project_detail", project_id=project_id) + "#project-documents")

    with get_db() as db:
        project = db.execute("""
            SELECT p.*, c.name AS client_name
            FROM projects p
            JOIN clients c ON c.id = p.client_id
            WHERE p.id = ?
        """, (project_id,)).fetchone()
    if not project:
        abort(404)

    original_filename = secure_filename(uploaded.filename)
    if not original_filename:
        flash("That document filename could not be used.")
        return redirect(url_for("project_detail", project_id=project_id) + "#project-documents")

    if not allowed_document(original_filename):
        flash("Unsupported document type. Use PDF, Word, Excel, CSV, TXT, image, DWG, or DXF files.")
        return redirect(url_for("project_detail", project_id=project_id) + "#project-documents")

    stored_filename = f"projdoc_{project_id}_{secrets.token_hex(8)}_{original_filename}"
    destination = UPLOAD_DIR / stored_filename
    uploaded.save(destination)

    try:
        file_size = destination.stat().st_size
    except OSError:
        destination.unlink(missing_ok=True)
        flash("The project document could not be saved.")
        return redirect(url_for("project_detail", project_id=project_id) + "#project-documents")

    if file_size > MAX_JOB_DOCUMENT_BYTES:
        destination.unlink(missing_ok=True)
        flash("Project documents can be up to 20 MB each.")
        return redirect(url_for("project_detail", project_id=project_id) + "#project-documents")

    actor_type, actor_name = activity_actor()
    try:
        with get_db() as db:
            db.execute("""
                INSERT INTO project_documents (
                    project_id, stored_filename, original_filename, file_size,
                    content_type, actor_type, actor_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id,
                stored_filename,
                original_filename,
                file_size,
                uploaded.mimetype or "",
                actor_type,
                actor_name,
                now_iso(),
            ))
            record_activity(
                db,
                "Project Document Uploaded",
                f"Uploaded internal project document {original_filename} to "
                f"{project['client_name']} / {project['name']}.",
            )
            db.commit()
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    flash("Internal project document uploaded.")
    return redirect(url_for("project_detail", project_id=project_id) + "#project-documents")


@app.get("/projects/<int:project_id>/documents/<int:document_id>/download")
def download_project_document(project_id, document_id):
    with get_db() as db:
        document = db.execute("""
            SELECT *
            FROM project_documents
            WHERE id = ? AND project_id = ?
        """, (document_id, project_id)).fetchone()

    if not document:
        abort(404)

    path = UPLOAD_DIR / document["stored_filename"]
    if not path.exists():
        abort(404)

    return send_file(
        path,
        as_attachment=True,
        download_name=document["original_filename"],
        mimetype=document["content_type"] or None,
    )


@app.post("/projects/<int:project_id>/documents/<int:document_id>/delete")
def delete_project_document(project_id, document_id):
    with get_db() as db:
        document = db.execute("""
            SELECT pd.*, p.name AS project_name, c.name AS client_name
            FROM project_documents pd
            JOIN projects p ON p.id = pd.project_id
            JOIN clients c ON c.id = p.client_id
            WHERE pd.id = ? AND pd.project_id = ?
        """, (document_id, project_id)).fetchone()
        if not document:
            abort(404)

        db.execute(
            "DELETE FROM project_documents WHERE id = ? AND project_id = ?",
            (document_id, project_id),
        )
        record_activity(
            db,
            "Project Document Deleted",
            f"Deleted internal project document {document['original_filename']} from "
            f"{document['client_name']} / {document['project_name']}.",
        )
        db.commit()

    try:
        (UPLOAD_DIR / document["stored_filename"]).unlink(missing_ok=True)
    except OSError:
        pass

    flash("Internal project document deleted.")
    return redirect(url_for("project_detail", project_id=project_id) + "#project-documents")


@app.post("/jobs/<int:job_id>/documents")
def upload_job_document(job_id):
    uploaded = request.files.get("job_document")
    if not uploaded or not uploaded.filename:
        flash("Choose a document before uploading.")
        return redirect(url_for("job_detail", job_id=job_id) + "#job-documents")

    with get_db() as db:
        job = db.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        abort(404)

    original_filename = secure_filename(uploaded.filename)
    if not original_filename:
        flash("That document filename could not be used.")
        return redirect(url_for("job_detail", job_id=job_id) + "#job-documents")

    if not allowed_document(original_filename):
        flash("Unsupported document type. Use PDF, Word, Excel, CSV, TXT, image, DWG, or DXF files.")
        return redirect(url_for("job_detail", job_id=job_id) + "#job-documents")

    stored_filename = f"jobdoc_{job_id}_{secrets.token_hex(8)}_{original_filename}"
    destination = UPLOAD_DIR / stored_filename
    uploaded.save(destination)

    try:
        file_size = destination.stat().st_size
    except OSError:
        destination.unlink(missing_ok=True)
        flash("The document could not be saved.")
        return redirect(url_for("job_detail", job_id=job_id) + "#job-documents")

    if file_size > MAX_JOB_DOCUMENT_BYTES:
        destination.unlink(missing_ok=True)
        flash("Job documents can be up to 20 MB each.")
        return redirect(url_for("job_detail", job_id=job_id) + "#job-documents")

    actor_type, actor_name = activity_actor()
    try:
        with get_db() as db:
            db.execute("""
                INSERT INTO job_documents (
                    job_id, stored_filename, original_filename, file_size,
                    content_type, actor_type, actor_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                stored_filename,
                original_filename,
                file_size,
                uploaded.mimetype or "",
                actor_type,
                actor_name,
                now_iso(),
            ))
            record_activity(
                db,
                "Job Document Uploaded",
                f"Uploaded internal job document: {original_filename}.",
                job_id=job_id,
            )
            db.commit()
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    flash("Internal job document uploaded.")
    return redirect(url_for("job_detail", job_id=job_id) + "#job-documents")


@app.get("/jobs/<int:job_id>/documents/<int:document_id>/download")
def download_job_document(job_id, document_id):
    with get_db() as db:
        document = db.execute("""
            SELECT *
            FROM job_documents
            WHERE id = ? AND job_id = ?
        """, (document_id, job_id)).fetchone()

    if not document:
        abort(404)

    path = UPLOAD_DIR / document["stored_filename"]
    if not path.exists():
        abort(404)

    return send_file(
        path,
        as_attachment=True,
        download_name=document["original_filename"],
        mimetype=document["content_type"] or None,
    )


@app.post("/jobs/<int:job_id>/documents/<int:document_id>/delete")
def delete_job_document(job_id, document_id):
    with get_db() as db:
        document = db.execute("""
            SELECT *
            FROM job_documents
            WHERE id = ? AND job_id = ?
        """, (document_id, job_id)).fetchone()
        if not document:
            abort(404)

        db.execute(
            "DELETE FROM job_documents WHERE id = ? AND job_id = ?",
            (document_id, job_id),
        )
        record_activity(
            db,
            "Job Document Deleted",
            f"Deleted internal job document: {document['original_filename']}.",
            job_id=job_id,
        )
        db.commit()

    try:
        (UPLOAD_DIR / document["stored_filename"]).unlink(missing_ok=True)
    except OSError:
        pass

    flash("Internal job document deleted.")
    return redirect(url_for("job_detail", job_id=job_id) + "#job-documents")


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

        manage_job_access = can_manage_job_access(job)
        team_options = user_team_options(db, include_disabled=True)

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
            crew_state = resolve_job_crew_form(db, request.form)
            crew_lead = crew_state["crew_lead"]
            assigned_crew = crew_state["assigned_crew"]
            team_id = job["team_id"]
            if manage_job_access:
                team_id, team_error = resolve_job_team_id(db, request.form.get("team_id"), allow_disabled=True)
                if team_error:
                    flash(team_error)
                    return redirect(url_for("edit_job", job_id=job_id))
            planned_crew_size_raw = request.form.get("planned_crew_size", "").strip()
            planned_crew_size = None
            if planned_crew_size_raw:
                try:
                    planned_crew_size = int(planned_crew_size_raw)
                except ValueError:
                    planned_crew_size = -1
                if planned_crew_size < 1:
                    planned_crew_size = -1

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
                        "planned_crew_size": planned_crew_size_raw,
                        "reminder_enabled": reminder_enabled,
                        "reminder_hours_before": reminder_hours_before,
                    },
                    crew_members=get_crew_members_for_picker(db, job_id),
                    selected_crew_ids=crew_state["selected_crew_ids"],
                    selected_lead_id=crew_state["selected_lead_id"],
                    custom_crew_lead=crew_state["custom_crew_lead"],
                    custom_crew_names=crew_state["custom_crew_names"],
                    team_options=team_options,
                    selected_team_id=team_id,
                    can_manage_job_access=manage_job_access,
                )

            if planned_crew_size == -1:
                flash("Planned Crew Size must be a whole number of at least 1.")
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
                        "planned_crew_size": planned_crew_size_raw,
                        "reminder_enabled": reminder_enabled,
                        "reminder_hours_before": reminder_hours_before,
                    },
                    crew_members=get_crew_members_for_picker(db, job_id),
                    selected_crew_ids=crew_state["selected_crew_ids"],
                    selected_lead_id=crew_state["selected_lead_id"],
                    custom_crew_lead=crew_state["custom_crew_lead"],
                    custom_crew_names=crew_state["custom_crew_names"],
                    team_options=team_options,
                    selected_team_id=team_id,
                    can_manage_job_access=manage_job_access,
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
            note_change("Crew Lead", job["crew_lead"], crew_lead)
            note_change(
                "Planned Crew Size",
                job["planned_crew_size"],
                planned_crew_size,
            )
            note_change("Crew / Installers", job["assigned_crew"], assigned_crew)
            if manage_job_access and job["team_id"] != team_id:
                old_team = db.execute("SELECT name FROM teams WHERE id = ?", (job["team_id"],)).fetchone() if job["team_id"] else None
                new_team = db.execute("SELECT name FROM teams WHERE id = ?", (team_id,)).fetchone() if team_id else None
                changes.append(
                    f"Job Access: {'Team · ' + old_team['name'] if old_team else 'Personal'} → "
                    f"{'Team · ' + new_team['name'] if new_team else 'Personal'}"
                )
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
                        crew_lead = ?,
                        planned_crew_size = ?,
                        assigned_crew = ?,
                        team_id = ?,
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
                    crew_lead,
                    planned_crew_size,
                    assigned_crew,
                    team_id,
                    reminder_enabled,
                    reminder_hours_before,
                    job_id,
                ))

                save_job_crew_assignments(
                    db,
                    job_id,
                    crew_state["selected_crew_ids"],
                    crew_state["selected_lead_id"],
                )

                record_activity(
                    db,
                    "Job Details Updated",
                    " · ".join(changes),
                    job_id=job_id,
                )
                db.commit()
                flash("Job details updated.")
            else:
                existing_ids = [
                    row["crew_member_id"]
                    for row in db.execute("""
                        SELECT crew_member_id
                        FROM job_crew_assignments
                        WHERE job_id = ?
                        ORDER BY sort_order, id
                    """, (job_id,)).fetchall()
                ]
                existing_lead = db.execute("""
                    SELECT crew_member_id
                    FROM job_crew_assignments
                    WHERE job_id = ? AND is_lead = 1
                    LIMIT 1
                """, (job_id,)).fetchone()
                existing_lead_id = existing_lead["crew_member_id"] if existing_lead else None

                if (
                    existing_ids != crew_state["selected_crew_ids"]
                    or existing_lead_id != crew_state["selected_lead_id"]
                ):
                    save_job_crew_assignments(
                        db,
                        job_id,
                        crew_state["selected_crew_ids"],
                        crew_state["selected_lead_id"],
                    )
                    record_activity(
                        db,
                        "Crew Assignment Updated",
                        "Updated the structured Crew Directory assignment for this job.",
                        job_id=job_id,
                    )
                    db.commit()
                    flash("Crew assignment updated.")
                else:
                    flash("No job detail changes were made.")

            return redirect(url_for("job_detail", job_id=job_id))

        crew_picker_state = job_crew_picker_state(db, job)
        crew_members = get_crew_members_for_picker(db, job_id)

        form_values = {
            "job_name": job["job_name"] or "",
            "project_site": job["project_site"] or "",
            "installation_date": job["installation_date"] or "",
            "contact_name": job["contact_name"] or "",
            "contact_email": job["contact_email"] or "",
            "contact_phone": job["contact_phone"] or "",
            "planned_crew_size": job["planned_crew_size"] or "",
            "reminder_enabled": int(job["reminder_enabled"] or 0),
            "reminder_hours_before": int(
                job["reminder_hours_before"] or DEFAULT_REMINDER_HOURS_BEFORE
            ),
        }

    return render_template(
        "edit_job.html",
        job=job,
        form_values=form_values,
        crew_members=crew_members,
        selected_crew_ids=crew_picker_state["selected_crew_ids"],
        selected_lead_id=crew_picker_state["selected_lead_id"],
        custom_crew_lead=crew_picker_state["custom_crew_lead"],
        custom_crew_names=crew_picker_state["custom_crew_names"],
        team_options=team_options,
        selected_team_id=job["team_id"],
        can_manage_job_access=manage_job_access,
    )


@app.route("/jobs/<int:job_id>")
def job_detail(job_id):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            abort(404)

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
        job_documents = db.execute("""
            SELECT *
            FROM job_documents
            WHERE job_id = ?
            ORDER BY id DESC
            LIMIT 100
        """, (job_id,)).fetchall()
        communication_events = db.execute("""
            SELECT *
            FROM email_events
            WHERE job_id = ?
              AND event_type IN ('READINESS_REQUEST', 'REMINDER', 'CLIENT_REPORT', 'FIELD_UPDATE_REQUEST')
            ORDER BY id DESC
            LIMIT 20
        """, (job_id,)).fetchall()
        communication_event_count = db.execute("""
            SELECT COUNT(*) AS c
            FROM email_events
            WHERE job_id = ?
              AND event_type IN ('READINESS_REQUEST', 'REMINDER', 'CLIENT_REPORT', 'FIELD_UPDATE_REQUEST')
        """, (job_id,)).fetchone()["c"]
        field_progress_count = db.execute("SELECT COUNT(*) AS c FROM field_progress_entries WHERE job_id = ?", (job_id,)).fetchone()["c"]
        field_progress_day_count = db.execute("SELECT COUNT(DISTINCT work_date) AS c FROM field_progress_entries WHERE job_id = ? AND entry_type = 'DAILY_PROGRESS'", (job_id,)).fetchone()["c"]
        project_documents = []
        if job["project_id"]:
            project_documents = db.execute("""
                SELECT *
                FROM project_documents
                WHERE project_id = ?
                ORDER BY id DESC
                LIMIT 100
            """, (job["project_id"],)).fetchall()
        client_documents = []
        if job["client_id"]:
            client_documents = db.execute("""
                SELECT *
                FROM client_documents
                WHERE client_id = ?
                ORDER BY id DESC
                LIMIT 100
            """, (job["client_id"],)).fetchall()

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
        assigned_team = db.execute("SELECT * FROM teams WHERE id = ?", (job["team_id"],)).fetchone() if job["team_id"] else None
        job_owner = db.execute("SELECT id, full_name, username FROM users WHERE id = ?", (job["owner_user_id"],)).fetchone() if job["owner_user_id"] else None
        all_crew_conflicts, _crew_conflict_group_count = get_active_crew_conflicts(db, {job_id})
        crew_conflicts = all_crew_conflicts.get(job_id, [])
        all_crew_unavailability, _crew_unavailability_group_count = get_active_crew_unavailability_issues(db)
        crew_unavailability_issues = all_crew_unavailability.get(job_id, [])
        assigned_crew_records = db.execute("""
            SELECT cm.*, jca.is_lead, jca.sort_order
            FROM job_crew_assignments jca
            JOIN crew_members cm ON cm.id = jca.crew_member_id
            WHERE jca.job_id = ?
            ORDER BY jca.sort_order, LOWER(cm.name), cm.id
        """, (job_id,)).fetchall()

    staffing_gap = None if job["status"] == "COMPLETED" else job_staffing_gap(job)

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
        job_documents=job_documents,
        communication_events=communication_events,
        communication_event_count=communication_event_count,
        field_progress_count=field_progress_count,
        field_progress_day_count=field_progress_day_count,
        project_documents=project_documents,
        client_documents=client_documents,
        assigned_client=assigned_client,
        assigned_project=assigned_project,
        assignment_clients=assignment_clients,
        assignment_projects=assignment_projects,
        crew_conflicts=crew_conflicts,
        crew_unavailability_issues=crew_unavailability_issues,
        assigned_crew_records=assigned_crew_records,
        staffing_gap=staffing_gap,
        assigned_team=assigned_team,
        job_owner=job_owner,
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

#!/usr/bin/env python3
"""
Greenshift Renewable Energy Solutions Ltd - website backend.

Uses ONLY Python's standard library, so there is nothing to `pip install`.
Works on Python 3.8 or newer.

What it does:
  * Serves the website from the ./public folder
  * POST /api/enquiry   -> validates the form, saves it to SQLite, emails the team
                           (and the customer, if they gave an email address)
  * GET  /api/enquiries -> staff-only list of saved enquiries (needs ADMIN_KEY)
  * GET  /api/health    -> simple "is it alive" check
"""

import hmac
import json
import mimetypes
import os
import re
import smtplib
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from contextlib import closing
from datetime import datetime, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"

ENQUIRY_TYPES = [
    "New solar installation",
    "Battery / inverter upgrade",
    "System maintenance",
    "EPC / commercial project",
    "Training enquiry",
]

MAX_BODY_BYTES = 20_000          # reject bigger requests outright
RATE_LIMIT_MAX = 10              # submissions allowed ...
RATE_LIMIT_WINDOW = 15 * 60      # ... per this many seconds, per visitor

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^[0-9+()\-.\s]+$")


# --------------------------------------------------------------------------
# Configuration (.env file)
# --------------------------------------------------------------------------
def load_env(path):
    """Tiny .env reader: KEY=VALUE per line. Real environment variables win."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def db_path():
    return os.environ.get("DB_PATH") or str(BASE_DIR / "greenshift.db")


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
def db_connect():
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(db_connect()) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS enquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT,
                type TEXT,
                message TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_enquiry(enq):
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with closing(db_connect()) as conn:
        with conn:  # commits on success
            cur = conn.execute(
                "INSERT INTO enquiries (name, phone, email, type, message, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (enq["name"], enq["phone"], enq["email"], enq["type"], enq["message"], created),
            )
            return cur.lastrowid


def list_enquiries():
    with closing(db_connect()) as conn:
        rows = conn.execute("SELECT * FROM enquiries ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
_CTRL_ONE_LINE = re.compile(r"[\x00-\x1f\x7f]")
_CTRL_KEEP_NEWLINES = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_enquiry(data):
    """Return (cleaned_dict, errors). Never trusts what the browser sent."""
    errors = []

    def text(key):
        value = data.get(key, "")
        if value is None:
            return ""
        if not isinstance(value, str):
            errors.append("Invalid value for %s." % key)
            return ""
        return value

    name = _CTRL_ONE_LINE.sub(" ", text("name")).strip()
    phone = _CTRL_ONE_LINE.sub(" ", text("phone")).strip()
    email = _CTRL_ONE_LINE.sub("", text("email")).strip()
    etype = _CTRL_ONE_LINE.sub(" ", text("type")).strip()
    message = _CTRL_KEEP_NEWLINES.sub("", text("message")).strip()

    if len(name) < 2:
        errors.append("Full name is required.")
    elif len(name) > 100:
        errors.append("Full name is too long.")

    digits = sum(ch.isdigit() for ch in phone)
    if digits < 7 or len(phone) > 30 or not PHONE_RE.match(phone):
        errors.append("A valid phone number is required.")

    if email and (len(email) > 254 or not EMAIL_RE.match(email)):
        errors.append("Email address looks invalid.")

    if etype and etype not in ENQUIRY_TYPES:
        errors.append("Invalid enquiry type.")

    if len(message) > 3000:
        errors.append("Message is too long (3000 characters maximum).")

    cleaned = {
        "name": name,
        "phone": phone,
        "email": email,
        "type": etype or "Not specified",
        "message": message,
    }
    return cleaned, errors


# --------------------------------------------------------------------------
# Email (Gmail SMTP)
# --------------------------------------------------------------------------
RESEND_URL = "https://api.resend.com/emails"


def resend_configured():
    return bool(os.environ.get("RESEND_API_KEY", "").strip())


def gmail_configured():
    return bool(os.environ.get("GMAIL_USER", "").strip() and os.environ.get("GMAIL_APP_PASSWORD", "").strip())


def email_configured():
    return resend_configured() or gmail_configured()


def build_team_message(enq, enquiry_id, sender, recipient):
    msg = EmailMessage()
    msg["From"] = "Greenshift Website <%s>" % sender
    msg["To"] = recipient
    if enq["email"]:
        msg["Reply-To"] = enq["email"]
    msg["Subject"] = "New enquiry: %s - %s" % (enq["type"], enq["name"])
    msg.set_content(
        "\n".join(
            [
                "New enquiry received on the website (#%s)" % enquiry_id,
                "",
                "Name: %s" % enq["name"],
                "Phone: %s" % enq["phone"],
                "Email: %s" % (enq["email"] or "Not provided"),
                "Enquiry type: %s" % enq["type"],
                "",
                "Site details:",
                enq["message"] or "Not provided",
            ]
        )
    )
    return msg


def build_customer_message(enq, sender):
    msg = EmailMessage()
    msg["From"] = "Greenshift Renewable Energy <%s>" % sender
    msg["To"] = enq["email"]
    msg["Subject"] = "We received your enquiry - Greenshift Renewable Energy"
    msg.set_content(
        "\n".join(
            [
                "Hi %s," % enq["name"],
                "",
                "Thank you for reaching out to Greenshift Renewable Energy Solutions Ltd.",
                "We have received your enquiry and a member of our team will contact you",
                "shortly to arrange a site survey and quotation.",
                "",
                "Summary of what you sent us:",
                "Enquiry type: %s" % enq["type"],
                "Message: %s" % (enq["message"] or "Not provided"),
                "",
                "If you need to reach us urgently, call 0706 824 9172.",
                "",
                "- Greenshift Renewable Energy Solutions Ltd",
            ]
        )
    )
    return msg


def resend_send(msg):
    """Send an EmailMessage through Resend's web API (HTTPS, port 443).

    Many hosts, including Render's free plan, block the normal email ports
    (25/465/587), so on those hosts email has to go out over HTTPS instead.
    """
    payload = {
        "from": str(msg["From"]),
        "to": [str(msg["To"])],
        "subject": str(msg["Subject"]),
        "text": msg.get_content(),
    }
    if msg["Reply-To"]:
        payload["reply_to"] = str(msg["Reply-To"])
    req = urllib.request.Request(
        RESEND_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + os.environ["RESEND_API_KEY"].strip(),
            "Content-Type": "application/json",
            # Resend sits behind a firewall that rejects Python's default User-Agent.
            "User-Agent": "greenshift-backend/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError("Resend answered %s: %s" % (exc.code, detail))


def _send_with_resend(enq, enquiry_id):
    recipient = os.environ.get("NOTIFY_EMAIL", "").strip()
    if not recipient:
        print("RESEND_API_KEY is set but NOTIFY_EMAIL is empty. Set NOTIFY_EMAIL to the email address you signed up to Resend with.")
        return False
    # Without your own verified domain, Resend only allows its test sender, and only to
    # the address you signed up with. With a verified domain, set MAIL_FROM to an address on it.
    verified_from = os.environ.get("MAIL_FROM", "").strip()
    resend_send(build_team_message(enq, enquiry_id, verified_from or "onboarding@resend.dev", recipient))
    if enq["email"] and verified_from:
        try:
            resend_send(build_customer_message(enq, verified_from))
        except Exception as exc:  # noqa: BLE001
            print("Customer confirmation failed for enquiry #%s: %s" % (enquiry_id, exc))
    return True


def _send_with_gmail(enq, enquiry_id):
    sender = os.environ["GMAIL_USER"].strip()
    # Google shows app passwords in groups of 4 with spaces; strip them.
    password = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "").strip()
    recipient = (os.environ.get("NOTIFY_EMAIL") or sender).strip()
    team_sent = False
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
        smtp.login(sender, password)
        try:
            smtp.send_message(build_team_message(enq, enquiry_id, sender, recipient))
            team_sent = True
        except Exception as exc:  # noqa: BLE001
            print("Team notification failed for enquiry #%s: %s" % (enquiry_id, exc))
        if enq["email"]:
            try:
                smtp.send_message(build_customer_message(enq, sender))
            except Exception as exc:  # noqa: BLE001
                print("Customer confirmation failed for enquiry #%s: %s" % (enquiry_id, exc))
    return team_sent


def log_lead(enq, enquiry_id):
    """Last-resort record: if the team email did not go out, put the lead in the server log."""
    print(
        "LEAD #%s (team email NOT sent) | %s | %s | %s | %s | %s"
        % (
            enquiry_id,
            enq["name"],
            enq["phone"],
            enq["email"] or "-",
            enq["type"],
            enq["message"].replace("\n", " / ") or "-",
        )
    )


def send_enquiry_emails(enq, enquiry_id):
    """Runs in a background thread. Never raises: the enquiry is already saved."""
    team_sent = False
    try:
        if resend_configured():
            team_sent = _send_with_resend(enq, enquiry_id)
        elif gmail_configured():
            team_sent = _send_with_gmail(enq, enquiry_id)
        else:
            print("Email not configured - enquiry #%s was saved to the database only." % enquiry_id)
    except Exception as exc:  # noqa: BLE001
        print("Email send failed for enquiry #%s: %s" % (enquiry_id, exc))
    if not team_sent:
        log_lead(enq, enquiry_id)


# --------------------------------------------------------------------------
# Rate limiting (simple in-memory, per visitor)
# --------------------------------------------------------------------------
_hits = defaultdict(deque)
_hits_lock = threading.Lock()


def is_rate_limited(ip):
    now = time.time()
    with _hits_lock:
        if len(_hits) > 5000:  # keep memory bounded
            for key in [k for k, q in _hits.items() if not q or now - q[-1] > RATE_LIMIT_WINDOW]:
                del _hits[key]
        q = _hits[ip]
        while q and now - q[0] > RATE_LIMIT_WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT_MAX:
            return True
        q.append(now)
        return False


# --------------------------------------------------------------------------
# HTTP server
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "Greenshift"
    sys_version = ""

    # ---- helpers ----
    def client_ip(self):
        # Behind a host's proxy (e.g. Render) the real visitor is the LAST entry
        # the proxy appended to X-Forwarded-For.
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()
        return self.client_address[0]

    def send_bytes(self, status, body, content_type, head_only=False, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def send_json(self, status, payload, head_only=False, extra=None):
        body = json.dumps(payload).encode("utf-8")
        self.send_bytes(status, body, "application/json; charset=utf-8", head_only, extra)

    # ---- routing ----
    def do_GET(self):
        self.handle_get(head_only=False)

    def do_HEAD(self):
        self.handle_get(head_only=True)

    def handle_get(self, head_only):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.send_json(200, {"ok": True}, head_only)
        if path == "/api/enquiries":
            return self.handle_list(head_only)
        if path == "/api/enquiry":
            return self.send_json(405, {"ok": False, "errors": ["Use POST."]}, head_only, {"Allow": "POST"})
        self.serve_static(path, head_only)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/enquiry":
            return self.send_json(404, {"ok": False, "errors": ["Not found."]})
        self.handle_enquiry()

    def _method_not_allowed(self):
        self.send_json(405, {"ok": False, "errors": ["Method not allowed."]}, extra={"Allow": "GET, HEAD, POST"})

    do_PUT = do_DELETE = do_PATCH = _method_not_allowed

    # ---- endpoints ----
    def handle_enquiry(self):
        if is_rate_limited(self.client_ip()):
            return self.send_json(
                429,
                {"ok": False, "errors": ["Too many enquiries from this device. Please try again later or call us directly."]},
            )

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0:
            return self.send_json(400, {"ok": False, "errors": ["Invalid request."]})
        if length > MAX_BODY_BYTES:
            return self.send_json(413, {"ok": False, "errors": ["Request too large."]})

        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self.send_json(400, {"ok": False, "errors": ["Invalid request."]})
        if not isinstance(data, dict):
            return self.send_json(400, {"ok": False, "errors": ["Invalid request."]})

        enq, errors = clean_enquiry(data)
        if errors:
            return self.send_json(400, {"ok": False, "errors": errors})

        try:
            enquiry_id = save_enquiry(enq)
        except sqlite3.Error as exc:
            print("Database error:", exc)
            return self.send_json(500, {"ok": False, "errors": ["Could not save your enquiry. Please call us directly."]})

        # Email in the background so the visitor isn't kept waiting.
        threading.Thread(target=send_enquiry_emails, args=(enq, enquiry_id), daemon=True).start()
        self.send_json(200, {"ok": True, "message": "Enquiry received - we will contact you shortly."})

    def handle_list(self, head_only):
        expected = os.environ.get("ADMIN_KEY", "")
        supplied = self.headers.get("x-admin-key", "")
        if not expected or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
            return self.send_json(401, {"ok": False, "error": "Unauthorized"}, head_only)
        rows = list_enquiries()
        self.send_json(200, {"ok": True, "count": len(rows), "enquiries": rows}, head_only)

    def serve_static(self, url_path, head_only):
        rel = unquote(url_path).lstrip("/") or "index.html"
        try:
            target = (PUBLIC_DIR / rel).resolve()
        except (OSError, ValueError):
            target = None
        public_root = PUBLIC_DIR.resolve()
        if target is None or public_root not in target.parents or not target.is_file():
            return self.send_bytes(404, b"Not found", "text/plain; charset=utf-8", head_only)
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_bytes(200, target.read_bytes(), ctype, head_only)

    def log_message(self, fmt, *args):
        sys.stdout.write("%s - %s\n" % (self.client_ip(), fmt % args))


def main():
    hosted = "PORT" in os.environ  # hosting services set PORT themselves
    load_env(BASE_DIR / ".env")
    init_db()

    port = int(os.environ.get("PORT", "3000"))
    host = os.environ.get("HOST") or ("0.0.0.0" if hosted else "127.0.0.1")

    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        print("Could not start on port %d: %s" % (port, exc))
        print("Another program may already be using that port. Add PORT=3001 to your .env file and try again.")
        sys.exit(1)

    print("Greenshift backend running on http://localhost:%d" % port)
    if not email_configured():
        print("NOTE: no email settings found (RESEND_API_KEY, or GMAIL_USER + GMAIL_APP_PASSWORD) - enquiries will be saved but no emails sent.")
    elif resend_configured() and not os.environ.get("NOTIFY_EMAIL"):
        print("NOTE: RESEND_API_KEY is set but NOTIFY_EMAIL is not - no emails can be sent until you set it.")
    if not os.environ.get("ADMIN_KEY"):
        print("NOTE: ADMIN_KEY not set - the /api/enquiries staff view is disabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

# cd ".\CatalystSolutionsDemo\Catalyst Solutions Demo"; python app.py
import hashlib
import io
import hmac
import json
import os
import secrets
import smtplib
import time
import click
from email.message import EmailMessage
from functools import wraps
from datetime import date
from uuid import uuid4

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# Local settings (database password etc.) can live in a .env file next to this one.
# It is never committed; on Vercel the same names are set as Environment Variables.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

import database
from user_database import DuplicateEmailError, UserDatabase

# CSS, JavaScript and images live in public/static: Vercel serves the public folder straight
# from its CDN at /static/..., and Flask serves the same folder when you run it yourself.
app = Flask(__name__, instance_path=os.environ.get("APP_INSTANCE_PATH"),
            static_folder="public/static", static_url_path="/static")
# Vercel refuses requests over 4.5 MB, so uploads are capped at 4 MB per request
# (one file, or several files on the document page together).
MAX_UPLOAD_MB = 4
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024 + 256 * 1024   # + room for the form fields
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "").lower() == "true"

user_database = UserDatabase()
DEMO_EMAIL = "demo@buffbison.com"
DEMO_PASSWORD = "Buffbison123"
DEMO_NAME = "Demo Employee"
DEMO_CLIENT_EMAIL = "demo.client@buffbison.com"
DEMO_CLIENT_PASSWORD = "ClientDemo123!"
DEMO_CLIENT_NAME = "Demo Client"
DEMO_SUBCONTRACTOR_EMAIL = "demo.subcontractor@buffbison.com"
DEMO_SUBCONTRACTOR_PASSWORD = "SubcontractorDemo123!"
DEMO_SUBCONTRACTOR_NAME = "Demo Subcontractor"
ALLOWED_DOCUMENT_EXTENSIONS = {"csv", "doc", "docx", "pdf", "txt", "xls", "xlsx"}
ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
DOCUMENT_TYPES = ("Estimate", "Invoice", "Receipt", "Contract", "Other")
ROLES = ("employee", "subcontractor", "client")

# On Vercel (the VERCEL variable is set there) the files can't be written and there is no
# instance folder, so the secret key must come from the FLASK_SECRET_KEY environment variable.
# On your own computer a random key is created once in instance/.secret_key if it isn't set.
ON_VERCEL = bool(os.environ.get("VERCEL"))
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "").strip()
if not app.secret_key:
    if ON_VERCEL:
        raise RuntimeError("Set FLASK_SECRET_KEY in Vercel (Project Settings -> Environment Variables).")
    os.makedirs(app.instance_path, exist_ok=True)
    secret_key_file = os.path.join(app.instance_path, ".secret_key")
    try:
        with open(secret_key_file, "x", encoding="utf-8") as secret_file:
            secret_file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    with open(secret_key_file, encoding="utf-8") as secret_file:
        app.secret_key = secret_file.read().strip()

if ON_VERCEL:
    # Vercel serves the site over https and passes the real address in X-Forwarded-* headers;
    # trust them so links in emails (password reset) are https://your-site, and cookies are secure.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "true").lower() != "false"


def initialize_user_database():
    user_database.initialize([
        (DEMO_EMAIL, DEMO_NAME, generate_password_hash(DEMO_PASSWORD), "employee"),
        (DEMO_CLIENT_EMAIL, DEMO_CLIENT_NAME, generate_password_hash(DEMO_CLIENT_PASSWORD), "client"),
        (DEMO_SUBCONTRACTOR_EMAIL, DEMO_SUBCONTRACTOR_NAME,
         generate_password_hash(DEMO_SUBCONTRACTOR_PASSWORD), "subcontractor"),
    ])


# Everything (logins, projects, estimates, invoices, ...) lives in one MySQL database.
# 1) create any missing tables from schema.sql, 2) add the demo logins,
# 3) load the sample data the first time. See database.py.
database.init_app(app)
initialize_user_database()
database.seed_if_empty()

# JSON endpoints used by the Estimates and Invoices pages (see api.py).
from api import api  # noqa: E402  (imported here, after the database is set up)
app.register_blueprint(api)


# ---------- Template formatting helpers ----------
@app.context_processor
def demo_photo_assets():
    return {"demo_photo_images": {
        "Flooring Installation": "images/demo/flooring.png",
        "Bathroom Before Renovation": "images/demo/bathroom.png",
        "Roof Installation": "images/demo/roof.png",
        "Kitchen Progress": "images/demo/kitchen.png",
    }}


app.add_template_filter(database.format_phone, "phone")
# Usage in templates: {{ project.budget_amount|currency }}, {{ project.due_date|short_date }},
# <span class="status {{ project.status|status_class }}">

@app.template_filter("currency")
def format_currency(value):
    return f"${float(value or 0):,.0f}"


@app.template_filter("short_date")
def format_short_date(value):
    if not value:
        return "—"
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%b %d, %Y")
    except ValueError:
        return value


@app.template_filter("status_class")
def project_status_class(status):
    return {
        "In Progress": "progress",
        "Planning": "planning",
        "On Hold": "hold",
        "Completed": "completed",
        # tasks, invoices, estimates and subcontractor invoices (project page tabs)
        "Not Started": "pending",
        "Paid": "completed",
        "Approved": "completed",
        "Converted": "completed",
        "Sent": "progress",
        "Pending Approval": "progress",
        "Rejected": "hold",
        "Active": "completed",
        "Inactive": "planning",
    }.get(status, "planning")


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if session.get("role") not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


@app.before_request
def protect_post_requests():
    # Forms send the token as a hidden "csrf_token" field; the JavaScript on the
    # Estimates/Invoices pages sends it in an "X-CSRF-Token" header instead.
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        submitted_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        session_token = session.get("csrf_token", "")
        if not session_token or not secrets.compare_digest(submitted_token, session_token):
            if request.path.startswith("/api/"):
                return jsonify(error="Your session expired. Refresh the page and try again."), 400
            abort(400, description="Invalid or missing CSRF token.")


@app.context_processor
def provide_template_security_helpers():
    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    return {"csrf_token": csrf_token, "current_role": session.get("role")}


@app.cli.command("create-user")
def create_user():
    """Create an account with a securely hashed password."""
    import click

    email = click.prompt("Email").strip().lower()
    name = click.prompt("Display name").strip()
    role = click.prompt("Role", type=click.Choice(ROLES, case_sensitive=False)).lower()
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)

    if "@" not in email or any(character.isspace() for character in email):
        raise click.ClickException("Enter a valid email address.")
    if not name or len(password) < 12:
        raise click.ClickException("Display name is required and password must be at least 12 characters.")

    try:
        user_database.create_user(email, name, generate_password_hash(password), role)
    except DuplicateEmailError as error:
        raise click.ClickException("An account with that email already exists.") from error

    click.echo(f"Created {role} account for {email}.")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = user_database.find_by_email(email)

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["email"] = user["email"]
            session["user"] = user["name"]
            session["role"] = user["role"]
            destination = {
                "employee": "dashboard",
                "client": "dashboard",
                "subcontractor": "dashboard",
            }[user["role"]]
            return redirect(url_for(destination))

        error = "Invalid email address or password."

    return render_template("login.html", error=error)


# ---------- Forgot password (step 12) ----------
# The reset link carries a signed token (itsdangerous, part of Flask) holding the user id and a
# fingerprint of their current password hash. It expires after RESET_LINK_MINUTES, and it stops
# working as soon as the password changes, so each link can be used once. No table is needed,
# so the reset links need no extra table.
#
# Email is sent through SMTP when MAIL_SERVER is set (see BACKEND.md). Without it, the link is
# printed in the terminal running the app, which is enough for local demos.
RESET_LINK_MINUTES = 30
RESET_EMAIL_COOLDOWN_SECONDS = 60
_recent_reset_emails = {}  # email -> time of the last link sent (stops one inbox being flooded)


def _reset_serializer():
    return URLSafeTimedSerializer(app.secret_key, salt="password-reset")


def _password_fingerprint(password_hash):
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:24]


def make_password_reset_token(user):
    return _reset_serializer().dumps({"user_id": user["id"], "pw": _password_fingerprint(user["password_hash"])})


def user_for_reset_token(token):
    """Returns (user, None) for a valid link, or (None, reason) when it can't be used."""
    try:
        data = _reset_serializer().loads(token, max_age=RESET_LINK_MINUTES * 60)
    except SignatureExpired:
        return None, "This reset link has expired."
    except BadSignature:
        return None, "This reset link is not valid."
    user = user_database.find_by_id(data.get("user_id")) if isinstance(data, dict) else None
    if user is None or not hmac.compare_digest(_password_fingerprint(user["password_hash"]), str(data.get("pw", ""))):
        return None, "This reset link has already been used."
    return user, None


def send_password_reset(user, link):
    """Email the reset link, or print it in the terminal when no mail server is configured."""
    body = (
        f"Hi {user['name']},\n\n"
        "Someone asked to reset the password for your Buff Bison Construction portal account.\n"
        f"Open this link within {RESET_LINK_MINUTES} minutes to choose a new password:\n\n"
        f"{link}\n\n"
        "If you didn't ask for this, you can ignore this email; your password stays the same.\n"
    )
    server = os.environ.get("MAIL_SERVER", "").strip()
    if not server:
        print(f"\n[password reset] No MAIL_SERVER set, so the email was not sent.\n"
              f"[password reset] Link for {user['email']}: {link}\n", flush=True)
        return
    message = EmailMessage()
    message["Subject"] = "Reset your Buff Bison password"
    message["From"] = os.environ.get("MAIL_FROM") or os.environ.get("MAIL_USERNAME") or "no-reply@buffbison.com"
    message["To"] = user["email"]
    message.set_content(body)
    try:
        with smtplib.SMTP(server, int(os.environ.get("MAIL_PORT", "587")), timeout=15) as smtp:
            if os.environ.get("MAIL_USE_TLS", "true").lower() != "false":
                smtp.starttls()
            if os.environ.get("MAIL_USERNAME"):
                smtp.login(os.environ["MAIL_USERNAME"], os.environ.get("MAIL_PASSWORD", ""))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        # The page still shows the usual message, so it never reveals whether the account exists.
        app.logger.error("Password reset email to %s failed: %s", user["email"], error)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    message = None
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            error = "Enter your email address."
        elif len(email) > 254 or "@" not in email:
            error = "Enter a valid email address."
        else:
            user = user_database.find_by_email(email)
            last_sent = _recent_reset_emails.get(email, 0)
            if user and time.monotonic() - last_sent >= RESET_EMAIL_COOLDOWN_SECONDS:
                _recent_reset_emails[email] = time.monotonic()
                link = url_for("reset_password", token=make_password_reset_token(user), _external=True)
                send_password_reset(user, link)
            # Same message either way, so this page can't be used to find out who has an account.
            message = (
                "If an account uses that email, we've sent it a link to reset the password. "
                f"The link works for {RESET_LINK_MINUTES} minutes."
            )

    return render_template("forgot_password.html", message=message, error=error)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user, problem = user_for_reset_token(token)
    if user is None:
        return render_template("reset_password.html", problem=problem, error=None), 400

    error = None
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirmation = request.form.get("confirm_password", "")
        if not 12 <= len(new_password) <= 128:
            error = "Your new password must be between 12 and 128 characters."
        elif new_password != confirmation:
            error = "The new passwords do not match."
        elif check_password_hash(user["password_hash"], new_password):
            error = "Choose a new password different from your current password."
        elif not user_database.update_password(user["id"], user["password_hash"], generate_password_hash(new_password)):
            return render_template("reset_password.html", problem="This reset link has already been used.", error=None), 400
        else:
            session.clear()
            flash("Your password has been reset. Sign in with your new password.", "password_reset")
            return redirect(url_for("login"))

    return render_template("reset_password.html", problem=None, error=error, email=user["email"])


@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/dashboard")
@role_required(*ROLES)
def dashboard():
    if session["role"] == "subcontractor":
        projects = database.portal_projects(session["user_id"], "subcontractor")
        project_ids = {project["project_id"] for project in projects}
        me = database.subcontractor_for_user(session["user_id"])
        invoices = database.get_subcontractor_invoices(me["subcontractor_id"]) if me else []
        today = database.local_today().isoformat()
        tasks = [dict(task, overdue=task["due_date"] < today)
                 for task in database.get_open_tasks() if task["project_id"] in project_ids]
        return render_template(
            "subcontractor.dashboard.html",
            user_name=session["user"],
            linked=me is not None,
            projects=projects,
            tasks=tasks,
            pending_invoices=[i for i in invoices if i["status"] == "Pending Approval"],
            invoices=invoices,
        )
    if session["role"] == "client":
        estimates = database.client_estimates(session["user_id"])
        invoices = database.client_invoices(session["user_id"])
        today = database.local_today().isoformat()
        open_invoices = [dict(i, overdue=i["due_date"] < today) for i in invoices if i["status"] == "Unpaid"]
        return render_template(
            "client.dashboard.html",
            user_name=session["user"],
            client=database.client_for_user(session["user_id"]),
            projects=database.portal_projects(session["user_id"], "client"),
            pending_estimates=[e for e in estimates if e["status"] == "Sent"],
            open_invoices=open_invoices,
            open_total=sum(float(i["total_amount"]) for i in open_invoices),
        )
    dashboard_data = database.get_dashboard()
    return render_template(
        "dashboard.html",
        user_name=session["user"],
        stats=dashboard_data["stats"],
        projects=dashboard_data["projects"],
        activity=dashboard_data["activity"],
        tasks=get_upcoming_tasks(),
    )


def get_upcoming_tasks(limit=6):
    """Open tasks for the Dashboard, soonest first (overdue ones on top).
    Same tasks as the Schedule page (database)."""
    today = database.local_today().isoformat()
    open_tasks = database.get_open_tasks()   # already sorted by due date
    return {
        "count": len(open_tasks),
        "items": [{**task, "overdue": task["due_date"] < today} for task in open_tasks[:limit]],
    }


# ---------- PROJECTS ----------

@app.route("/projects")
@role_required(*ROLES)
def projects():
    if session["role"] in ("subcontractor", "client"):
        return render_template(
            "my_projects.html",
            user_name=session["user"],
            projects=database.portal_projects(session["user_id"], session["role"]),
        )
    return render_template(
        "projects.html",
        user_name=session["user"],
        projects=database.get_projects(),
        counts=database.get_project_counts(),
    )

@app.route("/estimates")
@role_required("employee")
def estimates():
    return render_template("estimates.html", user_name=session["user"])

@app.route("/invoices")
@role_required("employee")
def invoices():
    return render_template("invoices.html", user_name=session["user"])


@app.route("/job-costs")
@role_required("employee")
def job_costs():
    return render_template(
        "job_costs.html",
        user_name=session["user"],
        job_cost_data=database.get_job_cost_data(),
    )


@app.route("/schedule")
@role_required("employee")
def schedule():
    return render_template(
        "schedule.html",
        user_name=session["user"],
        schedule_data=database.get_schedule_data(),
    )


# ---------- Client portal ----------
# Clients only ever see records for their own client account (database.client_*).

@app.route("/client/my-projects")
@role_required("client")
def client_my_projects():
    return render_template(
        "my_projects.html",
        user_name=session["user"],
        projects=database.portal_projects(session["user_id"], "client"),
    )


@app.route("/client/estimates")
@role_required("client")
def client_estimates():
    return render_template(
        "client_records.html",
        user_name=session["user"],
        active_page="estimates",
        kind="client_estimates",
        page_title="Estimates",
        page_description="Review the estimates Buff Bison has sent you and approve or decline them.",
        records=database.client_estimates(session["user_id"]),
        linked=database.client_for_user(session["user_id"]) is not None,
    )


@app.route("/client/estimates/<int:estimate_id>/decision", methods=["POST"])
@role_required("client")
def client_estimate_decision(estimate_id):
    decision = request.form.get("decision")
    if decision not in ("approve", "reject"):
        abort(400)
    try:
        database.client_decide_estimate(session["user_id"], estimate_id, decision)
    except database.RuleError as error:
        if error.status_code == 404:
            abort(404)
        flash(error.message)
    else:
        flash("Thank you. The estimate was approved." if decision == "approve" else "The estimate was declined.")
    return redirect(url_for("client_estimates"))


@app.route("/client/invoices")
@role_required("client")
def client_invoices():
    today = database.local_today().isoformat()
    records = [dict(i, overdue=i["status"] == "Unpaid" and i["due_date"] < today)
               for i in database.client_invoices(session["user_id"])]
    return render_template(
        "client_records.html",
        user_name=session["user"],
        active_page="invoices",
        kind="client_invoices",
        page_title="Invoices",
        page_description="Invoices for your projects. Open one to view or print it.",
        records=records,
        linked=database.client_for_user(session["user_id"]) is not None,
    )


@app.route("/client/invoices/<int:invoice_id>")
@role_required("client")
def client_invoice(invoice_id):
    invoice = database.client_invoice(session["user_id"], invoice_id)
    if invoice is None:
        abort(404)
    return render_template("portal_invoice.html", user_name=session["user"], invoice=invoice,
                           overdue=invoice["status"] == "Unpaid" and invoice["due_date"] < database.local_today().isoformat())


# ---------- Subcontractor portal ----------
# Subcontractors only see projects they are assigned to and their own invoices.
SUB_INVOICE_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


@app.route("/subcontractor/invoices", methods=["GET", "POST"])
@role_required("subcontractor")
def subcontractor_invoices():
    me = database.subcontractor_for_user(session["user_id"])
    projects = database.portal_projects(session["user_id"], "subcontractor")
    errors, values = [], {}
    if request.method == "POST" and me is not None:
        values = request.form
        project_id, project_error = _chosen_project(request.form, projects, required=True)
        number = request.form.get("invoice_number", "").strip()
        description = request.form.get("description", "").strip()
        if project_error:
            errors.append(project_error)
        if not number or len(number) > 50:
            errors.append("Enter your invoice number (up to 50 characters).")
        if len(description) > 300:
            errors.append("Description must be 300 characters or fewer.")
        try:
            amount = round(float(request.form.get("amount", "")), 2)
            if not 0 < amount <= 10_000_000:
                raise ValueError
        except ValueError:
            errors.append("Enter an amount greater than $0.00.")
            amount = 0
        data = {"invoice_number": number, "description": description, "amount": amount}
        upload = request.files.get("invoice_file")
        if not errors and upload and upload.filename:
            try:
                data["original_filename"], data["file_path"] = _save_upload(upload, SUB_INVOICE_EXTENSIONS)
            except ValueError:
                errors.append("Attach a PDF, JPG or PNG file (or leave it empty).")
        if not errors:
            assignment = database.subcontractor_assignment(session["user_id"], project_id)
            database.submit_subcontractor_invoice(assignment["assignment_id"], data)
            flash(f"Invoice {number} was submitted for approval.")
            return redirect(url_for("subcontractor_invoices"))
    return render_template(
        "client_records.html",
        user_name=session["user"],
        active_page="invoices",
        kind="subcontractor_invoices",
        page_title="My Invoices",
        page_description="Submit invoices for your assigned projects and track their approval.",
        records=database.get_subcontractor_invoices(me["subcontractor_id"]) if me else [],
        linked=me is not None,
        projects=projects,
        errors=errors,
        values=values,
    )


@app.route("/subcontractor-invoices/<int:sub_invoice_id>/file")
@role_required("employee", "subcontractor")
def subcontractor_invoice_file(sub_invoice_id):
    invoice = database.get_subcontractor_invoice(sub_invoice_id)
    if invoice is None or not invoice["file_path"]:
        abort(404)
    if session["role"] == "subcontractor":
        me = database.subcontractor_for_user(session["user_id"])
        if me is None or me["subcontractor_id"] != invoice["subcontractor_id"]:
            abort(404)
    return _send_stored_file(invoice["file_path"], download_name=invoice["original_filename"] or invoice["file_path"])


@app.route("/subcontractor-invoices/<int:sub_invoice_id>/review", methods=["POST"])
@role_required("employee")
def review_subcontractor_invoice(sub_invoice_id):
    try:
        invoice = database.review_subcontractor_invoice(
            sub_invoice_id, request.form.get("status", ""), session["user_id"])
        flash(f"Invoice {invoice['invoice_number']} from {invoice['company_name']} marked {invoice['status'].lower()}.")
    except database.RuleError as error:
        flash(error.message)
    back = request.form.get("next", "")
    if back.startswith("/project/") and "//" not in back:
        return redirect(back)
    return redirect(url_for("subcontractors") + "#sub-invoices")


@app.route("/project/<int:project_id>/tasks/<int:task_id>/status", methods=["POST"])
@role_required("subcontractor")
def subcontractor_task_status(project_id, task_id):
    try:
        task = database.subcontractor_update_task(session["user_id"], task_id, request.form.get("status", ""))
        flash(f"Updated \"{task['name']}\" to {task['status']}.")
    except database.RuleError as error:
        if error.status_code == 404:
            abort(404)
        flash(error.message)
    return redirect(url_for("project_details", project_id=project_id))


@app.route("/new-project", methods=["GET", "POST"])
@role_required("employee")
def new_project():
    managers = database.get_project_managers()
    errors = []
    form = request.form
    selected_client = None
    if request.args.get("client"):
        selected_client = database.get_client(request.args.get("client", type=int))
        if selected_client is None:
            abort(404)
        form = dict(request.form)
        form.update(client_name=selected_client['name'], client_email=selected_client['email'] or '',
                    client_phone=selected_client['phone'] or '')

    if request.method == "POST":
        data, errors = validate_new_project(form, managers)
        if not errors:
            database.create_project(data)
            if selected_client:
                return redirect(url_for('new_client', client_id=selected_client['client_id']))
            return redirect(url_for("projects"))

    return render_template(
        "new_project.html",
        user_name=session["user"],
        managers=managers,
        statuses=database.PROJECT_STATUSES,
        errors=errors,
        form=form,
        selected_client=selected_client,
    )


PROJECT_TYPES = ("Kitchen Remodel", "Bathroom Remodel", "Roofing", "Home Addition", "Full Renovation", "Other")


def validate_new_project(form, managers, editing=False):
    """Check the New Project / Edit Project form. Returns (clean data, list of error messages).
    When editing, the client stays as it is (managed on the Clients page) and progress can be set."""
    errors = []
    data = {
        "name": form.get("project_name", "").strip(),
        "project_type": form.get("project_type", "").strip(),
        "description": form.get("description", "").strip(),
        "client_name": form.get("client_name", "").strip(),
        "client_email": form.get("client_email", "").strip(),
        "client_phone": form.get("client_phone", "").strip(),
        "address": form.get("address", "").strip(),
        "status": form.get("status", "Planning"),
        "start_date": form.get("start_date", ""),
        "due_date": form.get("end_date", ""),
    }

    if not data["name"]:
        errors.append("Project name is required.")
    if data["project_type"] not in PROJECT_TYPES:
        errors.append("Choose a project type.")
    if not data["client_name"] and not editing:
        errors.append("Client name is required.")
    if editing:
        try:
            data["progress"] = int(form.get("progress", "0") or 0)
            if not 0 <= data["progress"] <= 100:
                raise ValueError
        except ValueError:
            errors.append("Progress must be a whole number from 0 to 100.")
    if not data["address"] and not editing:
        errors.append("Address is required.")
    if data["status"] not in database.PROJECT_STATUSES:
        errors.append("Choose a valid status.")

    manager_ids = {str(manager["id"]) for manager in managers}
    if form.get("manager", "") not in manager_ids:
        errors.append("Choose a project manager.")
    else:
        data["manager_id"] = int(form["manager"])

    budget_text = form.get("budget", "").strip()
    try:
        data["budget"] = round(float(budget_text), 2) if budget_text else 0.0
        if data["budget"] < 0:
            raise ValueError
    except ValueError:
        errors.append("Budget must be a number of 0 or more.")

    for field, label in (("start_date", "Start date"), ("due_date", "End date")):
        if data[field]:
            try:
                date.fromisoformat(data[field])
            except ValueError:
                errors.append(f"{label} is not a valid date.")
    if data["start_date"] and data["due_date"] and data["due_date"] < data["start_date"]:
        errors.append("End date can't be before the start date.")

    return data, errors


@app.route("/project/<int:project_id>")
@role_required(*ROLES)
def project_details(project_id):
    if session["role"] in ("subcontractor", "client"):
        project = database.portal_project(project_id, session["user_id"], session["role"])
        if project is None:
            abort(404)
        today = database.local_today().isoformat()
        context = {"project": project, "tasks": [dict(t, overdue=t["status"] != "Completed" and t["due_date"] < today)
                                                 for t in database.get_tasks(project_id)]}
        if session["role"] == "client":
            context["estimates"] = [e for e in database.client_estimates(session["user_id"])
                                    if e.get("project_id") == project_id]
            context["invoices"] = [dict(i, overdue=i["status"] == "Unpaid" and i["due_date"] < today)
                                   for i in database.client_invoices(session["user_id"]) if i["project_id"] == project_id]
        else:
            me = database.subcontractor_for_user(session["user_id"])
            context["invoices"] = database.get_subcontractor_invoices(me["subcontractor_id"], project_id) if me else []
            context["task_statuses"] = database.TASK_STATUSES
        return render_template("client_assignment.html", user_name=session["user"], **context)
    project = database.get_project(project_id)
    if project is None:
        abort(404)
    # Employee view: every tab is filled from the database (step 9).
    today = database.local_today().isoformat()
    tasks = [dict(t, overdue=t["status"] != "Completed" and t["due_date"] < today)
             for t in database.get_tasks(project_id)]
    upcoming = sorted((t for t in tasks if t["status"] != "Completed"), key=lambda t: t["due_date"])[:4]
    invoices = [dict(i, overdue=i["status"] == "Unpaid" and i["due_date"] < today)
                for i in database.get_invoices() if i["project_id"] == project_id]
    estimate = None
    if project["estimate_id"]:
        try:
            estimate = database.get_estimate(project["estimate_id"])
        except database.RuleError:
            estimate = None
    tab = request.args.get("tab", "overview")
    return render_template(
        "project_details.html",
        user_name=session["user"],
        project=project,
        tasks=tasks,
        upcoming_tasks=upcoming,
        costs=database.get_project_costs(project_id),
        invoices=invoices,
        invoice_totals={
            "billed": sum(i["total_amount"] for i in invoices if i["status"] != "Draft"),
            "paid": sum(i["total_amount"] for i in invoices if i["status"] == "Paid"),
            "unpaid": sum(i["total_amount"] for i in invoices if i["status"] == "Unpaid"),
        },
        documents=database.get_documents(session["user_id"], session["role"], project_id),
        photos=database.get_photos(session["user_id"], session["role"], project_id),
        assignments=database.get_project_assignments(project_id),
        sub_invoices=database.get_subcontractor_invoices(project_id=project_id),
        transitions=database.SUB_INVOICE_TRANSITIONS,
        estimate=estimate,
        activity=database.get_project_activity(project_id),
        active_tab=tab if tab in PROJECT_TABS else "overview",
    )


PROJECT_TABS = ("overview", "costs", "invoices", "documents", "photos", "schedule", "subcontractors")


@app.route("/project/<int:project_id>/edit", methods=["GET", "POST"])
@role_required("employee")
def edit_project(project_id):
    project = database.get_project(project_id)
    if project is None:
        abort(404)
    managers = database.get_project_managers()
    errors = []
    if request.method == "POST":
        form = request.form
        data, errors = validate_new_project(form, managers, editing=True)
        if not errors:
            database.update_project(project_id, data)
            flash("Project updated.")
            return redirect(url_for("project_details", project_id=project_id))
    else:
        form = {
            "project_name": project["name"], "project_type": project["project_type"] or "",
            "description": project["description"] or "", "client_name": project["client_name"],
            "address": project["address"] or "", "manager": str(project["project_manager_id"] or ""),
            "start_date": project["start_date"] or "", "end_date": project["due_date"] or "",
            "budget": f"{float(project['budget_amount'] or 0):.2f}", "status": project["status"],
            "progress": str(project["progress_percent"]),
        }
    return render_template(
        "new_project.html",
        user_name=session["user"],
        managers=managers,
        statuses=database.PROJECT_STATUSES,
        errors=errors,
        form=form,
        project=project,
    )


@app.route("/search")
@role_required("employee")
def search():
    text = request.args.get("q", "").strip()[:100]
    results = database.search_everything(text) if text else None
    return render_template(
        "search.html",
        user_name=session["user"],
        query=text,
        results=results,
        total=sum(len(rows) for rows in results.values()) if results else 0,
    )


@app.route("/logout", methods=["POST"])
@role_required(*ROLES)
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Clients and subcontractors (employee directory) ----------

def _directory_text(form, key, label, errors, required=False, limit=200):
    value = form.get(key, "").strip()
    if required and not value:
        errors.append(f"{label} is required.")
    elif len(value) > limit:
        errors.append(f"{label} must be {limit} characters or fewer.")
    return value


def _check_email(value, label, errors, required=False):
    if not value:
        if required:
            errors.append(f"{label} is required.")
    elif "@" not in value or "." not in value.split("@")[-1] or " " in value:
        errors.append(f"{label} doesn't look like a valid email address.")


@app.route("/subcontractors")
@role_required("employee")
def subcontractors():
    return render_template("subcontractors.html", user_name=session["user"],
                           subcontractors=database.get_subcontractors(),
                           sub_invoices=database.get_subcontractor_invoices(),
                           transitions=database.SUB_INVOICE_TRANSITIONS)


@app.route("/clients/<int:client_id>/delete", methods=["POST"])
@role_required("employee")
def delete_client(client_id):
    try:
        database.delete_client(client_id)
    except database.RuleError as error:
        if error.status_code == 404:
            abort(404)
        flash(error.message)
    else:
        flash("Client deleted. Their login account was kept.")
    return redirect(url_for("clients"))


@app.route("/subcontractors/<int:subcontractor_id>/delete", methods=["POST"])
@role_required("employee")
def delete_subcontractor(subcontractor_id):
    try:
        database.delete_subcontractor(subcontractor_id)
    except database.RuleError as error:
        if error.status_code == 404:
            abort(404)
        flash(error.message)
    else:
        flash("Subcontractor deleted. Project assignments were removed; their login account was kept.")
    return redirect(url_for("subcontractors"))


@app.route("/subcontractors/new", methods=["GET", "POST"], defaults={"subcontractor_id": None})
@app.route("/subcontractors/<int:subcontractor_id>/edit", methods=["GET", "POST"])
@role_required("employee")
def new_subcontractor(subcontractor_id):
    existing = None
    if subcontractor_id is not None:
        existing = database.get_subcontractor(subcontractor_id)
        if existing is None:
            abort(404)
    projects = database.get_project_choices()
    errors = []

    if request.method == "POST":
        form = request.form
        data = {
            "name": _directory_text(form, "full_name", "Full name", errors, required=True),
            "company": _directory_text(form, "company", "Company name", errors, required=True),
            "email": _directory_text(form, "email", "Email address", errors),
            "phone": _directory_text(form, "phone", "Phone number", errors, limit=40),
            "address": _directory_text(form, "address", "Business address", errors),
            "trade": _directory_text(form, "trade", "Trade/specialty", errors, required=True, limit=100),
            "license_number": _directory_text(form, "license", "License number", errors, limit=100),
            "status": form.get("status", "Active"),
            "notes": _directory_text(form, "notes", "Notes", errors, limit=1000),
        }
        _check_email(data["email"], "Email address", errors, required=True)
        if data["email"] and database.subcontractor_email_taken(data["email"], subcontractor_id):
            errors.append("Another subcontractor already uses that email address.")
        if data["status"] not in database.DIRECTORY_STATUSES:
            errors.append("Choose a valid status.")
        valid_ids = {project["project_id"] for project in projects}
        try:
            project_ids = {int(value) for value in form.getlist("project_ids")}
        except ValueError:
            project_ids = {0}
        if not project_ids <= valid_ids:
            errors.append("One of the selected projects doesn't exist.")
        if not errors:
            database.save_subcontractor(data, project_ids, subcontractor_id)
            return redirect(url_for("subcontractors"))
        values = dict(form)
        assigned = project_ids & valid_ids
    elif existing is not None:
        values = {"full_name": existing["contact_name"], "company": existing["company_name"],
                  "email": existing["email"], "phone": existing["phone"], "address": existing["address"],
                  "trade": existing["trade"], "license": existing["license_number"],
                  "status": existing["status"], "notes": existing["notes"]}
        assigned = set(database.get_subcontractor_project_ids(subcontractor_id))
    else:
        values, assigned = {}, set()

    return render_template("new_subcontractor.html", user_name=session["user"], errors=errors,
                           values=values, projects=projects, assigned=assigned, existing=existing)


@app.route("/clients")
@role_required("employee")
def clients():
    return render_template("clients.html", user_name=session["user"], clients=database.get_clients())


@app.route("/clients/new", methods=["GET", "POST"], defaults={"client_id": None})
@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
@role_required("employee")
def new_client(client_id):
    existing = None
    if client_id is not None:
        existing = database.get_client(client_id)
        if existing is None:
            abort(404)
    errors = []

    if request.method == "POST":
        form = request.form
        data = {
            "name": _directory_text(form, "client_name", "Client name", errors, required=True),
            "company": _directory_text(form, "company", "Company", errors),
            "email": _directory_text(form, "email", "Email address", errors),
            "phone": _directory_text(form, "phone", "Phone number", errors, limit=40),
            "address": _directory_text(form, "address", "Address", errors),
            "status": form.get("status", "Active"),
            "notes": _directory_text(form, "notes", "Notes", errors, limit=1000),
        }
        _check_email(data["email"], "Email address", errors)
        if data["name"] and database.client_name_taken(data["name"], client_id):
            errors.append("A client with that name already exists.")
        if data["status"] not in database.DIRECTORY_STATUSES:
            errors.append("Choose a valid status.")
        if not errors:
            database.save_client(data, client_id)
            return redirect(url_for("clients"))
        values = dict(form)
    elif existing is not None:
        values = {"client_name": existing["name"], "company": existing["company"], "email": existing["email"],
                  "phone": existing["phone"], "address": existing["address"], "status": existing["status"],
                  "notes": existing["notes"]}
    else:
        values = {}

    return render_template("new_client.html", user_name=session["user"], errors=errors,
                           values=values, existing=existing,
                           client_projects=database.get_client_projects(client_id) if existing else [])


@app.route("/settings")
@role_required(*ROLES)
def settings():
    return render_template("settings.html", user_name=session["user"])


@app.route("/settings/change-password", methods=["GET", "POST"])
@role_required(*ROLES)
def change_password():
    user = user_database.find_by_id(session["user_id"])
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    error = None
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirmation = request.form.get("confirm_password", "")
        if not check_password_hash(user["password_hash"], current_password):
            error = "Your current password is incorrect."
        elif not 12 <= len(new_password) <= 128:
            error = "Your new password must be between 12 and 128 characters."
        elif new_password != confirmation:
            error = "The new passwords do not match."
        elif check_password_hash(user["password_hash"], new_password):
            error = "Choose a new password different from your current password."
        elif not user_database.update_password(
            user["id"], user["password_hash"], generate_password_hash(new_password)
        ):
            error = "Your account changed while saving. Please try again."
        else:
            session.pop("csrf_token", None)
            flash("Your password has been changed successfully.", "password_success")
            return redirect(url_for("settings"))

    return render_template("change_password.html", user_name=session["user"], error=error)


# ---------- Documents and photos ----------
# Records live in the documents/photos tables (database.py); the files themselves are
# saved in the uploaded_files table. Employees see everything;
# subcontractors see their assigned projects plus anything they uploaded.

def _project_filter():
    """Optional ?project=<id> filter (used by the project page tabs)."""
    try:
        return int(request.args["project"])
    except (KeyError, ValueError):
        return None


def _save_upload(uploaded_file, allowed_extensions):
    """Validates an uploaded file and stores it in the database (uploaded_files).
    Returns (original name, stored name) or raises ValueError."""
    safe_filename = secure_filename(uploaded_file.filename or "")
    extension = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
    if not safe_filename or extension not in allowed_extensions:
        raise ValueError
    stored_filename = f"{uuid4().hex}.{extension}"
    database.save_file(stored_filename, uploaded_file.read())
    return uploaded_file.filename.strip()[-150:], stored_filename


def _send_stored_file(stored_filename, download_name=None, as_attachment=False):
    """Sends a file kept in the database (404 if it is missing)."""
    data = database.read_file(stored_filename)
    if data is None:
        abort(404)
    return send_file(io.BytesIO(data), download_name=download_name or stored_filename,
                     as_attachment=as_attachment, max_age=0)


def _chosen_project(form, projects, required):
    """Project id from the form, only if it is one this user may choose."""
    value = form.get("project_id", "")
    if not value and not required:
        return None, None
    try:
        project_id = int(value)
    except ValueError:
        return None, "Choose a project."
    if project_id not in {project["project_id"] for project in projects}:
        return None, "Choose a project."
    return project_id, None


def _remove_file(stored_filename):
    database.delete_files(stored_filename)


@app.route("/documents")
@role_required("employee", "subcontractor")
def documents():
    project_id = _project_filter()
    return render_template(
        "documents.html",
        user_name=session["user"],
        documents=database.get_documents(session["user_id"], session["role"], project_id),
        filter_project=database.get_project(project_id) if project_id else None,
    )


@app.route("/documents/upload", methods=["GET", "POST"])
@role_required("employee")
def upload_document():
    error = None
    projects = database.projects_for(session["user_id"], session["role"])
    if request.method == "POST":
        uploaded_file = request.files.get("document")
        document_type = request.form.get("document_type", "")
        project_id, project_error = _chosen_project(request.form, projects, required=False)

        if uploaded_file is None or not uploaded_file.filename:
            error = "Choose a document to upload."
        elif document_type not in DOCUMENT_TYPES:
            error = "Choose a document type."
        elif project_error:
            error = project_error
        else:
            try:
                original, stored = _save_upload(uploaded_file, ALLOWED_DOCUMENT_EXTENSIONS)
            except ValueError:
                error = "Choose a PDF, Word, Excel, CSV, or TXT file."
            else:
                database.add_document(project_id, session["user_id"], document_type, original, stored)
                if request.args.get("from") == "project" and project_id:
                    return redirect(url_for("project_details", project_id=project_id, tab="documents"))
                return redirect(url_for("documents", project=project_id) if request.args.get("project") else url_for("documents"))

    return render_template(
        "upload_document.html",
        user_name=session["user"],
        document_types=DOCUMENT_TYPES,
        projects=projects,
        selected_project=request.form.get("project_id") or request.args.get("project", ""),
        error=error,
    )


@app.route("/documents/<int:document_id>/edit", methods=["GET", "POST"])
@role_required("employee")
def edit_document(document_id):
    document = database.get_visible_file("documents", document_id, session["user_id"], session["role"])
    if document is None:
        abort(404)
    projects = database.projects_for(session["user_id"], session["role"])
    values = dict(document) if request.method == "GET" else request.form
    error = None
    if request.method == "POST":
        name = request.form.get("original_filename", "").strip()
        document_type = request.form.get("document_type", "")
        project_id, project_error = _chosen_project(request.form, projects, required=False)
        if not name or len(name) > 150 or '/' in name or '\\' in name or any(ord(char) < 32 for char in name):
            error = "Enter a document name of 1–150 characters without slashes or control characters."
        elif document_type not in DOCUMENT_TYPES:
            error = "Choose a document type."
        elif project_error:
            error = project_error
        else:
            attachments = []
            try:
                for uploaded_file in request.files.getlist("document"):
                    if uploaded_file.filename:
                        attachments.append(_save_upload(uploaded_file, ALLOWED_DOCUMENT_EXTENSIONS))
            except ValueError:
                error = "Choose a PDF, Word, Excel, CSV, or TXT file."
                for _, stored in attachments:
                    _remove_file(stored)
            except Exception:
                for _, stored in attachments:
                    _remove_file(stored)
                raise
            if error is None:
                try:
                    database.update_document(document_id, name, document_type, project_id,
                                             attachments, session["user_id"] if attachments else None)
                except Exception:
                    for _, stored in attachments:
                        _remove_file(stored)
                    raise
                return redirect(url_for("edit_document", document_id=document_id, saved=1))
    return render_template("edit_document.html", user_name=session["user"], document=document,
                           values=values, projects=projects, document_types=DOCUMENT_TYPES, error=error,
                           attachments=database.get_document_attachments(document_id))


@app.route("/documents/<int:document_id>/attachments/<int:attachment_id>/delete", methods=["POST"])
@role_required("employee")
def delete_document_attachment(document_id, attachment_id):
    try:
        stored = database.remove_document_attachment(document_id, attachment_id)
    except database.RuleError:
        abort(404)
    _remove_file(stored)
    return redirect(url_for("edit_document", document_id=document_id))


@app.route("/documents/<int:document_id>/attachments/<int:attachment_id>/download")
@role_required("employee", "subcontractor")
def download_document_attachment(document_id, attachment_id):
    if database.get_visible_file("documents", document_id, session["user_id"], session["role"]) is None:
        abort(404)
    attachment = next((a for a in database.get_document_attachments(document_id)
                       if a['attachment_id'] == attachment_id), None)
    if attachment is None:
        abort(404)
    return _send_stored_file(attachment['file_path'], download_name=attachment['original_filename'], as_attachment=True)


@app.route("/documents/<int:document_id>/download")
@role_required("employee", "subcontractor")
def download_document(document_id):
    document = database.get_visible_file("documents", document_id, session["user_id"], session["role"])
    if document is None or not document["file_path"]:
        return "Document not found.", 404
    return _send_stored_file(document["file_path"], as_attachment=True,
                             download_name=document["attachment_filename"] or document["original_filename"])


@app.route("/documents/<int:document_id>/delete", methods=["POST"])
@role_required("employee")
def delete_document(document_id):
    attachments = database.get_document_attachments(document_id)
    _remove_file(database.delete_file_record("documents", document_id))
    for attachment in attachments:
        _remove_file(attachment['file_path'])
    return redirect(request.referrer if (request.referrer or "").startswith(request.host_url) else url_for("documents"))


@app.route("/photos")
@role_required("employee", "subcontractor")
def photos():
    project_id = _project_filter()
    return render_template(
        "photos.html",
        user_name=session["user"],
        photos=database.get_photos(session["user_id"], session["role"], project_id),
        projects=database.projects_for(session["user_id"], session["role"]),
        filter_project_id=project_id,
    )


@app.route("/photos/upload", methods=["GET", "POST"])
@role_required("employee", "subcontractor")
def upload_photo():
    error = None
    projects = database.projects_for(session["user_id"], session["role"])
    if request.method == "POST":
        uploaded_file = request.files.get("photo")
        title = request.form.get("title", "").strip()
        project_id, project_error = _chosen_project(request.form, projects, required=True)

        if uploaded_file is None or not uploaded_file.filename:
            error = "Choose a photo to upload."
        elif not title:
            error = "Enter a title for the photo."
        elif len(title) > 120:
            error = "The title must be 120 characters or fewer."
        elif project_error:
            error = project_error
        else:
            try:
                original, stored = _save_upload(uploaded_file, ALLOWED_PHOTO_EXTENSIONS)
            except ValueError:
                error = "Choose a JPG, PNG, GIF, or WebP image."
            else:
                database.add_photo(project_id, session["user_id"], title, original, stored)
                if request.args.get("from") == "project" and session["role"] == "employee":
                    return redirect(url_for("project_details", project_id=project_id, tab="photos"))
                return redirect(url_for("photos", project=project_id) if request.args.get("project") else url_for("photos"))

    return render_template(
        "upload_photo.html",
        user_name=session["user"],
        projects=projects,
        selected_project=request.form.get("project_id") or request.args.get("project", ""),
        error=error,
    )


@app.route("/photos/<int:photo_id>/image")
@role_required("employee", "subcontractor")
def photo_image(photo_id):
    photo = database.get_visible_file("photos", photo_id, session["user_id"], session["role"])
    if photo is None or not photo["file_path"]:
        return "Photo not found.", 404
    return _send_stored_file(photo["file_path"])


@app.route("/photos/<int:photo_id>/delete", methods=["POST"])
@role_required("employee")
def delete_photo(photo_id):
    _remove_file(database.delete_file_record("photos", photo_id))
    return redirect(request.referrer if (request.referrer or "").startswith(request.host_url) else url_for("photos"))


@app.errorhandler(413)
def upload_too_large(_error):
    message = f"That upload is too large. Files must be {MAX_UPLOAD_MB} MB or smaller in total."
    if request.path.startswith("/api/"):
        return jsonify({"error": message}), 413
    back = request.referrer if (request.referrer or "").startswith(request.host_url) else url_for("dashboard")
    return render_template("upload_too_large.html", message=message, back=back), 413


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "").lower() == "true")

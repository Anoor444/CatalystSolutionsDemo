# cd ".\CatalystSolutionsDemo\Catalyst Solutions Demo"; python app.py
import json
import os
import secrets
import sqlite3
from functools import wraps
from datetime import date
from uuid import uuid4

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "").lower() == "true"

DOCUMENT_UPLOAD_FOLDER = os.path.join(app.instance_path, "document_uploads")
DOCUMENT_METADATA_FILE = os.path.join(app.instance_path, "documents.json")
PHOTO_UPLOAD_FOLDER = os.path.join(app.instance_path, "photo_uploads")
PHOTO_METADATA_FILE = os.path.join(app.instance_path, "photos.json")
USER_DATABASE_FILE = os.path.join(app.instance_path, "users.sqlite3")
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
SAMPLE_DOCUMENTS = (
    {
        "filename": "Kitchen Renovation Estimate.pdf",
        "document_type": "Estimate",
        "project_name": "Riverstone Kitchen Remodel",
        "date_added": "October 12, 2026",
    },
    {
        "filename": "Roofing Invoice.pdf",
        "document_type": "Invoice",
        "project_name": "Sugar Land Roof Replacement",
        "date_added": "October 14, 2026",
    },
    {
        "filename": "Material Receipt.pdf",
        "document_type": "Receipt",
        "project_name": "Riverstone Kitchen Remodel",
        "date_added": "October 15, 2026",
    },
    {
        "filename": "Project Agreement.pdf",
        "document_type": "Contract",
        "project_name": "Memorial Bathroom Renovation",
        "date_added": "October 17, 2026",
    },
)
SAMPLE_PHOTOS = (
    {
        "title": "Kitchen Progress",
        "project_name": "Riverstone Kitchen Remodel",
        "date_added": "October 12, 2026",
        "uploaded_by": "Employee",
    },
    {
        "title": "Roof Installation",
        "project_name": "Sugar Land Roof Replacement",
        "date_added": "October 14, 2026",
        "uploaded_by": "Subcontractor",
    },
    {
        "title": "Bathroom Before Renovation",
        "project_name": "Memorial Bathroom Renovation",
        "date_added": "October 15, 2026",
        "uploaded_by": "Employee",
    },
    {
        "title": "Flooring Installation",
        "project_name": "Riverstone Kitchen Remodel",
        "date_added": "October 17, 2026",
        "uploaded_by": "Subcontractor",
    },
)
SAMPLE_CLIENT_PROJECTS = (
    {
        "project": "Riverstone Kitchen Remodel",
        "status": "In Progress",
        "progress": 65,
        "due_date": "November 15, 2026",
    },
    {
        "project": "Sugar Land Roof Replacement",
        "status": "In Progress",
        "progress": 55,
        "due_date": "October 28, 2026",
    },
    {
        "project": "Memorial Bathroom Renovation",
        "status": "Planning",
        "progress": 10,
        "due_date": "December 12, 2026",
    },
    {
        "project": "Katy Home Addition",
        "status": "In Progress",
        "progress": 48,
        "due_date": "January 20, 2027",
    },
)
SAMPLE_CLIENT_ESTIMATES = (
    {
        "estimate": "Kitchen Remodel Estimate",
        "project": "Riverstone Kitchen Remodel",
        "date": "October 12, 2026",
        "amount": "$48,500",
        "status": "Pending Review",
    },
    {
        "estimate": "Roof Replacement Estimate",
        "project": "Sugar Land Roof Replacement",
        "date": "October 14, 2026",
        "amount": "$22,000",
        "status": "Approved",
    },
)
SAMPLE_CLIENT_INVOICES = (
    {
        "invoice": "Invoice #1042",
        "project": "Riverstone Kitchen Remodel",
        "date": "October 15, 2026",
        "amount": "$8,250",
        "status": "Due November 15, 2026",
    },
    {
        "invoice": "Invoice #1038",
        "project": "Sugar Land Roof Replacement",
        "date": "October 10, 2026",
        "amount": "$4,100",
        "status": "Paid",
    },
)

os.makedirs(app.instance_path, exist_ok=True)
secret_key_file = os.path.join(app.instance_path, ".secret_key")
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
if not app.secret_key:
    try:
        with open(secret_key_file, "x", encoding="utf-8") as secret_file:
            secret_file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    with open(secret_key_file, encoding="utf-8") as secret_file:
        app.secret_key = secret_file.read().strip()


def initialize_user_database():
    with sqlite3.connect(USER_DATABASE_FILE) as database:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('employee', 'subcontractor', 'client'))
            )
            """
        )
        database.execute(
            """
            INSERT OR IGNORE INTO users (email, name, password_hash, role)
            VALUES (?, ?, ?, 'employee')
            """,
            (DEMO_EMAIL, DEMO_NAME, generate_password_hash(DEMO_PASSWORD)),
        )
        database.execute(
            """
            INSERT OR IGNORE INTO users (email, name, password_hash, role)
            VALUES (?, ?, ?, 'client')
            """,
            (
                DEMO_CLIENT_EMAIL,
                DEMO_CLIENT_NAME,
                generate_password_hash(DEMO_CLIENT_PASSWORD),
            ),
        )


        database.execute(
            """
            INSERT OR IGNORE INTO users (email, name, password_hash, role)
            VALUES (?, ?, ?, 'subcontractor')
            """,
            (
                DEMO_SUBCONTRACTOR_EMAIL,
                DEMO_SUBCONTRACTOR_NAME,
                generate_password_hash(DEMO_SUBCONTRACTOR_PASSWORD),
            ),
        )


initialize_user_database()


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
    if request.method == "POST":
        submitted_token = request.form.get("csrf_token", "")
        session_token = session.get("csrf_token", "")
        if not session_token or not secrets.compare_digest(submitted_token, session_token):
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
        with sqlite3.connect(USER_DATABASE_FILE) as database:
            database.execute(
                "INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, ?, ?)",
                (email, name, generate_password_hash(password), role),
            )
    except sqlite3.IntegrityError as error:
        raise click.ClickException("An account with that email already exists.") from error

    click.echo(f"Created {role} account for {email}.")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with sqlite3.connect(USER_DATABASE_FILE) as database:
            database.row_factory = sqlite3.Row
            user = database.execute(
                "SELECT id, email, name, password_hash, role FROM users WHERE email = ?",
                (email,),
            ).fetchone()

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


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    message = None
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            error = "Enter your email address."
        else:
            message = (
                "Password reset emails are not configured for this demo yet. "
                "Please contact your administrator to reset your password."
            )

    return render_template("forgot_password.html", message=message, error=error)


@app.route("/")
@role_required(*ROLES)
def dashboard():
    if session["role"] == "subcontractor":
        return render_template(
            "subcontractor.dashboard.html",
            user_name=session["user"],
            projects=(),
            open_invoices=(),
        )
    if session["role"] == "client":
        pending_estimates = tuple(
            estimate
            for estimate in SAMPLE_CLIENT_ESTIMATES
            if estimate["status"] == "Pending Review"
        )
        open_invoices = tuple(
            invoice
            for invoice in SAMPLE_CLIENT_INVOICES
            if invoice["status"] != "Paid"
        )
        return render_template(
            "client.dashboard.html",
            user_name=session["user"],
            projects=SAMPLE_CLIENT_PROJECTS,
            pending_estimates=pending_estimates,
            open_invoices=open_invoices,
        )
    return render_template("dashboard.html", user_name=session["user"])


# ---------- PROJECTS ----------

@app.route("/projects")
@role_required(*ROLES)
def projects():
    if session["role"] == "subcontractor":
        return render_template(
            "my_projects.html",
            user_name=session["user"],
            projects=(),
        )
    if session["role"] == "client":
        return render_template(
            "my_projects.html",
            user_name=session["user"],
            projects=SAMPLE_CLIENT_PROJECTS,
        )
    return render_template("projects.html", user_name=session["user"])


@app.route("/client/my-projects")
@role_required("client")
def client_my_projects():
    return render_template(
        "my_projects.html",
        user_name=session["user"],
        projects=SAMPLE_CLIENT_PROJECTS,
    )


@app.route("/client/estimates")
@role_required("client")
def client_estimates():
    return render_template(
        "client_records.html",
        user_name=session["user"],
        active_page="estimates",
        page_title="Estimates",
        page_description="Review estimates for your projects.",
        records=SAMPLE_CLIENT_ESTIMATES,
        first_column="Estimate",
        first_value="estimate",
        records_label="Your Estimates",
    )


@app.route("/client/invoices")
@role_required("client")
def client_invoices():
    return render_template(
        "client_records.html",
        user_name=session["user"],
        active_page="invoices",
        page_title="Invoices",
        page_description="Review invoices for your projects.",
        records=SAMPLE_CLIENT_INVOICES,
        first_column="Invoice",
        first_value="invoice",
        records_label="Your Invoices",
    )


@app.route("/subcontractor/invoices")
@role_required("subcontractor")
def subcontractor_invoices():
    return render_template(
        "client_records.html",
        user_name=session["user"],
        active_page="invoices",
        page_title="My Invoices",
        page_description="Review invoices for your assigned projects.",
        records=(),
        first_column="Invoice",
        first_value="invoice",
        records_label="Your Invoices",
    )


@app.route("/new-project", methods=["GET", "POST"])
@role_required("employee")
def new_project():
    if request.method == "POST":
        # Nothing is saved yet. Later: insert the form data into MySQL here.
        return redirect(url_for("projects"))

    return render_template("new_project.html", user_name=session["user"])


@app.route("/project/<int:project_id>")
@role_required(*ROLES)
def project_details(project_id):
    # For now every ID shows the same sample project.
    # Later: look up project_id in MySQL.
    return render_template("project_details.html", user_name=session["user"])


@app.route("/logout", methods=["POST"])
@role_required(*ROLES)
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/subcontractors")
@role_required("employee")
def subcontractors():
    return render_template("subcontractors.html", user_name=session["user"])

@app.route("/subcontractors/new", methods=["GET", "POST"])
@role_required("employee")
def new_subcontractor():
    if request.method == "POST":
        # Nothing is saved yet. Later: insert the form data into MySQL here.
        return redirect(url_for("subcontractors"))

    return render_template("new_subcontractor.html", user_name=session["user"])

@app.route("/clients")
@role_required("employee")
def clients():
    return render_template("clients.html", user_name=session["user"])


@app.route("/clients/new", methods=["GET", "POST"])
@role_required("employee")
def new_client():
    if request.method == "POST":
        # Client records are not persisted yet; storage will be added with the database.
        return redirect(url_for("clients"))

    return render_template("new_client.html", user_name=session["user"])


@app.route("/settings")
@role_required(*ROLES)
def settings():
    return render_template("settings.html", user_name=session["user"])


@app.route("/documents")
@role_required("employee", "subcontractor")
def documents():
    if os.path.exists(DOCUMENT_METADATA_FILE):
        with open(DOCUMENT_METADATA_FILE, encoding="utf-8") as metadata_file:
            documents = json.load(metadata_file)
    else:
        documents = []

    return render_template(
        "documents.html",
        user_name=session["user"],
        documents=documents,
        sample_documents=SAMPLE_DOCUMENTS,
    )


@app.route("/documents/upload", methods=["GET", "POST"])
@role_required("employee")
def upload_document():
    error = None
    if request.method == "POST":
        uploaded_file = request.files.get("document")
        document_type = request.form.get("document_type", "")
        project_name = request.form.get("project_name", "").strip()

        if uploaded_file is None or not uploaded_file.filename:
            error = "Choose a document to upload."
        else:
            safe_filename = secure_filename(uploaded_file.filename)
            extension = (
                safe_filename.rsplit(".", 1)[-1].lower()
                if "." in safe_filename
                else ""
            )

            if not safe_filename or extension not in ALLOWED_DOCUMENT_EXTENSIONS:
                error = "Choose a PDF, Word, Excel, CSV, or TXT file."
            elif document_type not in DOCUMENT_TYPES:
                error = "Choose a document type."
            else:
                document_id = uuid4().hex
                stored_filename = f"{document_id}.{extension}"
                os.makedirs(DOCUMENT_UPLOAD_FOLDER, exist_ok=True)
                uploaded_file.save(os.path.join(DOCUMENT_UPLOAD_FOLDER, stored_filename))

                if os.path.exists(DOCUMENT_METADATA_FILE):
                    with open(DOCUMENT_METADATA_FILE, encoding="utf-8") as metadata_file:
                        documents = json.load(metadata_file)
                else:
                    documents = []

                documents.append(
                    {
                        "id": document_id,
                        "filename": safe_filename,
                        "stored_filename": stored_filename,
                        "document_type": document_type,
                        "project_name": project_name or "Not specified",
                        "date_added": date.today().isoformat(),
                    }
                )
                with open(DOCUMENT_METADATA_FILE, "w", encoding="utf-8") as metadata_file:
                    json.dump(documents, metadata_file, indent=2)

                return redirect(url_for("documents"))

    return render_template(
        "upload_document.html",
        user_name=session["user"],
        document_types=DOCUMENT_TYPES,
        error=error,
    )


@app.route("/documents/<document_id>/download")
@role_required("employee", "subcontractor")
def download_document(document_id):
    if not os.path.exists(DOCUMENT_METADATA_FILE):
        return "Document not found.", 404

    with open(DOCUMENT_METADATA_FILE, encoding="utf-8") as metadata_file:
        documents = json.load(metadata_file)

    document = next((item for item in documents if item["id"] == document_id), None)
    if document is None:
        return "Document not found.", 404

    return send_from_directory(
        DOCUMENT_UPLOAD_FOLDER,
        document["stored_filename"],
        as_attachment=True,
        download_name=document["filename"],
    )


@app.route("/photos")
@role_required("employee", "subcontractor")
def photos():
    if os.path.exists(PHOTO_METADATA_FILE):
        with open(PHOTO_METADATA_FILE, encoding="utf-8") as metadata_file:
            photos = json.load(metadata_file)
    else:
        photos = []

    return render_template(
        "photos.html",
        user_name=session["user"],
        photos=photos,
        sample_photos=SAMPLE_PHOTOS,
    )


@app.route("/photos/upload", methods=["GET", "POST"])
@role_required("employee", "subcontractor")
def upload_photo():
    error = None
    if request.method == "POST":
        uploaded_file = request.files.get("photo")
        title = request.form.get("title", "").strip()
        project_name = request.form.get("project_name", "").strip()

        if uploaded_file is None or not uploaded_file.filename:
            error = "Choose a photo to upload."
        elif not title:
            error = "Enter a title for the photo."
        else:
            safe_filename = secure_filename(uploaded_file.filename)
            extension = (
                safe_filename.rsplit(".", 1)[-1].lower()
                if "." in safe_filename
                else ""
            )

            if not safe_filename or extension not in ALLOWED_PHOTO_EXTENSIONS:
                error = "Choose a JPG, PNG, GIF, or WebP image."
            else:
                photo_id = uuid4().hex
                stored_filename = f"{photo_id}.{extension}"
                os.makedirs(PHOTO_UPLOAD_FOLDER, exist_ok=True)
                uploaded_file.save(os.path.join(PHOTO_UPLOAD_FOLDER, stored_filename))

                if os.path.exists(PHOTO_METADATA_FILE):
                    with open(PHOTO_METADATA_FILE, encoding="utf-8") as metadata_file:
                        photos = json.load(metadata_file)
                else:
                    photos = []

                photos.append(
                    {
                        "id": photo_id,
                        "filename": safe_filename,
                        "stored_filename": stored_filename,
                        "title": title,
                        "project_name": project_name or "Not specified",
                        "date_added": date.today().isoformat(),
                        "uploaded_by": session["user"],
                    }
                )
                os.makedirs(app.instance_path, exist_ok=True)
                with open(PHOTO_METADATA_FILE, "w", encoding="utf-8") as metadata_file:
                    json.dump(photos, metadata_file, indent=2)

                return redirect(url_for("photos"))

    return render_template("upload_photo.html", user_name=session["user"], error=error)


@app.route("/photos/<photo_id>/image")
@role_required("employee", "subcontractor")
def photo_image(photo_id):
    if not os.path.exists(PHOTO_METADATA_FILE):
        return "Photo not found.", 404

    with open(PHOTO_METADATA_FILE, encoding="utf-8") as metadata_file:
        photos = json.load(metadata_file)

    photo = next((item for item in photos if item["id"] == photo_id), None)
    if photo is None:
        return "Photo not found.", 404

    return send_from_directory(PHOTO_UPLOAD_FOLDER, photo["stored_filename"])

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "").lower() == "true")

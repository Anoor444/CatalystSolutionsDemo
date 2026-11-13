"""
Database helpers for the Buff Bison Construction Portal.

- One SQLite file (the same one the login system already uses).
- get_db() gives each request its own connection; it closes automatically.
- init_app(app) creates the tables from schema.sql and loads the sample
  data the first time the app runs.
- `flask --app app reset-demo-data` wipes the business tables and reloads
  the sample data (user accounts are kept).

Query functions for each page live at the bottom of this file, so app.py
routes stay short.
"""
import os
import sqlite3

import click
from flask import g

DATABASE_FILE = None  # set by init_app()
SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

# Tables cleared by reset-demo-data, children first so foreign keys are happy.
BUSINESS_TABLES = (
    "documents", "photos", "tasks", "subcontractor_invoices", "project_assignments",
    "receipts", "invoice_line_items", "invoices", "projects",
    "estimate_line_items", "estimates", "subcontractors", "clients", "cost_categories",
)

PROJECT_STATUSES = ("Planning", "In Progress", "On Hold", "Completed")


# ---------------------------------------------------------------------
# Connection handling
# ---------------------------------------------------------------------
def connect(path=None):
    connection = sqlite3.connect(path or DATABASE_FILE)
    connection.row_factory = sqlite3.Row          # rows behave like dicts: row["name"]
    connection.execute("PRAGMA foreign_keys = ON")  # SQLite needs this to enforce FKs
    return connection


def get_db():
    """Connection for the current request (opened once, reused, closed at the end)."""
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_app(app, database_file):
    global DATABASE_FILE
    DATABASE_FILE = database_file
    app.teardown_appcontext(close_db)
    app.cli.add_command(reset_demo_data_command)

    with connect() as connection:
        create_tables(connection)
        if connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
            from seed_data import load_sample_data
            load_sample_data(connection)


def create_tables(connection):
    with open(SCHEMA_FILE, encoding="utf-8") as schema:
        connection.executescript(schema.read())


@click.command("reset-demo-data")
def reset_demo_data_command():
    """Delete all business data and reload the sample data (keeps user accounts)."""
    from seed_data import load_sample_data

    with connect() as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        for table in BUSINESS_TABLES:
            connection.execute(f"DELETE FROM {table}")
        connection.execute("PRAGMA foreign_keys = ON")
        load_sample_data(connection)
    click.echo("Sample data reloaded.")


# ---------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------
# Actual cost = receipts + subcontractor invoices that were approved or paid.
_PROJECT_SELECT = """
    SELECT p.*,
           c.name  AS client_name,
           u.name  AS manager_name,
           COALESCE(r.total, 0) + COALESCE(s.total, 0) AS actual_cost
    FROM projects p
    JOIN clients c      ON c.client_id = p.client_id
    LEFT JOIN users u   ON u.id = p.project_manager_id
    LEFT JOIN (SELECT project_id, SUM(amount) AS total
               FROM receipts GROUP BY project_id) r
           ON r.project_id = p.project_id
    LEFT JOIN (SELECT pa.project_id, SUM(si.amount) AS total
               FROM subcontractor_invoices si
               JOIN project_assignments pa ON pa.assignment_id = si.assignment_id
               WHERE si.status IN ('Approved', 'Paid')
               GROUP BY pa.project_id) s
           ON s.project_id = p.project_id
"""


def get_projects():
    return get_db().execute(_PROJECT_SELECT + " ORDER BY p.project_id").fetchall()


def get_project(project_id):
    return get_db().execute(_PROJECT_SELECT + " WHERE p.project_id = ?", (project_id,)).fetchone()


def get_project_counts():
    rows = get_db().execute("SELECT status, COUNT(*) AS n FROM projects GROUP BY status").fetchall()
    by_status = {row["status"]: row["n"] for row in rows}
    return {
        "total": sum(by_status.values()),
        "active": by_status.get("In Progress", 0),
        "planning": by_status.get("Planning", 0),
        "on_hold": by_status.get("On Hold", 0),
        "completed": by_status.get("Completed", 0),
    }


def get_project_managers():
    return get_db().execute(
        "SELECT id, name FROM users WHERE role = 'employee' ORDER BY name"
    ).fetchall()


def find_or_create_client(connection, name, email=None, phone=None):
    """Reuse an existing client with the same name (case-insensitive), otherwise add one."""
    row = connection.execute(
        "SELECT client_id FROM clients WHERE lower(name) = lower(?)", (name,)
    ).fetchone()
    if row:
        if email or phone:
            connection.execute(
                "UPDATE clients SET email = COALESCE(?, email), phone = COALESCE(?, phone) WHERE client_id = ?",
                (email or None, phone or None, row["client_id"]),
            )
        return row["client_id"]
    cursor = connection.execute(
        "INSERT INTO clients (name, email, phone) VALUES (?, ?, ?)",
        (name, email or None, phone or None),
    )
    return cursor.lastrowid


def create_project(data):
    """Insert a project from already-validated form data. Returns the new project_id."""
    connection = get_db()
    with connection:  # one transaction: client + project together, or neither
        client_id = find_or_create_client(
            connection, data["client_name"], data.get("client_email"), data.get("client_phone")
        )
        cursor = connection.execute(
            """
            INSERT INTO projects (project_number, name, project_type, description, address,
                                  client_id, project_manager_id, status, budget_amount,
                                  progress_percent, start_date, due_date)
            VALUES ('pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"], data["project_type"], data.get("description") or None, data["address"],
                client_id, data["manager_id"], data["status"], data["budget"],
                100 if data["status"] == "Completed" else 0,
                data.get("start_date") or None, data.get("due_date") or None,
            ),
        )
        project_id = cursor.lastrowid
        connection.execute(
            "UPDATE projects SET project_number = ? WHERE project_id = ?",
            (f"BB-{project_id:04d}", project_id),
        )
    return project_id

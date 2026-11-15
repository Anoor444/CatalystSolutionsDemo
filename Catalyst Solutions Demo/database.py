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
        # Step 4 replaced the original (never used) tasks table with a fuller one.
        columns = [row[1] for row in connection.execute("PRAGMA table_info(tasks)")]
        if columns and "priority" not in columns and \
                connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
            connection.execute("DROP TABLE tasks")
            columns = []
        tasks_table_is_new = not columns

        create_tables(connection)
        from seed_data import load_billing_samples, load_sample_data, load_task_samples

        def count(table):
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        if count("projects") == 0:
            load_sample_data(connection)          # brand-new database: everything
        else:
            if count("estimates") == 0 and count("invoices") == 0:
                load_billing_samples(connection)  # database from step 1: add sample estimates/invoices
            if tasks_table_is_new:
                load_task_samples(connection)     # database from before step 4: add sample tasks

        # Databases created before step 3 stamped the sample projects with their creation time,
        # which would fill "Recent Activity" with 12 "project created" entries. Backdate them once.
        from seed_data import PROJECTS, SAMPLE_PROJECT_CREATED_AT
        names = [p[0] for p in PROJECTS]
        connection.execute(
            f"UPDATE projects SET created_at = ? WHERE description IS NULL "
            f"AND created_at > ? AND name IN ({','.join('?' * len(names))})",
            (SAMPLE_PROJECT_CREATED_AT, SAMPLE_PROJECT_CREATED_AT, *names),
        )


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


# ---------------------------------------------------------------------
# Shared helpers for estimates and invoices
# ---------------------------------------------------------------------
class RuleError(Exception):
    """Raised when a request breaks a business rule (wrong status, missing record...).
    The API turns it into a 400/404/409 JSON error with this message."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _money(value):
    return round(float(value or 0), 2)


def get_lookups():
    """Dropdown data for the Estimates and Invoices pages."""
    db = get_db()
    return {
        "clients": [dict(r) for r in db.execute("SELECT client_id, name FROM clients ORDER BY name")],
        "categories": [dict(r) for r in db.execute(
            "SELECT category_id, name FROM cost_categories WHERE is_active = 1 ORDER BY category_id")],
        "managers": [dict(r) for r in db.execute(
            "SELECT id AS user_id, name FROM users WHERE role = 'employee' ORDER BY name")],
        "projects": [dict(r) for r in db.execute(
            """SELECT p.project_id, p.name, c.name AS client_name
               FROM projects p JOIN clients c ON c.client_id = p.client_id ORDER BY p.name""")],
    }


# ---------------------------------------------------------------------
# Estimates (RTM A3, A4)
# ---------------------------------------------------------------------
ESTIMATE_EDITABLE = ("Draft", "Sent")
# status a user can move an estimate to, from its current status
ESTIMATE_TRANSITIONS = {
    "Sent": ("Approved", "Rejected"),
    "Rejected": ("Draft",),
}


def get_estimates(estimate_id=None):
    db = get_db()
    where, params = ("WHERE e.estimate_id = ?", (estimate_id,)) if estimate_id else ("", ())
    rows = db.execute(
        f"""SELECT e.*, date(e.created_at) AS created_date, c.name AS client_name,
                   u.name AS created_by_name, p.project_id, p.project_number
            FROM estimates e
            JOIN clients c        ON c.client_id = e.client_id
            LEFT JOIN users u     ON u.id = e.created_by
            LEFT JOIN projects p  ON p.estimate_id = e.estimate_id
            {where}
            ORDER BY e.estimate_id DESC""",
        params,
    ).fetchall()
    items = {}
    for li in db.execute("SELECT * FROM estimate_line_items ORDER BY line_item_id"):
        items.setdefault(li["estimate_id"], []).append(dict(li))
    result = []
    for row in rows:
        estimate = dict(row)
        estimate["created_at"] = estimate.pop("created_date")
        estimate["line_items"] = items.get(row["estimate_id"], [])
        result.append(estimate)
    return result


def get_estimate(estimate_id):
    found = get_estimates(estimate_id)
    if not found:
        raise RuleError("Estimate not found.", 404)
    return found[0]


def _save_estimate_lines(db, estimate_id, line_items):
    db.execute("DELETE FROM estimate_line_items WHERE estimate_id = ?", (estimate_id,))
    total = 0
    for li in line_items:
        line_total = _money(li["quantity"] * li["unit_cost"])
        total += line_total
        db.execute(
            """INSERT INTO estimate_line_items (estimate_id, category_id, description, quantity, unit_cost, line_total)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (estimate_id, li["category_id"], li["description"], li["quantity"], li["unit_cost"], line_total),
        )
    db.execute("UPDATE estimates SET total_amount = ? WHERE estimate_id = ?", (_money(total), estimate_id))


def create_estimate(data, user_id):
    db = get_db()
    with db:
        cursor = db.execute(
            "INSERT INTO estimates (estimate_number, title, client_id, created_by, status, created_at) "
            "VALUES ('pending', ?, ?, ?, ?, datetime('now', 'localtime'))",
            (data["title"], data["client_id"], user_id, data["status"]),
        )
        estimate_id = cursor.lastrowid
        db.execute("UPDATE estimates SET estimate_number = ? WHERE estimate_id = ?", (f"EST-{estimate_id}", estimate_id))
        _save_estimate_lines(db, estimate_id, data["line_items"])
    return get_estimate(estimate_id)


def update_estimate(estimate_id, data):
    current = get_estimate(estimate_id)
    if current["status"] not in ESTIMATE_EDITABLE:
        raise RuleError(f"A {current['status'].lower()} estimate can't be edited.", 409)
    if current["status"] == "Sent" and data["status"] == "Draft":
        raise RuleError("A sent estimate can't go back to draft.", 409)
    db = get_db()
    with db:
        db.execute(
            "UPDATE estimates SET title = ?, client_id = ?, status = ? WHERE estimate_id = ?",
            (data["title"], data["client_id"], data["status"], estimate_id),
        )
        _save_estimate_lines(db, estimate_id, data["line_items"])
    return get_estimate(estimate_id)


def set_estimate_status(estimate_id, new_status):
    current = get_estimate(estimate_id)
    allowed = ESTIMATE_TRANSITIONS.get(current["status"], ())
    if new_status not in allowed:
        raise RuleError(f"Can't change a {current['status'].lower()} estimate to {new_status.lower()}.", 409)
    db = get_db()
    with db:
        db.execute("UPDATE estimates SET status = ? WHERE estimate_id = ?", (new_status, estimate_id))
    return get_estimate(estimate_id)


def delete_estimate(estimate_id):
    current = get_estimate(estimate_id)
    if current["status"] != "Draft":
        raise RuleError("Only draft estimates can be deleted.", 409)
    db = get_db()
    with db:
        db.execute("DELETE FROM estimates WHERE estimate_id = ?", (estimate_id,))


def convert_estimate(estimate_id, data):
    """Create a project from an approved estimate (RTM A4)."""
    current = get_estimate(estimate_id)
    if current["status"] != "Approved":
        raise RuleError("Only approved estimates can be converted.", 409)
    db = get_db()
    with db:
        cursor = db.execute(
            """INSERT INTO projects (project_number, name, description, client_id, estimate_id,
                                     project_manager_id, status, budget_amount, start_date, due_date)
               VALUES ('pending', ?, ?, ?, ?, ?, 'Planning', ?, ?, ?)""",
            (data["name"], f"Created from {current['estimate_number']}", current["client_id"], estimate_id,
             data["project_manager_id"], data["budget_amount"], data["start_date"], data["due_date"]),
        )
        project_id = cursor.lastrowid
        project_number = f"BB-{project_id:04d}"
        db.execute("UPDATE projects SET project_number = ? WHERE project_id = ?", (project_number, project_id))
        db.execute("UPDATE estimates SET status = 'Converted' WHERE estimate_id = ?", (estimate_id,))
    return {"project_id": project_id, "project_number": project_number, "estimate": get_estimate(estimate_id)}


# ---------------------------------------------------------------------
# Invoices (RTM A5)
# ---------------------------------------------------------------------
INVOICE_EDITABLE = ("Draft", "Unpaid")
INVOICE_TRANSITIONS = {
    "Unpaid": ("Paid",),
    "Paid": ("Unpaid",),   # undo a mistaken "Mark Paid"
}


def get_invoices(invoice_id=None):
    db = get_db()
    where, params = ("WHERE i.invoice_id = ?", (invoice_id,)) if invoice_id else ("", ())
    rows = db.execute(
        f"""SELECT i.*, p.name AS project_name, c.name AS client_name
            FROM invoices i
            JOIN projects p ON p.project_id = i.project_id
            JOIN clients c  ON c.client_id = p.client_id
            {where}
            ORDER BY i.invoice_id DESC""",
        params,
    ).fetchall()
    items = {}
    for li in db.execute("SELECT * FROM invoice_line_items ORDER BY invoice_line_item_id"):
        items.setdefault(li["invoice_id"], []).append(dict(li))
    return [dict(row, line_items=items.get(row["invoice_id"], [])) for row in rows]


def get_invoice(invoice_id):
    found = get_invoices(invoice_id)
    if not found:
        raise RuleError("Invoice not found.", 404)
    return found[0]


def _save_invoice_lines(db, invoice_id, line_items):
    db.execute("DELETE FROM invoice_line_items WHERE invoice_id = ?", (invoice_id,))
    total = 0
    for li in line_items:
        line_total = _money(li["quantity"] * li["unit_price"])
        total += line_total
        db.execute(
            """INSERT INTO invoice_line_items (invoice_id, description, quantity, unit_price, line_total)
               VALUES (?, ?, ?, ?, ?)""",
            (invoice_id, li["description"], li["quantity"], li["unit_price"], line_total),
        )
    db.execute("UPDATE invoices SET total_amount = ? WHERE invoice_id = ?", (_money(total), invoice_id))


def create_invoice(data):
    db = get_db()
    with db:
        cursor = db.execute(
            """INSERT INTO invoices (invoice_number, project_id, issue_date, due_date, status)
               VALUES ('pending', ?, ?, ?, ?)""",
            (data["project_id"], data["issue_date"], data["due_date"], data["status"]),
        )
        invoice_id = cursor.lastrowid
        db.execute("UPDATE invoices SET invoice_number = ? WHERE invoice_id = ?", (f"INV-{invoice_id}", invoice_id))
        _save_invoice_lines(db, invoice_id, data["line_items"])
    return get_invoice(invoice_id)


def update_invoice(invoice_id, data):
    current = get_invoice(invoice_id)
    if current["status"] not in INVOICE_EDITABLE:
        raise RuleError("A paid invoice can't be edited. Mark it unpaid first.", 409)
    if current["status"] == "Unpaid" and data["status"] == "Draft":
        raise RuleError("A sent invoice can't go back to draft.", 409)
    db = get_db()
    with db:
        db.execute(
            "UPDATE invoices SET project_id = ?, issue_date = ?, due_date = ?, status = ? WHERE invoice_id = ?",
            (data["project_id"], data["issue_date"], data["due_date"], data["status"], invoice_id),
        )
        _save_invoice_lines(db, invoice_id, data["line_items"])
    return get_invoice(invoice_id)


def set_invoice_status(invoice_id, new_status):
    current = get_invoice(invoice_id)
    if new_status not in INVOICE_TRANSITIONS.get(current["status"], ()):
        raise RuleError(f"Can't change a {current['status'].lower()} invoice to {new_status.lower()}.", 409)
    db = get_db()
    with db:
        db.execute(
            "UPDATE invoices SET status = ?, paid_at = CASE WHEN ? = 'Paid' THEN date('now', 'localtime') END "
            "WHERE invoice_id = ?",
            (new_status, new_status, invoice_id),
        )
    return get_invoice(invoice_id)


def delete_invoice(invoice_id):
    current = get_invoice(invoice_id)
    if current["status"] != "Draft":
        raise RuleError("Only draft invoices can be deleted.", 409)
    db = get_db()
    with db:
        db.execute("DELETE FROM invoices WHERE invoice_id = ?", (invoice_id,))


# ---------------------------------------------------------------------
# Dashboard (employee)
# ---------------------------------------------------------------------
def get_dashboard():
    db = get_db()
    one = lambda sql: db.execute(sql).fetchone()[0]
    stats = {
        "active_projects": one("SELECT COUNT(*) FROM projects WHERE status = 'In Progress'"),
        "pending_estimates": one("SELECT COUNT(*) FROM estimates WHERE status = 'Sent'"),
        "unpaid_total": one("SELECT COALESCE(SUM(total_amount), 0) FROM invoices WHERE status = 'Unpaid'"),
        "unpaid_count": one("SELECT COUNT(*) FROM invoices WHERE status = 'Unpaid'"),
        "overdue_count": one(
            "SELECT COUNT(*) FROM invoices WHERE status = 'Unpaid' AND due_date < date('now', 'localtime')"),
    }
    open_projects = db.execute(
        _PROJECT_SELECT + " WHERE p.status != 'Completed' "
        "ORDER BY CASE p.status WHEN 'In Progress' THEN 0 WHEN 'Planning' THEN 1 ELSE 2 END, "
        "p.due_date IS NULL, p.due_date"
    ).fetchall()

    # Recent activity is built from the timestamps already stored on each record.
    events = db.execute(
        """
        SELECT created_at AS at, 'Estimate ' || estimate_number || ' created: ' || title AS text
          FROM estimates
        UNION ALL
        SELECT issue_date, 'Invoice ' || i.invoice_number || ' sent: ' || p.name
          FROM invoices i JOIN projects p ON p.project_id = i.project_id WHERE i.status != 'Draft'
        UNION ALL
        SELECT paid_at, 'Invoice ' || invoice_number || ' paid ($' || printf('%,.2f', total_amount) || ')'
          FROM invoices WHERE paid_at IS NOT NULL
        UNION ALL
        SELECT created_at, 'Project ' || name || ' created'
               || CASE WHEN estimate_id IS NOT NULL THEN ' from an estimate' ELSE '' END
          FROM projects
        ORDER BY at DESC
        LIMIT 6
        """
    ).fetchall()
    return {"stats": stats, "projects": open_projects, "activity": events}


# ---------------------------------------------------------------------
# Tasks / Schedule (RTM A11)
# ---------------------------------------------------------------------
TASK_STATUSES = ("Not Started", "In Progress", "Completed")
TASK_PRIORITIES = ("Low", "Medium", "High")

# Same field names the Schedule page's JavaScript already uses.
_TASK_SELECT = """
    SELECT t.task_id AS id, t.project_id, p.name AS project_name, t.title AS name,
           COALESCE(t.description, '') AS description, COALESCE(t.assigned_to, '') AS assigned_to,
           t.start_date, t.due_date, t.priority, t.status
    FROM tasks t JOIN projects p ON p.project_id = t.project_id
"""


def get_tasks(project_id=None):
    if project_id is None:
        rows = get_db().execute(_TASK_SELECT + " ORDER BY t.due_date, t.task_id")
    else:
        rows = get_db().execute(_TASK_SELECT + " WHERE t.project_id = ? ORDER BY t.due_date, t.task_id", (project_id,))
    return [dict(row) for row in rows]


def get_task(task_id):
    row = get_db().execute(_TASK_SELECT + " WHERE t.task_id = ?", (task_id,)).fetchone()
    if row is None:
        raise RuleError("Task not found.", 404)
    return dict(row)


def get_schedule_data():
    projects = get_db().execute("SELECT project_id AS id, name FROM projects ORDER BY name").fetchall()
    return {
        "projects": [dict(p) for p in projects],
        "statuses": list(TASK_STATUSES),
        "priorities": list(TASK_PRIORITIES),
        "tasks": get_tasks(),
    }


def get_open_tasks():
    return [task for task in get_tasks() if task["status"] != "Completed"]


def create_task(data):
    db = get_db()
    with db:
        cursor = db.execute(
            """INSERT INTO tasks (project_id, title, description, assigned_to, start_date, due_date, priority, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (data["project_id"], data["name"], data["description"] or None, data["assigned_to"] or None,
             data["start_date"], data["due_date"], data["priority"], data["status"]),
        )
    return get_task(cursor.lastrowid)


def update_task(task_id, data):
    get_task(task_id)
    db = get_db()
    with db:
        db.execute(
            """UPDATE tasks SET project_id = ?, title = ?, description = ?, assigned_to = ?,
                                start_date = ?, due_date = ?, priority = ?, status = ?
               WHERE task_id = ?""",
            (data["project_id"], data["name"], data["description"] or None, data["assigned_to"] or None,
             data["start_date"], data["due_date"], data["priority"], data["status"], task_id),
        )
    return get_task(task_id)


def set_task_status(task_id, status):
    get_task(task_id)
    db = get_db()
    with db:
        db.execute("UPDATE tasks SET status = ? WHERE task_id = ?", (status, task_id))
    return get_task(task_id)


def delete_task(task_id):
    get_task(task_id)
    db = get_db()
    with db:
        db.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))

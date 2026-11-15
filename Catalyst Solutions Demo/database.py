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
    "documents", "photos", "tasks", "subcontractor_invoices", "project_assignments", "project_budget_items",
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

        # Step 5 rebuilt receipts (it only held placeholder "costs to date" rows) and
        # added project_budget_items. Both are refilled with sample costs below.
        receipt_columns = [row[1] for row in connection.execute("PRAGMA table_info(receipts)")]
        if receipt_columns and "description" not in receipt_columns:
            connection.execute("DROP TABLE receipts")
        # Step 7: documents/photos move from JSON files into these tables. The original
        # tables were never used (always empty), so they are rebuilt with the new columns.
        files_are_new = False
        photo_columns = [row[1] for row in connection.execute("PRAGMA table_info(photos)")]
        if not photo_columns or ("title" not in photo_columns and
                                 connection.execute("SELECT COUNT(*) FROM photos").fetchone()[0] == 0):
            if photo_columns:
                connection.execute("DROP TABLE photos")
                if connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0:
                    connection.execute("DROP TABLE documents")
            files_are_new = True

        # Step 8: subcontractor_invoices gets description/review/file columns. It was never
        # used before (always empty), so it is rebuilt.
        sub_invoice_columns = [row[1] for row in connection.execute("PRAGMA table_info(subcontractor_invoices)")]
        sub_invoices_are_new = not sub_invoice_columns or "description" not in sub_invoice_columns
        if sub_invoice_columns and sub_invoices_are_new and \
                connection.execute("SELECT COUNT(*) FROM subcontractor_invoices").fetchone()[0] == 0:
            connection.execute("DROP TABLE subcontractor_invoices")

        costs_are_new = not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'project_budget_items'").fetchone()

        create_tables(connection)

        # Step 6 added contact/status columns to clients and subcontractors.
        # (SQLite can add columns to an existing table; the CHECK lives in schema.sql for new databases.)
        directory_upgraded = False
        for table, new_columns in (
            ("clients", (("company", "TEXT"), ("address", "TEXT"),
                         ("status", "TEXT NOT NULL DEFAULT 'Active'"), ("notes", "TEXT"))),
            ("subcontractors", (("address", "TEXT"), ("license_number", "TEXT"),
                                ("status", "TEXT NOT NULL DEFAULT 'Active'"), ("notes", "TEXT"))),
        ):
            existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            for column, definition in new_columns:
                if column not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    directory_upgraded = True

        from seed_data import (import_legacy_file_lists, load_billing_samples, load_cost_samples,
                               load_directory_samples, load_file_samples, load_sample_data,
                               load_subcontractor_invoice_samples, load_task_samples, load_demo_client_estimate)

        def count(table):
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        if count("projects") == 0:
            load_sample_data(connection)          # brand-new database: everything
        else:
            if count("estimates") == 0 and count("invoices") == 0:
                load_billing_samples(connection)  # database from step 1: add sample estimates/invoices
            if tasks_table_is_new:
                load_task_samples(connection)     # database from before step 4: add sample tasks
            if costs_are_new:
                load_cost_samples(connection)     # database from before step 5: add sample job costs
            if directory_upgraded:
                load_directory_samples(connection)  # database from before step 6: client details, subcontractors
            if files_are_new:
                load_file_samples(connection)       # database from before step 7: sample documents/photos
            if sub_invoices_are_new:
                load_subcontractor_invoice_samples(connection)  # database from before step 8
            load_demo_client_estimate(connection)   # step 10: once (skips if it is already there)
        if files_are_new:
            # Anything uploaded before step 7 was listed in instance/documents.json and photos.json.
            import_legacy_file_lists(connection, os.path.dirname(DATABASE_FILE))

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
        from seed_data import copy_estimate_budget
        copy_estimate_budget(db, project_id)   # Job Costs "Estimated" column comes from the estimate
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


# ---------------------------------------------------------------------
# Job costs (RTM A6, A7)
# ---------------------------------------------------------------------
_EXPENSE_SELECT = """
    SELECT r.receipt_id AS id, r.project_id, r.expense_date, r.description, c.name AS category,
           CAST(r.amount AS REAL) AS amount, r.receipt_filename AS receipt_name,
           (r.file_path IS NOT NULL) AS has_receipt
    FROM receipts r JOIN cost_categories c ON c.category_id = r.category_id
"""


def get_expenses(project_id=None):
    sql, params = _EXPENSE_SELECT, ()
    if project_id is not None:
        sql, params = sql + " WHERE r.project_id = ?", (project_id,)
    rows = get_db().execute(sql + " ORDER BY r.expense_date DESC, r.receipt_id DESC", params)
    return [dict(row, has_receipt=bool(row["has_receipt"])) for row in rows]


def get_expense(expense_id):
    row = get_db().execute(_EXPENSE_SELECT + " WHERE r.receipt_id = ?", (expense_id,)).fetchone()
    if row is None:
        raise RuleError("Expense not found.", 404)
    return dict(row, has_receipt=bool(row["has_receipt"]))


def get_receipt_file(expense_id):
    row = get_db().execute(
        "SELECT file_path, receipt_filename FROM receipts WHERE receipt_id = ?", (expense_id,)).fetchone()
    if row is None or row["file_path"] is None:
        raise RuleError("No receipt file is on record for this expense.", 404)
    return row["file_path"], row["receipt_filename"]


def get_job_cost_data():
    db = get_db()
    return {
        "projects": [dict(r) for r in db.execute(
            "SELECT project_id AS id, name, CAST(budget_amount AS REAL) AS budget FROM projects ORDER BY name")],
        "categories": [r[0] for r in db.execute(
            "SELECT name FROM cost_categories WHERE is_active = 1 ORDER BY category_id")],
        "estimates": [dict(r) for r in db.execute(
            """SELECT b.project_id, c.name AS category, CAST(b.estimated_amount AS REAL) AS estimated_amount
               FROM project_budget_items b JOIN cost_categories c ON c.category_id = b.category_id""")],
        "expenses": get_expenses() + approved_subcontractor_costs(),
    }


def approved_subcontractor_costs(project_id=None):
    """Approved/paid subcontractor invoices, shaped like expenses (read-only on Job Costs).
    Projects' Actual Cost already includes them, so Job Costs shows them too."""
    sql = """SELECT 'sub-' || si.sub_invoice_id AS id, pa.project_id, date(si.submitted_at, 'localtime') AS expense_date,
                    s.company_name || ' invoice ' || si.invoice_number AS description,
                    COALESCE(c.name, 'Subcontractor') AS category, CAST(si.amount AS REAL) AS amount,
                    NULL AS receipt_name, 0 AS has_receipt, 1 AS read_only
             FROM subcontractor_invoices si
             JOIN project_assignments pa ON pa.assignment_id = si.assignment_id
             JOIN subcontractors s ON s.subcontractor_id = pa.subcontractor_id
             LEFT JOIN cost_categories c ON c.category_id = si.category_id
             WHERE si.status IN ('Approved', 'Paid')"""
    params = ()
    if project_id is not None:
        sql, params = sql + " AND pa.project_id = ?", (project_id,)
    return [dict(row, has_receipt=False, read_only=True) for row in get_db().execute(sql, params)]


def category_id_for(name):
    row = get_db().execute(
        "SELECT category_id FROM cost_categories WHERE name = ? AND is_active = 1", (name,)).fetchone()
    return row["category_id"] if row else None


def create_expense(data, user_id):
    db = get_db()
    with db:
        cursor = db.execute(
            """INSERT INTO receipts (project_id, category_id, uploaded_by, description, amount, expense_date,
                                     receipt_filename, file_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (data["project_id"], data["category_id"], user_id, data["description"], data["amount"],
             data["expense_date"], data.get("receipt_filename"), data.get("file_path")),
        )
    return get_expense(cursor.lastrowid)


def update_expense(expense_id, data):
    """Returns (updated expense, stored file name that is no longer used or None)."""
    old_file = get_db().execute("SELECT file_path FROM receipts WHERE receipt_id = ?", (expense_id,)).fetchone()
    if old_file is None:
        raise RuleError("Expense not found.", 404)
    replaced = None
    db = get_db()
    with db:
        db.execute(
            """UPDATE receipts SET project_id = ?, category_id = ?, description = ?, amount = ?, expense_date = ?
               WHERE receipt_id = ?""",
            (data["project_id"], data["category_id"], data["description"], data["amount"],
             data["expense_date"], expense_id),
        )
        if data.get("file_path"):
            db.execute("UPDATE receipts SET receipt_filename = ?, file_path = ? WHERE receipt_id = ?",
                       (data["receipt_filename"], data["file_path"], expense_id))
            replaced = old_file["file_path"]
    return get_expense(expense_id), replaced


def delete_expense(expense_id):
    """Returns the stored file name to remove from disk (or None)."""
    row = get_db().execute("SELECT file_path FROM receipts WHERE receipt_id = ?", (expense_id,)).fetchone()
    if row is None:
        raise RuleError("Expense not found.", 404)
    db = get_db()
    with db:
        db.execute("DELETE FROM receipts WHERE receipt_id = ?", (expense_id,))
    return row["file_path"]


# ---------------------------------------------------------------------
# Clients and subcontractors (employee directory)
# ---------------------------------------------------------------------
DIRECTORY_STATUSES = ("Active", "Inactive")


def _link_login(db, table, key, record_id, email, role):
    """If a login account with this email exists for the role, link it (used by the portals)."""
    if not email:
        return
    user = db.execute("SELECT id FROM users WHERE lower(email) = lower(?) AND role = ?", (email, role)).fetchone()
    if user and not db.execute(f"SELECT 1 FROM {table} WHERE user_id = ? AND {key} != ?", (user["id"], record_id)).fetchone():
        db.execute(f"UPDATE {table} SET user_id = ? WHERE {key} = ? AND user_id IS NULL", (user["id"], record_id))


def get_clients():
    return get_db().execute(
        """SELECT c.*, COUNT(p.project_id) AS project_count,
                  SUM(CASE WHEN p.status != 'Completed' THEN 1 ELSE 0 END) AS open_projects
           FROM clients c LEFT JOIN projects p ON p.client_id = c.client_id
           GROUP BY c.client_id ORDER BY c.name"""
    ).fetchall()


def get_client(client_id):
    return get_db().execute("SELECT * FROM clients WHERE client_id = ?", (client_id,)).fetchone()


def client_name_taken(name, exclude_id=None):
    return get_db().execute(
        "SELECT 1 FROM clients WHERE lower(name) = lower(?) AND client_id != ?", (name, exclude_id or 0)
    ).fetchone() is not None


def save_client(data, client_id=None):
    db = get_db()
    values = (data["name"], data["company"] or None, data["email"] or None, data["phone"] or None,
              data["address"] or None, data["status"], data["notes"] or None)
    with db:
        if client_id is None:
            client_id = db.execute(
                """INSERT INTO clients (name, company, email, phone, address, status, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""", values).lastrowid
        else:
            db.execute(
                """UPDATE clients SET name = ?, company = ?, email = ?, phone = ?, address = ?, status = ?, notes = ?
                   WHERE client_id = ?""", (*values, client_id))
        _link_login(db, "clients", "client_id", client_id, data["email"], "client")
    return client_id


def get_subcontractors():
    rows = get_db().execute(
        """SELECT s.*, COUNT(pa.assignment_id) AS project_count, GROUP_CONCAT(p.name, ', ') AS project_names
           FROM subcontractors s
           LEFT JOIN project_assignments pa ON pa.subcontractor_id = s.subcontractor_id
           LEFT JOIN projects p ON p.project_id = pa.project_id
           GROUP BY s.subcontractor_id ORDER BY s.contact_name"""
    ).fetchall()
    return rows


def get_subcontractor(subcontractor_id):
    return get_db().execute("SELECT * FROM subcontractors WHERE subcontractor_id = ?", (subcontractor_id,)).fetchone()


def get_subcontractor_project_ids(subcontractor_id):
    return [row[0] for row in get_db().execute(
        "SELECT project_id FROM project_assignments WHERE subcontractor_id = ?", (subcontractor_id,))]


def subcontractor_email_taken(email, exclude_id=None):
    return get_db().execute(
        "SELECT 1 FROM subcontractors WHERE lower(email) = lower(?) AND subcontractor_id != ?", (email, exclude_id or 0)
    ).fetchone() is not None


def save_subcontractor(data, project_ids, subcontractor_id=None):
    db = get_db()
    values = (data["company"], data["name"], data["trade"], data["email"], data["phone"] or None,
              data["address"] or None, data["license_number"] or None, data["status"], data["notes"] or None)
    with db:
        if subcontractor_id is None:
            subcontractor_id = db.execute(
                """INSERT INTO subcontractors (company_name, contact_name, trade, email, phone, address,
                                               license_number, status, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", values).lastrowid
        else:
            db.execute(
                """UPDATE subcontractors SET company_name = ?, contact_name = ?, trade = ?, email = ?, phone = ?,
                          address = ?, license_number = ?, status = ?, notes = ? WHERE subcontractor_id = ?""",
                (*values, subcontractor_id))
        # Assignments: keep existing rows that are still checked, add new ones, remove unchecked.
        current = set(get_subcontractor_project_ids(subcontractor_id))
        wanted = set(project_ids)
        for project_id in current - wanted:
            db.execute("DELETE FROM project_assignments WHERE subcontractor_id = ? AND project_id = ?",
                       (subcontractor_id, project_id))
        for project_id in wanted - current:
            db.execute(
                """INSERT INTO project_assignments (project_id, subcontractor_id, status, assigned_date)
                   VALUES (?, ?, 'Active', date('now', 'localtime'))""", (project_id, subcontractor_id))
        _link_login(db, "subcontractors", "subcontractor_id", subcontractor_id, data["email"], "subcontractor")
    return subcontractor_id


def get_project_choices():
    return get_db().execute("SELECT project_id, name, status FROM projects ORDER BY name").fetchall()


# ---------------------------------------------------------------------
# Access by role (used by Documents/Photos now and the portals later)
# ---------------------------------------------------------------------
def accessible_project_ids(user_id, role):
    """None = every project (employees). Otherwise the set of project ids this login may see:
    a subcontractor's assigned projects, or a client's own projects."""
    if role == "employee":
        return None
    db = get_db()
    if role == "subcontractor":
        rows = db.execute(
            """SELECT pa.project_id FROM project_assignments pa
               JOIN subcontractors s ON s.subcontractor_id = pa.subcontractor_id
               WHERE s.user_id = ?""", (user_id,))
    elif role == "client":
        rows = db.execute(
            "SELECT p.project_id FROM projects p JOIN clients c ON c.client_id = p.client_id WHERE c.user_id = ?",
            (user_id,))
    else:
        return set()
    return {row[0] for row in rows}


def projects_for(user_id, role):
    allowed = accessible_project_ids(user_id, role)
    rows = get_db().execute("SELECT project_id, name FROM projects ORDER BY name").fetchall()
    return [row for row in rows if allowed is None or row["project_id"] in allowed]


# ---------------------------------------------------------------------
# Documents and photos
# ---------------------------------------------------------------------
_FILE_TABLES = {
    "documents": ("document_id", "d", "original_filename"),
    "photos": ("photo_id", "d", "title"),
}


def _visible_files(table, user_id, role, project_id=None):
    key, alias, order = _FILE_TABLES[table]
    sql = f"""SELECT {alias}.*, {alias}.{key} AS id, p.name AS project_name, u.name AS uploaded_by_name,
                     date({alias}.created_at, 'localtime') AS date_added
              FROM {table} {alias}
              LEFT JOIN projects p ON p.project_id = {alias}.project_id
              LEFT JOIN users u ON u.id = {alias}.uploaded_by
              WHERE 1 = 1"""
    params = []
    allowed = accessible_project_ids(user_id, role)
    if allowed is not None:
        marks = ",".join("?" * len(allowed)) or "NULL"
        sql += f" AND ({alias}.project_id IN ({marks}) OR {alias}.uploaded_by = ?)"
        params += [*allowed, user_id]
    if project_id is not None:
        sql += f" AND {alias}.project_id = ?"
        params.append(project_id)
    sql += f" ORDER BY {alias}.created_at DESC, {alias}.{key} DESC"
    return get_db().execute(sql, params).fetchall()


def get_documents(user_id, role, project_id=None):
    return _visible_files("documents", user_id, role, project_id)


def get_photos(user_id, role, project_id=None):
    return _visible_files("photos", user_id, role, project_id)


def get_project_assignments(project_id):
    """Subcontractors assigned to one project (employee project page, Subcontractors tab)."""
    return get_db().execute(
        """SELECT pa.assignment_id, pa.scope_of_work, pa.status, pa.assigned_date,
                  s.subcontractor_id, s.company_name, s.contact_name, s.trade, s.email, s.phone,
                  s.status AS subcontractor_status, s.user_id
           FROM project_assignments pa
           JOIN subcontractors s ON s.subcontractor_id = pa.subcontractor_id
           WHERE pa.project_id = ?
           ORDER BY s.company_name""", (project_id,)).fetchall()


def get_project_costs(project_id):
    """Estimated vs actual by cost category for one project, plus its expense rows (Costs tab).
    Same numbers as the Job Costs page."""
    db = get_db()
    estimated = {r["category"]: float(r["amount"]) for r in db.execute(
        """SELECT c.name AS category, b.estimated_amount AS amount
           FROM project_budget_items b JOIN cost_categories c ON c.category_id = b.category_id
           WHERE b.project_id = ?""", (project_id,))}
    expenses = get_expenses(project_id) + approved_subcontractor_costs(project_id)
    expenses.sort(key=lambda e: (e["expense_date"] or "", str(e["id"])), reverse=True)
    actual = {}
    for e in expenses:
        actual[e["category"]] = actual.get(e["category"], 0) + float(e["amount"] or 0)
    categories = [r[0] for r in db.execute("SELECT name FROM cost_categories WHERE is_active = 1 ORDER BY category_id")]
    categories += [c for c in list(estimated) + list(actual) if c not in categories]
    rows = [{"category": c, "estimated": estimated.get(c, 0.0), "actual": actual.get(c, 0.0)} for c in categories]
    for row in rows:
        row["variance"] = row["actual"] - row["estimated"]
    return {"rows": rows, "expenses": expenses,
            "estimated_total": sum(r["estimated"] for r in rows), "actual_total": sum(r["actual"] for r in rows)}


def get_project_activity(project_id, limit=6):
    """Recent events for one project, built from timestamps already stored on its records."""
    return get_db().execute(
        """SELECT * FROM (
             SELECT datetime(created_at, 'localtime') AS at, 'Project created' AS text
               FROM projects WHERE project_id = :p
             UNION ALL
             SELECT issue_date, 'Invoice ' || invoice_number || ' sent'
               FROM invoices WHERE project_id = :p AND status != 'Draft'
             UNION ALL
             SELECT paid_at, 'Invoice ' || invoice_number || ' paid'
               FROM invoices WHERE project_id = :p AND paid_at IS NOT NULL
             UNION ALL
             SELECT datetime(created_at, 'localtime'), document_type || ' uploaded: ' || original_filename
               FROM documents WHERE project_id = :p
             UNION ALL
             SELECT datetime(created_at, 'localtime'), 'Photo uploaded: ' || title
               FROM photos WHERE project_id = :p
             UNION ALL
             SELECT datetime(si.submitted_at, 'localtime'), s.company_name || ' submitted invoice ' || si.invoice_number
               FROM subcontractor_invoices si
               JOIN project_assignments pa ON pa.assignment_id = si.assignment_id
               JOIN subcontractors s ON s.subcontractor_id = pa.subcontractor_id
               WHERE pa.project_id = :p
           ) WHERE at IS NOT NULL ORDER BY at DESC LIMIT :n""", {"p": project_id, "n": limit}).fetchall()


def update_project(project_id, data):
    """Save the Edit Project form (already validated). The client is managed on the Clients page."""
    db = get_db()
    with db:
        db.execute(
            """UPDATE projects SET name = ?, project_type = ?, description = ?, address = ?,
                      project_manager_id = ?, status = ?, budget_amount = ?, progress_percent = ?,
                      start_date = ?, due_date = ?
               WHERE project_id = ?""",
            (data["name"], data["project_type"], data.get("description") or None, data["address"] or None,
             data["manager_id"], data["status"], data["budget"],
             100 if data["status"] == "Completed" else data["progress"],
             data.get("start_date") or None, data.get("due_date") or None, project_id))


def search_everything(text, limit=20):
    """Header search (employee): projects, clients, invoices, estimates and subcontractors whose
    names, numbers or contact details contain the text (case-insensitive)."""
    like = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    db = get_db()

    def find(sql):
        return db.execute(sql.replace("~", "LIKE :q ESCAPE '\\'"), {"q": like, "n": limit}).fetchall()

    return {
        "projects": find("""SELECT p.project_id, p.name, p.project_number, p.status, c.name AS client_name
                            FROM projects p JOIN clients c ON c.client_id = p.client_id
                            WHERE p.name ~ OR p.project_number ~ OR c.name ~ OR COALESCE(p.address, '') ~
                            ORDER BY p.name LIMIT :n"""),
        "clients": find("""SELECT client_id, name, company, email, phone, status FROM clients
                           WHERE name ~ OR COALESCE(company, '') ~ OR COALESCE(email, '') ~ OR COALESCE(phone, '') ~
                           ORDER BY name LIMIT :n"""),
        "invoices": find("""SELECT i.invoice_id, i.invoice_number, i.status, i.total_amount, i.due_date,
                                  p.name AS project_name, c.name AS client_name
                            FROM invoices i JOIN projects p ON p.project_id = i.project_id
                            JOIN clients c ON c.client_id = p.client_id
                            WHERE i.invoice_number ~ OR p.name ~ OR c.name ~
                            ORDER BY i.invoice_id DESC LIMIT :n"""),
        "estimates": find("""SELECT e.estimate_id, e.estimate_number, e.title, e.status, e.total_amount,
                                   c.name AS client_name
                             FROM estimates e JOIN clients c ON c.client_id = e.client_id
                             WHERE e.estimate_number ~ OR e.title ~ OR c.name ~
                             ORDER BY e.estimate_id DESC LIMIT :n"""),
        "subcontractors": find("""SELECT subcontractor_id, company_name, contact_name, trade, status FROM subcontractors
                                  WHERE company_name ~ OR COALESCE(contact_name, '') ~ OR COALESCE(trade, '') ~
                                        OR COALESCE(email, '') ~
                                  ORDER BY company_name LIMIT :n"""),
    }


def get_visible_file(table, file_id, user_id, role):
    """One document/photo if this login may see it, otherwise None."""
    key = _FILE_TABLES[table][0]
    for row in _visible_files(table, user_id, role):
        if row[key] == file_id:
            return row
    return None


def add_document(project_id, user_id, document_type, original_filename, stored_filename):
    db = get_db()
    with db:
        return db.execute(
            """INSERT INTO documents (project_id, uploaded_by, document_type, original_filename, file_path)
               VALUES (?, ?, ?, ?, ?)""",
            (project_id, user_id, document_type, original_filename, stored_filename)).lastrowid


def add_photo(project_id, user_id, title, original_filename, stored_filename):
    db = get_db()
    with db:
        return db.execute(
            """INSERT INTO photos (project_id, uploaded_by, title, original_filename, file_path)
               VALUES (?, ?, ?, ?, ?)""",
            (project_id, user_id, title, original_filename, stored_filename)).lastrowid


def delete_file_record(table, file_id):
    """Deletes the row and returns its stored file name (or None) so the caller can remove the file."""
    key = _FILE_TABLES[table][0]
    db = get_db()
    row = db.execute(f"SELECT file_path FROM {table} WHERE {key} = ?", (file_id,)).fetchone()
    if row is None:
        return None
    with db:
        db.execute(f"DELETE FROM {table} WHERE {key} = ?", (file_id,))
    return row["file_path"]


# ---------------------------------------------------------------------
# Client and subcontractor portals (step 8)
# ---------------------------------------------------------------------
# Every function takes the logged-in user's id and only returns that user's records.

def client_for_user(user_id):
    return get_db().execute("SELECT * FROM clients WHERE user_id = ?", (user_id,)).fetchone()


def subcontractor_for_user(user_id):
    return get_db().execute("SELECT * FROM subcontractors WHERE user_id = ?", (user_id,)).fetchone()


def portal_projects(user_id, role):
    allowed = accessible_project_ids(user_id, role)
    return [project for project in get_projects() if allowed is None or project["project_id"] in allowed]


def portal_project(project_id, user_id, role):
    """The project if this login may see it, otherwise None."""
    allowed = accessible_project_ids(user_id, role)
    if allowed is not None and project_id not in allowed:
        return None
    return get_project(project_id)


# ----- Client: estimates and invoices -----
def client_estimates(user_id):
    """Estimates for this client's account, without drafts (those are still being written)."""
    client = client_for_user(user_id)
    if client is None:
        return []
    return [e for e in get_estimates() if e["client_id"] == client["client_id"] and e["status"] != "Draft"]


def client_decide_estimate(user_id, estimate_id, decision):
    """Client approves or rejects an estimate that was sent to them."""
    estimate = next((e for e in client_estimates(user_id) if e["estimate_id"] == estimate_id), None)
    if estimate is None:
        raise RuleError("Estimate not found.", 404)
    if estimate["status"] != "Sent":
        raise RuleError("This estimate has already been answered.", 409)
    return set_estimate_status(estimate_id, "Approved" if decision == "approve" else "Rejected")


def client_invoices(user_id):
    allowed = accessible_project_ids(user_id, "client")
    return [i for i in get_invoices() if i["project_id"] in allowed and i["status"] != "Draft"]


def client_invoice(user_id, invoice_id):
    return next((i for i in client_invoices(user_id) if i["invoice_id"] == invoice_id), None)


# ----- Subcontractor: tasks and invoices -----
def subcontractor_update_task(user_id, task_id, status):
    task = get_task(task_id)
    if task["project_id"] not in accessible_project_ids(user_id, "subcontractor"):
        raise RuleError("Task not found.", 404)
    if status not in TASK_STATUSES:
        raise RuleError("Choose a valid status.")
    return set_task_status(task_id, status)


_SUB_INVOICE_SELECT = """
    SELECT si.*, si.sub_invoice_id AS id, date(si.submitted_at, 'localtime') AS submitted_date, p.project_id, p.name AS project_name, s.subcontractor_id,
           s.company_name, s.contact_name, c.name AS category_name, u.name AS reviewed_by_name
    FROM subcontractor_invoices si
    JOIN project_assignments pa ON pa.assignment_id = si.assignment_id
    JOIN projects p ON p.project_id = pa.project_id
    JOIN subcontractors s ON s.subcontractor_id = pa.subcontractor_id
    LEFT JOIN cost_categories c ON c.category_id = si.category_id
    LEFT JOIN users u ON u.id = si.reviewed_by
"""


def get_subcontractor_invoices(subcontractor_id=None, project_id=None):
    sql, params = _SUB_INVOICE_SELECT + " WHERE 1 = 1", []
    if subcontractor_id is not None:
        sql += " AND s.subcontractor_id = ?"
        params.append(subcontractor_id)
    if project_id is not None:
        sql += " AND p.project_id = ?"
        params.append(project_id)
    sql += " ORDER BY CASE si.status WHEN 'Pending Approval' THEN 0 ELSE 1 END, si.submitted_at DESC"
    return get_db().execute(sql, params).fetchall()


def get_subcontractor_invoice(sub_invoice_id):
    return get_db().execute(_SUB_INVOICE_SELECT + " WHERE si.sub_invoice_id = ?", (sub_invoice_id,)).fetchone()


def subcontractor_assignment(user_id, project_id):
    return get_db().execute(
        """SELECT pa.assignment_id FROM project_assignments pa
           JOIN subcontractors s ON s.subcontractor_id = pa.subcontractor_id
           WHERE s.user_id = ? AND pa.project_id = ?""", (user_id, project_id)).fetchone()


def submit_subcontractor_invoice(assignment_id, data):
    db = get_db()
    with db:
        return db.execute(
            """INSERT INTO subcontractor_invoices (assignment_id, category_id, invoice_number, description, amount,
                                                  original_filename, file_path)
               VALUES (?, (SELECT category_id FROM cost_categories WHERE name = 'Subcontractor'), ?, ?, ?, ?, ?)""",
            (assignment_id, data["invoice_number"], data["description"] or None, data["amount"],
             data.get("original_filename"), data.get("file_path"))).lastrowid


# status an employee can move a subcontractor invoice to, from its current status
SUB_INVOICE_TRANSITIONS = {
    "Pending Approval": ("Approved", "Rejected"),
    "Approved": ("Paid", "Pending Approval"),
    "Rejected": ("Pending Approval",),
    "Paid": ("Approved",),
}


def review_subcontractor_invoice(sub_invoice_id, new_status, reviewer_id):
    invoice = get_subcontractor_invoice(sub_invoice_id)
    if invoice is None:
        raise RuleError("Invoice not found.", 404)
    if new_status not in SUB_INVOICE_TRANSITIONS.get(invoice["status"], ()):
        raise RuleError(f"Can't change a {invoice['status'].lower()} invoice to {new_status.lower()}.", 409)
    db = get_db()
    with db:
        db.execute(
            """UPDATE subcontractor_invoices SET status = ?, reviewed_by = ?, reviewed_at = datetime('now')
               WHERE sub_invoice_id = ?""", (new_status, reviewer_id, sub_invoice_id))
    return get_subcontractor_invoice(sub_invoice_id)

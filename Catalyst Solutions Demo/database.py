"""
Database helpers for the Buff Bison Construction Portal (MySQL).

- Works with MySQL 8, Amazon RDS for MySQL and MySQL-compatible hosts (TiDB Cloud).
- Connection settings come from environment variables (see BACKEND.md / .env.example):
  MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE, MYSQL_SSL, MYSQL_SSL_CA,
  MYSQL_POOL_SIZE, APP_TIMEZONE.
- get_db() gives each request one connection from a small pool; it goes back to the pool
  at the end of the request. Pools are per server instance, which suits Vercel's functions.
- Queries are written with "?" placeholders (or ":name" with a dict). The Connection
  wrapper below turns them into MySQL's %s / %(name)s, so the query code stays readable.
- Rows work like dictionaries and tuples at once: row["name"], row[0] and dict(row) all work.
  DECIMAL comes back as float and DATE/DATETIME as "YYYY-MM-DD" / "YYYY-MM-DD HH:MM:SS"
  strings, which is what the templates, JSON API and JavaScript expect.
- init_app(app) creates the tables from schema.sql the first time (empty database);
  seed_if_empty() loads the sample data once.
- `flask --app app reset-demo-data` wipes the business tables and reloads the sample
  data (user accounts are kept).

Query functions for each page live further down, so app.py routes stay short.
"""
import datetime as _dt
from decimal import Decimal
import os
import re
import threading
from zoneinfo import ZoneInfo

import click
import mysql.connector
from mysql.connector import errors as mysql_errors
from mysql.connector import pooling
from flask import g

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_FILE = os.path.join(PROJECT_DIR, "schema.sql")

# Tables cleared by reset-demo-data (user accounts are kept).
BUSINESS_TABLES = (
    "uploaded_files", "document_attachments", "documents", "photos", "tasks", "subcontractor_invoices", "project_assignments", "project_budget_items",
    "receipts", "invoice_line_items", "invoices", "projects",
    "estimate_line_items", "estimates", "subcontractors", "clients", "cost_categories",
)
ALL_TABLES = ("users",) + BUSINESS_TABLES

PROJECT_STATUSES = ("Planning", "In Progress", "On Hold", "Completed")

IntegrityError = mysql_errors.IntegrityError   # duplicate key, foreign key problems


# ---------------------------------------------------------------------
# Settings and time zone
# ---------------------------------------------------------------------
def _env_flag(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def connection_settings():
    """MySQL connection settings from environment variables."""
    settings = {
        "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USER", "catalyst_app"),
        "password": os.environ.get("MYSQL_PASSWORD", ""),
        "database": os.environ.get("MYSQL_DATABASE", "catalyst_demo"),
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
        "connection_timeout": 10,
        "autocommit": True,           # each statement commits; `with db:` groups a transaction
        "use_pure": True,             # the pure-Python driver: no compiler needed on Windows or Vercel
    }
    if _env_flag("MYSQL_SSL"):
        # Hosted MySQL (TiDB Cloud, Amazon RDS) needs TLS. TiDB uses public certificates
        # (certifi's list works); for RDS, set MYSQL_SSL_CA to AWS's RDS certificate bundle.
        ca = os.environ.get("MYSQL_SSL_CA", "").strip()
        if not ca:
            import certifi
            ca = certifi.where()
        elif not os.path.isabs(ca):
            ca = os.path.join(PROJECT_DIR, ca)
        settings.update(ssl_ca=ca, ssl_verify_cert=True, ssl_verify_identity=True)
    return settings


APP_TIMEZONE = ZoneInfo(os.environ.get("APP_TIMEZONE", "America/Chicago"))


def local_now():
    """Current time in the app's time zone (Houston by default), whatever the server's clock says."""
    return _dt.datetime.now(APP_TIMEZONE)


def local_today():
    return local_now().date()


def _utc_offset():
    """e.g. "-06:00": used as the MySQL session time zone, so NOW()/CURDATE() and the
    DATETIME defaults are in the app's local time."""
    minutes = int(local_now().utcoffset().total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


# ---------------------------------------------------------------------
# Rows and results (simple, uniform results for all query code)
# ---------------------------------------------------------------------
def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, _dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, bytearray):
        return bytes(value)
    return value


class Row(tuple):
    """A result row: row[0], row["column"], dict(row) and row.keys() all work."""

    def __new__(cls, names, values):
        row = super().__new__(cls, (_plain(v) for v in values))
        row._names = names
        row._index = {name: i for i, name in enumerate(names)}
        return row

    def __getitem__(self, key):
        if isinstance(key, str):
            return tuple.__getitem__(self, self._index[key])
        return tuple.__getitem__(self, key)

    def keys(self):
        return list(self._names)

    def get(self, key, default=None):
        return self[key] if key in self._index else default


class Result:
    def __init__(self, rows, lastrowid, rowcount):
        self._rows = rows
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


_NAMED_PARAMETER = re.compile(r"(?<![\w:]):([A-Za-z_]\w*)")
_translations = {}


def _translate(sql, named):
    """'?' -> '%s' (or ':name' -> '%(name)s'), and a literal % becomes %%."""
    key = (sql, named)
    if key not in _translations:
        text = sql.replace("%", "%%")
        text = _NAMED_PARAMETER.sub(r"%(\1)s", text) if named else text.replace("?", "%s")
        _translations[key] = text
    return _translations[key]


class Connection:
    """Wraps one MySQL connection. `with db:` runs the block as one transaction."""

    def __init__(self, raw):
        self.raw = raw
        self._depth = 0

    def execute(self, sql, params=None):
        if params:
            named = isinstance(params, dict)
            sql, params = _translate(sql, named), (params if named else tuple(params))
        else:
            params = None
        cursor = self.raw.cursor()
        try:
            cursor.execute(sql, params)
            rows = []
            if cursor.description:
                names = tuple(cursor.column_names)
                rows = [Row(names, values) for values in cursor.fetchall()]
            return Result(rows, cursor.lastrowid, cursor.rowcount)
        finally:
            cursor.close()

    def executemany(self, sql, seq_of_params):
        for params in seq_of_params:
            self.execute(sql, params)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def __enter__(self):
        if self._depth == 0:
            self.raw.start_transaction()
        self._depth += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self._depth -= 1
        if self._depth == 0:
            if exc_type is None:
                self.raw.commit()
            else:
                self.raw.rollback()
        return False

    def close(self):
        try:
            if self.raw.in_transaction:
                self.raw.rollback()
        except mysql_errors.Error:
            pass
        self.raw.close()   # a pooled connection goes back to the pool


# ---------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------
_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                size = max(1, min(int(os.environ.get("MYSQL_POOL_SIZE", "3")), 32))
                _pool = pooling.MySQLConnectionPool(
                    pool_name="buffbison", pool_size=size, pool_reset_session=True, **connection_settings())
    return _pool


def connect():
    """A connection from the pool (or a one-off connection when all pooled ones are busy).
    Close it to give it back."""
    try:
        raw = _get_pool().get_connection()   # reconnects automatically if the server dropped it
    except mysql_errors.PoolError:
        raw = mysql.connector.connect(**connection_settings())
    raw.autocommit = True
    cursor = raw.cursor()
    try:
        cursor.execute(f"SET time_zone = '{_utc_offset()}'")
    finally:
        cursor.close()
    return Connection(raw)


def get_db():
    """Connection for the current request (opened once, reused, returned at the end)."""
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


# ---------------------------------------------------------------------
# Schema, sample data and reset
# ---------------------------------------------------------------------
def init_app(app):
    """Registers the request teardown and CLI commands, and creates any missing tables."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(reset_demo_data_command)
    app.cli.add_command(init_db_command)
    create_database_if_missing()
    connection = connect()
    try:
        existing = {row[0] for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()")}
        if not set(ALL_TABLES) <= {name.lower() for name in existing}:
            create_tables(connection)
    finally:
        connection.close()


def create_database_if_missing():
    """Hosted MySQL (e.g. TiDB Cloud) starts with only a "test" database: create MYSQL_DATABASE
    the first time, so there is nothing to set up by hand."""
    settings = connection_settings()
    name = settings.pop("database")
    raw = mysql.connector.connect(**settings)
    try:
        cursor = raw.cursor()
        cursor.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (name,))
        if cursor.fetchone() is None:
            safe = name.replace("`", "``")
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{safe}` "
                           "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.close()
    finally:
        raw.close()


def create_tables(connection):
    """Runs schema.sql (every statement is CREATE TABLE IF NOT EXISTS)."""
    with open(SCHEMA_FILE, encoding="utf-8") as schema:
        text = "\n".join(line.split("--", 1)[0] for line in schema.read().splitlines())
    for statement in text.split(";"):
        if statement.strip():
            connection.execute(statement)


def seed_if_empty():
    """Loads the sample data into a brand-new database (needs the demo logins to exist)."""
    from seed_data import load_demo_client_estimate, load_sample_data

    connection = connect()
    try:
        with connection:
            if connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
                load_sample_data(connection)
            load_demo_client_estimate(connection)   # once (skips if it is already there)
    finally:
        connection.close()


@click.command("init-db")
def init_db_command():
    """Create any missing tables and load the sample data into an empty database."""
    connection = connect()
    try:
        create_tables(connection)
    finally:
        connection.close()
    seed_if_empty()
    click.echo("Database ready.")


@click.command("reset-demo-data")
def reset_demo_data_command():
    """Delete all business data and reload the sample data (keeps user accounts)."""
    reset_business_data()
    click.echo("Sample data reloaded.")


def reset_business_data():
    """Delete all business data and reload the sample data (keeps user accounts).
    Used by `flask reset-demo-data` and by the automated tests (tests/support.py)."""
    from seed_data import load_sample_data

    connection = connect()
    try:
        connection.execute("SET FOREIGN_KEY_CHECKS = 0")
        try:
            for table in BUSINESS_TABLES:
                connection.execute(f"TRUNCATE TABLE {table}")   # also restarts the id counters
        finally:
            connection.execute("SET FOREIGN_KEY_CHECKS = 1")
        with connection:
            load_sample_data(connection)
    finally:
        connection.close()


# ---------------------------------------------------------------------
# Uploaded files (stored in MySQL, step 14)
# ---------------------------------------------------------------------
# Records keep a stored name (e.g. "3f2a...c1.pdf") in their file_path column; the bytes
# live in uploaded_files under that name.
def save_file(stored_name, data):
    save_file_with(get_db(), stored_name, data)


def save_file_with(connection, stored_name, data):
    """Same as save_file, on a given connection (used by tools/sqlite_to_mysql.py)."""
    connection.execute("INSERT INTO uploaded_files (stored_name, content, size_bytes) VALUES (?, ?, ?)",
                       (stored_name, data, len(data)))


def read_file(stored_name):
    """The file's bytes, or None if there is no such file."""
    if not stored_name:
        return None
    row = get_db().execute("SELECT content FROM uploaded_files WHERE stored_name = ?", (stored_name,)).fetchone()
    return row[0] if row else None


def delete_files(*stored_names):
    for name in stored_names:
        if name:
            get_db().execute("DELETE FROM uploaded_files WHERE stored_name = ?", (name,))


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
            "VALUES ('pending', ?, ?, ?, ?, NOW())",
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
            "UPDATE invoices SET status = ?, paid_at = CASE WHEN ? = 'Paid' THEN CURDATE() END "
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
            "SELECT COUNT(*) FROM invoices WHERE status = 'Unpaid' AND due_date < CURDATE()"),
    }
    open_projects = db.execute(
        _PROJECT_SELECT + " WHERE p.status != 'Completed' "
        "ORDER BY CASE p.status WHEN 'In Progress' THEN 0 WHEN 'Planning' THEN 1 ELSE 2 END, "
        "p.due_date IS NULL, p.due_date"
    ).fetchall()

    # Recent activity is built from the timestamps already stored on each record.
    events = db.execute(
        """
        SELECT created_at AS at, CONCAT('Estimate ', estimate_number, ' created: ', title) AS text
          FROM estimates
        UNION ALL
        SELECT issue_date, CONCAT('Invoice ', i.invoice_number, ' sent: ', p.name)
          FROM invoices i JOIN projects p ON p.project_id = i.project_id WHERE i.status != 'Draft'
        UNION ALL
        SELECT paid_at, CONCAT('Invoice ', invoice_number, ' paid ($', FORMAT(total_amount, 2), ')')
          FROM invoices WHERE paid_at IS NOT NULL
        UNION ALL
        SELECT created_at, CONCAT('Project ', name, ' created',
               CASE WHEN estimate_id IS NOT NULL THEN ' from an estimate' ELSE '' END)
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
           r.amount AS amount, r.receipt_filename AS receipt_name,
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
            "SELECT project_id AS id, name, budget_amount AS budget FROM projects ORDER BY name")],
        "categories": [r[0] for r in db.execute(
            "SELECT name FROM cost_categories WHERE is_active = 1 ORDER BY category_id")],
        "estimates": [dict(r) for r in db.execute(
            """SELECT b.project_id, c.name AS category, b.estimated_amount AS estimated_amount
               FROM project_budget_items b JOIN cost_categories c ON c.category_id = b.category_id""")],
        "expenses": get_expenses() + approved_subcontractor_costs(),
    }


def approved_subcontractor_costs(project_id=None):
    """Approved/paid subcontractor invoices, shaped like expenses (read-only on Job Costs).
    Projects' Actual Cost already includes them, so Job Costs shows them too."""
    sql = """SELECT CONCAT('sub-', si.sub_invoice_id) AS id, pa.project_id, DATE(si.submitted_at) AS expense_date,
                    CONCAT(s.company_name, ' invoice ', si.invoice_number) AS description,
                    COALESCE(c.name, 'Subcontractor') AS category, si.amount AS amount,
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


def get_client_projects(client_id):
    return get_db().execute(
        "SELECT * FROM projects WHERE client_id = ? ORDER BY created_at DESC, project_id DESC",
        (client_id,)).fetchall()


def delete_client(client_id):
    db = get_db()
    with db:
        if get_client(client_id) is None:
            raise RuleError("Client not found.", 404)
        linked = db.execute(
            """SELECT 1 FROM projects WHERE client_id = ?
               UNION ALL SELECT 1 FROM estimates WHERE client_id = ? LIMIT 1""",
            (client_id, client_id)
        ).fetchone()
        if linked:
            raise RuleError("This client has projects or estimates and cannot be deleted. Edit their status to Inactive instead.", 409)
        db.execute("DELETE FROM clients WHERE client_id = ?", (client_id,))


def format_phone(value):
    value = str(value or '').strip()
    if not all(char in '0123456789+().- ' for char in value):
        return value
    digits = ''.join(char for char in value if char in '0123456789')
    prefix = ''
    if len(digits) == 11 and digits.startswith('1'):
        prefix, digits = '+1 ', digits[1:]
    if len(digits) == 10:
        return f'{prefix}({digits[:3]}) {digits[3:6]}-{digits[6:]}'
    return value


def save_client(data, client_id=None):
    db = get_db()
    values = (data["name"], data["company"] or None, data["email"] or None, format_phone(data["phone"]) or None,
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
        """SELECT s.*, COUNT(pa.assignment_id) AS project_count, GROUP_CONCAT(p.name ORDER BY pa.assignment_id SEPARATOR ', ') AS project_names
           FROM subcontractors s
           LEFT JOIN project_assignments pa ON pa.subcontractor_id = s.subcontractor_id
           LEFT JOIN projects p ON p.project_id = pa.project_id
           GROUP BY s.subcontractor_id ORDER BY s.contact_name"""
    ).fetchall()
    return rows


def get_subcontractor(subcontractor_id):
    return get_db().execute("SELECT * FROM subcontractors WHERE subcontractor_id = ?", (subcontractor_id,)).fetchone()


def delete_subcontractor(subcontractor_id):
    db = get_db()
    with db:
        if get_subcontractor(subcontractor_id) is None:
            raise RuleError("Subcontractor not found.", 404)
        if db.execute(
            """SELECT 1 FROM subcontractor_invoices si
               JOIN project_assignments pa ON pa.assignment_id = si.assignment_id
               WHERE pa.subcontractor_id = ? LIMIT 1""", (subcontractor_id,)
        ).fetchone():
            raise RuleError("This subcontractor has invoice history and cannot be deleted. Edit their status to Inactive instead.", 409)
        db.execute("DELETE FROM project_assignments WHERE subcontractor_id = ?", (subcontractor_id,))
        db.execute("DELETE FROM subcontractors WHERE subcontractor_id = ?", (subcontractor_id,))


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
                   VALUES (?, ?, 'Active', CURDATE())""", (project_id, subcontractor_id))
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
                     DATE({alias}.created_at) AS date_added
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
             SELECT created_at AS at, 'Project created' AS text
               FROM projects WHERE project_id = :p
             UNION ALL
             SELECT issue_date, CONCAT('Invoice ', invoice_number, ' sent')
               FROM invoices WHERE project_id = :p AND status != 'Draft'
             UNION ALL
             SELECT paid_at, CONCAT('Invoice ', invoice_number, ' paid')
               FROM invoices WHERE project_id = :p AND paid_at IS NOT NULL
             UNION ALL
             SELECT created_at, CONCAT(document_type, ' uploaded: ', original_filename)
               FROM documents WHERE project_id = :p
             UNION ALL
             SELECT created_at, CONCAT('Photo uploaded: ', title)
               FROM photos WHERE project_id = :p
             UNION ALL
             SELECT si.submitted_at, CONCAT(s.company_name, ' submitted invoice ', si.invoice_number)
               FROM subcontractor_invoices si
               JOIN project_assignments pa ON pa.assignment_id = si.assignment_id
               JOIN subcontractors s ON s.subcontractor_id = pa.subcontractor_id
               WHERE pa.project_id = :p
           ) AS events WHERE at IS NOT NULL ORDER BY at DESC LIMIT :n""", {"p": project_id, "n": limit}).fetchall()


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
    # "!" is the escape character, so a typed % or _ is matched literally.
    like = "%" + text.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
    db = get_db()

    def find(sql):
        return db.execute(sql.replace("~", "LIKE :q ESCAPE '!'"), {"q": like, "n": limit}).fetchall()

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


def get_document_attachments(document_id):
    return get_db().execute("SELECT * FROM document_attachments WHERE document_id = ? ORDER BY attachment_id",
                            (document_id,)).fetchall()


def remove_document_attachment(document_id, attachment_id):
    db = get_db()
    with db:
        if attachment_id == 0:
            row = db.execute("SELECT file_path FROM documents WHERE document_id = ?", (document_id,)).fetchone()
            if row is None or not row['file_path']:
                raise RuleError('Attachment not found.', 404)
            next_file = db.execute("SELECT * FROM document_attachments WHERE document_id = ? ORDER BY attachment_id LIMIT 1",
                                   (document_id,)).fetchone()
            db.execute("UPDATE documents SET file_path = ?, attachment_filename = ? WHERE document_id = ?",
                       (next_file['file_path'] if next_file else None,
                        next_file['original_filename'] if next_file else None, document_id))
            if next_file:
                db.execute("DELETE FROM document_attachments WHERE attachment_id = ?", (next_file['attachment_id'],))
        else:
            row = db.execute("SELECT file_path FROM document_attachments WHERE document_id = ? AND attachment_id = ?",
                             (document_id, attachment_id)).fetchone()
            if row is None:
                raise RuleError('Attachment not found.', 404)
            db.execute("DELETE FROM document_attachments WHERE attachment_id = ?", (attachment_id,))
    return row['file_path']


def update_document(document_id, name, document_type, project_id, attachments=(), uploaded_by=None):
    db = get_db()
    with db:
        current = db.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,)).fetchone()
        primary = current['file_path']
        primary_name = current['attachment_filename'] or current['original_filename']
        for original, stored in attachments:
            if not primary:
                primary = stored
                primary_name = original
            else:
                db.execute("INSERT INTO document_attachments (document_id, original_filename, file_path) VALUES (?, ?, ?)",
                           (document_id, original, stored))
        db.execute("""UPDATE documents SET original_filename = ?, document_type = ?, project_id = ?,
                      file_path = ?, attachment_filename = ?, uploaded_by = COALESCE(?, uploaded_by)
                      WHERE document_id = ?""",
                   (name, document_type, project_id, primary, primary_name, uploaded_by, document_id))


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
    SELECT si.*, si.sub_invoice_id AS id, DATE(si.submitted_at) AS submitted_date, p.project_id, p.name AS project_name, s.subcontractor_id,
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
            """UPDATE subcontractor_invoices SET status = ?, reviewed_by = ?, reviewed_at = NOW()
               WHERE sub_invoice_id = ?""", (new_status, reviewer_id, sub_invoice_id))
    return get_subcontractor_invoice(sub_invoice_id)

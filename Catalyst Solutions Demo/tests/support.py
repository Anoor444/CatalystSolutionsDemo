"""Shared setup for the backend tests.

The app runs against a separate MySQL test database and a temporary folder for uploads,
so running the tests never touches your real data. The test database is
MYSQL_TEST_DATABASE (default "catalyst_test"); its name must end in "_test", and it is
dropped and created again at the start of every run. Connection settings (host, user,
password, TLS) are the same ones the app uses: environment variables or the .env file.
Every test starts from fresh sample data, so tests don't depend on each other or on their order.

Run every test from the `Catalyst Solutions Demo` folder:
    python -m unittest discover -s tests -v
"""
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))


def _prepare_test_database():
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_DIR / ".env")
    except ImportError:
        pass
    name = os.environ.get("MYSQL_TEST_DATABASE", "catalyst_test")
    if not re.fullmatch(r"\w+_test", name):
        raise RuntimeError(f"MYSQL_TEST_DATABASE must be a plain name ending in _test (got {name!r}); "
                           "the tests drop and recreate it.")
    import mysql.connector
    import database as db_module

    settings = db_module.connection_settings()
    settings.pop("database")
    try:
        connection = mysql.connector.connect(**settings)
    except mysql.connector.Error as error:
        raise RuntimeError(f"Can't connect to MySQL for the tests ({error}). Check MYSQL_HOST/USER/PASSWORD "
                           "in your environment or .env file.") from error
    try:
        cursor = connection.cursor()
        cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
        cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.close()
    finally:
        connection.close()
    # Permanent for this test run: every connection (pooled or not) uses the test database.
    os.environ["MYSQL_DATABASE"] = name


if "app" not in sys.modules:
    _prepare_test_database()
    _instance = tempfile.TemporaryDirectory(prefix="buffbison-test-")
    os.environ["APP_INSTANCE_PATH"] = _instance.name
    import app as _app_module  # noqa: F401
from app import app, user_database  # noqa: E402
import database  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

app.testing = True
# Safety nets: never run against real data.
assert database.connection_settings()["database"].endswith("_test"), "Tests must use a *_test database"
assert "buffbison-" in app.instance_path, f"Tests must use a temporary instance folder, not {app.instance_path}"

EMPLOYEE = ("demo@buffbison.com", "Buffbison123")
CLIENT = ("demo.client@buffbison.com", "ClientDemo123!")
SUBCONTRACTOR = ("demo.subcontractor@buffbison.com", "SubcontractorDemo123!")


def reset_demo_passwords():
    """Set the demo passwords back to their documented values (test_password_change changes them)."""
    for email, password in (EMPLOYEE, CLIENT, SUBCONTRACTOR):
        user = user_database.find_by_email(email)
        user_database.update_password(user["id"], user["password_hash"], generate_password_hash(password))


class BackendTestCase(unittest.TestCase):
    """Base class: fresh sample data before every test, plus login and database helpers.
    Subclasses that need their own setUp should call super().setUp() first."""

    @classmethod
    def setUpClass(cls):
        reset_demo_passwords()

    def setUp(self):
        database.reset_business_data()

    # ---- logging in -------------------------------------------------
    @staticmethod
    def form_token(client, path):
        """The csrf_token hidden field on a server-rendered form page."""
        page = client.get(path)
        match = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True))
        assert match, f"No form token on {path} (status {page.status_code})"
        return match.group(1)

    def login(self, account):
        client = app.test_client()
        email, password = account
        response = client.post("/login", data={"email": email, "password": password,
                                                "csrf_token": self.form_token(client, "/login")})
        self.assertEqual(response.status_code, 302, f"login failed for {email}")
        return client

    @staticmethod
    def download(client, url):
        """Body of a file response (and close it, so the file on disk is released)."""
        response = client.get(url)
        try:
            return response.data
        finally:
            response.close()

    def api_headers(self, client):
        """Header for JSON API calls (the page's <meta name="csrf-token">)."""
        page = client.get("/estimates").get_data(as_text=True)
        return {"X-CSRF-Token": re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)}

    # ---- reading the database directly -------------------------------
    def query(self, sql, *params):
        connection = database.connect()
        try:
            return [tuple(row) for row in connection.execute(sql, params).fetchall()]
        finally:
            connection.close()

    def value(self, sql, *params):
        rows = self.query(sql, *params)
        return rows[0][0] if rows else None

    def project_id(self, name):
        return self.value("SELECT project_id FROM projects WHERE name = ?", name)

    def assertBlocked(self, response, message=None):
        """Logged-in users without the right role are redirected or refused."""
        self.assertIn(response.status_code, (302, 401, 403), message)

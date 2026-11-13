"""Account storage, selectable with DB_BACKEND=sqlite or mysql."""

import os
import sqlite3
from contextlib import closing, contextmanager


class DuplicateEmailError(Exception):
    pass


class UserDatabase:
    def __init__(self, sqlite_path):
        self.sqlite_path = sqlite_path
        self.backend = os.environ.get("DB_BACKEND", "sqlite").lower()
        if self.backend not in {"sqlite", "mysql"}:
            raise ValueError("DB_BACKEND must be sqlite or mysql.")

    @contextmanager
    def connection(self):
        if self.backend == "mysql":
            import mysql.connector

            database = mysql.connector.connect(
                host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
                port=int(os.environ.get("MYSQL_PORT", "3306")),
                user=os.environ.get("MYSQL_USER", "catalyst_app"),
                password=os.environ.get("MYSQL_PASSWORD", ""),
                database=os.environ.get("MYSQL_DATABASE", "catalyst_demo"),
                charset="utf8mb4",
                connection_timeout=10,
            )
        else:
            database = sqlite3.connect(self.sqlite_path)
            database.row_factory = sqlite3.Row
            database.execute("PRAGMA foreign_keys = ON")
        try:
            yield database
            database.commit()
        except Exception:
            database.rollback()
            raise
        finally:
            database.close()

    def execute(self, database, sql, parameters=()):
        if self.backend == "mysql":
            cursor = database.cursor(dictionary=True)
            sql = sql.replace("?", "%s")
        else:
            cursor = database.cursor()
        try:
            cursor.execute(sql, parameters)
            return cursor.fetchone() if cursor.description else None
        finally:
            cursor.close()

    def initialize(self, demo_users):
        if self.backend == "mysql":
            schema = """
                CREATE TABLE IF NOT EXISTS users (
                    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) COLLATE utf8mb4_unicode_ci NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role ENUM('employee', 'subcontractor', 'client') NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
            """
        else:
            schema = """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('employee', 'subcontractor', 'client'))
                )
            """
        with self.connection() as database:
            self.execute(database, schema)
            cursor = database.cursor()
            try:
                cursor.execute("SHOW COLUMNS FROM users" if self.backend == "mysql" else "PRAGMA table_info(users)")
                columns = {row[0] if self.backend == "mysql" else row[1] for row in cursor.fetchall()}
            finally:
                cursor.close()
            for column in ("first_name", "last_name"):
                if column not in columns:
                    self.execute(database, f"ALTER TABLE users ADD COLUMN {column} VARCHAR(255) NOT NULL DEFAULT ''")
            for email, name, password_hash, role in demo_users:
                if not self.execute(database, "SELECT id FROM users WHERE email = ?", (email,)):
                    self.execute(
                        database,
                        "INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, ?, ?)",
                        (email, name, password_hash, role),
                    )
            cursor = database.cursor()
            try:
                cursor.execute("SELECT id, name FROM users WHERE first_name = ''")
                names = cursor.fetchall()
            finally:
                cursor.close()
            for user_id, name in names:
                first, _, last = name.partition(" ")
                self.execute(database, "UPDATE users SET first_name = ?, last_name = ? WHERE id = ?", (first, last, user_id))

    def find_by_email(self, email):
        with self.connection() as database:
            return self.execute(
                database,
                "SELECT id, email, name, password_hash, role FROM users WHERE email = ?",
                (email,),
            )

    def create_user(self, email, name, password_hash, role):
        first, _, last = name.partition(" ")
        try:
            with self.connection() as database:
                self.execute(
                    database,
                    "INSERT INTO users (email, name, password_hash, role, first_name, last_name) VALUES (?, ?, ?, ?, ?, ?)",
                    (email, name, password_hash, role, first, last),
                )
        except Exception as error:
            if isinstance(error, sqlite3.IntegrityError) or getattr(error, "errno", None) == 1062:
                raise DuplicateEmailError from error
            raise

    def find_by_id(self, user_id):
        with self.connection() as database:
            return self.execute(
                database,
                "SELECT id, email, name, password_hash, role FROM users WHERE id = ?",
                (user_id,),
            )

    def update_password(self, user_id, current_hash, new_hash):
        """Update only if the verified password has not changed in the meantime."""
        with self.connection() as database:
            cursor = database.cursor()
            try:
                sql = "UPDATE users SET password_hash = ? WHERE id = ? AND password_hash = ?"
                if self.backend == "mysql":
                    sql = sql.replace("?", "%s")
                cursor.execute(sql, (new_hash, user_id, current_hash))
                return cursor.rowcount == 1
            finally:
                cursor.close()

    def migrate_sqlite(self, source_path, replace_existing=False):
        """Copy account hashes without deleting or modifying the source database."""
        if self.backend != "mysql":
            raise ValueError("Set DB_BACKEND=mysql before migrating accounts.")
        from pathlib import Path

        with closing(sqlite3.connect(Path(source_path).resolve().as_uri() + "?mode=ro", uri=True)) as source:
            users = source.execute("SELECT email, name, password_hash, role FROM users").fetchall()
        imported = skipped = 0
        with self.connection() as database:
            for email, name, password_hash, role in users:
                first, _, last = name.partition(" ")
                existing = self.execute(database, "SELECT id FROM users WHERE email = ?", (email,))
                if existing:
                    if not replace_existing:
                        skipped += 1
                        continue
                    self.execute(
                        database,
                        "UPDATE users SET name = ?, password_hash = ?, role = ?, first_name = ?, last_name = ? WHERE id = ?",
                        (name, password_hash, role, first, last, existing["id"]),
                    )
                else:
                    self.execute(
                        database,
                        "INSERT INTO users (email, name, password_hash, role, first_name, last_name) VALUES (?, ?, ?, ?, ?, ?)",
                        (email, name, password_hash, role, first, last),
                    )
                imported += 1
        return imported, skipped

"""Login accounts, stored in the same MySQL database as everything else (the `users` table
in schema.sql). Projects, documents, portals and so on join this same table."""

from contextlib import contextmanager

from flask import has_app_context

import database


class DuplicateEmailError(Exception):
    pass


class UserDatabase:
    @contextmanager
    def connection(self):
        """The request's connection when there is one, otherwise a short-lived one (startup, CLI)."""
        if has_app_context():
            yield database.get_db()
            return
        db = database.connect()
        try:
            yield db
        finally:
            db.close()

    def initialize(self, demo_users):
        """Adds the demo logins if they are missing, and fills first/last names for older rows."""
        with self.connection() as db, db:
            for email, name, password_hash, role in demo_users:
                if not db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
                    first, _, last = name.partition(" ")
                    db.execute(
                        "INSERT INTO users (email, name, password_hash, role, first_name, last_name) VALUES (?, ?, ?, ?, ?, ?)",
                        (email, name, password_hash, role, first, last),
                    )
            for user_id, name in db.execute("SELECT id, name FROM users WHERE first_name = ''").fetchall():
                first, _, last = name.partition(" ")
                db.execute("UPDATE users SET first_name = ?, last_name = ? WHERE id = ?", (first, last, user_id))

    def find_by_email(self, email):
        with self.connection() as db:
            return db.execute(
                "SELECT id, email, name, password_hash, role FROM users WHERE email = ?", (email,)
            ).fetchone()

    def find_by_id(self, user_id):
        with self.connection() as db:
            return db.execute(
                "SELECT id, email, name, password_hash, role FROM users WHERE id = ?", (user_id,)
            ).fetchone()

    def create_user(self, email, name, password_hash, role):
        first, _, last = name.partition(" ")
        try:
            with self.connection() as db, db:
                db.execute(
                    "INSERT INTO users (email, name, password_hash, role, first_name, last_name) VALUES (?, ?, ?, ?, ?, ?)",
                    (email, name, password_hash, role, first, last),
                )
        except database.IntegrityError as error:
            if getattr(error, "errno", None) == 1062:   # duplicate email
                raise DuplicateEmailError from error
            raise

    def update_password(self, user_id, current_hash, new_hash):
        """Update only if the verified password has not changed in the meantime."""
        with self.connection() as db, db:
            result = db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ? AND password_hash = ?",
                (new_hash, user_id, current_hash),
            )
            return result.rowcount == 1

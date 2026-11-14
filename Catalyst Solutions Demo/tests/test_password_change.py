"""Use a temporary account database; never change the running demo accounts."""
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_instance = tempfile.TemporaryDirectory(prefix="buffbison-password-test-")
with patch.dict(os.environ, {"APP_INSTANCE_PATH": _instance.name, "DB_BACKEND": "sqlite"}):
    from app import app, user_database
from werkzeug.security import check_password_hash, generate_password_hash


class PasswordChangeTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.accounts = [
            ("demo@buffbison.com", "Buffbison123", "employee"),
            ("demo.client@buffbison.com", "ClientDemo123!", "client"),
            ("demo.subcontractor@buffbison.com", "SubcontractorDemo123!", "subcontractor"),
        ]
        for email, password, _ in self.accounts:
            user = user_database.find_by_email(email)
            user_database.update_password(user["id"], user["password_hash"], generate_password_hash(password))

    def token(self, path):
        page = self.client.get(path)
        self.assertEqual(page.status_code, 200)
        return re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]

    def login(self, email, password):
        return self.client.post("/login", data={"email": email, "password": password, "csrf_token": self.token("/login")})

    def change(self, current, new="ReplacementPassword123!", confirmation=None):
        return self.client.post("/settings/change-password", data={
            "csrf_token": self.token("/settings/change-password"),
            "current_password": current, "new_password": new,
            "confirm_password": new if confirmation is None else confirmation,
        })

    def test_all_roles_can_change_only_their_own_password(self):
        for email, password, role in self.accounts:
            with self.subTest(role=role):
                self.client = app.test_client()
                self.assertEqual(self.login(email, password).status_code, 302)
                self.assertIn('/settings/change-password', self.client.get('/settings').text)
                self.assertEqual(self.change(password).status_code, 302)
                self.assertIn('changed successfully', self.client.get('/settings').text)
                user = user_database.find_by_email(email)
                self.assertTrue(check_password_hash(user['password_hash'], 'ReplacementPassword123!'))
                self.assertFalse(check_password_hash(user['password_hash'], password))
                self.client = app.test_client()
                self.assertEqual(self.login(email, password).status_code, 200)
                self.assertEqual(self.login(email, 'ReplacementPassword123!').status_code, 302)

    def test_invalid_changes_leave_password_unchanged(self):
        email, password, _ = self.accounts[0]
        self.login(email, password)
        cases = [
            ('wrong', 'ReplacementPassword123!', None, 'current password is incorrect'),
            (password, 'short', None, 'between 12 and 128'),
            (password, 'x' * 129, None, 'between 12 and 128'),
            (password, 'ReplacementPassword123!', 'DifferentPassword123!', 'do not match'),
            (password, password, None, 'different from your current'),
        ]
        for current, new, confirmation, message in cases:
            self.assertIn(message, self.change(current, new, confirmation).text)
            self.assertTrue(check_password_hash(user_database.find_by_email(email)['password_hash'], password))
        # Check password reuse for the client account as well.
        self.client = app.test_client()
        email, password, _ = self.accounts[1]
        self.login(email, password)
        self.assertIn('different from your current', self.change(password, password).text)

    def test_authentication_and_csrf_required(self):
        self.assertEqual(self.client.get('/settings/change-password').status_code, 302)
        self.login(*self.accounts[0][:2])
        self.assertEqual(self.client.post('/settings/change-password', data={}).status_code, 400)

    def test_employee_change_does_not_change_client(self):
        email, password, _ = self.accounts[1]
        original = user_database.find_by_email(email)['password_hash']
        self.login(*self.accounts[0][:2])
        self.change(self.accounts[0][1])
        self.assertEqual(user_database.find_by_email(email)['password_hash'], original)


if __name__ == '__main__':
    try:
        unittest.main()
    finally:
        _instance.cleanup()

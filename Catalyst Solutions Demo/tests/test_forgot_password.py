"""Forgot password: reset links, email sending and the reset page (backend step 12)."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from support import CLIENT, EMPLOYEE, BackendTestCase, app, reset_demo_passwords, user_database

app_module = sys.modules["app"]
NEW_PASSWORD = "BrandNewPassword123!"


class ForgotPasswordTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        reset_demo_passwords()
        app_module._recent_reset_emails.clear()
        self.browser = app.test_client()

    def request_link(self, email):
        """Submit the Forgot Password form; returns (page text, links that would have been emailed)."""
        sent = []
        with patch.object(app_module, "send_password_reset", side_effect=lambda user, link: sent.append((user["email"], link))):
            page = self.browser.post("/forgot-password", data={
                "csrf_token": self.form_token(self.browser, "/forgot-password"), "email": email}).get_data(as_text=True)
        return page, sent

    def reset(self, link, password=NEW_PASSWORD, confirmation=None):
        path = link.replace("http://localhost", "")
        return self.browser.post(path, data={"csrf_token": self.form_token(self.browser, path),
                                             "new_password": password,
                                             "confirm_password": password if confirmation is None else confirmation})

    def can_log_in(self, email, password):
        client = app.test_client()
        response = client.post("/login", data={"email": email, "password": password,
                                                "csrf_token": self.form_token(client, "/login")})
        return response.status_code == 302

    def test_login_page_links_here(self):
        self.assertIn('href="/forgot-password"', self.browser.get("/login").get_data(as_text=True))

    def test_same_message_whether_or_not_the_account_exists(self):
        known_page, known_sent = self.request_link(EMPLOYEE[0].upper())  # any capitalization
        unknown_page, unknown_sent = self.request_link("nobody@example.com")
        self.assertIn("If an account uses that email", known_page)
        self.assertIn("If an account uses that email", unknown_page)
        self.assertEqual(len(known_sent), 1)
        self.assertEqual(known_sent[0][0], EMPLOYEE[0])
        self.assertIn("/reset-password/", known_sent[0][1])
        self.assertEqual(unknown_sent, [])

    def test_form_validation(self):
        self.assertIn("Enter your email address", self.request_link("   ")[0])
        self.assertIn("Enter a valid email address", self.request_link("not-an-email")[0])
        self.assertEqual(self.browser.post("/forgot-password", data={"email": EMPLOYEE[0]}).status_code, 400, "CSRF required")

    def test_one_email_per_minute_per_address(self):
        self.assertEqual(len(self.request_link(EMPLOYEE[0])[1]), 1)
        page, sent = self.request_link(EMPLOYEE[0])
        self.assertEqual(sent, [], "second request within a minute sends nothing")
        self.assertIn("If an account uses that email", page, "but the page looks the same")

    def test_full_reset_then_sign_in(self):
        link = self.request_link(CLIENT[0])[1][0][1]
        form = self.browser.get(link).get_data(as_text=True)
        self.assertIn("Choose a new password for", form)
        self.assertIn(CLIENT[0], form)
        self.assertIn('name="referrer" content="no-referrer"', form)
        response = self.reset(link)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/login"))
        self.assertIn("Your password has been reset", self.browser.get("/login").get_data(as_text=True))
        self.assertTrue(self.can_log_in(CLIENT[0], NEW_PASSWORD))
        self.assertFalse(self.can_log_in(CLIENT[0], CLIENT[1]), "old password no longer works")

    def test_link_works_only_once(self):
        link = self.request_link(EMPLOYEE[0])[1][0][1]
        self.reset(link)
        again = self.browser.get(link)
        self.assertEqual(again.status_code, 400)
        self.assertIn("already been used", again.get_data(as_text=True))
        path = link.replace("http://localhost", "")
        posted = self.browser.post(path, data={"csrf_token": self.form_token(self.browser, "/login"),
                                               "new_password": "AnotherPassword123!", "confirm_password": "AnotherPassword123!"})
        self.assertEqual(posted.status_code, 400)
        self.assertTrue(self.can_log_in(EMPLOYEE[0], NEW_PASSWORD))

    def test_link_stops_working_when_password_changes_another_way(self):
        link = self.request_link(EMPLOYEE[0])[1][0][1]
        user = user_database.find_by_email(EMPLOYEE[0])
        user_database.update_password(user["id"], user["password_hash"], "changed-elsewhere")
        self.assertIn("already been used", self.browser.get(link).get_data(as_text=True))

    def test_expired_and_tampered_links(self):
        link = self.request_link(EMPLOYEE[0])[1][0][1]
        with patch.object(app_module, "RESET_LINK_MINUTES", -1):
            self.assertIn("expired", self.browser.get(link).get_data(as_text=True))
        tampered = self.browser.get(link[:-3] + ("aaa" if not link.endswith("aaa") else "bbb"))
        self.assertEqual(tampered.status_code, 400)
        self.assertIn("not valid", tampered.get_data(as_text=True))
        self.assertIn("not valid", self.browser.get("/reset-password/nonsense").get_data(as_text=True))

    def test_new_password_rules(self):
        link = self.request_link(EMPLOYEE[0])[1][0][1]
        self.assertIn("between 12 and 128", self.reset(link, "short").get_data(as_text=True))
        self.assertIn("do not match", self.reset(link, NEW_PASSWORD, "SomethingElse123!").get_data(as_text=True))
        self.assertIn("different from your current", self.reset(link, EMPLOYEE[1]).get_data(as_text=True))
        path = link.replace("http://localhost", "")
        self.assertEqual(self.browser.post(path, data={"new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD}).status_code,
                         400, "CSRF required")
        self.assertTrue(self.can_log_in(EMPLOYEE[0], EMPLOYEE[1]), "nothing changed")


class ResetEmailDeliveryTests(BackendTestCase):
    user = {"name": "Demo Employee", "email": "demo@buffbison.com"}

    def test_without_mail_server_the_link_is_printed(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"MAIL_SERVER": ""}), redirect_stdout(output):
            app_module.send_password_reset(self.user, "http://localhost/reset-password/abc")
        self.assertIn("http://localhost/reset-password/abc", output.getvalue())

    def test_with_mail_server_it_is_emailed(self):
        smtp = MagicMock()
        settings = {"MAIL_SERVER": "smtp.example.com", "MAIL_PORT": "587", "MAIL_USERNAME": "team@example.com",
                    "MAIL_PASSWORD": "app-password", "MAIL_FROM": "Buff Bison <team@example.com>"}
        with patch.dict(os.environ, settings), patch.object(app_module.smtplib, "SMTP", return_value=smtp) as connect:
            app_module.send_password_reset(self.user, "http://localhost/reset-password/abc")
        connect.assert_called_once_with("smtp.example.com", 587, timeout=15)
        session = smtp.__enter__.return_value
        session.starttls.assert_called_once()
        session.login.assert_called_once_with("team@example.com", "app-password")
        message = session.send_message.call_args[0][0]
        self.assertEqual(message["To"], "demo@buffbison.com")
        self.assertIn("http://localhost/reset-password/abc", message.get_content())

    def test_mail_failure_is_logged_not_shown(self):
        with patch.dict(os.environ, {"MAIL_SERVER": "smtp.example.com"}), \
                patch.object(app_module.smtplib, "SMTP", side_effect=OSError("connection refused")), \
                self.assertLogs(app.logger, level="ERROR") as logs:
            app_module.send_password_reset(self.user, "http://localhost/reset-password/abc")
        self.assertIn("failed", logs.output[0])


if __name__ == "__main__":
    unittest.main()

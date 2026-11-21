"""Schedule (tasks API, step 4) and Job Costs (expenses + receipt uploads, step 5)."""
import io
import json
import re
import unittest
from unittest.mock import patch

from support import CLIENT, EMPLOYEE, BackendTestCase, app
import api

GOOD_TASK = {"name": "Paint trim", "project_id": 1, "description": "Two coats", "assigned_to": "Finish Crew B",
             "start_date": "", "due_date": "2026-12-01", "priority": "Low", "status": "Not Started"}


class TaskApiTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.login(EMPLOYEE)
        self.headers = self.api_headers(self.client)

    def test_login_and_csrf_required(self):
        self.assertEqual(app.test_client().get("/api/tasks").status_code, 401)
        self.assertEqual(self.client.post("/api/tasks", json={}).status_code, 400)

    def test_sample_tasks(self):
        self.assertEqual(len(self.client.get("/api/tasks").get_json()), 18)

    def test_validation(self):
        bad = self.client.post("/api/tasks", headers=self.headers, json={
            "name": "", "project_id": 999, "due_date": "x", "priority": "Urgent", "status": "Done"})
        self.assertEqual(bad.status_code, 400)
        self.assertGreaterEqual(len(bad.get_json()["errors"]), 5)
        backwards = self.client.post("/api/tasks", headers=self.headers,
                                     json=dict(GOOD_TASK, start_date="2026-12-10", due_date="2026-12-01"))
        self.assertEqual(backwards.status_code, 400)

    def test_create_edit_complete_delete(self):
        response = self.client.post("/api/tasks", json=GOOD_TASK, headers=self.headers)
        task = response.get_json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(task["project_name"], "Riverstone Kitchen Remodel")
        self.assertIsNone(task["start_date"])
        edited = self.client.put(f"/api/tasks/{task['id']}", headers=self.headers,
                                 json=dict(task, name="Paint trim and doors", priority="High")).get_json()
        self.assertEqual(edited["priority"], "High")
        done = self.client.patch(f"/api/tasks/{task['id']}/status", json={"status": "Completed"}, headers=self.headers)
        self.assertEqual(done.get_json()["status"], "Completed")
        self.assertEqual(self.client.delete(f"/api/tasks/{task['id']}", headers=self.headers).status_code, 204)
        self.assertEqual(self.client.delete(f"/api/tasks/{task['id']}", headers=self.headers).status_code, 404)

    def test_dashboard_and_project_page_use_the_same_tasks(self):
        tasks = self.client.get("/api/tasks").get_json()
        open_count = sum(1 for t in tasks if t["status"] != "Completed")
        self.assertIn(f">{open_count}<", self.client.get("/dashboard").get_data(as_text=True).replace(" ", ""))
        riverstone = sum(1 for t in tasks if t["project_id"] == 1)
        self.assertIn(f"Schedule ({riverstone})", self.client.get("/project/1").get_data(as_text=True))


class JobCostTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.login(EMPLOYEE)
        self.headers = self.api_headers(self.client)
        page = self.client.get("/job-costs").get_data(as_text=True)
        self.data = json.loads(re.search(r'<script id="jc-data" type="application/json">(.*?)</script>', page, re.S).group(1))
        self.pearland = self.project_id("Pearland Patio Extension")

    def expense(self, method, url, **fields):
        form = {"project_id": self.pearland, "expense_date": "2026-11-14", "description": "Concrete delivery",
                "category": "Materials", "amount": "1250.75"}
        form.update(fields)
        return self.client.open(url, method=method, headers=self.headers, data=form, content_type="multipart/form-data")

    def files_stored(self):
        """Uploaded files kept in the database (the name is from when they were on disk)."""
        return self.stored_files()

    def test_sample_costs_match_projects_page(self):
        ids = {p["name"]: p["id"] for p in self.data["projects"]}
        self.assertEqual(len(self.data["categories"]), 7)
        for name, actual, estimated in (("Riverstone Kitchen Remodel", 31200, 48500), ("Katy Home Addition", 44600, 92000),
                                        ("Spring Office Build-Out", 81500, 124000), ("Clear Lake Deck Restoration", 15950, 16400)):
            with self.subTest(project=name):
                self.assertEqual(round(sum(e["amount"] for e in self.data["expenses"] if e["project_id"] == ids[name]), 2), actual)
                self.assertEqual(round(sum(e["estimated_amount"] for e in self.data["estimates"] if e["project_id"] == ids[name]), 2), estimated)
        projects_page = self.client.get("/projects").get_data(as_text=True)
        self.assertIn("$31,200", projects_page)
        self.assertIn("$44,600", projects_page)

    def test_access_and_validation(self):
        self.assertIn(self.login(CLIENT).post("/api/expenses").status_code, (400, 403))
        self.assertEqual(self.client.post("/api/expenses", data={}).status_code, 400, "CSRF header required")
        bad = self.expense("POST", "/api/expenses", description="", category="Nope", amount="-5")
        self.assertEqual(bad.status_code, 400)
        self.assertGreaterEqual(len(bad.get_json()["errors"]), 3)
        exe = self.expense("POST", "/api/expenses", receipt=(io.BytesIO(b"MZ..."), "virus.exe"))
        self.assertEqual(exe.status_code, 400)
        # Same rule as a real 4 MB+ file, but with the limit lowered so the test stays small and fast.
        with patch.object(api, "MAX_RECEIPT_BYTES", 1024):
            big = self.expense("POST", "/api/expenses", receipt=(io.BytesIO(b"x" * 2048), "big.pdf"))
        self.assertEqual(big.status_code, 400)
        self.assertIn("MB or smaller", big.get_json()["error"])

    def test_receipt_upload_replace_and_delete(self):
        before = self.files_stored()
        pdf = b"%PDF-1.4 test receipt"
        response = self.expense("POST", "/api/expenses", receipt=(io.BytesIO(pdf), "Concrete invoice.pdf"))
        expense = response.get_json()
        self.assertEqual(response.status_code, 201)
        self.assertTrue(expense["has_receipt"])
        self.assertEqual(self.download(self.client, f"/api/expenses/{expense['id']}/receipt"), pdf)
        self.assertEqual(self.login(CLIENT).get(f"/api/expenses/{expense['id']}/receipt").status_code, 403)
        self.assertEqual(app.test_client().get(f"/api/expenses/{expense['id']}/receipt").status_code, 401)
        first_file = self.files_stored() - before
        self.assertEqual(len(first_file), 1)

        replaced = self.expense("PUT", f"/api/expenses/{expense['id']}", amount="1300",
                                receipt=(io.BytesIO(b"\x89PNG new"), "photo.png")).get_json()
        self.assertEqual((replaced["receipt_name"], replaced["amount"]), ("photo.png", 1300))
        second_file = self.files_stored() - before
        self.assertEqual(len(second_file), 1)
        self.assertNotEqual(second_file, first_file, "old receipt file removed")

        kept = self.expense("PUT", f"/api/expenses/{expense['id']}", amount="1300", category="Labor").get_json()
        self.assertEqual((kept["receipt_name"], kept["category"]), ("photo.png", "Labor"))
        self.assertIn("$15,500", self.client.get("/projects").get_data(as_text=True), "14,200 + 1,300")

        self.assertEqual(self.client.delete(f"/api/expenses/{expense['id']}", headers=self.headers).status_code, 204)
        self.assertEqual(self.files_stored(), before)
        self.assertEqual(self.client.get(f"/api/expenses/{expense['id']}/receipt").status_code, 404)

    def test_sample_receipt_without_file(self):
        sample = next(e for e in self.data["expenses"] if e["receipt_name"] and not e["has_receipt"])
        self.assertEqual(self.client.get(f"/api/expenses/{sample['id']}/receipt").status_code, 404)


if __name__ == "__main__":
    unittest.main()

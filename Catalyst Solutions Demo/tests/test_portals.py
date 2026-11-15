"""Client and subcontractor portals, and subcontractor invoice approval (backend step 8)."""
import io
import unittest

from support import CLIENT, EMPLOYEE, SUBCONTRACTOR, BackendTestCase, app
import database

EMPLOYEE_ONLY_PAGES = ("/estimates", "/invoices", "/job-costs", "/subcontractors", "/clients", "/schedule")


class ClientPortalTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.login(CLIENT)
        self.client_id = self.value("SELECT client_id FROM clients WHERE user_id = "
                                    "(SELECT id FROM users WHERE email = ?)", CLIENT[0])

    def test_pages_render(self):
        for url in ("/dashboard", "/projects", "/client/my-projects", "/client/estimates", "/client/invoices"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_only_own_projects(self):
        own = {r[0] for r in self.query("SELECT name FROM projects WHERE client_id = ?", self.client_id)}
        others = {r[0] for r in self.query("SELECT name FROM projects WHERE client_id <> ?", self.client_id)}
        page = self.client.get("/client/my-projects").get_data(as_text=True)
        self.assertTrue(own)
        self.assertTrue(all(name in page for name in own))
        self.assertFalse(any(name in page for name in others))
        other = self.value("SELECT project_id FROM projects WHERE client_id <> ?", self.client_id)
        mine = self.value("SELECT project_id FROM projects WHERE client_id = ?", self.client_id)
        self.assertEqual(self.client.get(f"/project/{other}").status_code, 404)
        self.assertEqual(self.client.get(f"/project/{mine}").status_code, 200)

    def test_estimates_never_show_drafts_or_other_clients(self):
        page = self.client.get("/client/estimates").get_data(as_text=True)
        hidden = self.query("SELECT estimate_number FROM estimates WHERE status = 'Draft' OR client_id <> ?", self.client_id)
        self.assertFalse(any(number in page for (number,) in hidden))

    def test_approve_sent_estimate_once(self):
        eid = self.value("SELECT estimate_id FROM estimates WHERE client_id = ? AND status = 'Sent'", self.client_id)
        token = self.form_token(self.client, "/client/estimates")
        self.assertEqual(self.client.post(f"/client/estimates/{eid}/decision", data={"decision": "approve"}).status_code, 400,
                         "CSRF required")
        self.client.post(f"/client/estimates/{eid}/decision", data={"csrf_token": token, "decision": "approve"})
        self.assertEqual(self.value("SELECT status FROM estimates WHERE estimate_id = ?", eid), "Approved")
        self.client.post(f"/client/estimates/{eid}/decision", data={"csrf_token": token, "decision": "reject"})
        self.assertEqual(self.value("SELECT status FROM estimates WHERE estimate_id = ?", eid), "Approved", "decided only once")

    def test_cannot_decide_another_clients_estimate(self):
        eid = self.value("SELECT estimate_id FROM estimates WHERE client_id <> ? AND status = 'Sent'", self.client_id)
        token = self.form_token(self.client, "/client/estimates")
        self.client.post(f"/client/estimates/{eid}/decision", data={"csrf_token": token, "decision": "approve"})
        self.assertEqual(self.value("SELECT status FROM estimates WHERE estimate_id = ?", eid), "Sent")

    def test_invoices_and_printable_page(self):
        mine = self.query("""SELECT i.invoice_id, i.invoice_number FROM invoices i JOIN projects p ON p.project_id = i.project_id
                             WHERE p.client_id = ? AND i.status <> 'Draft'""", self.client_id)
        hidden = self.query("""SELECT i.invoice_id, i.invoice_number FROM invoices i JOIN projects p ON p.project_id = i.project_id
                               WHERE p.client_id <> ? OR i.status = 'Draft'""", self.client_id)
        page = self.client.get("/client/invoices").get_data(as_text=True)
        self.assertTrue(all(number in page for _, number in mine))
        self.assertFalse(any(number in page for _, number in hidden))
        printable = self.client.get(f"/client/invoices/{mine[0][0]}").get_data(as_text=True)
        self.assertIn(mine[0][1], printable)
        self.assertIn("window.print", printable)
        self.assertEqual(self.client.get(f"/client/invoices/{hidden[0][0]}").status_code, 404)

    def test_employee_pages_blocked(self):
        for url in EMPLOYEE_ONLY_PAGES + ("/subcontractor/invoices",):
            with self.subTest(url=url):
                self.assertBlocked(self.client.get(url))
        self.assertBlocked(self.client.get("/api/estimates"))


class SubcontractorPortalTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.sub = self.login(SUBCONTRACTOR)
        self.sub_id = self.value("SELECT subcontractor_id FROM subcontractors WHERE user_id = "
                                 "(SELECT id FROM users WHERE email = ?)", SUBCONTRACTOR[0])
        self.memorial = self.project_id("Memorial Bathroom Renovation")
        self.katy = self.project_id("Katy Home Addition")  # not assigned to the demo subcontractor

    def submit(self, **fields):
        form = {"csrf_token": self.form_token(self.sub, "/subcontractor/invoices"), "project_id": str(self.memorial),
                "invoice_number": "T-1", "description": "Tile labor", "amount": "1500.50"}
        form.update(fields)
        return self.sub.post("/subcontractor/invoices", data=form, content_type="multipart/form-data")

    def test_pages_render_and_blocked_pages(self):
        for url in ("/dashboard", "/projects", "/subcontractor/invoices", "/documents", "/photos"):
            with self.subTest(url=url):
                self.assertEqual(self.sub.get(url).status_code, 200)
        for url in EMPLOYEE_ONLY_PAGES + ("/client/estimates", "/client/invoices"):
            with self.subTest(url=url):
                self.assertBlocked(self.sub.get(url))

    def test_only_assigned_projects(self):
        assigned = {r[0] for r in self.query("""SELECT p.name FROM project_assignments a JOIN projects p
                                                ON p.project_id = a.project_id WHERE a.subcontractor_id = ?""", self.sub_id)}
        page = self.sub.get("/projects").get_data(as_text=True)
        self.assertTrue(assigned)
        self.assertTrue(all(name in page for name in assigned))
        self.assertNotIn("Katy Home Addition", page)
        self.assertEqual(self.sub.get(f"/project/{self.katy}").status_code, 404)
        self.assertEqual(self.sub.get(f"/project/{self.memorial}").status_code, 200)

    def test_task_status_updates(self):
        task_id = self.value("SELECT task_id FROM tasks WHERE project_id = ? AND status <> 'Completed'", self.memorial)
        token = self.form_token(self.sub, f"/project/{self.memorial}")
        self.sub.post(f"/project/{self.memorial}/tasks/{task_id}/status", data={"csrf_token": token, "status": "Completed"})
        self.assertEqual(self.value("SELECT status FROM tasks WHERE task_id = ?", task_id), "Completed")
        self.sub.post(f"/project/{self.memorial}/tasks/{task_id}/status", data={"csrf_token": token, "status": "Bogus"})
        self.assertEqual(self.value("SELECT status FROM tasks WHERE task_id = ?", task_id), "Completed", "invalid status ignored")
        other_task = self.value("SELECT task_id FROM tasks WHERE project_id = ?", self.katy)
        before = self.value("SELECT status FROM tasks WHERE task_id = ?", other_task)
        self.sub.post(f"/project/{self.katy}/tasks/{other_task}/status", data={"csrf_token": token, "status": "Completed"})
        self.assertEqual(self.value("SELECT status FROM tasks WHERE task_id = ?", other_task), before, "unassigned project")

    def test_invoice_submission_rules(self):
        self.submit(project_id=str(self.katy), invoice_number="X-1")
        self.assertIsNone(self.value("SELECT 1 FROM subcontractor_invoices WHERE invoice_number = 'X-1'"), "unassigned project")
        self.assertEqual(self.submit(invoice_number="", amount="-5").status_code, 200)
        self.assertIsNone(self.value("SELECT 1 FROM subcontractor_invoices WHERE amount < 0"))
        self.submit(invoice_number="T-2", invoice_file=(io.BytesIO(b"x"), "bad.exe"))
        self.assertIsNone(self.value("SELECT 1 FROM subcontractor_invoices WHERE invoice_number = 'T-2'"), ".exe refused")

    def test_submit_then_employee_reviews(self):
        self.assertEqual(self.submit(invoice_file=(io.BytesIO(b"%PDF t"), "t.pdf")).status_code, 302)
        sid, status, amount = self.query("SELECT sub_invoice_id, status, amount FROM subcontractor_invoices "
                                         "WHERE invoice_number = 'T-1'")[0]
        self.assertEqual((status, amount), ("Pending Approval", 1500.5))
        employee = self.login(EMPLOYEE)
        self.assertEqual(self.download(self.sub, f"/subcontractor-invoices/{sid}/file"), b"%PDF t")
        self.assertEqual(self.download(employee, f"/subcontractor-invoices/{sid}/file"), b"%PDF t")
        self.assertIn(self.login(CLIENT).get(f"/subcontractor-invoices/{sid}/file").status_code, (302, 403, 404))

        token = self.form_token(self.sub, "/subcontractor/invoices")
        self.assertBlocked(self.sub.post(f"/subcontractor-invoices/{sid}/review", data={"csrf_token": token, "status": "Approved"}))
        status = lambda: self.value("SELECT status FROM subcontractor_invoices WHERE sub_invoice_id = ?", sid)
        self.assertEqual(status(), "Pending Approval", "can't approve your own invoice")

        page = employee.get("/subcontractors").get_data(as_text=True)
        self.assertIn('id="sub-invoices"', page)
        self.assertIn("T-1", page)
        token = self.form_token(employee, "/subcontractors")
        employee.post(f"/subcontractor-invoices/{sid}/review", data={"csrf_token": token, "status": "Paid"})
        self.assertEqual(status(), "Pending Approval", "Pending can't jump to Paid")
        response = employee.post(f"/subcontractor-invoices/{sid}/review", data={"csrf_token": token, "status": "Approved"})
        self.assertTrue(response.headers["Location"].endswith("#sub-invoices"))
        self.assertEqual(status(), "Approved")
        with app.app_context():
            costs = database.approved_subcontractor_costs(self.memorial)
            job_costs = database.get_job_cost_data()
        self.assertTrue(any(c["amount"] == 1500.5 and c["read_only"] for c in costs))
        self.assertTrue(any(str(e["id"]) == f"sub-{sid}" for e in job_costs["expenses"]))
        employee.post(f"/subcontractor-invoices/{sid}/review", data={"csrf_token": token, "status": "Paid"})
        self.assertEqual(status(), "Paid")
        self.assertIn(employee.delete(f"/api/expenses/sub-{sid}", headers=self.api_headers(employee)).status_code,
                      (400, 403, 404, 405), "read-only cost can't be deleted")


if __name__ == "__main__":
    unittest.main()

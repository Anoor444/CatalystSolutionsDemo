"""Employee project page tabs and Edit Project (backend step 9)."""
import html
import io
import unittest

from support import CLIENT, EMPLOYEE, SUBCONTRACTOR, BackendTestCase, app
import database


class ProjectPageTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.employee = self.login(EMPLOYEE)
        self.riverstone = self.project_id("Riverstone Kitchen Remodel")

    def test_every_project_shows_its_own_records(self):
        for project_id, name in self.query("SELECT project_id, name FROM projects"):
            with self.subTest(project=name):
                response = self.employee.get(f"/project/{project_id}")
                page = response.get_data(as_text=True)
                self.assertEqual(response.status_code, 200)
                self.assertIn(html.escape(name), page)
                count = lambda table: self.value(f"SELECT COUNT(*) FROM {table} WHERE project_id = ?", project_id)
                self.assertIn(f"Invoices ({count('invoices')})", page)
                self.assertIn(f"Schedule ({count('tasks')})", page)
                self.assertIn(f"Subcontractors ({count('project_assignments')})", page)
                self.assertNotIn("Coming soon", page)

    def test_riverstone_tabs(self):
        page = self.employee.get(f"/project/{self.riverstone}").get_data(as_text=True)
        self.assertIn("Source Estimate", page)
        self.assertIn("EST-1001", page)
        self.assertIn("DS-1001", page)  # pending subcontractor invoice, with Approve
        for (number,) in self.query("SELECT invoice_number FROM invoices WHERE project_id = ?", self.riverstone):
            self.assertIn(number, page)
        other = self.value("SELECT invoice_number FROM invoices WHERE project_id <> ?", self.riverstone)
        self.assertNotIn(other, page)
        self.assertIn(f"/invoices?new=1&amp;project={self.riverstone}", page)
        self.assertIn(f"/job-costs?project={self.riverstone}", page)
        self.assertEqual(self.employee.get("/project/99999").status_code, 404)

    def test_tab_in_address(self):
        page = self.employee.get(f"/project/{self.riverstone}?tab=photos").get_data(as_text=True)
        self.assertIn('id="tab-photos" role="tabpanel" aria-labelledby="tab-btn-photos" class="tab-panel active"', page)
        page = self.employee.get(f"/project/{self.riverstone}?tab=<script>").get_data(as_text=True)
        self.assertIn('id="tab-overview" role="tabpanel" aria-labelledby="tab-btn-overview" class="tab-panel active"', page)

    def test_costs_tab_matches_actual_cost(self):
        with app.app_context():
            for (project_id,) in self.query("SELECT project_id FROM projects"):
                costs, project = database.get_project_costs(project_id), database.get_project(project_id)
                self.assertAlmostEqual(costs["actual_total"], float(project["actual_cost"]), places=2)

    def test_portal_users_keep_their_own_project_page(self):
        client = self.login(CLIENT)
        self.assertEqual(client.get(f"/project/{self.riverstone}").status_code, 200)
        self.assertNotIn("Edit Project", client.get(f"/project/{self.riverstone}").get_data(as_text=True))
        self.assertBlocked(client.get(f"/project/{self.riverstone}/edit"))
        self.assertBlocked(self.login(SUBCONTRACTOR).get(f"/project/{self.riverstone}/edit"))

    def test_uploads_and_deletes_return_to_the_tab(self):
        pearland = self.project_id("Pearland Patio Extension")
        url = f"/documents/upload?project={pearland}&from=project"
        response = self.employee.post(url, content_type="multipart/form-data", data={
            "csrf_token": self.form_token(self.employee, url), "document_type": "Contract", "project_id": str(pearland),
            "document": (io.BytesIO(b"%PDF"), "Patio Contract.pdf")})
        self.assertTrue(response.headers["Location"].endswith(f"/project/{pearland}?tab=documents"))
        self.assertIn(f'href="/project/{pearland}?tab=documents"', self.employee.get(url).get_data(as_text=True), "Cancel")
        did = self.value("SELECT document_id FROM documents WHERE original_filename = 'Patio Contract.pdf'")
        response = self.employee.post(f"/documents/{did}/delete", data={"csrf_token": self.form_token(self.employee, "/documents")},
                                      headers={"Referer": f"http://localhost/project/{pearland}?tab=documents"})
        self.assertTrue(response.headers["Location"].endswith(f"/project/{pearland}?tab=documents"))

        url = f"/photos/upload?project={pearland}&from=project"
        response = self.employee.post(url, content_type="multipart/form-data", data={
            "csrf_token": self.form_token(self.employee, url), "title": "Patio pour", "project_id": str(pearland),
            "photo": (io.BytesIO(b"\x89PNG"), "p.png")})
        self.assertTrue(response.headers["Location"].endswith(f"/project/{pearland}?tab=photos"))

    def test_approval_returns_to_tab_and_ignores_outside_links(self):
        sid = self.value("""SELECT si.sub_invoice_id FROM subcontractor_invoices si JOIN project_assignments pa
                            ON pa.assignment_id = si.assignment_id WHERE pa.project_id = ? AND si.status = 'Pending Approval'""",
                         self.riverstone)
        token = self.form_token(self.employee, f"/project/{self.riverstone}")
        back = f"/project/{self.riverstone}?tab=subcontractors"
        response = self.employee.post(f"/subcontractor-invoices/{sid}/review", data={"csrf_token": token, "status": "Approved", "next": back})
        self.assertTrue(response.headers["Location"].endswith(back))
        self.assertIn("(subcontractor invoice)", self.employee.get(f"/project/{self.riverstone}?tab=costs").get_data(as_text=True))
        for unsafe in ("https://evil.example/x", "/project//evil.example"):
            response = self.employee.post(f"/subcontractor-invoices/{sid}/review", data={"csrf_token": token, "status": "Paid", "next": unsafe})
            self.assertTrue(response.headers["Location"].endswith("/subcontractors#sub-invoices"), unsafe)


class EditProjectTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.employee = self.login(EMPLOYEE)
        self.pid = self.project_id("Pearland Patio Extension")
        self.url = f"/project/{self.pid}/edit"
        self.form = {"csrf_token": self.form_token(self.employee, self.url), "project_name": "Pearland Patio Extension II",
                     "project_type": "Other", "description": "Bigger patio", "address": "", "start_date": "2026-09-01",
                     "end_date": "2026-12-01", "budget": "12345.67", "status": "In Progress", "progress": "40",
                     "manager": str(self.value("SELECT project_manager_id FROM projects WHERE project_id = ?", self.pid))}

    def row(self):
        return self.query("SELECT name, budget_amount, progress_percent, status, due_date FROM projects WHERE project_id = ?", self.pid)[0]

    def test_form_is_prefilled_and_client_is_read_only(self):
        page = self.employee.get(self.url).get_data(as_text=True)
        self.assertIn('value="Pearland Patio Extension"', page)
        self.assertIn('name="progress"', page)
        self.assertNotIn('name="client_name"', page)

    def test_save_without_address(self):
        response = self.employee.post(self.url, data=self.form)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.row(), ("Pearland Patio Extension II", 12345.67, 40, "In Progress", "2026-12-01"))
        self.assertIn("Project updated.", self.employee.get(f"/project/{self.pid}").get_data(as_text=True))

    def test_validation(self):
        page = self.employee.post(self.url, data=dict(self.form, progress="140", end_date="2026-01-01", budget="-5")).get_data(as_text=True)
        self.assertIn("Progress must be", page)
        self.assertIn("End date", page)
        self.assertIn("Budget must", page)
        self.assertEqual(self.row()[0], "Pearland Patio Extension", "nothing saved")
        self.assertEqual(self.employee.post(self.url, data=dict(self.form, csrf_token="x")).status_code, 400)

    def test_completed_saves_at_100_percent(self):
        self.employee.post(self.url, data=dict(self.form, status="Completed", progress="10"))
        self.assertEqual(self.row()[2:4], (100, "Completed"))

    def test_new_project_still_requires_address(self):
        token = self.form_token(self.employee, "/new-project")
        data = {"csrf_token": token, "project_name": "No Address", "project_type": "Roofing", "client_name": "Someone",
                "address": "", "manager": self.form["manager"], "status": "Planning"}
        self.assertIn("Address is required", self.employee.post("/new-project", data=data).get_data(as_text=True))
        self.assertEqual(self.employee.post("/new-project", data=dict(data, address="1 Main St")).status_code, 302)


if __name__ == "__main__":
    unittest.main()

"""Clients and Subcontractors pages (backend step 6)."""
import re
import unittest

from support import CLIENT, EMPLOYEE, BackendTestCase


class DirectoryTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.login(EMPLOYEE)

    def test_sample_lists(self):
        clients = self.client.get("/clients").get_data(as_text=True)
        self.assertEqual(len(re.findall(r'<tr>\s*<td><a class="project-name-link"', clients)), 12)
        self.assertIn("sarah.johnson@example.com", clients)
        subs = self.client.get("/subcontractors").get_data(as_text=True)
        self.assertEqual(subs.count('class="sub-row"'), 11)
        self.assertIn("Has portal login", subs)

    def test_client_validation_keeps_input(self):
        token = self.form_token(self.client, "/clients/new")
        page = self.client.post("/clients/new", data={"csrf_token": token, "client_name": "sarah johnson",
                                                      "email": "bad", "status": "Active"}).get_data(as_text=True)
        self.assertIn("already exists", page)
        self.assertIn("valid email", page)
        self.assertIn('value="sarah johnson"', page)

    def test_add_and_edit_client(self):
        token = self.form_token(self.client, "/clients/new")
        response = self.client.post("/clients/new", data={
            "csrf_token": token, "client_name": "Grace Kim", "company": "Kim Bakery", "email": "grace@kimbakery.example.com",
            "phone": "(713) 555-0300", "address": "9 Elm St", "status": "Active", "notes": "Prefers email"})
        self.assertEqual(response.status_code, 302)
        cid = self.value("SELECT client_id FROM clients WHERE name = 'Grace Kim'")
        form = self.client.get(f"/clients/{cid}/edit").get_data(as_text=True)
        self.assertIn('value="Grace Kim"', form)
        self.assertIn("Prefers email", form)
        self.client.post(f"/clients/{cid}/edit", data={"csrf_token": token, "client_name": "Grace Kim", "company": "Kim Bakery",
                                                      "email": "grace@kimbakery.example.com", "status": "Inactive"})
        self.assertEqual(self.value("SELECT status FROM clients WHERE client_id = ?", cid), "Inactive")
        self.assertEqual(self.client.get("/clients/9999/edit").status_code, 404)

    def test_subcontractor_validation(self):
        token = self.form_token(self.client, "/subcontractors/new")
        page = self.client.post("/subcontractors/new", data={
            "csrf_token": token, "full_name": "", "company": "", "email": "john@millerelectrical.example.com",
            "trade": "", "status": "Active", "project_ids": ["99999"]}).get_data(as_text=True)
        self.assertIn("Full name is required", page)
        self.assertIn("already uses that email", page)

    def test_subcontractor_project_assignments(self):
        token = self.form_token(self.client, "/subcontractors/new")
        katy, pearland = self.project_id("Katy Home Addition"), self.project_id("Pearland Patio Extension")
        form = {"csrf_token": token, "full_name": "Ana Lopez", "company": "Lopez Drywall",
                "email": "ana@lopezdrywall.example.com", "trade": "Drywall", "status": "Active"}
        self.assertEqual(self.client.post("/subcontractors/new", data=dict(form, project_ids=[str(katy), str(pearland)])).status_code, 302)
        sid = self.value("SELECT subcontractor_id FROM subcontractors WHERE contact_name = 'Ana Lopez'")
        assigned = lambda: sorted(r[0] for r in self.query("SELECT project_id FROM project_assignments WHERE subcontractor_id = ?", sid))
        self.assertEqual(assigned(), sorted([katy, pearland]))
        self.client.post(f"/subcontractors/{sid}/edit", data=dict(form, project_ids=[str(katy)]))
        self.assertEqual(assigned(), [katy], "unticked project removed")

    def test_employees_only_and_csrf(self):
        client = self.login(CLIENT)
        self.assertBlocked(client.get("/clients"))
        self.assertBlocked(client.get("/subcontractors/new"))
        self.assertEqual(self.client.post("/clients/new", data={"client_name": "x"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()

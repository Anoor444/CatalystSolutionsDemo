"""Clients and Subcontractors pages (backend step 6)."""
import re
import unittest

from support import CLIENT, EMPLOYEE, SUBCONTRACTOR, BackendTestCase, app, database


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

    def test_add_project_from_client_details(self):
        cid = self.value("SELECT client_id FROM clients WHERE name = 'Sarah Johnson'")
        url = f'/clients/{cid}/edit'
        before = self.value('SELECT COUNT(*) FROM projects WHERE client_id = ?', cid)
        client_count = self.value('SELECT COUNT(*) FROM clients')
        page = self.client.get(url).get_data(as_text=True)
        self.assertIn(f'Associated Projects ({before})', page)
        self.assertIn('Riverstone Kitchen Remodel', page)
        project_url = f'/new-project?client={cid}'
        token = self.form_token(self.client, project_url)
        page = self.client.get(project_url).get_data(as_text=True)
        self.assertIn('value="Sarah Johnson" readonly', page)
        form = {'csrf_token': token, 'project_name': 'Additional Client Project', 'project_type': 'Other',
                'address': '123 Test St', 'status': 'Planning', 'budget': '5000',
                'manager': str(self.value("SELECT id FROM users WHERE role = 'employee' LIMIT 1")),
                'client_name': 'Forged name'}
        invalid = self.client.post(project_url, data=dict(form, project_name='')).get_data(as_text=True)
        self.assertIn(f'action="/new-project?client={cid}"', invalid)
        response = self.client.post(project_url, data=form)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith(url))
        self.assertEqual(self.value('SELECT COUNT(*) FROM clients'), client_count)
        self.assertEqual(self.value('SELECT COUNT(*) FROM projects WHERE client_id = ?', cid), before + 1)
        page = self.client.get(url).get_data(as_text=True)
        self.assertIn(f'Associated Projects ({before + 1})', page)
        self.assertIn('Additional Client Project', page)
        self.assertEqual(self.client.get('/new-project?client=99999').status_code, 404)
        self.assertEqual(self.client.get('/new-project?client=invalid').status_code, 404)

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

    def test_delete_subcontractor_removes_assignments(self):
        token = self.form_token(self.client, "/subcontractors/new")
        self.client.post('/subcontractors/new', data={
            'csrf_token': token, 'full_name': 'Delete Test', 'company': 'Test Company',
            'trade': 'Drywall', 'status': 'Active', 'email': 'delete@example.com',
            'project_ids': [str(self.project_id('Katy Home Addition'))]})
        sid = self.value("SELECT subcontractor_id FROM subcontractors WHERE contact_name = 'Delete Test'")
        url = f'/subcontractors/{sid}/delete'
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 400)
        for account in (CLIENT, SUBCONTRACTOR):
            other = self.login(account)
            other_token = self.form_token(other, '/login')
            self.assertBlocked(other.post(url, data={'csrf_token': other_token}))
        page = self.client.post(url, data={'csrf_token': token}, follow_redirects=True)
        self.assertIn('Subcontractor deleted.', page.get_data(as_text=True))
        self.assertEqual(self.value('SELECT COUNT(*) FROM subcontractors WHERE subcontractor_id = ?', sid), 0)
        self.assertEqual(self.value('SELECT COUNT(*) FROM project_assignments WHERE subcontractor_id = ?', sid), 0)
        self.assertEqual(self.client.post(url, data={'csrf_token': token}).status_code, 404)

    def test_delete_preserves_invoice_history(self):
        sid = self.value('''SELECT pa.subcontractor_id FROM project_assignments pa
                            JOIN subcontractor_invoices si ON si.assignment_id = pa.assignment_id LIMIT 1''')
        before = self.value('SELECT COUNT(*) FROM subcontractor_invoices')
        token = self.form_token(self.client, '/subcontractors')
        page = self.client.post(f'/subcontractors/{sid}/delete', data={'csrf_token': token}, follow_redirects=True)
        self.assertIn('has invoice history', page.get_data(as_text=True))
        self.assertEqual(self.value('SELECT COUNT(*) FROM subcontractors WHERE subcontractor_id = ?', sid), 1)
        self.assertEqual(self.value('SELECT COUNT(*) FROM subcontractor_invoices'), before)

    def test_delete_client(self):
        token = self.form_token(self.client, '/clients')
        self.client.post('/clients/new', data={'csrf_token': token, 'client_name': 'Delete Client', 'status': 'Active'})
        cid = self.value("SELECT client_id FROM clients WHERE name = 'Delete Client'")
        url = f'/clients/{cid}/delete'
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 400)
        for account in (CLIENT, SUBCONTRACTOR):
            other = self.login(account)
            other_token = self.form_token(other, '/login')
            self.assertBlocked(other.post(url, data={'csrf_token': other_token}))
        page = self.client.post(url, data={'csrf_token': token}, follow_redirects=True)
        self.assertIn('Client deleted.', page.get_data(as_text=True))
        self.assertEqual(self.value('SELECT COUNT(*) FROM clients WHERE client_id = ?', cid), 0)
        self.assertEqual(self.client.post(url, data={'csrf_token': token}).status_code, 404)

    def test_delete_client_preserves_projects_and_estimates(self):
        token = self.form_token(self.client, '/clients')
        project_client = self.value('SELECT client_id FROM projects LIMIT 1')
        with app.app_context():
            db = database.get_db()
            with db:
                estimate_client = db.execute("INSERT INTO clients (name) VALUES ('Estimate Only')").lastrowid
                db.execute("INSERT INTO estimates (estimate_number, title, client_id) VALUES ('TEST-DELETE', 'Test', ?)", (estimate_client,))
        for cid in (project_client, estimate_client):
            page = self.client.post(f'/clients/{cid}/delete', data={'csrf_token': token}, follow_redirects=True)
            self.assertIn('has projects or estimates', page.get_data(as_text=True))
            self.assertEqual(self.value('SELECT COUNT(*) FROM clients WHERE client_id = ?', cid), 1)

    def test_employees_only_and_csrf(self):
        client = self.login(CLIENT)
        self.assertBlocked(client.get("/clients"))
        self.assertBlocked(client.get("/subcontractors/new"))
        self.assertEqual(self.client.post("/clients/new", data={"client_name": "x"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()

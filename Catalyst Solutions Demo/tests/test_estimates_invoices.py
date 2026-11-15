"""Estimates and invoices: JSON API rules (backend step 2)."""
import unittest

from support import CLIENT, EMPLOYEE, BackendTestCase, app


class EstimatesApiTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.login(EMPLOYEE)
        self.headers = self.api_headers(self.client)

    def lookups(self):
        return self.client.get("/api/lookups").get_json()

    def new_estimate(self, **changes):
        body = {"title": "Test Job", "client_id": self.lookups()["clients"][0]["client_id"], "status": "Draft",
                "line_items": [{"category_id": 1, "description": "Labor", "quantity": 10, "unit_cost": 85.5},
                               {"category_id": 2, "description": "Tile", "quantity": 3, "unit_cost": 12.333}]}
        body.update(changes)
        return self.client.post("/api/estimates", json=body, headers=self.headers)

    def test_login_and_role_required(self):
        self.assertEqual(app.test_client().get("/api/estimates").status_code, 401)
        self.assertEqual(self.login(CLIENT).get("/api/estimates").status_code, 403)

    def test_sample_data(self):
        estimates = {e["estimate_number"]: e for e in self.client.get("/api/estimates").get_json()}
        self.assertEqual(len(estimates), 11)  # 10 samples + the demo client's estimate
        self.assertEqual(estimates["EST-1001"]["status"], "Converted")
        self.assertEqual(estimates["EST-1001"]["project_number"], "BB-0001")
        self.assertEqual(estimates["EST-1001"]["total_amount"], 48500)
        lookups = self.lookups()
        self.assertEqual((len(lookups["clients"]), len(lookups["categories"]), len(lookups["projects"])), (12, 7, 12))

    def test_csrf_header_required(self):
        response = self.client.post("/api/estimates", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("session", response.get_json()["error"].lower())
        self.assertEqual(self.client.delete("/api/estimates/1008").status_code, 400)

    def test_invalid_estimate_rejected_with_messages(self):
        response = self.client.post("/api/estimates", headers=self.headers, json={
            "title": "", "client_id": 999, "status": "Approved",
            "line_items": [{"description": "", "quantity": 0, "unit_cost": -5, "category_id": 99}]})
        self.assertEqual(response.status_code, 400)
        self.assertGreaterEqual(len(response.get_json()["errors"]), 5)

    def test_server_calculates_totals_and_creator(self):
        response = self.new_estimate(total_amount=1)  # a total sent by the browser is ignored
        estimate = response.get_json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(estimate["total_amount"], 891.99)
        self.assertEqual(estimate["estimate_number"], f"EST-{estimate['estimate_id']}")
        self.assertEqual(estimate["created_by_name"], "Demo Employee")

    def test_status_rules_and_convert_to_project(self):
        estimate = self.new_estimate().get_json()
        eid, cid = estimate["estimate_id"], estimate["client_id"]
        manager = self.lookups()["managers"][0]["user_id"]
        self.assertEqual(self.client.patch(f"/api/estimates/{eid}/status", json={"status": "Approved"},
                                           headers=self.headers).status_code, 409, "draft must be sent first")
        sent = self.client.put(f"/api/estimates/{eid}", headers=self.headers, json={
            "title": "Test Job", "client_id": cid, "status": "Sent",
            "line_items": [{"category_id": 1, "description": "Labor", "quantity": 2, "unit_cost": 100}]}).get_json()
        self.assertEqual((sent["status"], sent["total_amount"]), ("Sent", 200))
        self.assertEqual(self.client.delete(f"/api/estimates/{eid}", headers=self.headers).status_code, 409)
        convert = {"name": "Test Job Project", "project_manager_id": manager, "budget_amount": 200,
                   "start_date": "2026-12-01", "due_date": "2027-01-15"}
        self.assertEqual(self.client.post(f"/api/estimates/{eid}/convert", json=convert,
                                          headers=self.headers).status_code, 409, "convert needs approval")
        self.client.patch(f"/api/estimates/{eid}/status", json={"status": "Approved"}, headers=self.headers)
        self.assertEqual(self.client.post(f"/api/estimates/{eid}/convert", json=dict(convert, due_date="2026-11-01"),
                                          headers=self.headers).status_code, 400, "due before start")
        response = self.client.post(f"/api/estimates/{eid}/convert", json=convert, headers=self.headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["estimate"]["status"], "Converted")
        self.assertEqual(self.client.post(f"/api/estimates/{eid}/convert", json=convert,
                                          headers=self.headers).status_code, 409, "only once")
        self.assertIn("Test Job Project", self.client.get("/projects").get_data(as_text=True))

    def test_only_drafts_can_be_deleted(self):
        before = len(self.client.get("/api/estimates").get_json())
        self.assertEqual(self.client.delete("/api/estimates/1008", headers=self.headers).status_code, 204)
        self.assertEqual(len(self.client.get("/api/estimates").get_json()), before - 1)


class InvoicesApiTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.login(EMPLOYEE)
        self.headers = self.api_headers(self.client)

    def invoice_body(self, **changes):
        body = {"project_id": 3, "issue_date": "2026-11-12", "due_date": "2026-12-12", "status": "Unpaid",
                "line_items": [{"description": "Tile install", "quantity": 120, "unit_price": 12.5}]}
        body.update(changes)
        return body

    def test_sample_invoices(self):
        invoices = self.client.get("/api/invoices").get_json()
        self.assertEqual(len(invoices), 9)
        self.assertEqual(sum(i["total_amount"] for i in invoices if i["status"] == "Unpaid"), 24750)

    def test_due_date_cannot_be_before_issue_date(self):
        response = self.client.post("/api/invoices", json=self.invoice_body(due_date="2026-11-01"), headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_create_pay_and_unpay(self):
        response = self.client.post("/api/invoices", json=self.invoice_body(), headers=self.headers)
        invoice = response.get_json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual((invoice["total_amount"], invoice["client_name"]), (1500, "Emily Davis"))
        iid = invoice["invoice_id"]
        paid = self.client.patch(f"/api/invoices/{iid}/status", json={"status": "Paid"}, headers=self.headers).get_json()
        self.assertEqual(paid["status"], "Paid")
        self.assertTrue(paid["paid_at"])
        self.assertEqual(self.client.put(f"/api/invoices/{iid}", json=self.invoice_body(),
                                         headers=self.headers).status_code, 409, "paid invoices are locked")
        unpaid = self.client.patch(f"/api/invoices/{iid}/status", json={"status": "Unpaid"}, headers=self.headers).get_json()
        self.assertEqual((unpaid["status"], unpaid["paid_at"]), ("Unpaid", None))
        self.assertEqual(self.client.delete(f"/api/invoices/{iid}", headers=self.headers).status_code, 409)

    def test_delete_draft_and_unknown_invoice(self):
        self.assertEqual(self.client.delete("/api/invoices/1048", headers=self.headers).status_code, 204)
        self.assertEqual(self.client.patch("/api/invoices/99999/status", json={"status": "Paid"},
                                           headers=self.headers).status_code, 404)


if __name__ == "__main__":
    unittest.main()

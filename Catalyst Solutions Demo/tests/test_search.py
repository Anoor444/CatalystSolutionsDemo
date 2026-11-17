"""Header search and the demo client's sample estimate (backend step 10)."""
import unittest

from support import CLIENT, EMPLOYEE, SUBCONTRACTOR, BackendTestCase
import database
from seed_data import DEMO_CLIENT_ESTIMATE, load_demo_client_estimate

TITLE = DEMO_CLIENT_ESTIMATE[0]


class DemoClientEstimateTests(BackendTestCase):
    def run_loader_again(self):
        connection = database.connect()
        try:
            with connection:
                load_demo_client_estimate(connection)
        finally:
            connection.close()

    def test_added_once_in_sent_status(self):
        rows = self.query("""SELECT e.estimate_id, e.estimate_number, e.status, e.total_amount, c.name
                             FROM estimates e JOIN clients c ON c.client_id = e.client_id WHERE e.title = ?""", TITLE)
        self.assertEqual(len(rows), 1)
        estimate_id, number, status, total, client = rows[0]
        self.assertEqual((number, status, client), (f"EST-{estimate_id}", "Sent", "Sarah Johnson"))
        self.assertAlmostEqual(total, 2800 + 24 * 85 + 950)
        self.assertEqual(self.value("SELECT COUNT(*) FROM estimate_line_items WHERE estimate_id = ?", estimate_id), 3)

    def test_not_added_again(self):
        self.run_loader_again()
        self.assertEqual(self.value("SELECT COUNT(*) FROM estimates WHERE title = ?", TITLE), 1)

    def test_client_can_approve_it_and_it_stays_approved(self):
        client = self.login(CLIENT)
        number, estimate_id = self.query("SELECT estimate_number, estimate_id FROM estimates WHERE title = ?", TITLE)[0]
        page = client.get("/client/estimates").get_data(as_text=True)
        self.assertIn(number, page)
        self.assertIn("Approve", page)
        self.assertIn(number, client.get("/dashboard").get_data(as_text=True), "listed under Needs Your Attention")
        client.post(f"/client/estimates/{estimate_id}/decision",
                    data={"csrf_token": self.form_token(client, "/client/estimates"), "decision": "approve"})
        self.run_loader_again()
        self.assertEqual(self.query("SELECT status FROM estimates WHERE title = ?", TITLE), [("Approved",)])

    def test_next_estimate_number_follows_it(self):
        employee = self.login(EMPLOYEE)
        demo_id = self.value("SELECT estimate_id FROM estimates WHERE title = ?", TITLE)
        response = employee.post("/api/estimates", headers=self.api_headers(employee), json={
            "title": "After demo", "client_id": 1, "status": "Draft",
            "line_items": [{"description": "x", "quantity": 1, "unit_cost": 5, "category_id": 1}]})
        created = response.get_json()
        self.assertEqual(response.status_code, 201)
        self.assertGreater(created["estimate_id"], demo_id)
        self.assertEqual(created["estimate_number"], f"EST-{created['estimate_id']}")


class SearchTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.employee = self.login(EMPLOYEE)

    def search(self, text):
        response = self.employee.get("/search", query_string={"q": text})
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_dashboard_box_is_a_real_search_form(self):
        page = self.employee.get("/dashboard").get_data(as_text=True)
        self.assertIn('action="/search"', page)
        self.assertIn('name="q"', page)

    def test_employees_only(self):
        self.assertBlocked(self.login(CLIENT).get("/search?q=a"))
        self.assertBlocked(self.login(SUBCONTRACTOR).get("/search?q=a"))

    def test_finds_each_kind_of_record(self):
        page = self.search("riverstone")  # any capitalization
        for expected in ("Riverstone Kitchen Remodel", "/project/1", "EST-1001", "INV-1045"):
            self.assertIn(expected, page)
        self.assertIn("/invoices?open=", self.search("1045"))
        self.assertIn("/clients/", self.search("Sarah"))
        self.assertIn("Miller Electrical Services", self.search("electrical"))  # subcontractor trade
        self.assertIn("Katy Home Addition", self.search("BB-0004"))             # project number

    def test_wildcards_are_literal_and_input_is_escaped(self):
        self.assertIn("No matches", self.search("%"))
        self.assertIn("No matches", self.search("_"))
        page = self.search("<script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.search("x" * 500)  # long input is handled (trimmed)

    def test_empty_and_no_results(self):
        self.assertIn("Projects, clients, invoices", self.search(""))
        page = self.search("zzzznotfound")
        self.assertIn("No matches", page)
        self.assertIn("0 results", page)


if __name__ == "__main__":
    unittest.main()

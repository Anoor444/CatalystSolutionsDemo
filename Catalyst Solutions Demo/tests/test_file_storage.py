"""Uploaded files are stored in MySQL, not on disk (backend step 14)."""
import io
import os
import unittest
from unittest.mock import patch

from support import EMPLOYEE, SUBCONTRACTOR, BackendTestCase, app


class FileStorageTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.employee = self.login(EMPLOYEE)

    def files_under_instance(self):
        found = []
        for folder, _dirs, files in os.walk(app.instance_path):
            found += [os.path.join(folder, name) for name in files if not name.startswith(".")]
        return found

    def upload_document(self, filename, content):
        token = self.form_token(self.employee, "/documents/upload")
        return self.employee.post("/documents/upload", content_type="multipart/form-data", data={
            "csrf_token": token, "document_type": "Contract", "project_id": "",
            "document": (io.BytesIO(content), filename)})

    def test_document_lives_in_the_database(self):
        self.assertEqual(self.upload_document("Plan.pdf", b"%PDF plan").status_code, 302)
        stored = self.value("SELECT file_path FROM documents WHERE original_filename = 'Plan.pdf'")
        self.assertEqual(self.value("SELECT size_bytes FROM uploaded_files WHERE stored_name = ?", stored), 9)
        self.assertEqual(self.files_under_instance(), [], "nothing is written to disk")
        did = self.value("SELECT document_id FROM documents WHERE original_filename = 'Plan.pdf'")
        response = self.employee.get(f"/documents/{did}/download")
        self.assertEqual(response.data, b"%PDF plan")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertIn("Plan.pdf", response.headers["Content-Disposition"])
        response.close()
        self.employee.post(f"/documents/{did}/delete", data={"csrf_token": self.form_token(self.employee, "/documents")})
        self.assertFalse(self.file_stored(stored), "deleting the document deletes its file")

    def test_photo_and_subcontractor_invoice_files(self):
        sub = self.login(SUBCONTRACTOR)
        memorial = self.project_id("Memorial Bathroom Renovation")
        token = self.form_token(sub, "/photos/upload")
        sub.post("/photos/upload", content_type="multipart/form-data", data={
            "csrf_token": token, "title": "Tile", "project_id": str(memorial), "photo": (io.BytesIO(b"\x89PNG tile"), "t.png")})
        photo_id = self.value("SELECT photo_id FROM photos WHERE title = 'Tile'")
        image = self.employee.get(f"/photos/{photo_id}/image")
        self.assertEqual((image.data, image.mimetype), (b"\x89PNG tile", "image/png"))
        image.close()
        token = self.form_token(sub, "/subcontractor/invoices")
        sub.post("/subcontractor/invoices", content_type="multipart/form-data", data={
            "csrf_token": token, "project_id": str(memorial), "invoice_number": "F-1", "amount": "10",
            "invoice_file": (io.BytesIO(b"%PDF inv"), "inv.pdf")})
        sid = self.value("SELECT sub_invoice_id FROM subcontractor_invoices WHERE invoice_number = 'F-1'")
        self.assertEqual(self.download(self.employee, f"/subcontractor-invoices/{sid}/file"), b"%PDF inv")
        self.assertEqual(self.files_under_instance(), [])

    def test_missing_file_is_404_not_an_error(self):
        self.upload_document("Gone.pdf", b"%PDF gone")
        did = self.value("SELECT document_id FROM documents WHERE original_filename = 'Gone.pdf'")
        self.query("DELETE FROM uploaded_files")
        self.assertEqual(self.employee.get(f"/documents/{did}/download").status_code, 404)

    def test_reset_clears_files(self):
        self.upload_document("Old.pdf", b"%PDF old")
        import database
        database.reset_business_data()
        self.assertEqual(self.stored_files(), set())

    def test_too_large_upload_gets_a_clear_message(self):
        with patch.dict(app.config, {"MAX_CONTENT_LENGTH": 2048}):
            page = self.upload_document("Huge.pdf", b"x" * 4096)
            self.assertEqual(page.status_code, 413)
            self.assertIn("MB or smaller", page.get_data(as_text=True))
            self.assertIn("Go Back", page.get_data(as_text=True))
            api = self.employee.post("/api/expenses", headers=self.api_headers(self.employee),
                                     content_type="multipart/form-data",
                                     data={"description": "x", "receipt": (io.BytesIO(b"x" * 4096), "r.pdf")})
            self.assertEqual(api.status_code, 413)
            self.assertIn("MB or smaller", api.get_json()["error"])
        self.assertIsNone(self.value("SELECT 1 FROM documents WHERE original_filename = 'Huge.pdf'"))

    def test_limit_fits_vercel(self):
        self.assertLessEqual(app.config["MAX_CONTENT_LENGTH"], int(4.5 * 1024 * 1024))


if __name__ == "__main__":
    unittest.main()

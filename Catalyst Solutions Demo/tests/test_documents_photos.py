"""Documents and Photos stored in the database (backend step 7)."""
import io
import unittest

from support import CLIENT, EMPLOYEE, SUBCONTRACTOR, BackendTestCase


class DocumentsPhotosTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.employee = self.login(EMPLOYEE)
        self.sub = self.login(SUBCONTRACTOR)  # assigned to Riverstone, Sugar Land and Memorial

    def upload_document(self, client, filename, content=b"%PDF test", project=None, doc_type="Contract"):
        token = self.form_token(client, "/documents/upload")
        return client.post("/documents/upload", content_type="multipart/form-data", data={
            "csrf_token": token, "document_type": doc_type, "project_id": "" if project is None else str(project),
            "document": (io.BytesIO(content), filename)})

    def upload_photo(self, client, title, project, content=b"\x89PNG test", filename="a.png"):
        token = self.form_token(client, "/photos/upload")
        return client.post("/photos/upload", content_type="multipart/form-data", data={
            "csrf_token": token, "title": title, "project_id": str(project), "photo": (io.BytesIO(content), filename)})

    def test_sample_documents_listed(self):
        page = self.employee.get("/documents").get_data(as_text=True)
        self.assertIn("Kitchen Renovation Estimate.pdf", page)
        self.assertNotIn("demo-notice", page)

    def test_document_upload_download_and_rules(self):
        katy = self.project_id("Katy Home Addition")
        self.assertEqual(self.upload_document(self.employee, "Katy Contract.pdf", b"%PDF new", katy).status_code, 302)
        did = self.value("SELECT document_id FROM documents WHERE original_filename = 'Katy Contract.pdf'")
        self.assertEqual(self.download(self.employee, f"/documents/{did}/download"), b"%PDF new")
        self.assertIn("Choose a PDF", self.upload_document(self.employee, "bad.exe", b"x").get_data(as_text=True))
        self.assertIn("Choose a project", self.upload_document(self.employee, "a.pdf", project=99999).get_data(as_text=True))
        self.assertEqual(self.upload_document(self.employee, "General.txt", b"general", None, "Other").status_code, 302,
                         "documents without a project are allowed")

    def test_subcontractor_sees_only_assigned_projects(self):
        katy = self.project_id("Katy Home Addition")
        self.upload_document(self.employee, "Katy Contract.pdf", project=katy)
        did = self.value("SELECT document_id FROM documents WHERE original_filename = 'Katy Contract.pdf'")
        page = self.sub.get("/documents").get_data(as_text=True)
        self.assertIn("Kitchen Renovation Estimate.pdf", page)
        self.assertNotIn("Katy Contract.pdf", page)
        self.assertEqual(self.sub.get(f"/documents/{did}/download").status_code, 404)
        self.assertBlocked(self.sub.get("/documents/upload"), "subcontractors can't upload documents")
        client = self.login(CLIENT)
        self.assertBlocked(client.get("/documents"))
        self.assertBlocked(client.get("/photos"))

    def test_subcontractor_photo_uploads(self):
        upload_page = self.sub.get("/photos/upload").get_data(as_text=True)
        self.assertIn("Riverstone Kitchen Remodel", upload_page)
        self.assertNotIn("Katy Home Addition", upload_page)
        self.assertIn("Choose a project", self.upload_photo(self.sub, "Sneaky", self.project_id("Katy Home Addition")).get_data(as_text=True))
        self.assertEqual(self.upload_photo(self.sub, "Tile done", self.project_id("Memorial Bathroom Renovation"), b"\x89PNG tile").status_code, 302)
        pid = self.value("SELECT photo_id FROM photos WHERE title = 'Tile done'")
        self.assertEqual(self.download(self.employee, f"/photos/{pid}/image"), b"\x89PNG tile")
        self.assertIn("Demo Subcontractor", self.employee.get("/photos").get_data(as_text=True), "uploader name shown")

    def test_photo_visibility_filter_and_delete(self):
        katy = self.project_id("Katy Home Addition")
        self.upload_photo(self.employee, "Katy framing", katy)
        kid = self.value("SELECT photo_id FROM photos WHERE title = 'Katy framing'")
        self.assertEqual(self.sub.get(f"/photos/{kid}/image").status_code, 404)
        self.assertNotIn("Katy framing", self.sub.get("/photos").get_data(as_text=True))
        self.assertIn("Katy framing", self.employee.get(f"/photos?project={katy}").get_data(as_text=True))
        self.assertBlocked(self.sub.post(f"/photos/{kid}/delete", data={"csrf_token": self.form_token(self.sub, "/photos")}))
        self.assertEqual(self.employee.post(f"/photos/{kid}/delete", data={}).status_code, 400, "CSRF required")
        token = self.form_token(self.employee, "/photos")
        self.assertEqual(self.employee.post(f"/photos/{kid}/delete", data={"csrf_token": token}).status_code, 302)
        self.assertEqual(self.employee.get(f"/photos/{kid}/image").status_code, 404)


if __name__ == "__main__":
    unittest.main()

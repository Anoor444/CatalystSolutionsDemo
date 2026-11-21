"""Documents and Photos stored in the database (backend step 7)."""
import io
import unittest
from unittest.mock import patch

from support import CLIENT, EMPLOYEE, SUBCONTRACTOR, BackendTestCase, app


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

    def test_edit_document_details_preserves_file_and_checks_access(self):
        project = self.project_id('Katy Home Addition')
        self.upload_document(self.employee, 'Edit Me.pdf', b'%PDF unchanged', project)
        did = self.value("SELECT document_id FROM documents WHERE original_filename = 'Edit Me.pdf'")
        url = f'/documents/{did}/edit'
        token = self.form_token(self.employee, url)
        self.assertIn(url, self.employee.get('/documents').get_data(as_text=True))
        self.assertEqual(self.employee.post(url).status_code, 400)
        form = {'csrf_token': token, 'original_filename': 'Updated.pdf', 'document_type': 'Other', 'project_id': ''}
        self.assertEqual(self.employee.post(url, data=form).status_code, 302)
        self.assertEqual(self.value('SELECT original_filename FROM documents WHERE document_id = ?', did), 'Updated.pdf')
        self.assertIsNone(self.value('SELECT project_id FROM documents WHERE document_id = ?', did))
        self.assertEqual(self.download(self.employee, f'/documents/{did}/download'), b'%PDF unchanged')
        for changes, error in (({'original_filename': ''}, 'Enter a document name'),
                               ({'document_type': 'invalid'}, 'Choose a document type'),
                               ({'project_id': '99999'}, 'Choose a project')):
            page = self.employee.post(url, data=dict(form, **changes)).get_data(as_text=True)
            self.assertIn(error, page)
        self.assertEqual(self.value('SELECT original_filename FROM documents WHERE document_id = ?', did), 'Updated.pdf')
        for client in (self.sub, self.login(CLIENT)):
            self.assertBlocked(client.get(url))
            other_token = self.form_token(client, '/login')
            self.assertBlocked(client.post(url, data=dict(form, csrf_token=other_token)))
        self.assertEqual(self.employee.get('/documents/99999/edit').status_code, 404)
        sample = self.value('SELECT document_id FROM documents WHERE file_path IS NULL LIMIT 1')
        self.assertEqual(self.employee.post(f'/documents/{sample}/edit', data=form).status_code, 302)

    def test_multiple_attachments_and_individual_deletion(self):
        did = self.value('SELECT document_id FROM documents WHERE file_path IS NULL LIMIT 1')
        url = f'/documents/{did}/edit'
        token = self.form_token(self.employee, url)
        form = {'csrf_token': token, 'original_filename': 'Attached.pdf', 'document_type': 'Other', 'project_id': ''}
        def upload(filename, content, **changes):
            return self.employee.post(url, content_type='multipart/form-data', data={
                **form, **changes, 'document': (io.BytesIO(content), filename)})
        response = upload('first.pdf', b'%PDF first')
        self.assertEqual(response.status_code, 302)
        self.assertIn(url, response.location)
        self.assertEqual(self.download(self.employee, f'/documents/{did}/download'), b'%PDF first')
        old_name = self.value('SELECT file_path FROM documents WHERE document_id = ?', did)
        self.assertTrue(self.file_stored(old_name))
        self.assertIn('Choose a PDF', upload('bad.exe', b'bad').get_data(as_text=True))
        self.assertIn('Choose a project', upload('new.pdf', b'%PDF invalid', project_id='99999').get_data(as_text=True))
        self.assertEqual(self.download(self.employee, f'/documents/{did}/download'), b'%PDF first')
        before = self.stored_files()
        with patch('app.database.update_document', side_effect=RuntimeError('test database failure')):
            with self.assertRaises(RuntimeError):
                upload('failed.pdf', b'%PDF failed')
        self.assertEqual(self.stored_files(), before)
        self.assertTrue(self.file_stored(old_name))
        self.assertEqual(upload('additional.pdf', b'%PDF additional').status_code, 302)
        self.assertTrue(self.file_stored(old_name))
        aid = self.value('SELECT attachment_id FROM document_attachments WHERE document_id = ?', did)
        download_url = f'/documents/{did}/attachments/{aid}/download'
        self.assertEqual(self.download(self.employee, download_url), b'%PDF additional')
        self.assertEqual(self.download(self.employee, f'/documents/{did}/download'), b'%PDF first')
        self.assertEqual(self.employee.post(url, data=form).status_code, 302)
        delete_url = f'/documents/{did}/attachments/0/delete'
        self.assertEqual(self.employee.post(delete_url).status_code, 400)
        other_token = self.form_token(self.sub, '/login')
        self.assertBlocked(self.sub.post(delete_url, data={'csrf_token': other_token}))
        self.assertEqual(self.sub.get(download_url).status_code, 404)
        self.assertEqual(self.employee.post(delete_url, data={'csrf_token': token}).status_code, 302)
        self.assertFalse(self.file_stored(old_name))
        self.assertEqual(self.download(self.employee, f'/documents/{did}/download'), b'%PDF additional')
        self.assertEqual(self.employee.post(delete_url, data={'csrf_token': token}).status_code, 302)
        self.assertEqual(self.employee.get(f'/documents/{did}/download').status_code, 404)
        self.assertIn('No attachments yet.', self.employee.get(url).get_data(as_text=True))
        self.assertEqual(self.employee.post(url, content_type='multipart/form-data', data={
            **form, 'document': [(io.BytesIO(b'%PDF one'), 'one.pdf'), (io.BytesIO(b'two'), 'two.txt')]
        }).status_code, 302)
        aid = self.value('SELECT attachment_id FROM document_attachments WHERE document_id = ?', did)
        wrong_doc = self.value('SELECT document_id FROM documents WHERE document_id != ? LIMIT 1', did)
        self.assertEqual(self.employee.post(f'/documents/{wrong_doc}/attachments/{aid}/delete', data={'csrf_token': token}).status_code, 404)
        self.assertEqual(self.employee.post(f'/documents/{did}/attachments/{aid}/delete', data={'csrf_token': token}).status_code, 302)
        self.assertEqual(self.download(self.employee, f'/documents/{did}/download'), b'%PDF one')
        before = self.stored_files()
        page = self.employee.post(url, content_type='multipart/form-data', data={
            **form, 'document': [(io.BytesIO(b'%PDF ok'), 'ok.pdf'), (io.BytesIO(b'bad'), 'bad.exe')]
        })
        self.assertIn('Choose a PDF', page.get_data(as_text=True))
        self.assertEqual(self.stored_files(), before)

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

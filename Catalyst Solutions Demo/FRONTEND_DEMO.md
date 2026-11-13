# Frontend portal demo

Employee Estimates, Invoices, Job Costs, and Schedule have been restored to their original screens and behavior. The shared frontend enhancement does not replace or add its demo banner to these four pages. Estimates, costs, and task edits on those pages use their original in-memory behavior. Other portal and project-detail enhancements remain.

Start the existing Flask app with `python app.py`. No new Python or npm dependencies are required for these features.

Settings now includes **Change Password** for employees, clients, and subcontractors. This account feature updates the real configured SQLite/MySQL account password, independently of browser demo records. It requires the current password and a matching new password of 12–128 characters. Verify it with `python tests/test_password_change.py`; these tests use a temporary database and leave demo accounts unchanged.

- Employees: create/edit projects, convert approved estimates, create/view invoices, mark paid/unpaid, download PDFs, search projects/client names/invoice numbers, manage costs/tasks, and attach project receipts/photos.
- Subcontractors: view their three sample assigned projects, submit itemized invoices with optional attachments, view submitted invoices/PDFs, and upload progress photos.
- Clients: view the sample Riverstone project, its approved estimate with line items, invoice details/PDFs, and project tasks.

The project tabs now display costs, invoices, receipts/documents, photos, tasks, assigned subcontractors, and the approved estimate. Employees can assign subcontractors by login email, name, and trade, or remove assignments. Those assignments determine the projects and upload choices shown in the subcontractor portal in the same browser. Assigning an email does not create an account.

Records use localStorage keys starting with `buffbison.frontend.v1.`. They persist across reloads and demo-account switches in the same browser. They do not sync to other browsers or the server. Client access is modeled with project 1; subcontractor access is modeled with projects 1–3. These frontend filters are demonstration behavior, not authorization enforcement.

Attachments have a 2 MB per-file limit and share the browser's storage quota. PDF/image receipts are supported. The existing server-uploaded sample/legacy gallery remains separate from new browser demo attachments.

To reset the demo, remove only the `buffbison.frontend.v1.*` localStorage entries in the browser's developer tools. This also removes browser demo attachments.

## Verification

Run `node tests/frontend_smoke.mjs` from this directory. It uses installed Chrome/Edge, a temporary browser profile, an isolated SQLite instance, and ports 5187/9287. Set `BROWSER_PATH` if the browser is installed elsewhere. The test checks employee/client/subcontractor workflows, project creation/editing, estimate conversion, invoice totals/status and PDF contents, expenses, photo/receipt attachments, task persistence, project filters, and universal search.

Invoice search results open the selected invoice inside its project, leaving the restored employee invoice page unchanged. Project actual costs use expense totals when a ledger exists, otherwise the project?s sample actual cost.

# Backend notes

## How the data is stored

- **One SQLite file:** `instance/users.sqlite3`. It holds the login `users` table and all business tables (projects, clients, estimates, invoices, receipts and so on).
- **The `instance/` folder is not in Git.** Each person has their own copy of the database, the secret key, uploads and logs.
- **The first time you run `python app.py`,** the app creates every table from `schema.sql` and loads the sample data from `seed_data.py`. On later runs it leaves your data alone.

## Files

| File | What it does |
|---|---|
| `schema.sql` | Every table, based on the team ERD. Safe to run again. |
| `database.py` | Opens the connection for each request, sets up tables at startup, and holds the query functions pages use (`get_projects()`, `create_project()`, ...). |
| `seed_data.py` | Sample data: the 12 projects, clients, project managers, cost categories, costs to date, 10 estimates, 9 invoices, 18 tasks, category budgets, expenses, client contact details and 11 subcontractors with project assignments. |
| `api.py` | JSON API used by the Estimates and Invoices pages (see below). |
| `static/js/api-client.js` | `apiRequest()`, the helper the pages use to call the API (sends the CSRF token). |

## Commands

Run these from the `Catalyst Solutions Demo` folder:

```bash
python app.py                              # run the site
python -m flask --app app reset-demo-data  # wipe projects/clients/etc. and reload the sample data (keeps logins)
python -m flask --app app create-user      # add a login account
```

To start completely fresh, stop the app, delete the `instance` folder and run `python app.py`. Note that this also deletes uploaded documents and photos.

## Demo logins

| Role | Email | Password |
|---|---|---|
| Employee | demo@buffbison.com | Buffbison123 |
| Client | demo.client@buffbison.com | ClientDemo123! |
| Subcontractor | demo.subcontractor@buffbison.com | SubcontractorDemo123! |

The client demo account is linked to the client **Sarah Johnson** (Riverstone Kitchen Remodel).

## Adding a page that uses the database

1. Add a query function in `database.py`. Use `get_db()` and `?` placeholders, never f-strings with user input.
2. Call it from the route in `app.py` and pass the result to the template.
3. In the template, loop over the rows. Formatting filters are available: `|currency`, `|short_date`, `|status_class`.

## What's connected so far

- [x] Login (users table)
- [x] Projects page and its cards (employee view)
- [x] New Project form (saves to the database)
- [x] Dashboard (employee): cards, open projects, upcoming tasks and recent activity from the database
- [x] Schedule: tasks are stored in the database (add, edit, complete, delete); project pages show the same tasks
- [ ] Project details tabs other than Schedule and Costs (invoices, documents, photos, subcontractors still use browser demo data)
- [x] Estimates: create, edit, send, approve or reject, delete drafts, convert to a project
- [x] Invoices: create, edit, send, mark paid or unpaid, delete drafts, PDF
- [x] Job Costs: expenses, budget by category and receipt uploads (PDF/JPG/PNG, 10 MB) in the database
- [x] Clients and Subcontractors: list, add, edit (status Active/Inactive instead of delete); subcontractors are assigned to projects from their form (`project_assignments`). A client or subcontractor record is linked to a login automatically when the emails match (used by the portals).
- [x] Client portal: dashboard, My Projects, project page (progress, schedule, invoices), Estimates (approve or decline sent estimates) and Invoices (printable invoice page) — all from the database, only for the client linked to the login
- [x] Subcontractor portal: dashboard, assigned projects only, task status updates, submit invoices (optional PDF/JPG/PNG in `instance/subcontractor_invoice_uploads`), Documents and Photos links
- [x] Subcontractor invoice approval: employees approve, reject, mark paid or reopen on the Subcontractors page (`#sub-invoices`). Approved and paid invoices count as project cost and show on Job Costs as read-only rows (`id` like `sub-3`).
- [x] Documents and Photos: records in the database (files in `instance/document_uploads` and `instance/photo_uploads`), real project dropdowns, delete for employees, `?project=<id>` filter. Subcontractors only see their assigned projects (plus their own uploads). Old `documents.json`/`photos.json` lists are imported once.

## JSON API (api.py)

All endpoints need a logged-in **employee**. POST, PUT, PATCH and DELETE need the CSRF token in an `X-CSRF-Token` header; `apiRequest()` adds it for you. Errors come back as `{"error": "message"}`.

| Method | URL | What it does |
|---|---|---|
| GET | `/api/lookups` | Clients, cost categories, project managers and projects for dropdowns |
| GET / POST | `/api/estimates` | List estimates, or create one (`status`: Draft or Sent) |
| PUT / DELETE | `/api/estimates/<id>` | Edit (Draft and Sent only) or delete (Draft only) |
| PATCH | `/api/estimates/<id>/status` | Sent → Approved or Rejected; Rejected → Draft |
| POST | `/api/estimates/<id>/convert` | Approved estimate → new project (RTM A4) |
| GET / POST | `/api/invoices` | List invoices, or create one (`status`: Draft or Unpaid) |
| PUT / DELETE | `/api/invoices/<id>` | Edit (Draft and Unpaid only) or delete (Draft only) |
| PATCH | `/api/invoices/<id>/status` | Unpaid ↔ Paid (sets or clears `paid_at`) |
| GET / POST | `/api/tasks` | List tasks, or create one |
| PUT / DELETE | `/api/tasks/<id>` | Edit or delete a task |
| PATCH | `/api/tasks/<id>/status` | Change status (e.g. Completed) |
| GET / POST | `/api/expenses` | List expenses, or add one (multipart form: fields + optional `receipt` file) |
| PUT / DELETE | `/api/expenses/<id>` | Edit (a new file replaces the old receipt) or delete (removes the file too) |
| GET | `/api/expenses/<id>/receipt` | Open the saved receipt file |

Receipt files are saved in `instance/receipt_uploads/` (not in Git). Converting an estimate copies its line items into the project's budget by category.

The server recalculates every line total and grand total. Unit prices are rounded to cents.

## Moving to MySQL later

The SQL is plain and portable. The main changes would be:
- `INTEGER PRIMARY KEY` → `INT AUTO_INCREMENT PRIMARY KEY`
- `TEXT` → `VARCHAR(...)`
- `datetime('now')` → `CURRENT_TIMESTAMP`
- `connect()` in `database.py` would use a MySQL driver instead of `sqlite3`

## Who can see what

`database.accessible_project_ids(user_id, role)` returns `None` for employees (all projects), or the set of project ids a subcontractor is assigned to / a client owns. Use it for any page a non-employee can open.

Portal pages call `database.portal_projects` / `database.portal_project` (and the `client_*` / `subcontractor_*` helpers), which check the login on the server — opening another client's project or invoice by URL returns 404. `portal.js` (the browser demo layer) is turned off for the client and subcontractor roles.

Subcontractor invoice status flow (`SUB_INVOICE_TRANSITIONS`): Pending Approval → Approved or Rejected; Approved → Paid (or back to Pending); Rejected → Pending; Paid → Approved.

# Backend notes

## How the data is stored

- **One MySQL database** (MySQL 8, Amazon RDS for MySQL, or a MySQL-compatible host such as TiDB Cloud). It holds the login `users` table and all business tables (projects, clients, estimates, invoices, receipts and so on).
- **Connection settings come from environment variables**, or a `.env` file in this folder for local use. Copy `.env.example` to `.env` and fill it in. `.env` is never committed; on Vercel the same names go in the project's Environment Variables.
- **The first time the app connects to an empty database,** it creates every table from `schema.sql` and loads the sample data from `seed_data.py`. Later it leaves your data alone.
- **Uploaded files** (documents, attachments, photos, receipts, subcontractor invoices) are stored **in MySQL** too, in the `uploaded_files` table. Each record's `file_path` column holds the file's stored name. Nothing is saved on disk, which is what hosts like Vercel need.
- **Upload limit: 4 MB per request** (one file, or several files together on the document page). Vercel refuses anything over 4.5 MB. Change `MAX_UPLOAD_MB` in `app.py` (and `MAX_RECEIPT_BYTES` in `api.py`) only if you deploy somewhere else.

### Moving your old SQLite data into MySQL

If you used the app before step 13, your old data is still in `instance/users.sqlite3`, and your uploaded files are in the `instance/*_uploads` folders. To copy all of it into MySQL (logins and passwords, ids and links are kept):

```bash
python tools/sqlite_to_mysql.py --replace
```

It shows which MySQL database it will write to and asks you to type that database's name to confirm, because **it empties that MySQL database first** (normally it only holds the sample data). The SQLite file and folders are only read, never changed. At the end it prints the row count of every table in SQLite and in MySQL, and how many files were copied.

If you only need the files (records already in MySQL, files still in `instance/*_uploads`): `python tools/sqlite_to_mysql.py --uploads-only`. It's safe to run more than once.

### Setting up MySQL on your computer

1. Install **MySQL Server 8** (free Community edition) and MySQL Workbench.
2. In Workbench, open `setup_mysql.sql`, replace the placeholder password, and run it. It creates the `catalyst_demo` database, a `catalyst_test` database for the tests, and a `catalyst_app` login.
3. Copy `.env.example` to `.env` and put that password in `MYSQL_PASSWORD`.
4. `pip install -r requirements.txt`, then `python app.py`.

| Setting | Default | What it is |
|---|---|---|
| `MYSQL_HOST` / `MYSQL_PORT` | `127.0.0.1` / `3306` | Database server |
| `MYSQL_USER` / `MYSQL_PASSWORD` | `catalyst_app` / (empty) | Database login |
| `MYSQL_DATABASE` | `catalyst_demo` | Database name |
| `MYSQL_SSL` | `false` | `true` for hosted databases (TiDB Cloud, Amazon RDS): connects over verified TLS |
| `MYSQL_SSL_CA` | (certifi's list) | Certificate file to trust. Not needed for TiDB Cloud; for Amazon RDS, AWS's RDS bundle (`global-bundle.pem`) |
| `MYSQL_POOL_SIZE` | `3` | Connections kept open per server instance (more are opened if needed) |
| `MYSQL_TEST_DATABASE` | `catalyst_test` | Used by the tests; must end in `_test` (it is wiped on every test run) |
| `APP_TIMEZONE` | `America/Chicago` | "Today", overdue checks and timestamps use this time zone, whatever the server's clock says |

## Files

| File | What it does |
|---|---|
| `schema.sql` | Every table (MySQL), based on the team ERD, with foreign keys. Safe to run again. |
| `setup_mysql.sql` | One-time local setup: databases and the `catalyst_app` login. |
| `.env.example` | The settings to copy into your own `.env`. |
| `tools/sqlite_to_mysql.py` | One-time copy of the old SQLite database and upload folders into MySQL (not part of the website). |
| `database.py` | Connection pool (one connection per request), table setup at startup, and the query functions pages use (`get_projects()`, `create_project()`, ...). |
| `user_database.py` | Login accounts (the same `users` table, same database). |
| `seed_data.py` | Sample data: the 12 projects, clients, project managers, cost categories, costs to date, 10 estimates, 9 invoices, 18 tasks, category budgets, expenses, client contact details and 11 subcontractors with project assignments. |
| `public/static/` | CSS, JavaScript and images. They live in `public/` so Vercel serves them from its CDN at `/static/...`; Flask serves the same folder locally, so `url_for('static', ...)` works the same in both. |
| `.vercelignore` | Files Vercel never uploads: `instance/`, `.env`, SQLite files, `tests/`, `tools/`. |
| `api.py` | JSON API used by the Estimates and Invoices pages (see below). |
| `public/static/js/api-client.js` | `apiRequest()`, the helper the pages use to call the API (sends the CSRF token). |

## Deploying on Vercel (free)

The site runs on Vercel's free Hobby plan with a free hosted MySQL database (TiDB Cloud Starter). Nothing is written to disk: data and uploaded files are in MySQL, and the secret key comes from an environment variable.

1. **Database:** create a free TiDB Cloud Starter instance (pick AWS **us-east-1**, the same region as Vercel's default). Click **Connect**, choose **Public**, and click **Generate Password**. Write down the host, port (4000), user (looks like `xxxx.root`) and password.
2. **Vercel:** sign in with GitHub, **Add New -> Project**, import the repository and set **Root Directory** to `Catalyst Solutions Demo`. Vercel detects Flask from `app.py`.
3. **Environment Variables** (same screen, before **Deploy**):

| Name | Value |
|---|---|
| `MYSQL_HOST` | host from TiDB's Connect dialog |
| `MYSQL_PORT` | `4000` |
| `MYSQL_USER` | user from TiDB (`xxxx.root`) |
| `MYSQL_PASSWORD` | the generated password |
| `MYSQL_DATABASE` | `catalyst_demo` |
| `MYSQL_SSL` | `true` |
| `FLASK_SECRET_KEY` | a long random value: `python -c "import secrets; print(secrets.token_hex(32))"` |

Optional: the `MAIL_*` settings (see Forgot password) so reset emails are really sent; otherwise the reset link appears in Vercel's **Logs**.

4. **Deploy.** On the first visit the app creates the `catalyst_demo` database, every table and the sample data by itself. Log in with the demo accounts.

Every merge to `main` deploys again automatically. Notes:
- Without `FLASK_SECRET_KEY` the site refuses to start on Vercel (logins would break otherwise). Changing it logs everyone out.
- To put your local data online, point your `.env` at TiDB for a moment (same values as above) and run `python tools/sqlite_to_mysql.py --replace`, or copy tables with MySQL Workbench. Then put your `.env` back.
- Uploads are limited to 4 MB (Vercel's limit is 4.5 MB per request).
- Errors and printed messages are under the project's **Logs** tab in Vercel.

## Commands

Run these from the `Catalyst Solutions Demo` folder:

```bash
python app.py                              # run the site
python -m flask --app app init-db          # create missing tables + sample data (also happens on startup)
python -m flask --app app reset-demo-data  # wipe projects/clients/etc. and reload the sample data (keeps logins)
python -m flask --app app create-user      # add a login account
```

To start completely fresh, drop and recreate the `catalyst_demo` database in Workbench, then run `python app.py`.

## Forgot password

1. **Forgot Password?** on the sign-in page asks for an email address. The page always says the same thing, so it can't be used to find out which emails have accounts. Each address gets at most one email a minute.
2. If the account exists, it gets a link like `/reset-password/<token>`. The token is signed with the app's secret key and holds the user id plus a fingerprint of the current password. It expires after 30 minutes (`RESET_LINK_MINUTES` in `app.py`) and stops working once the password changes, so each link works once.
3. The link opens a page to choose a new password (same rules as Change Password: 12–128 characters). Afterwards the user goes back to sign in.

**Without email settings (the default)**, the link is printed in the terminal running `python app.py`:

```
[password reset] Link for demo.client@buffbison.com: http://127.0.0.1:5000/reset-password/...
```

That's how to demo it: the demo accounts' emails aren't real inboxes.

**To actually send emails**, set these before starting the app (PowerShell example for Gmail, which needs an [app password](https://support.google.com/accounts/answer/185833), not your normal password):

```powershell
$env:MAIL_SERVER="smtp.gmail.com"
$env:MAIL_PORT="587"
$env:MAIL_USERNAME="yourteam@gmail.com"
$env:MAIL_PASSWORD="your-16-letter-app-password"
$env:MAIL_FROM="Buff Bison <yourteam@gmail.com>"
python app.py
```

`MAIL_USE_TLS` defaults to `true`. Never commit these values. If sending fails, the error is logged in the terminal and the page still shows the usual message.

## Running the tests

From the `Catalyst Solutions Demo` folder:

```bash
python -m unittest discover -s tests -v
```

About 90 tests, roughly a minute. They need MySQL running (same settings as the app) and use a **separate test database**, `catalyst_test` (`MYSQL_TEST_DATABASE`; the name must end in `_test`), which is dropped and recreated on every run, plus a temporary upload folder. Your real data is never touched, and every test starts from fresh sample data. `pytest tests` works too if you have pytest installed.

| File | Covers |
|---|---|
| `tests/test_estimates_invoices.py` | Estimates and invoices API: validation, status rules, convert to project, CSRF |
| `tests/test_schedule_job_costs.py` | Tasks API; job costs, expenses and receipt uploads |
| `tests/test_directory.py` | Clients and subcontractors pages, project assignments |
| `tests/test_documents_photos.py` | Document and photo uploads, downloads, who can see what |
| `tests/test_file_storage.py` | Files stored in MySQL (not on disk), deletes, 4 MB limit message |
| `tests/test_portals.py` | Client and subcontractor portals, subcontractor invoice approval |
| `tests/test_project_page.py` | Employee project page tabs, Edit Project |
| `tests/test_search.py` | Search, demo client estimate |
| `tests/test_forgot_password.py` | Forgot password: reset links, expiry, one-time use, email sending |
| `tests/test_password_change.py` | Changing passwords (all roles) |
| `tests/support.py` | Shared setup (temporary database, logins, helpers) — not a test file |

`flask --app app reset-demo-data` and the tests use the same `database.reset_business_data()`.

Note: `tests/frontend_smoke.mjs` was written for the earlier browser-only demo (it checks browser-storage features that the database versions replaced), so it no longer passes as-is.

## Demo logins

| Role | Email | Password |
|---|---|---|
| Employee | demo@buffbison.com | Buffbison123 |
| Client | demo.client@buffbison.com | ClientDemo123! |
| Subcontractor | demo.subcontractor@buffbison.com | SubcontractorDemo123! |

The client demo account is linked to the client **Sarah Johnson** (Riverstone Kitchen Remodel).

## Adding a page that uses the database

Employees can click a document name to edit its details and manage attachments.
The details page accepts multiple files per save (4 MB total), adds them to the
existing files, and offers an individual download and delete action for each file.
Deleting an attachment keeps the document details. Existing uploads remain available
after the automatic schema upgrade; extra files are stored in `document_attachments`
and every file is stored in the `uploaded_files` table.

1. Add a query function in `database.py`. Use `get_db()` and `?` placeholders (they become MySQL's `%s` automatically), never f-strings with user input. Use MySQL SQL: `CONCAT()` to join text, `NOW()` / `CURDATE()` for the current time.
2. Call it from the route in `app.py` and pass the result to the template.
3. In the template, loop over the rows. Formatting filters are available: `|currency`, `|short_date`, `|status_class`.

## What's connected so far

- [x] Login (users table)
- [x] Projects page and its cards (employee view)
- [x] New Project form (saves to the database)
- [x] Dashboard (employee): cards, open projects, upcoming tasks and recent activity from the database
- [x] Schedule: tasks are stored in the database (add, edit, complete, delete); project pages show the same tasks
- [x] Project details page (employee): overview, Costs (budget vs actual by category + expenses), Invoices, Documents, Photos, Schedule and Subcontractors (assignments + invoice approval) tabs, all server-rendered from the database. `?tab=<name>` opens a tab; uploads started from a tab (`?project=<id>&from=project`) and approvals return to it.
- [x] Edit Project (`/project/<id>/edit`): reuses the New Project form; client stays fixed (Clients page), progress can be set, address optional for older projects
- [x] Invoices page links: `/invoices?new=1&project=<id>` opens a new invoice for that project, `/invoices?open=<id>` opens one invoice (Estimates page: `/estimates?open=<id>`)
- [x] Search (employee): the Dashboard search box goes to `/search?q=...`, which finds projects (name, number, client, address), clients (name, company, email, phone), invoices, estimates and subcontractors (company, contact, trade, email). Case-insensitive; `%` and `_` are matched literally.
- [x] Demo client sample estimate: "Riverstone Backsplash and Lighting Upgrade" is added once in Sent status for Sarah Johnson (next free estimate number), so the client portal has something to approve or decline
- [x] Estimates: create, edit, send, approve or reject, delete drafts, convert to a project
- [x] Invoices: create, edit, send, mark paid or unpaid, delete drafts, PDF
- [x] Job Costs: expenses, budget by category and receipt uploads (PDF/JPG/PNG, 4 MB) in the database
- [x] Clients and Subcontractors: list, add, edit (status Active/Inactive instead of delete); subcontractors are assigned to projects from their form (`project_assignments`). A client or subcontractor record is linked to a login automatically when the emails match (used by the portals).
- [x] Client portal: dashboard, My Projects, project page (progress, schedule, invoices), Estimates (approve or decline sent estimates) and Invoices (printable invoice page) — all from the database, only for the client linked to the login
- [x] Subcontractor portal: dashboard, assigned projects only, task status updates, submit invoices (optional PDF/JPG/PNG, stored in MySQL), Documents and Photos links
- [x] Subcontractor invoice approval: employees approve, reject, mark paid or reopen on the Subcontractors page (`#sub-invoices`). Approved and paid invoices count as project cost and show on Job Costs as read-only rows (`id` like `sub-3`).
- [x] Documents and Photos: records and files in the database, real project dropdowns, delete for employees, `?project=<id>` filter. Subcontractors only see their assigned projects (plus their own uploads). Old `documents.json`/`photos.json` lists are imported once.

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

Receipt files are stored in MySQL (`uploaded_files`). Converting an estimate copies its line items into the project's budget by category.

The server recalculates every line total and grand total. Unit prices are rounded to cents.

## Who can see what

`database.accessible_project_ids(user_id, role)` returns `None` for employees (all projects), or the set of project ids a subcontractor is assigned to / a client owns. Use it for any page a non-employee can open.

Portal pages call `database.portal_projects` / `database.portal_project` (and the `client_*` / `subcontractor_*` helpers), which check the login on the server — opening another client's project or invoice by URL returns 404. `portal.js` (the browser demo layer) is turned off for the client and subcontractor roles.

Subcontractor invoice status flow (`SUB_INVOICE_TRANSITIONS`): Pending Approval → Approved or Rejected; Approved → Paid (or back to Pending); Rejected → Pending; Paid → Approved.

The browser demo layer (`portal.js` + `demo-store.js`) is now off for every employee page and for the client and subcontractor portals; it only still runs on pages that have no server version yet.

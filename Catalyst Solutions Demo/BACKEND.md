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
| `seed_data.py` | Sample data: the 12 projects, clients, project managers, cost categories and costs to date. |

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
- [ ] Dashboard cards
- [ ] Project details page
- [ ] Estimates, Invoices (front end ready; replace the `TODO(backend)` calls in the JS)
- [ ] Job costs, receipts, schedule, clients, subcontractors
- [ ] Client and subcontractor portals (still use the sample lists in `app.py`)
- [ ] Documents and photos (still saved to JSON files in `instance/`)

## Moving to MySQL later

The SQL is plain and portable. The main changes would be:
- `INTEGER PRIMARY KEY` → `INT AUTO_INCREMENT PRIMARY KEY`
- `TEXT` → `VARCHAR(...)`
- `datetime('now')` → `CURRENT_TIMESTAMP`
- `connect()` in `database.py` would use a MySQL driver instead of `sqlite3`

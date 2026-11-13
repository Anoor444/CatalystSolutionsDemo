# CatalystSolutionsDemo

## MySQL setup

The app supports MySQL for accounts, with the same demo accounts, password hashing,
and role permissions. Dashboards and demo pages use sample data; document and photo
galleries use files and JSON metadata.
SQLite remains the default until `DB_BACKEND=mysql` is set.

### Configure MySQL

1. Open `Catalyst Solutions Demo/setup_mysql.sql` in MySQL Workbench as an
   administrator. Replace the placeholder password, then run the script to create
   the database and application account. The MySQL server must be running.
2. From the workspace root, run these commands in PowerShell:

```powershell
cd ".\CatalystSolutionsDemo\Catalyst Solutions Demo"
python -m pip install -r requirements.txt
$env:DB_BACKEND = "mysql"
$env:MYSQL_HOST = "127.0.0.1"
$env:MYSQL_PORT = "3306"
$env:MYSQL_DATABASE = "catalyst_demo"
$env:MYSQL_USER = "catalyst_app"
$mysqlCredential = Get-Credential -UserName "catalyst_app" -Message "Enter the MySQL application password"
$env:MYSQL_PASSWORD = $mysqlCredential.GetNetworkCredential().Password
```

3. To copy existing SQLite accounts, run this once before starting the server:

```powershell
python -m flask --app app migrate-sqlite-users
```

The migration copies password hashes, so imported users keep their passwords.
It leaves the SQLite file intact and skips emails already in MySQL. The app
automatically seeds the three demo accounts; to copy modified SQLite demo
passwords or intentionally replace other matching MySQL accounts, use
`python -m flask --app app migrate-sqlite-users --replace-existing`.
Account IDs can change during migration; restart the server and log in again.

4. Start the app from the same terminal:

```powershell
python app.py
```

Open http://127.0.0.1:5000. Environment variables above apply to this terminal
session; set them again in a new terminal. To use SQLite again, set
`$env:DB_BACKEND = "sqlite"` and restart. MySQL changes are not copied back to SQLite.
Connection errors usually mean the server is stopped, the database was not
created, or the credentials do not match the application account.

## Secure login and roles

From the `Catalyst Solutions Demo` folder, create an account using the Flask CLI:

```powershell
flask --app app create-user
```

Enter an email, display name, role (`employee`, `subcontractor`, or `client`), and a password of at least 12 characters. Passwords are stored as hashes in the configured database (MySQL, or `instance/users.sqlite3` by default); there is no public sign-up page.

For local demonstrations, the app creates this employee account if it does not already exist:

- Email: `demo@buffbison.com`
- Password: `Buffbison123`

The app also creates a read-only client demo account:

- Email: `demo.client@buffbison.com`
- Password: `ClientDemo123!`

These shared demo credentials are for local demonstration only. Remove demo account seeding and delete the three demo accounts from the configured database before deploying or exposing the app to other users.

Run the app with:

```powershell
python app.py
```

For production, set a private random `FLASK_SECRET_KEY` environment variable and set `COOKIE_SECURE=true` when serving the app over HTTPS. Without `FLASK_SECRET_KEY`, the app creates a local secret in `instance/.secret_key` for development.

### Starter permissions

- **Employee:** full access, including management pages and upload functions.
- **Subcontractor:** projects, documents, and photos; may upload photos.
- **Client:** a client portal with Dashboard, My Projects, Estimates, and Invoices. The dashboard summarizes project progress and items awaiting client review. Clients cannot access the employee dashboard, management pages, documents, or photos.

The client portal's project, estimate, and invoice records are currently sample data shared by the demo. Users are not yet limited to records belonging to their specific project. Add project membership and enforce it on every record lookup before using this with real client data.

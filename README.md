# CatalystSolutionsDemo

## Secure login and roles

From the `Catalyst Solutions Demo` folder, create an account using the Flask CLI:

```powershell
flask --app app create-user
```

Enter an email, display name, role (`employee`, `subcontractor`, or `client`), and a password of at least 12 characters. Passwords are stored as hashes in `instance/users.sqlite3`; there is no public sign-up page.

For local demonstrations, the app creates this employee account if it does not already exist:

- Email: `demo@buffbison.com`
- Password: `Buffbison123`

The app also creates a read-only client demo account:

- Email: `demo.client@buffbison.com`
- Password: `ClientDemo123!`

These shared demo credentials are for local demonstration only. Delete both demo accounts from `instance/users.sqlite3` before deploying or exposing the app to other users.

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
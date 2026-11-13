"""
Sample data loaded into the database the first time the app runs
(and again by `flask --app app reset-demo-data`).

These are the same 12 projects that were typed into projects.html, so the
pages look the same as before, but the numbers now come from the database.
"""
import secrets

from werkzeug.security import generate_password_hash

COST_CATEGORIES = (
    ("Labor", "Crew and hourly labor"),
    ("Materials", "Lumber, fixtures, finishes and supplies"),
    ("Equipment", "Rentals and machinery"),
    ("Subcontractor", "Work billed by subcontractors"),
    ("Permits & Fees", "City permits and inspection fees"),
    ("Disposal", "Dumpsters and haul-off"),
)

# Project managers shown on the Projects page. They are employee accounts with a
# random password, so nobody can log in as them until someone sets a real one
# with `flask --app app create-user` (or a future "reset password" feature).
PROJECT_MANAGERS = (
    ("daniel.carter@buffbison.com", "Daniel Carter"),
    ("james.wilson@buffbison.com", "James Wilson"),
    ("carlos.reyes@buffbison.com", "Carlos Reyes"),
)

# name, client, manager, status, budget, actual cost to date, progress %, due date, type
PROJECTS = (
    ("Riverstone Kitchen Remodel",      "Sarah Johnson",         "Daniel Carter", "In Progress",  48500, 31200,  65, "2026-11-15", "Kitchen Remodel"),
    ("Sugar Land Roof Replacement",     "Michael Thompson",      "Daniel Carter", "In Progress",  22000, 13800,  55, "2026-10-28", "Roofing"),
    ("Memorial Bathroom Renovation",    "Emily Davis",           "James Wilson",  "Planning",     35750,  2500,  10, "2026-12-12", "Bathroom Remodel"),
    ("Katy Home Addition",              "Robert Garcia",         "James Wilson",  "In Progress",  92000, 44600,  48, "2027-01-20", "Home Addition"),
    ("Cypress Storm Damage Repair",     "Robert Nguyen",         "Carlos Reyes",  "In Progress",  32750, 14700,  45, "2026-12-05", "Other"),
    ("Heights Garage Conversion",       "Olivia Martinez",       "Daniel Carter", "In Progress",  56800, 21400,  38, "2027-01-08", "Full Renovation"),
    ("Pearland Patio Extension",        "David Chen",            "Carlos Reyes",  "In Progress",  18900, 14200,  75, "2026-11-20", "Other"),
    ("Spring Office Build-Out",         "Lakeside Dental Group", "James Wilson",  "In Progress", 124000, 81500,  68, "2026-12-18", "Full Renovation"),
    ("West University Flooring Upgrade", "Rachel Morgan",        "Daniel Carter", "In Progress",  27600, 23100,  88, "2026-11-10", "Other"),
    ("Bellaire Outdoor Kitchen",        "Marcus Williams",       "Carlos Reyes",  "Planning",     39500,  1800,   5, "2027-02-12", "Kitchen Remodel"),
    ("Richmond Primary Suite Addition", "Sophia Patel",          "James Wilson",  "Planning",    108000,  6500,   8, "2027-03-26", "Home Addition"),
    ("Clear Lake Deck Restoration",     "William Anderson",      "Carlos Reyes",  "Completed",    16400, 15950, 100, "2026-10-23", "Other"),
)

# The demo client account sees this client's projects in the client portal.
DEMO_CLIENT_EMAIL = "demo.client@buffbison.com"
DEMO_CLIENT_NAME_IN_DATA = "Sarah Johnson"


def load_sample_data(connection):
    category_ids = {}
    for name, description in COST_CATEGORIES:
        cursor = connection.execute(
            "INSERT INTO cost_categories (name, description) VALUES (?, ?)", (name, description)
        )
        category_ids[name] = cursor.lastrowid

    manager_ids = {}
    for email, name in PROJECT_MANAGERS:
        connection.execute(
            "INSERT OR IGNORE INTO users (email, name, password_hash, role) VALUES (?, ?, ?, 'employee')",
            (email, name, generate_password_hash(secrets.token_urlsafe(24))),
        )
        manager_ids[name] = connection.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()[0]

    demo_client_user = connection.execute(
        "SELECT id FROM users WHERE email = ?", (DEMO_CLIENT_EMAIL,)
    ).fetchone()

    client_ids = {}
    for project in PROJECTS:
        client_name = project[1]
        if client_name in client_ids:
            continue
        user_id = demo_client_user[0] if demo_client_user and client_name == DEMO_CLIENT_NAME_IN_DATA else None
        cursor = connection.execute(
            "INSERT INTO clients (user_id, name) VALUES (?, ?)", (user_id, client_name)
        )
        client_ids[client_name] = cursor.lastrowid

    for number, (name, client, manager, status, budget, actual, progress, due, kind) in enumerate(PROJECTS, start=1):
        cursor = connection.execute(
            """
            INSERT INTO projects (project_number, name, project_type, client_id, project_manager_id,
                                  status, budget_amount, progress_percent, due_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (f"BB-{number:04d}", name, kind, client_ids[client], manager_ids[manager],
             status, budget, progress, due),
        )
        project_id = cursor.lastrowid

        # Costs to date, split into materials and labor receipts so the
        # Actual Cost column adds up to the same numbers as before.
        materials = round(actual * 0.6)
        labor = actual - materials
        for category, vendor, amount in (
            ("Materials", "Materials to date (sample data)", materials),
            ("Labor", "Labor to date (sample data)", labor),
        ):
            connection.execute(
                """
                INSERT INTO receipts (project_id, category_id, vendor_name, amount, receipt_date)
                VALUES (?, ?, ?, ?, '2026-10-31')
                """,
                (project_id, category_ids[category], vendor, amount),
            )

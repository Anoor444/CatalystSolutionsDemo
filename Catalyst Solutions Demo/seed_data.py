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

# Sample projects are dated before the sample estimates, so they don't crowd "Recent Activity".
SAMPLE_PROJECT_CREATED_AT = "2026-08-15 09:00:00"

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
                                  status, budget_amount, progress_percent, due_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (f"BB-{number:04d}", name, kind, client_ids[client], manager_ids[manager],
             status, budget, progress, due, SAMPLE_PROJECT_CREATED_AT),
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

    load_billing_samples(connection)
    load_task_samples(connection)


# ---------------------------------------------------------------------
# Sample estimates and invoices (backend step 2)
# ---------------------------------------------------------------------
# id, title, client, created by, status, created date, converted into project, line items
# line item: (category, description, quantity, unit cost)
ESTIMATES = (
    (1001, "Riverstone Kitchen Remodel", "Sarah Johnson", "Daniel Carter", "Converted", "2026-08-18",
     "Riverstone Kitchen Remodel",
     (("Materials", "Cabinets and countertops", 1, 28500), ("Labor", "Demo and install labor (hours)", 120, 85),
      ("Subcontractor", "Plumbing and electrical", 1, 8500), ("Permits & Fees", "City permit", 1, 1300))),
    (1002, "Katy Home Addition", "Robert Garcia", "James Wilson", "Converted", "2026-08-25",
     "Katy Home Addition",
     (("Materials", "Foundation and framing package", 1, 46000), ("Materials", "Roofing and exterior", 1, 18000),
      ("Subcontractor", "Plumbing, electrical and HVAC", 1, 21500), ("Labor", "General labor (hours)", 80, 81.25))),
    (1003, "Cypress Window Replacement", "Robert Nguyen", "Carlos Reyes", "Approved", "2026-09-22", None,
     (("Materials", "Impact windows", 1, 9800), ("Labor", "Install labor (hours)", 64, 80),
      ("Disposal", "Old window haul-off", 1, 480))),
    (1004, "Bellaire Pool House", "Marcus Williams", "Daniel Carter", "Sent", "2026-09-29", None,
     (("Subcontractor", "Plumbing rough-in and finish", 1, 12500), ("Materials", "Tile, fixtures and finishes", 1, 16800),
      ("Labor", "General labor (hours)", 110, 85), ("Permits & Fees", "Permit and inspection", 1, 2350))),
    (1005, "Pearland Pergola", "David Chen", "Carlos Reyes", "Sent", "2026-10-01", None,
     (("Materials", "Cedar posts and beams", 1, 6200), ("Labor", "Framing labor (hours)", 60, 80),
      ("Equipment", "Post-hole auger rental (days)", 2, 175))),
    (1006, "Heights Attic Insulation", "Olivia Martinez", "James Wilson", "Sent", "2026-10-03", None,
     (("Labor", "Insulation install (hours)", 40, 82), ("Materials", "Spray foam insulation", 1, 4100))),
    (1007, "West University Fence Replacement", "Rachel Morgan", "Carlos Reyes", "Sent", "2026-10-06", None,
     (("Materials", "Pressure-treated pickets and rails", 210, 14.5), ("Labor", "Install labor (hours)", 48, 70),
      ("Disposal", "Old fence haul-off", 1, 650))),
    (1008, "Richmond Laundry Room Refresh", "Sophia Patel", "Daniel Carter", "Draft", "2026-10-09", None,
     (("Materials", "Cabinets and shelving", 1, 3400), ("Labor", "Install labor (hours)", 24, 80))),
    (1009, "Clear Lake Deck Lighting", "William Anderson", "James Wilson", "Draft", "2026-10-11", None,
     (("Materials", "Low-voltage deck lights", 45, 62), ("Labor", "Wiring and install (hours)", 36, 80))),
    (1010, "Spring Parking Lot Repaving", "Lakeside Dental Group", "Carlos Reyes", "Rejected", "2026-09-12", None,
     (("Subcontractor", "Asphalt repave and stripe", 1, 9800), ("Equipment", "Skid steer rental (days)", 2, 420))),
)

# id, project, status, issue date, due date, paid on, line items (description, quantity, unit price)
INVOICES = (
    (1040, "Riverstone Kitchen Remodel",   "Paid",   "2026-08-20", "2026-09-19", "2026-09-10", (("Deposit – 30% of contract", 1, 15000),)),
    (1041, "Katy Home Addition",           "Paid",   "2026-08-28", "2026-09-27", "2026-09-20", (("Foundation pour", 1, 14000), ("Site prep and grading", 1, 8000))),
    (1042, "Sugar Land Roof Replacement",  "Paid",   "2026-09-15", "2026-10-15", "2026-10-27", (("Tear-off and disposal", 1, 3800), ("Shingle installation – first half", 1, 6000))),
    (1043, "Katy Home Addition",           "Paid",   "2026-09-30", "2026-10-30", "2026-10-20", (("Rough plumbing and electrical", 1, 14600),)),
    (1044, "Memorial Bathroom Renovation", "Paid",   "2026-10-01", "2026-10-31", "2026-10-08", (("Deposit – design and planning", 1, 2500),)),
    (1045, "Riverstone Kitchen Remodel",   "Unpaid", "2026-10-10", "2026-11-09", None, (("Cabinet installation – progress billing", 1, 9500), ("Countertop templating", 1, 3000))),
    (1046, "Katy Home Addition",           "Unpaid", "2026-09-15", "2026-10-15", None, (("Framing labor (hours)", 75, 90), ("Lumber delivery", 1, 1500))),
    (1047, "Sugar Land Roof Replacement",  "Unpaid", "2026-10-20", "2026-11-19", None, (("Final roof inspection and cleanup", 1, 4000),)),
    (1048, "Memorial Bathroom Renovation", "Draft",  "2026-10-28", "2026-11-27", None, (("Design consultation", 1, 1000), ("Demo – bathroom fixtures", 1, 1500))),
)


def load_billing_samples(connection):
    """Add the sample estimates and invoices. Skips any row whose client or project
    no longer exists, so it is safe on a database people have already edited."""
    def lookup(sql, value):
        row = connection.execute(sql, (value,)).fetchone()
        return row[0] if row else None

    for est_id, title, client, creator, status, created, project_name, lines in ESTIMATES:
        client_id = lookup("SELECT client_id FROM clients WHERE name = ?", client)
        if client_id is None:
            continue
        items = [(lookup("SELECT category_id FROM cost_categories WHERE name = ?", cat), desc, qty, cost,
                  round(qty * cost, 2)) for cat, desc, qty, cost in lines]
        connection.execute(
            """INSERT INTO estimates (estimate_id, estimate_number, title, client_id, created_by, status, total_amount, created_at)
               VALUES (?, ?, ?, ?, (SELECT id FROM users WHERE name = ?), ?, ?, ?)""",
            (est_id, f"EST-{est_id}", title, client_id, creator, status,
             round(sum(item[4] for item in items), 2), f"{created} 09:00:00"),
        )
        connection.executemany(
            """INSERT INTO estimate_line_items (estimate_id, category_id, description, quantity, unit_cost, line_total)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(est_id, *item) for item in items],
        )
        if project_name:
            connection.execute(
                "UPDATE projects SET estimate_id = ? WHERE name = ? AND estimate_id IS NULL", (est_id, project_name)
            )

    for inv_id, project_name, status, issued, due, paid_on, lines in INVOICES:
        project_id = lookup("SELECT project_id FROM projects WHERE name = ?", project_name)
        if project_id is None:
            continue
        items = [(desc, qty, price, round(qty * price, 2)) for desc, qty, price in lines]
        connection.execute(
            """INSERT INTO invoices (invoice_id, invoice_number, project_id, issue_date, due_date, status, total_amount, paid_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (inv_id, f"INV-{inv_id}", project_id, issued, due, status,
             round(sum(item[3] for item in items), 2), paid_on),
        )
        connection.executemany(
            """INSERT INTO invoice_line_items (invoice_id, description, quantity, unit_price, line_total)
               VALUES (?, ?, ?, ?, ?)""",
            [(inv_id, *item) for item in items],
        )


# ---------------------------------------------------------------------
# Sample tasks (backend step 4)
# ---------------------------------------------------------------------
# Dates are days from the day the sample data is loaded, so a fresh demo
# always has some overdue, some current and some upcoming tasks.
# project, task, description, assigned to, start (days), due (days), priority, status
TASKS = (
    ("Riverstone Kitchen Remodel", "Order construction materials", "Order cabinets, countertops, and tile.", "Daniel Carter", -60, -55, "High", "Completed"),
    ("Riverstone Kitchen Remodel", "Complete demolition", "Remove old cabinets, flooring, and drywall.", "Demo Crew A", -50, -44, "High", "Completed"),
    ("Riverstone Kitchen Remodel", "Inspect electrical work", "City rough-in electrical inspection.", "Daniel Carter", -4, -2, "High", "In Progress"),
    ("Riverstone Kitchen Remodel", "Install cabinets", "Install upper and lower cabinets and hardware.", "Finish Crew B", -1, 5, "Medium", "In Progress"),
    ("Riverstone Kitchen Remodel", "Countertop measurement", "Template quartz countertops after cabinets are set.", "Stone Fabricator", 6, 7, "Medium", "Not Started"),
    ("Riverstone Kitchen Remodel", "Final project walkthrough", "Walkthrough and punch list with Sarah Johnson.", "Daniel Carter", 19, 20, "Medium", "Not Started"),
    ("Sugar Land Roof Replacement", "Tear off old roofing", "Remove shingles and damaged decking.", "Roofing Crew", -18, -14, "High", "Completed"),
    ("Sugar Land Roof Replacement", "Order replacement gutters", "Order seamless gutters and downspouts.", "Daniel Carter", -8, -5, "Low", "Not Started"),
    ("Sugar Land Roof Replacement", "Install underlayment and shingles", "Install synthetic underlayment and shingles.", "Roofing Crew", -3, 2, "High", "In Progress"),
    ("Sugar Land Roof Replacement", "Final roof inspection", "City final inspection and client walkthrough.", "Daniel Carter", 2, 3, "High", "Not Started"),
    ("Memorial Bathroom Renovation", "Submit permit application", "Bathroom remodel permit with the city.", "James Wilson", -16, -13, "High", "Completed"),
    ("Memorial Bathroom Renovation", "Finalize tile and fixture selections", "Confirm selections with Emily Davis.", "James Wilson", -7, 3, "Medium", "In Progress"),
    ("Memorial Bathroom Renovation", "Schedule subcontractor visit", "Plumber site visit to plan shower relocation.", "James Wilson", 4, 8, "Medium", "Not Started"),
    ("Memorial Bathroom Renovation", "Complete demolition", "Remove tub, tile, and vanity.", "Demo Crew A", 14, 17, "Low", "Not Started"),
    ("Katy Home Addition", "Pour foundation", "Form, inspect, and pour slab foundation.", "Concrete Sub LLC", -68, -60, "High", "Completed"),
    ("Katy Home Addition", "Frame walls and roof", "Frame exterior walls, interior walls, and roof.", "Framing Crew", -20, -1, "High", "In Progress"),
    ("Katy Home Addition", "Plumbing rough-in inspection", "City inspection before insulation.", "James Wilson", 3, 6, "Medium", "Not Started"),
    ("Katy Home Addition", "Install windows and exterior doors", "Install windows, patio door, and exterior trim.", "Framing Crew", 10, 15, "Medium", "Not Started"),
)


def load_task_samples(connection):
    from datetime import date, timedelta

    def day(offset):
        return (date.today() + timedelta(days=offset)).isoformat()

    for project, title, description, assigned, start, due, priority, status in TASKS:
        row = connection.execute("SELECT project_id FROM projects WHERE name = ?", (project,)).fetchone()
        if row is None:
            continue
        connection.execute(
            """INSERT INTO tasks (project_id, title, description, assigned_to, start_date, due_date, priority, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (row[0], title, description, assigned, day(start), day(due), priority, status),
        )

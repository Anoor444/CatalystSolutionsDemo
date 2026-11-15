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
    ("Miscellaneous", "Small supplies and other costs"),
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

    load_billing_samples(connection)
    load_task_samples(connection)
    load_cost_samples(connection)
    load_directory_samples(connection)


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


# ---------------------------------------------------------------------
# Sample job costs (backend step 5)
# ---------------------------------------------------------------------
# The first four projects get the detailed expenses and category budgets that the
# Job Costs page used to keep in demo_data.py. The other sample projects get their
# costs to date as two summary expenses (materials and labor), with a matching
# 60/40 category budget. Projects converted from an estimate get their category
# budget from the estimate's line items.
DEMO_CATEGORY_NAMES = {"Subcontractors": "Subcontractor", "Permits": "Permits & Fees"}


def load_cost_samples(connection):
    from demo_data import get_demo_projects, get_job_cost_data

    connection.execute(
        "INSERT OR IGNORE INTO cost_categories (name, description) VALUES ('Miscellaneous', 'Small supplies and other costs')"
    )
    category_ids = {row[1]: row[0] for row in connection.execute("SELECT category_id, name FROM cost_categories")}
    project_ids = {row[1]: row[0] for row in connection.execute("SELECT project_id, name FROM projects")}

    def category(name):
        return category_ids[DEMO_CATEGORY_NAMES.get(name, name)]

    def add_budget(project_id, category_name, amount):
        connection.execute(
            """INSERT INTO project_budget_items (project_id, category_id, estimated_amount) VALUES (?, ?, ?)
               ON CONFLICT (project_id, category_id) DO UPDATE SET estimated_amount = estimated_amount + excluded.estimated_amount""",
            (project_id, category(category_name), amount),
        )

    def add_expense(project_id, category_name, description, amount, day, filename=None):
        connection.execute(
            """INSERT INTO receipts (project_id, category_id, description, amount, expense_date, receipt_filename)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, category(category_name), description, amount, day, filename),
        )

    # 1) Detailed sample data for the first four projects
    demo = get_job_cost_data()
    demo_names = {p["id"]: p["name"] for p in get_demo_projects()}
    detailed = set()
    for row in demo["estimates"]:
        project_id = project_ids.get(demo_names[row["project_id"]])
        if project_id:
            add_budget(project_id, row["category"], row["estimated_amount"])
            detailed.add(project_id)
    for row in demo["expenses"]:
        project_id = project_ids.get(demo_names[row["project_id"]])
        if project_id:
            # Sample receipts are names only (no file on disk), so they show as "not on file".
            add_expense(project_id, row["category"], row["description"], row["amount"],
                        row["expense_date"], row["receipt_name"])

    # 2) Other sample projects: costs to date as two summary expenses
    for name, _client, _manager, _status, budget, actual, *_rest in PROJECTS:
        project_id = project_ids.get(name)
        if not project_id or project_id in detailed:
            continue
        materials = round(actual * 0.6)
        add_budget(project_id, "Materials", round(budget * 0.6, 2))
        add_budget(project_id, "Labor", round(budget - round(budget * 0.6, 2), 2))
        add_expense(project_id, "Materials", "Materials to date", materials, "2026-10-31")
        add_expense(project_id, "Labor", "Labor to date", actual - materials, "2026-10-31")
        detailed.add(project_id)

    # 3) Projects converted from an estimate: budget by category from the estimate
    for (project_id,) in connection.execute(
        "SELECT project_id FROM projects WHERE estimate_id IS NOT NULL").fetchall():
        if project_id not in detailed:
            copy_estimate_budget(connection, project_id)


def copy_estimate_budget(connection, project_id):
    """Category budget for a project = its estimate's line items, totalled by category."""
    connection.execute(
        """INSERT OR IGNORE INTO project_budget_items (project_id, category_id, estimated_amount)
           SELECT p.project_id, li.category_id, SUM(li.line_total)
           FROM projects p JOIN estimate_line_items li ON li.estimate_id = p.estimate_id
           WHERE p.project_id = ? AND li.category_id IS NOT NULL
           GROUP BY li.category_id""",
        (project_id,),
    )


# ---------------------------------------------------------------------
# Sample client details and subcontractors (backend step 6)
# ---------------------------------------------------------------------
# client: (email, phone, company)
CLIENT_DETAILS = {
    "Sarah Johnson": ("sarah.johnson@example.com", "(555) 010-1001", None),
    "Michael Thompson": ("michael.thompson@example.com", "(555) 010-1002", None),
    "Emily Davis": ("emily.davis@example.com", "(555) 010-1003", None),
    "Robert Garcia": ("robert.garcia@example.com", "(555) 010-1004", None),
    "Robert Nguyen": ("robert.nguyen@example.com", "(713) 555-0105", None),
    "Olivia Martinez": ("olivia.martinez@example.com", "(281) 555-0106", None),
    "David Chen": ("david.chen@example.com", "(832) 555-0107", None),
    "Lakeside Dental Group": ("office@lakesidedental.example.com", "(346) 555-0108", "Lakeside Dental Group"),
    "Rachel Morgan": ("rachel.morgan@example.com", "(713) 555-0109", None),
    "Marcus Williams": ("marcus.williams@example.com", "(281) 555-0110", None),
    "Sophia Patel": ("sophia.patel@example.com", "(832) 555-0111", None),
    "William Anderson": ("william.anderson@example.com", "(346) 555-0112", None),
}

# contact, company, trade, email, phone, status, assigned projects
SUBCONTRACTORS = (
    ("Demo Subcontractor", "Demo Subcontracting LLC", "General Construction", "demo.subcontractor@buffbison.com",
     "(555) 010-2000", "Active", ("Riverstone Kitchen Remodel", "Sugar Land Roof Replacement", "Memorial Bathroom Renovation")),
    ("John Miller", "Miller Electrical Services", "Electrical", "john@millerelectrical.example.com", "(713) 555-0201",
     "Active", ("Riverstone Kitchen Remodel", "Heights Garage Conversion")),
    ("Carlos Rodriguez", "Rodriguez Plumbing LLC", "Plumbing", "carlos@rodriguezplumbing.example.com", "(281) 555-0202",
     "Active", ("Memorial Bathroom Renovation",)),
    ("David Thompson", "Thompson Roofing", "Roofing", "david@thompsonroofing.example.com", "(832) 555-0203",
     "Inactive", ("Sugar Land Roof Replacement",)),
    ("Priya Patel", "Patel HVAC Services", "Heating & Cooling", "priya@patelhvac.example.com", "(346) 555-0204",
     "Active", ("Katy Home Addition", "Spring Office Build-Out", "Heights Garage Conversion")),
    ("Marcus Reed", "Reed Concrete Works", "Concrete & Foundations", "marcus@reedconcrete.example.com", "(713) 555-0205",
     "Active", ("Katy Home Addition", "Pearland Patio Extension")),
    ("Ashley Nguyen", "Nguyen Custom Cabinets", "Cabinetry & Millwork", "ashley@nguyencabinets.example.com", "(281) 555-0206",
     "Active", ("Riverstone Kitchen Remodel",)),
    ("Luis Martinez", "Martinez Flooring Co.", "Flooring & Tile", "luis@martinezflooring.example.com", "(832) 555-0207",
     "Active", ("West University Flooring Upgrade", "Memorial Bathroom Renovation")),
    ("Nicole Brooks", "Brooks Painting Studio", "Interior & Exterior Painting", "nicole@brookspainting.example.com",
     "(346) 555-0208", "Active", ("Cypress Storm Damage Repair",)),
    ("Kevin Wilson", "Wilson Framing Crew", "Framing & Carpentry", "kevin@wilsonframing.example.com", "(713) 555-0209",
     "Inactive", ()),
    ("Tanya Robinson", "Robinson Landscape Design", "Landscaping", "tanya@robinsonlandscape.example.com", "(281) 555-0210",
     "Active", ("Bellaire Outdoor Kitchen",)),
)


def load_directory_samples(connection):
    for name, (email, phone, company) in CLIENT_DETAILS.items():
        connection.execute(
            """UPDATE clients SET email = COALESCE(email, ?), phone = COALESCE(phone, ?), company = COALESCE(company, ?)
               WHERE name = ?""",
            (email, phone, company, name),
        )

    if connection.execute("SELECT COUNT(*) FROM subcontractors").fetchone()[0]:
        return
    for contact, company, trade, email, phone, status, projects in SUBCONTRACTORS:
        user = connection.execute(
            "SELECT id FROM users WHERE lower(email) = lower(?) AND role = 'subcontractor'", (email,)).fetchone()
        cursor = connection.execute(
            """INSERT INTO subcontractors (user_id, company_name, contact_name, trade, email, phone, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user[0] if user else None, company, contact, trade, email, phone, status),
        )
        for project in projects:
            row = connection.execute("SELECT project_id FROM projects WHERE name = ?", (project,)).fetchone()
            if row:
                connection.execute(
                    """INSERT INTO project_assignments (project_id, subcontractor_id, status, assigned_date)
                       VALUES (?, ?, ?, '2026-09-01')""",
                    (row[0], cursor.lastrowid, "Active" if status == "Active" else "Completed"),
                )

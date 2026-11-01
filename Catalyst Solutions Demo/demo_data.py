"""
demo_data.py
Buff Bison Construction Management System - Team 7 (Catalyst Solutions Demo)

TEMPORARY sample data for the Job Costs and Schedule pages.

The projects, ids, budgets, and actual costs match the sample rows on
projects.html, so every page tells the same story:

    id 1  Riverstone Kitchen Remodel     budget $48,500   actual $31,200
    id 2  Sugar Land Roof Replacement    budget $22,000   actual $13,800
    id 3  Memorial Bathroom Renovation   budget $35,750   actual  $2,500
    id 4  Katy Home Addition             budget $92,000   actual $44,600

Each list below is shaped like a future MySQL table (one dictionary = one row),
so later we can replace each function body with a database query and the
templates and JavaScript keep working without changes:

    get_demo_projects()  ->  SELECT id, name FROM projects
    estimates            ->  estimated cost per category (from approved estimates)
    expenses             ->  SELECT ... FROM project_expenses
    tasks                ->  SELECT ... FROM project_tasks
"""

from datetime import date, timedelta


# The six cost categories used on the Job Costs page.
COST_CATEGORIES = [
    "Materials",
    "Labor",
    "Equipment",
    "Subcontractors",
    "Permits",
    "Miscellaneous",
]

TASK_STATUSES = ["Not Started", "In Progress", "Completed"]
TASK_PRIORITIES = ["Low", "Medium", "High"]


def get_demo_projects():
    """Same ids and names as the rows on projects.html (/project/1 ... /project/4)."""
    return [
        {"id": 1, "name": "Riverstone Kitchen Remodel"},
        {"id": 2, "name": "Sugar Land Roof Replacement"},
        {"id": 3, "name": "Memorial Bathroom Renovation"},
        {"id": 4, "name": "Katy Home Addition"},
    ]


def _days_from_today(number_of_days):
    """Returns a 'YYYY-MM-DD' date relative to today (negative = in the past).
    Relative dates keep the demo realistic no matter which day it is shown."""
    return (date.today() + timedelta(days=number_of_days)).isoformat()


def get_job_cost_data():
    """Projects, categories, estimated cost per category, and individual expenses.
    Actual costs are NOT stored separately - the page adds up the expenses,
    so actual totals always match the expense table."""
    d = _days_from_today

    estimates = [
        # 1 - Riverstone Kitchen Remodel (total $48,500)
        {"project_id": 1, "category": "Materials", "estimated_amount": 21000.00},
        {"project_id": 1, "category": "Labor", "estimated_amount": 15000.00},
        {"project_id": 1, "category": "Equipment", "estimated_amount": 2500.00},
        {"project_id": 1, "category": "Subcontractors", "estimated_amount": 7500.00},
        {"project_id": 1, "category": "Permits", "estimated_amount": 1000.00},
        {"project_id": 1, "category": "Miscellaneous", "estimated_amount": 1500.00},
        # 2 - Sugar Land Roof Replacement (total $22,000)
        {"project_id": 2, "category": "Materials", "estimated_amount": 9500.00},
        {"project_id": 2, "category": "Labor", "estimated_amount": 7000.00},
        {"project_id": 2, "category": "Equipment", "estimated_amount": 1200.00},
        {"project_id": 2, "category": "Subcontractors", "estimated_amount": 2800.00},
        {"project_id": 2, "category": "Permits", "estimated_amount": 500.00},
        {"project_id": 2, "category": "Miscellaneous", "estimated_amount": 1000.00},
        # 3 - Memorial Bathroom Renovation (total $35,750)
        {"project_id": 3, "category": "Materials", "estimated_amount": 14000.00},
        {"project_id": 3, "category": "Labor", "estimated_amount": 11000.00},
        {"project_id": 3, "category": "Equipment", "estimated_amount": 1250.00},
        {"project_id": 3, "category": "Subcontractors", "estimated_amount": 7500.00},
        {"project_id": 3, "category": "Permits", "estimated_amount": 750.00},
        {"project_id": 3, "category": "Miscellaneous", "estimated_amount": 1250.00},
        # 4 - Katy Home Addition (total $92,000)
        {"project_id": 4, "category": "Materials", "estimated_amount": 38000.00},
        {"project_id": 4, "category": "Labor", "estimated_amount": 30000.00},
        {"project_id": 4, "category": "Equipment", "estimated_amount": 6000.00},
        {"project_id": 4, "category": "Subcontractors", "estimated_amount": 14000.00},
        {"project_id": 4, "category": "Permits", "estimated_amount": 2000.00},
        {"project_id": 4, "category": "Miscellaneous", "estimated_amount": 2000.00},
    ]

    # receipt_name is only a file NAME - no file is actually stored in the demo.
    expenses = [
        # 1 - Riverstone Kitchen: $31,200 total (Permits slightly over)
        {"id": 1, "project_id": 1, "expense_date": d(-62), "description": "City remodel permit", "category": "Permits", "amount": 850.00, "receipt_name": "remodel-permit.pdf"},
        {"id": 2, "project_id": 1, "expense_date": d(-58), "description": "Dumpster rental", "category": "Equipment", "amount": 1350.00, "receipt_name": "dumpster.jpg"},
        {"id": 3, "project_id": 1, "expense_date": d(-55), "description": "Cabinet package deposit", "category": "Materials", "amount": 9850.00, "receipt_name": "cabinet-deposit.pdf"},
        {"id": 4, "project_id": 1, "expense_date": d(-40), "description": "Framing and drywall crew (2 weeks)", "category": "Labor", "amount": 8400.00, "receipt_name": None},
        {"id": 5, "project_id": 1, "expense_date": d(-30), "description": "Licensed electrician - rough-in wiring", "category": "Subcontractors", "amount": 4950.00, "receipt_name": "electrician-invoice.pdf"},
        {"id": 6, "project_id": 1, "expense_date": d(-22), "description": "Permit revision fee (layout change)", "category": "Permits", "amount": 300.00, "receipt_name": None},
        {"id": 7, "project_id": 1, "expense_date": d(-15), "description": "Quartz countertops deposit", "category": "Materials", "amount": 5000.00, "receipt_name": "countertops.pdf"},
        {"id": 8, "project_id": 1, "expense_date": d(-6), "description": "Fasteners, caulk, and job-site supplies", "category": "Miscellaneous", "amount": 500.00, "receipt_name": None},

        # 2 - Sugar Land Roof: $13,800 total (Equipment over)
        {"id": 9, "project_id": 2, "expense_date": d(-35), "description": "Roofing permit", "category": "Permits", "amount": 500.00, "receipt_name": "roof-permit.pdf"},
        {"id": 10, "project_id": 2, "expense_date": d(-28), "description": "Architectural shingles (32 squares)", "category": "Materials", "amount": 6200.00, "receipt_name": "shingles.pdf"},
        {"id": 11, "project_id": 2, "expense_date": d(-27), "description": "Underlayment and flashing", "category": "Materials", "amount": 1250.00, "receipt_name": None},
        {"id": 12, "project_id": 2, "expense_date": d(-21), "description": "Material lift and roll-off dumpster", "category": "Equipment", "amount": 1450.00, "receipt_name": "lift-rental.pdf"},
        {"id": 13, "project_id": 2, "expense_date": d(-18), "description": "Tear-off and install crew", "category": "Labor", "amount": 4200.00, "receipt_name": None},
        {"id": 14, "project_id": 2, "expense_date": d(-10), "description": "Landfill disposal fees", "category": "Miscellaneous", "amount": 200.00, "receipt_name": None},

        # 3 - Memorial Bathroom: $2,500 total (planning stage)
        {"id": 15, "project_id": 3, "expense_date": d(-14), "description": "Bathroom remodel permit", "category": "Permits", "amount": 750.00, "receipt_name": "bath-permit.pdf"},
        {"id": 16, "project_id": 3, "expense_date": d(-9), "description": "Tile and fixture selections deposit", "category": "Materials", "amount": 1500.00, "receipt_name": "fixtures-deposit.pdf"},
        {"id": 17, "project_id": 3, "expense_date": d(-4), "description": "Site protection materials", "category": "Miscellaneous", "amount": 250.00, "receipt_name": None},

        # 4 - Katy Home Addition: $44,600 total (Permits over)
        {"id": 18, "project_id": 4, "expense_date": d(-75), "description": "Building permit", "category": "Permits", "amount": 1850.00, "receipt_name": "building-permit.pdf"},
        {"id": 19, "project_id": 4, "expense_date": d(-70), "description": "Excavator rental", "category": "Equipment", "amount": 3100.00, "receipt_name": "excavator.pdf"},
        {"id": 20, "project_id": 4, "expense_date": d(-66), "description": "Foundation concrete", "category": "Materials", "amount": 8400.00, "receipt_name": "concrete.pdf"},
        {"id": 21, "project_id": 4, "expense_date": d(-64), "description": "Foundation crew", "category": "Labor", "amount": 9800.00, "receipt_name": None},
        {"id": 22, "project_id": 4, "expense_date": d(-48), "description": "Framing lumber package", "category": "Materials", "amount": 11400.00, "receipt_name": "lumber.pdf"},
        {"id": 23, "project_id": 4, "expense_date": d(-40), "description": "Utility tap fee", "category": "Permits", "amount": 400.00, "receipt_name": None},
        {"id": 24, "project_id": 4, "expense_date": d(-30), "description": "Framing crew", "category": "Labor", "amount": 6700.00, "receipt_name": None},
        {"id": 25, "project_id": 4, "expense_date": d(-20), "description": "Plumber - underground rough-in", "category": "Subcontractors", "amount": 2700.00, "receipt_name": "plumber-invoice.pdf"},
        {"id": 26, "project_id": 4, "expense_date": d(-12), "description": "Temporary fencing", "category": "Miscellaneous", "amount": 250.00, "receipt_name": None},
    ]

    return {
        "projects": get_demo_projects(),
        "categories": COST_CATEGORIES,
        "estimates": estimates,
        "expenses": expenses,
    }


def get_schedule_data():
    """Projects, tasks, and option lists for the Schedule page.
    Dates are relative to today, so some tasks are always overdue or upcoming."""
    d = _days_from_today

    tasks = [
        # 1 - Riverstone Kitchen Remodel
        {"id": 1, "project_id": 1, "name": "Order construction materials", "description": "Order cabinets, countertops, and tile.", "assigned_to": "Daniel Carter", "start_date": d(-60), "due_date": d(-55), "priority": "High", "status": "Completed"},
        {"id": 2, "project_id": 1, "name": "Complete demolition", "description": "Remove old cabinets, flooring, and drywall.", "assigned_to": "Demo Crew A", "start_date": d(-50), "due_date": d(-44), "priority": "High", "status": "Completed"},
        {"id": 3, "project_id": 1, "name": "Inspect electrical work", "description": "City rough-in electrical inspection.", "assigned_to": "Daniel Carter", "start_date": d(-4), "due_date": d(-2), "priority": "High", "status": "In Progress"},
        {"id": 4, "project_id": 1, "name": "Install cabinets", "description": "Install upper and lower cabinets and hardware.", "assigned_to": "Finish Crew B", "start_date": d(-1), "due_date": d(5), "priority": "Medium", "status": "In Progress"},
        {"id": 5, "project_id": 1, "name": "Countertop measurement", "description": "Template quartz countertops after cabinets are set.", "assigned_to": "Stone Fabricator", "start_date": d(6), "due_date": d(7), "priority": "Medium", "status": "Not Started"},
        {"id": 6, "project_id": 1, "name": "Final project walkthrough", "description": "Walkthrough and punch list with Sarah Johnson.", "assigned_to": "Daniel Carter", "start_date": d(19), "due_date": d(20), "priority": "Medium", "status": "Not Started"},

        # 2 - Sugar Land Roof Replacement
        {"id": 7, "project_id": 2, "name": "Tear off old roofing", "description": "Remove shingles and damaged decking.", "assigned_to": "Roofing Crew", "start_date": d(-18), "due_date": d(-14), "priority": "High", "status": "Completed"},
        {"id": 8, "project_id": 2, "name": "Order replacement gutters", "description": "Order seamless gutters and downspouts.", "assigned_to": "Daniel Carter", "start_date": d(-8), "due_date": d(-5), "priority": "Low", "status": "Not Started"},
        {"id": 9, "project_id": 2, "name": "Install underlayment and shingles", "description": "Install synthetic underlayment and shingles.", "assigned_to": "Roofing Crew", "start_date": d(-3), "due_date": d(2), "priority": "High", "status": "In Progress"},
        {"id": 10, "project_id": 2, "name": "Final roof inspection", "description": "City final inspection and client walkthrough.", "assigned_to": "Daniel Carter", "start_date": d(2), "due_date": d(3), "priority": "High", "status": "Not Started"},

        # 3 - Memorial Bathroom Renovation
        {"id": 11, "project_id": 3, "name": "Submit permit application", "description": "Bathroom remodel permit with the city.", "assigned_to": "James Wilson", "start_date": d(-16), "due_date": d(-13), "priority": "High", "status": "Completed"},
        {"id": 12, "project_id": 3, "name": "Finalize tile and fixture selections", "description": "Confirm selections with Emily Davis.", "assigned_to": "James Wilson", "start_date": d(-7), "due_date": d(3), "priority": "Medium", "status": "In Progress"},
        {"id": 13, "project_id": 3, "name": "Schedule subcontractor visit", "description": "Plumber site visit to plan shower relocation.", "assigned_to": "James Wilson", "start_date": d(4), "due_date": d(8), "priority": "Medium", "status": "Not Started"},
        {"id": 14, "project_id": 3, "name": "Complete demolition", "description": "Remove tub, tile, and vanity.", "assigned_to": "Demo Crew A", "start_date": d(14), "due_date": d(17), "priority": "Low", "status": "Not Started"},

        # 4 - Katy Home Addition
        {"id": 15, "project_id": 4, "name": "Pour foundation", "description": "Form, inspect, and pour slab foundation.", "assigned_to": "Concrete Sub LLC", "start_date": d(-68), "due_date": d(-60), "priority": "High", "status": "Completed"},
        {"id": 16, "project_id": 4, "name": "Frame walls and roof", "description": "Frame exterior walls, interior walls, and roof.", "assigned_to": "Framing Crew", "start_date": d(-20), "due_date": d(-1), "priority": "High", "status": "In Progress"},
        {"id": 17, "project_id": 4, "name": "Plumbing rough-in inspection", "description": "City inspection before insulation.", "assigned_to": "James Wilson", "start_date": d(3), "due_date": d(6), "priority": "Medium", "status": "Not Started"},
        {"id": 18, "project_id": 4, "name": "Install windows and exterior doors", "description": "Install windows, patio door, and exterior trim.", "assigned_to": "Framing Crew", "start_date": d(10), "due_date": d(15), "priority": "Medium", "status": "Not Started"},
    ]

    return {
        "projects": get_demo_projects(),
        "statuses": TASK_STATUSES,
        "priorities": TASK_PRIORITIES,
        "tasks": tasks,
    }

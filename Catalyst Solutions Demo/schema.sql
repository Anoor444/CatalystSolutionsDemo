-- =====================================================================
-- Buff Bison Construction Portal – database schema
--
-- Based on the team ERD, plus the fixes the front end needed:
--   projects.start_date / due_date / progress_percent / project_type /
--   description / address, estimates.title / created_at, invoices.paid_at.
--
-- Written for SQLite now. Types are chosen so moving to MySQL later is
-- mostly search-and-replace (INTEGER PRIMARY KEY -> INT AUTO_INCREMENT
-- PRIMARY KEY, TEXT -> VARCHAR(...)). DECIMAL(12,2) works in both.
--
-- Every statement uses IF NOT EXISTS, so running this file again is safe.
-- The users table is created by app.py (login system) and is not repeated here.
-- =====================================================================

-- ---------- Lookups ----------

CREATE TABLE IF NOT EXISTS cost_categories (
    category_id   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    description   TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- ---------- People ----------

-- A client can be a person or a company, so the ERD's first/last name
-- columns are combined into one display name.
CREATE TABLE IF NOT EXISTS clients (
    client_id     INTEGER PRIMARY KEY,
    user_id       INTEGER UNIQUE REFERENCES users(id) ON DELETE SET NULL,  -- login for the client portal (optional)
    name          TEXT NOT NULL,
    email         TEXT,
    phone         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS subcontractors (
    subcontractor_id INTEGER PRIMARY KEY,
    user_id          INTEGER UNIQUE REFERENCES users(id) ON DELETE SET NULL,
    company_name     TEXT NOT NULL,
    contact_name     TEXT,
    trade            TEXT,
    email            TEXT,
    phone            TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- Estimates (RTM A3) ----------

CREATE TABLE IF NOT EXISTS estimates (
    estimate_id      INTEGER PRIMARY KEY,
    estimate_number  TEXT NOT NULL UNIQUE,
    title            TEXT NOT NULL,
    client_id        INTEGER NOT NULL REFERENCES clients(client_id),
    created_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status           TEXT NOT NULL DEFAULT 'Draft'
                     CHECK (status IN ('Draft', 'Sent', 'Approved', 'Rejected', 'Converted')),
    total_amount     DECIMAL(12,2) NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS estimate_line_items (
    line_item_id  INTEGER PRIMARY KEY,
    estimate_id   INTEGER NOT NULL REFERENCES estimates(estimate_id) ON DELETE CASCADE,
    category_id   INTEGER REFERENCES cost_categories(category_id),
    description   TEXT NOT NULL,
    quantity      DECIMAL(12,2) NOT NULL CHECK (quantity > 0),
    unit_cost     DECIMAL(12,2) NOT NULL CHECK (unit_cost >= 0),
    line_total    DECIMAL(12,2) NOT NULL
);

-- ---------- Projects (RTM A2, A4) ----------

CREATE TABLE IF NOT EXISTS projects (
    project_id          INTEGER PRIMARY KEY,
    project_number      TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    project_type        TEXT,
    description         TEXT,
    address             TEXT,
    client_id           INTEGER NOT NULL REFERENCES clients(client_id),
    estimate_id         INTEGER UNIQUE REFERENCES estimates(estimate_id) ON DELETE SET NULL,  -- set when created from an estimate (A4)
    project_manager_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status              TEXT NOT NULL DEFAULT 'Planning'
                        CHECK (status IN ('Planning', 'In Progress', 'On Hold', 'Completed')),
    budget_amount       DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (budget_amount >= 0),
    progress_percent    INTEGER NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
    start_date          TEXT,   -- YYYY-MM-DD
    due_date            TEXT,   -- YYYY-MM-DD
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- Invoices (RTM A5) ----------

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id      INTEGER PRIMARY KEY,
    invoice_number  TEXT NOT NULL UNIQUE,
    project_id      INTEGER NOT NULL REFERENCES projects(project_id),
    issue_date      TEXT NOT NULL,
    due_date        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'Draft' CHECK (status IN ('Draft', 'Unpaid', 'Paid')),
    total_amount    DECIMAL(12,2) NOT NULL DEFAULT 0,
    paid_at         TEXT,   -- set when status becomes Paid
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS invoice_line_items (
    invoice_line_item_id INTEGER PRIMARY KEY,
    invoice_id           INTEGER NOT NULL REFERENCES invoices(invoice_id) ON DELETE CASCADE,
    description          TEXT NOT NULL,
    quantity             DECIMAL(12,2) NOT NULL CHECK (quantity > 0),
    unit_price           DECIMAL(12,2) NOT NULL CHECK (unit_price >= 0),
    line_total           DECIMAL(12,2) NOT NULL
);

-- ---------- Job costs (RTM A6, A7) ----------

CREATE TABLE IF NOT EXISTS receipts (
    receipt_id    INTEGER PRIMARY KEY,
    project_id    INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    category_id   INTEGER REFERENCES cost_categories(category_id),
    uploaded_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    vendor_name   TEXT NOT NULL,
    amount        DECIMAL(12,2) NOT NULL CHECK (amount >= 0),
    receipt_date  TEXT NOT NULL,
    file_path     TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- Subcontractors (RTM A8) ----------

CREATE TABLE IF NOT EXISTS project_assignments (
    assignment_id     INTEGER PRIMARY KEY,
    project_id        INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    subcontractor_id  INTEGER NOT NULL REFERENCES subcontractors(subcontractor_id) ON DELETE CASCADE,
    scope_of_work     TEXT,
    status            TEXT NOT NULL DEFAULT 'Active',
    assigned_date     TEXT
);

CREATE TABLE IF NOT EXISTS subcontractor_invoices (
    sub_invoice_id  INTEGER PRIMARY KEY,
    assignment_id   INTEGER NOT NULL REFERENCES project_assignments(assignment_id) ON DELETE CASCADE,
    category_id     INTEGER REFERENCES cost_categories(category_id),
    reviewed_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    invoice_number  TEXT,
    amount          DECIMAL(12,2) NOT NULL CHECK (amount >= 0),
    status          TEXT NOT NULL DEFAULT 'Pending Approval'
                    CHECK (status IN ('Pending Approval', 'Approved', 'Rejected', 'Paid')),
    submitted_at    TEXT NOT NULL DEFAULT (datetime('now')),
    file_path       TEXT
);

-- ---------- Scheduling (RTM A11) ----------

CREATE TABLE IF NOT EXISTS tasks (
    task_id      INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    assigned_to  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    title        TEXT NOT NULL,
    due_date     TEXT,
    status       TEXT NOT NULL DEFAULT 'Not Started'
);

-- ---------- Files (RTM A10, documents page) ----------

CREATE TABLE IF NOT EXISTS photos (
    photo_id     INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    uploaded_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    task_id      INTEGER REFERENCES tasks(task_id) ON DELETE SET NULL,
    caption      TEXT,
    photo_type   TEXT,
    file_path    TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    document_id        INTEGER PRIMARY KEY,
    project_id         INTEGER REFERENCES projects(project_id) ON DELETE SET NULL,
    uploaded_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    document_type      TEXT NOT NULL CHECK (document_type IN ('Estimate', 'Invoice', 'Receipt', 'Contract', 'Other')),
    original_filename  TEXT NOT NULL,
    file_path          TEXT NOT NULL,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- Indexes for common lookups ----------

CREATE INDEX IF NOT EXISTS idx_projects_client     ON projects(client_id);
CREATE INDEX IF NOT EXISTS idx_projects_manager    ON projects(project_manager_id);
CREATE INDEX IF NOT EXISTS idx_estimates_client    ON estimates(client_id);
CREATE INDEX IF NOT EXISTS idx_invoices_project    ON invoices(project_id);
CREATE INDEX IF NOT EXISTS idx_receipts_project    ON receipts(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project       ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_assignments_project ON project_assignments(project_id);

-- =====================================================================
-- Buff Bison Construction Portal – database schema (MySQL 8)
--
-- Works with MySQL 8.0+, Amazon RDS for MySQL and MySQL-compatible hosts
-- such as TiDB Cloud. database.py runs this file automatically the first
-- time the app connects to an empty database; every statement uses
-- IF NOT EXISTS, so running it again is safe.
--
-- Conventions
--   * Text that is matched case-insensitively (names, emails, search) uses
--     the table default utf8mb4_unicode_ci collation. Password hashes use
--     utf8mb4_bin so they are compared exactly.
--   * Dates are DATE, timestamps are DATETIME in the app's time zone
--     (APP_TIMEZONE, default America/Chicago; set per connection).
--   * Foreign keys are written as table constraints. (MySQL ignores the
--     short "col INT REFERENCES t(id)" form, so it is never used here.)
-- =====================================================================

-- ---------- Logins (all roles) ----------

CREATE TABLE IF NOT EXISTS users (
    id             INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    email          VARCHAR(255) NOT NULL,
    name           VARCHAR(255) NOT NULL,
    first_name     VARCHAR(255) NOT NULL DEFAULT '',
    last_name      VARCHAR(255) NOT NULL DEFAULT '',
    password_hash  VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    role           VARCHAR(20) NOT NULL,
    UNIQUE KEY uq_users_email (email),
    CONSTRAINT chk_users_role CHECK (role IN ('employee', 'subcontractor', 'client'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- Lookups ----------

CREATE TABLE IF NOT EXISTS cost_categories (
    category_id   INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    description   TEXT,
    is_active     TINYINT NOT NULL DEFAULT 1,
    UNIQUE KEY uq_cost_categories_name (name),
    CONSTRAINT chk_cost_categories_active CHECK (is_active IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- People ----------

-- A client can be a person or a company, so the ERD's first/last name
-- columns are combined into one display name.
CREATE TABLE IF NOT EXISTS clients (
    client_id     INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NULL,           -- login for the client portal (optional)
    name          VARCHAR(255) NOT NULL,
    company       VARCHAR(255),
    email         VARCHAR(255),
    phone         VARCHAR(50),
    address       VARCHAR(500),
    status        VARCHAR(20) NOT NULL DEFAULT 'Active',
    notes         TEXT,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_clients_user (user_id),
    CONSTRAINT fk_clients_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT chk_clients_status CHECK (status IN ('Active', 'Inactive'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS subcontractors (
    subcontractor_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id          INT NULL,
    company_name     VARCHAR(255) NOT NULL,
    contact_name     VARCHAR(255),
    trade            VARCHAR(255),
    email            VARCHAR(255),
    phone            VARCHAR(50),
    address          VARCHAR(500),
    license_number   VARCHAR(100),
    status           VARCHAR(20) NOT NULL DEFAULT 'Active',
    notes            TEXT,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_subcontractors_user (user_id),
    CONSTRAINT fk_subcontractors_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT chk_subcontractors_status CHECK (status IN ('Active', 'Inactive'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- Estimates (RTM A3) ----------

CREATE TABLE IF NOT EXISTS estimates (
    estimate_id      INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    estimate_number  VARCHAR(50) NOT NULL,
    title            VARCHAR(255) NOT NULL,
    client_id        INT NOT NULL,
    created_by       INT NULL,
    status           VARCHAR(20) NOT NULL DEFAULT 'Draft',
    total_amount     DECIMAL(12,2) NOT NULL DEFAULT 0,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_estimates_number (estimate_number),
    KEY idx_estimates_client (client_id),
    CONSTRAINT fk_estimates_client FOREIGN KEY (client_id) REFERENCES clients(client_id),
    CONSTRAINT fk_estimates_creator FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT chk_estimates_status CHECK (status IN ('Draft', 'Sent', 'Approved', 'Rejected', 'Converted'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS estimate_line_items (
    line_item_id  INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    estimate_id   INT NOT NULL,
    category_id   INT NULL,
    description   VARCHAR(500) NOT NULL,
    quantity      DECIMAL(12,2) NOT NULL,
    unit_cost     DECIMAL(12,2) NOT NULL,
    line_total    DECIMAL(12,2) NOT NULL,
    CONSTRAINT fk_estimate_lines_estimate FOREIGN KEY (estimate_id) REFERENCES estimates(estimate_id) ON DELETE CASCADE,
    CONSTRAINT fk_estimate_lines_category FOREIGN KEY (category_id) REFERENCES cost_categories(category_id),
    CONSTRAINT chk_estimate_lines_quantity CHECK (quantity > 0),
    CONSTRAINT chk_estimate_lines_cost CHECK (unit_cost >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- Projects (RTM A2, A4) ----------

CREATE TABLE IF NOT EXISTS projects (
    project_id          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    project_number      VARCHAR(50) NOT NULL,
    name                VARCHAR(255) NOT NULL,
    project_type        VARCHAR(100),
    description         TEXT,
    address             VARCHAR(500),
    client_id           INT NOT NULL,
    estimate_id         INT NULL,     -- set when created from an estimate (A4)
    project_manager_id  INT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'Planning',
    budget_amount       DECIMAL(12,2) NOT NULL DEFAULT 0,
    progress_percent    INT NOT NULL DEFAULT 0,
    start_date          DATE,
    due_date            DATE,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_projects_number (project_number),
    UNIQUE KEY uq_projects_estimate (estimate_id),
    KEY idx_projects_client (client_id),
    KEY idx_projects_manager (project_manager_id),
    CONSTRAINT fk_projects_client FOREIGN KEY (client_id) REFERENCES clients(client_id),
    CONSTRAINT fk_projects_estimate FOREIGN KEY (estimate_id) REFERENCES estimates(estimate_id) ON DELETE SET NULL,
    CONSTRAINT fk_projects_manager FOREIGN KEY (project_manager_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT chk_projects_status CHECK (status IN ('Planning', 'In Progress', 'On Hold', 'Completed')),
    CONSTRAINT chk_projects_budget CHECK (budget_amount >= 0),
    CONSTRAINT chk_projects_progress CHECK (progress_percent BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- Invoices (RTM A5) ----------

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id      INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    invoice_number  VARCHAR(50) NOT NULL,
    project_id      INT NOT NULL,
    issue_date      DATE NOT NULL,
    due_date        DATE NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'Draft',
    total_amount    DECIMAL(12,2) NOT NULL DEFAULT 0,
    paid_at         DATE NULL,    -- set when status becomes Paid
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_invoices_number (invoice_number),
    KEY idx_invoices_project (project_id),
    CONSTRAINT fk_invoices_project FOREIGN KEY (project_id) REFERENCES projects(project_id),
    CONSTRAINT chk_invoices_status CHECK (status IN ('Draft', 'Unpaid', 'Paid'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS invoice_line_items (
    invoice_line_item_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    invoice_id           INT NOT NULL,
    description          VARCHAR(500) NOT NULL,
    quantity             DECIMAL(12,2) NOT NULL,
    unit_price           DECIMAL(12,2) NOT NULL,
    line_total           DECIMAL(12,2) NOT NULL,
    CONSTRAINT fk_invoice_lines_invoice FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id) ON DELETE CASCADE,
    CONSTRAINT chk_invoice_lines_quantity CHECK (quantity > 0),
    CONSTRAINT chk_invoice_lines_price CHECK (unit_price >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- Job costs (RTM A6, A7) ----------

-- One row per expense on the Job Costs page. The receipt file itself is optional.
CREATE TABLE IF NOT EXISTS receipts (
    receipt_id        INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    project_id        INT NOT NULL,
    category_id       INT NOT NULL,
    uploaded_by       INT NULL,
    description       VARCHAR(500) NOT NULL,
    amount            DECIMAL(12,2) NOT NULL,
    expense_date      DATE NOT NULL,
    receipt_filename  VARCHAR(255),   -- original name, shown to users
    file_path         VARCHAR(255),   -- stored file name
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_receipts_project (project_id),
    CONSTRAINT fk_receipts_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    CONSTRAINT fk_receipts_category FOREIGN KEY (category_id) REFERENCES cost_categories(category_id),
    CONSTRAINT fk_receipts_uploader FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT chk_receipts_amount CHECK (amount >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Estimated cost per category for each project (the "Estimated" column on Job Costs).
CREATE TABLE IF NOT EXISTS project_budget_items (
    project_id        INT NOT NULL,
    category_id       INT NOT NULL,
    estimated_amount  DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (project_id, category_id),
    CONSTRAINT fk_budget_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    CONSTRAINT fk_budget_category FOREIGN KEY (category_id) REFERENCES cost_categories(category_id),
    CONSTRAINT chk_budget_amount CHECK (estimated_amount >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- Subcontractors (RTM A8) ----------

CREATE TABLE IF NOT EXISTS project_assignments (
    assignment_id     INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    project_id        INT NOT NULL,
    subcontractor_id  INT NOT NULL,
    scope_of_work     TEXT,
    status            VARCHAR(20) NOT NULL DEFAULT 'Active',
    assigned_date     DATE,
    KEY idx_assignments_project (project_id),
    CONSTRAINT fk_assignments_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    CONSTRAINT fk_assignments_subcontractor FOREIGN KEY (subcontractor_id) REFERENCES subcontractors(subcontractor_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS subcontractor_invoices (
    sub_invoice_id    INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    assignment_id     INT NOT NULL,
    category_id       INT NULL,
    reviewed_by       INT NULL,
    invoice_number    VARCHAR(50) NOT NULL,
    description       TEXT,
    amount            DECIMAL(12,2) NOT NULL,
    status            VARCHAR(20) NOT NULL DEFAULT 'Pending Approval',
    submitted_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at       DATETIME NULL,
    original_filename VARCHAR(255),
    file_path         VARCHAR(255),
    CONSTRAINT fk_sub_invoices_assignment FOREIGN KEY (assignment_id) REFERENCES project_assignments(assignment_id) ON DELETE CASCADE,
    CONSTRAINT fk_sub_invoices_category FOREIGN KEY (category_id) REFERENCES cost_categories(category_id),
    CONSTRAINT fk_sub_invoices_reviewer FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT chk_sub_invoices_amount CHECK (amount >= 0),
    CONSTRAINT chk_sub_invoices_status CHECK (status IN ('Pending Approval', 'Approved', 'Rejected', 'Paid'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- Scheduling (RTM A11) ----------

-- assigned_to is free text because tasks are often given to crews or
-- subcontractors without a login (e.g. "Roofing Crew").
CREATE TABLE IF NOT EXISTS tasks (
    task_id      INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    project_id   INT NOT NULL,
    title        VARCHAR(255) NOT NULL,
    description  TEXT,
    assigned_to  VARCHAR(255),
    start_date   DATE,
    due_date     DATE NOT NULL,
    priority     VARCHAR(10) NOT NULL DEFAULT 'Medium',
    status       VARCHAR(20) NOT NULL DEFAULT 'Not Started',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_tasks_project (project_id),
    CONSTRAINT fk_tasks_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    CONSTRAINT chk_tasks_priority CHECK (priority IN ('Low', 'Medium', 'High')),
    CONSTRAINT chk_tasks_status CHECK (status IN ('Not Started', 'In Progress', 'Completed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- Files (RTM A10, documents page) ----------

-- file_path is NULL for sample rows that have no real file behind them.
CREATE TABLE IF NOT EXISTS photos (
    photo_id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    project_id         INT NULL,
    uploaded_by        INT NULL,
    task_id            INT NULL,
    title              VARCHAR(255) NOT NULL,
    caption            TEXT,
    original_filename  VARCHAR(255),
    file_path          VARCHAR(255),
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_photos_project (project_id),
    CONSTRAINT fk_photos_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    CONSTRAINT fk_photos_uploader FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_photos_task FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS documents (
    document_id         INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    project_id          INT NULL,
    uploaded_by         INT NULL,
    document_type       VARCHAR(20) NOT NULL,
    original_filename   VARCHAR(255) NOT NULL,
    attachment_filename VARCHAR(255),
    file_path           VARCHAR(255),
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_documents_project (project_id),
    CONSTRAINT fk_documents_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE SET NULL,
    CONSTRAINT fk_documents_uploader FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT chk_documents_type CHECK (document_type IN ('Estimate', 'Invoice', 'Receipt', 'Contract', 'Other'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_attachments (
    attachment_id      INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    document_id        INT NOT NULL,
    original_filename  VARCHAR(255) NOT NULL,
    file_path          VARCHAR(255) NOT NULL,
    KEY idx_document_attachments_document (document_id),
    CONSTRAINT fk_document_attachments_document FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

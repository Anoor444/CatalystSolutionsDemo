-- One-time local setup. Run as a MySQL administrator (root) in Workbench or the mysql client.
-- Hosted databases (TiDB Cloud, Amazon RDS) give you a database and login instead; see BACKEND.md.

CREATE DATABASE IF NOT EXISTS catalyst_demo
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Used by the automated tests; wiped on every test run.
CREATE DATABASE IF NOT EXISTS catalyst_test
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Replace this placeholder password before running, and put the same password in your .env file.
CREATE USER IF NOT EXISTS 'catalyst_app'@'localhost'
    IDENTIFIED BY 'REPLACE_WITH_YOUR_PASSWORD';

-- The app reads and writes data, creates its tables on first run, and the reset command
-- empties tables (TRUNCATE needs DROP).
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES
    ON catalyst_demo.* TO 'catalyst_app'@'localhost';

-- The tests drop and recreate their own database.
GRANT ALL PRIVILEGES ON catalyst_test.* TO 'catalyst_app'@'localhost';

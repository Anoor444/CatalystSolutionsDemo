-- Run as a MySQL administrator in Workbench or the mysql client.
CREATE DATABASE IF NOT EXISTS catalyst_demo
    CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

-- Replace this placeholder password before running the following statements.
CREATE USER IF NOT EXISTS 'catalyst_app'@'localhost'
    IDENTIFIED BY 'REPLACE_WITH_YOUR_PASSWORD';
GRANT SELECT, INSERT, UPDATE, CREATE, ALTER, REFERENCES ON catalyst_demo.* TO 'catalyst_app'@'localhost';

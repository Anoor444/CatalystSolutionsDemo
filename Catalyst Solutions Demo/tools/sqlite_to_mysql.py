"""Copy the old SQLite database (and its upload folders) into the MySQL database.

Before backend step 13 everything was saved in instance/users.sqlite3, and uploaded files
in instance/document_uploads, photo_uploads, receipt_uploads and subcontractor_invoice_uploads.
This copies all of it into the MySQL database the app now uses (the one in your .env file).

Run from the "Catalyst Solutions Demo" folder:

    python tools/sqlite_to_mysql.py --replace
        Empties the MySQL database, then copies every table and every uploaded file from
        instance/. You are asked to confirm first. Logins, ids and links are kept exactly.

    python tools/sqlite_to_mysql.py --uploads-only
        Copies only files: for records already in MySQL whose file is still sitting in an
        instance/*_uploads folder (e.g. uploaded between steps 13 and 14).

Options: --sqlite PATH (default instance/users.sqlite3), --instance FOLDER (default instance),
--yes (skip the confirmation question).

The SQLite file and the upload folders are only read, never changed. At the end the script
prints how many rows each table has in SQLite and in MySQL, and how many files were copied.
"""
import argparse
import datetime as dt
from pathlib import Path
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_DIR / ".env")
except ImportError:
    pass

import database  # noqa: E402  (after .env is loaded)

# Parents before children, so the copy reads naturally (foreign key checks are off while copying).
TABLES = ["users", "cost_categories", "clients", "subcontractors", "estimates", "estimate_line_items",
          "projects", "invoices", "invoice_line_items", "receipts", "project_budget_items",
          "project_assignments", "subcontractor_invoices", "tasks", "photos", "documents",
          "document_attachments"]

# Where each table's files were saved on disk.
UPLOAD_FOLDERS = {
    "documents": "document_uploads",
    "document_attachments": "document_uploads",
    "photos": "photo_uploads",
    "receipts": "receipt_uploads",
    "subcontractor_invoices": "subcontractor_invoice_uploads",
}

# SQLite stored these timestamps in UTC (datetime('now')); MySQL keeps local time (APP_TIMEZONE).
# estimates.created_at was already saved in local time.
LOCAL_TIME_ALREADY = {("estimates", "created_at")}


def mysql_columns(db, table):
    rows = db.execute(
        """SELECT column_name, data_type FROM information_schema.columns
           WHERE table_schema = DATABASE() AND table_name = ? ORDER BY ordinal_position""", (table,)).fetchall()
    return {name.lower(): kind.lower() for name, kind in rows}


def sqlite_tables(source):
    return {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def convert(value, kind, table, column):
    if value is None:
        return None
    if kind == "date":
        text = str(value).strip()
        return text[:10] or None
    if kind in ("datetime", "timestamp"):
        text = str(value).strip()
        if not text:
            return None
        moment = dt.datetime.fromisoformat(text if len(text) > 10 else text + " 00:00:00")
        if (table, column) not in LOCAL_TIME_ALREADY and len(text) > 10:
            moment = moment.replace(tzinfo=dt.timezone.utc).astimezone(database.APP_TIMEZONE).replace(tzinfo=None)
        return moment.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, bytes):
        return value
    return value


def count_rows(db, tables):
    return {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}


def copy_rows(source, db):
    """Copies every table. Returns {table: (sqlite rows, rows written)}."""
    available = sqlite_tables(source)
    report = {}
    with db:
        db.execute("SET FOREIGN_KEY_CHECKS = 0")
        try:
            for table in TABLES:
                if table not in available:
                    report[table] = (None, 0)
                    continue
                target = mysql_columns(db, table)
                source_columns = [row[1] for row in source.execute(f"PRAGMA table_info({table})")]
                columns = [c for c in source_columns if c.lower() in target]
                rows = source.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
                extra = []
                if table == "users":   # older account tables had no first/last name columns
                    extra = [c for c in ("first_name", "last_name") if c not in columns]
                sql = (f"INSERT INTO {table} ({', '.join(columns + extra)}) "
                       f"VALUES ({', '.join('?' * (len(columns) + len(extra)))})")
                for row in rows:
                    values = [convert(v, target[c.lower()], table, c.lower()) for c, v in zip(columns, row)]
                    if extra:
                        first, _, last = str(dict(zip(columns, row)).get("name", "")).partition(" ")
                        values += [{"first_name": first, "last_name": last}[c] for c in extra]
                    db.execute(sql, values)
                report[table] = (len(rows), len(rows))
        finally:
            db.execute("SET FOREIGN_KEY_CHECKS = 1")
    return report


def copy_files(db, instance):
    """Puts files from the instance/*_uploads folders into uploaded_files for records that need them."""
    copied, missing, failed = 0, [], []
    for table, folder in UPLOAD_FOLDERS.items():
        names = [row[0] for row in db.execute(
            f"""SELECT DISTINCT t.file_path FROM {table} t
                LEFT JOIN uploaded_files f ON f.stored_name = t.file_path
                WHERE t.file_path IS NOT NULL AND t.file_path != '' AND f.stored_name IS NULL""").fetchall()]
        for name in names:
            candidates = [instance / folder / name] + [instance / other / name for other in set(UPLOAD_FOLDERS.values())]
            path = next((p for p in candidates if p.is_file()), None)
            if path is None:
                missing.append(f"{table}: {name}")
                continue
            try:
                database.save_file_with(db, name, path.read_bytes())
                copied += 1
            except database.mysql_errors.Error as error:
                failed.append(f"{table}: {name} ({error.msg if hasattr(error, 'msg') else error})")
    return copied, missing, failed


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sqlite", default=str(PROJECT_DIR / "instance" / "users.sqlite3"))
    parser.add_argument("--instance", default=str(PROJECT_DIR / "instance"))
    parser.add_argument("--replace", action="store_true", help="empty the MySQL database first, then copy everything")
    parser.add_argument("--uploads-only", action="store_true", help="only copy files for records already in MySQL")
    parser.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    args = parser.parse_args()
    instance = Path(args.instance)

    settings = database.connection_settings()
    print(f"MySQL: {settings['user']}@{settings['host']}:{settings['port']} / database '{settings['database']}'")
    db = database.connect()
    try:
        existing = {row[0].lower() for row in db.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()")}
        if not set(database.ALL_TABLES) <= existing:
            print("Creating the MySQL tables first...")
            database.create_tables(db)

        if args.uploads_only:
            copied, missing, failed = copy_files(db, instance)
            print_files(copied, missing, failed)
            return 0

        source_path = Path(args.sqlite)
        if not source_path.is_file():
            print(f"No SQLite database at {source_path}. Nothing to copy.")
            return 1
        print(f"SQLite: {source_path} (opened read-only)")

        current = count_rows(db, database.ALL_TABLES)
        if any(current.values()):
            if not args.replace:
                print(f"\nThe MySQL database already has data ({current['projects']} projects, {current['users']} logins).")
                print("Run again with --replace to empty it and copy the SQLite data in its place.")
                return 1
            if not args.yes:
                answer = input(f"\nThis deletes everything in MySQL database '{settings['database']}' "
                               f"({current['projects']} projects, {current['users']} logins) and replaces it "
                               f"with the SQLite data.\nType the database name to continue: ")
                if answer.strip() != settings["database"]:
                    print("Cancelled. Nothing was changed.")
                    return 1
            db.execute("SET FOREIGN_KEY_CHECKS = 0")
            try:
                for table in database.ALL_TABLES:
                    db.execute(f"TRUNCATE TABLE {table}")
            finally:
                db.execute("SET FOREIGN_KEY_CHECKS = 1")

        source = sqlite3.connect(source_path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            report = copy_rows(source, db)
        finally:
            source.close()
        after = count_rows(db, TABLES)

        print(f"\n{'Table':<24}{'SQLite':>8}{'MySQL':>8}")
        problems = 0
        for table in TABLES:
            sqlite_count = report[table][0]
            ok = sqlite_count is None or sqlite_count == after[table]
            problems += not ok
            shown = "-" if sqlite_count is None else sqlite_count
            print(f"{table:<24}{shown:>8}{after[table]:>8}{'' if ok else '   <-- different!'}")

        copied, missing, failed = copy_files(db, instance)
        print_files(copied, missing, failed)
        print("\nDone." if not problems and not failed else "\nFinished with problems (see above).")
        return 0 if not problems and not failed else 2
    finally:
        db.close()


def print_files(copied, missing, failed):
    print(f"\nFiles copied into MySQL: {copied}")
    if missing:
        print(f"Files not found in the upload folders ({len(missing)}); those records keep working, "
              "but their download shows 'not found' (sample records never had files):")
        for item in missing[:20]:
            print("   ", item)
        if len(missing) > 20:
            print(f"    ... and {len(missing) - 20} more")
    for item in failed:
        print("   could not copy", item)


if __name__ == "__main__":
    sys.exit(main())

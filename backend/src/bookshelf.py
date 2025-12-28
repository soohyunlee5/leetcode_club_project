#!/usr/bin/env python3
import argparse
import hashlib
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parents[2] if len(Path(__file__).resolve().parents) >= 3 else Path.cwd()
DB_DIR = REPO_ROOT / "backend" / "db"
STORAGE_DIR = REPO_ROOT / "backend" / "storage"
DB_PATH = DB_DIR / "bookshelf.db"

DB_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

def connect_db():
    return sqlite3.connect(str(DB_PATH))

def init_db():
    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                filename TEXT NOT NULL UNIQUE,
                filetype TEXT NOT NULL,
                size_bytes INTEGER DEFAULT 0,
                sha256 TEXT,
                tags TEXT,
                added_on TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    print(f"✅ Database initialized at: {DB_PATH}")

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def normalize_type(filename: str) -> str:
    return Path(filename).suffix.lower().replace(".", "") or "unknown"

def cmd_add(src_path: str, tags: str = ""):
    src = Path(src_path).expanduser().resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"File not found: {src}")

    filename = src.name
    title = src.stem
    filetype = normalize_type(filename)
    dest = STORAGE_DIR / filename

    if not dest.exists():
        shutil.copy2(src, dest)
    size_bytes = dest.stat().st_size
    digest = sha256_file(dest)

    with connect_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO books
               (title, filename, filetype, size_bytes, sha256, tags)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, filename, filetype, size_bytes, digest, tags),
        )
        conn.commit()
    print(f"📥 Added: {title} ({filetype}) • {size_bytes} bytes")

def cmd_list(limit: int = 100):
    with connect_db() as conn:
        rows = conn.execute(
            """SELECT id, title, filetype, tags, added_on
               FROM books ORDER BY added_on DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    if not rows:
        print("(empty)")
    for r in rows:
        print(r)

def cmd_search(keyword: str):
    like = f"%{keyword}%"
    with connect_db() as conn:
        rows = conn.execute(
            """SELECT id, title, filetype, tags, added_on
               FROM books WHERE title LIKE ? OR tags LIKE ?
               ORDER BY added_on DESC""",
            (like, like),
        ).fetchall()
    if not rows:
        print("(no matches)")
    for r in rows:
        print(r)

def cmd_show(book_id: int):
    with connect_db() as conn:
        row = conn.execute(
            """SELECT id, title, filename, filetype, size_bytes, sha256, tags, added_on
               FROM books WHERE id = ?""",
            (book_id,),
        ).fetchone()
    if not row:
        print("Not found:", book_id)
        return
    labels = ["id", "title", "filename", "filetype", "size_bytes", "sha256", "tags", "added_on"]
    for k, v in zip(labels, row):
        print(f"{k:>10}: {v}")

def cmd_remove(book_id: int, delete_file: bool = False):
    with connect_db() as conn:
        row = conn.execute("SELECT filename FROM books WHERE id = ?", (book_id,)).fetchone()
        if not row:
            print("No book with id:", book_id)
            return
        filename = row[0]
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.commit()
    print(f"🗑️ Removed DB entry {book_id} ({filename})")

    if delete_file:
        try:
            (STORAGE_DIR / filename).unlink(missing_ok=True)
            print("🧹 Deleted file from storage.")
        except Exception as e:
            print("Could not delete file:", e)

def cmd_export_csv(out_path: str):
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as conn:
        rows = conn.execute(
            """SELECT id, title, filename, filetype, size_bytes, sha256, tags, added_on FROM books ORDER BY id"""
        ).fetchall()
    with out.open("w", encoding="utf-8") as f:
        f.write("id,title,filename,filetype,size_bytes,sha256,tags,added_on\n")
        for r in rows:
            safe = [str(x).replace(",", " ") for x in r]
            f.write(",".join(safe) + "\n")
    print("📤 Exported CSV:", out)

def main():
    p = argparse.ArgumentParser(description="SQLite Bookshelf CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    a = sub.add_parser("add"); a.add_argument("path"); a.add_argument("--tags", default="")
    l = sub.add_parser("list"); l.add_argument("--limit", type=int, default=100)
    s = sub.add_parser("search"); s.add_argument("keyword")
    sh = sub.add_parser("show"); sh.add_argument("id", type=int)
    r = sub.add_parser("remove"); r.add_argument("id", type=int); r.add_argument("--delete-file", action="store_true")
    e = sub.add_parser("export"); e.add_argument("--out", default=str(REPO_ROOT / "backend" / "books_export.csv"))

    args = p.parse_args()
    if args.cmd == "init": init_db()
    elif args.cmd == "add": init_db(); cmd_add(args.path, args.tags)
    elif args.cmd == "list": init_db(); cmd_list(args.limit)
    elif args.cmd == "search": init_db(); cmd_search(args.keyword)
    elif args.cmd == "show": init_db(); cmd_show(args.id)
    elif args.cmd == "remove": init_db(); cmd_remove(args.id, args.delete_file)
    elif args.cmd == "export": init_db(); cmd_export_csv(args.out)

if __name__ == "__main__":
    main()

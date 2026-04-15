from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
OUTDIR = ROOT_DIR / "data" / "local_dbs"
SQL_PATH = OUTDIR / "library_demo_schema.sql"
DB_PATH = OUTDIR / "library_demo.sqlite"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE Book (
    Book_no VARCHAR(10) PRIMARY KEY,
    Book_name VARCHAR(30),
    Author VARCHAR(30),
    Price FLOAT
);

CREATE TABLE Student (
    Student_no VARCHAR(10) PRIMARY KEY,
    Student_name VARCHAR(30),
    Grade VARCHAR(10)
);

CREATE TABLE Borrow (
    Student_no VARCHAR(10),
    Book_no VARCHAR(10),
    Return_date DATETIME,
    PRIMARY KEY(Student_no, Book_no),
    FOREIGN KEY(Student_no) REFERENCES Student(Student_no) ON DELETE CASCADE,
    FOREIGN KEY(Book_no) REFERENCES Book(Book_no) ON DELETE CASCADE
);
""".strip()


BOOK_ROWS = [
    ("T1001", "Java 程序设计", "李新珊", 89.5),
    ("T1002", "数据库原理及应用", "王敏", 39.0),
    ("T1003", "Java 高级编程", "陈明海", 63.5),
    ("T1004", "专业英语", "张倪宁", 23.1),
    ("T1005", "C++程序设计", "马天颖", 83.2),
    ("T1006", "编译原理", "王鑫单", 65.0),
]

STUDENT_ROWS = [
    ("K005", "张鑫翁", "大一"),
    ("K003", "徐晨皓", "大二"),
    ("K002", "王三优", "大三"),
    ("K001", "刘孔阴", "大三"),
    ("K004", "吴宇涵", "大四"),
]

BORROW_ROWS = [
    ("K001", "T1006", "2023-10-9"),
    ("K001", "T1001", "2024-3-1"),
    ("K002", "T1002", "2023-10-9"),
    ("K002", "T1003", "2024-4-5"),
    ("K002", "T1001", "2023-11-3"),
    ("K003", "T1005", "2024-1-4"),
    ("K004", "T1002", "2024-2-5"),
]


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    SQL_PATH.write_text(SCHEMA_SQL + "\n", encoding="utf-8")

    if DB_PATH.exists():
        DB_PATH.unlink()

    connection = sqlite3.connect(DB_PATH)
    try:
        cursor = connection.cursor()
        cursor.executescript(SCHEMA_SQL)
        cursor.executemany(
            "INSERT INTO Book (Book_no, Book_name, Author, Price) VALUES (?, ?, ?, ?)",
            BOOK_ROWS,
        )
        cursor.executemany(
            "INSERT INTO Student (Student_no, Student_name, Grade) VALUES (?, ?, ?)",
            STUDENT_ROWS,
        )
        cursor.executemany(
            "INSERT INTO Borrow (Student_no, Book_no, Return_date) VALUES (?, ?, ?)",
            BORROW_ROWS,
        )
        connection.commit()
    finally:
        connection.close()

    print(f"Created demo database: {DB_PATH}")
    print(f"Saved schema SQL: {SQL_PATH}")


if __name__ == "__main__":
    main()
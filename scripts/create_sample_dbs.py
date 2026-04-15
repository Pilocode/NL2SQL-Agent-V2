import sqlite3
from pathlib import Path

OUTDIR = Path("data/local_dbs")
OUTDIR.mkdir(parents=True, exist_ok=True)

def create_sales(path: Path):
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT, country TEXT)")
    c.execute("CREATE TABLE orders(id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL, year INTEGER)")
    c.executemany("INSERT INTO customers(name,country) VALUES(?,?)", [
        ("Alice","US"),("Bob","UK"),("Carlos","CN"),("Diana","US")
    ])
    c.executemany("INSERT INTO orders(customer_id,amount,year) VALUES(?,?,?)", [
        (1,120.5,2020),(2,55.0,2021),(1,300.0,2022),(3,75.25,2021),(4,200.0,2020)
    ])
    conn.commit(); conn.close()

def create_hr(path: Path):
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("CREATE TABLE employees(id INTEGER PRIMARY KEY, name TEXT, dept TEXT, salary INTEGER)")
    c.executemany("INSERT INTO employees(name,dept,salary) VALUES(?,?,?)", [
        ("张三","工程",12000),("李四","市场",9000),("王五","工程",15000)
    ])
    conn.commit(); conn.close()

def create_books(path: Path):
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("CREATE TABLE books(id INTEGER PRIMARY KEY, title TEXT, author TEXT, sold INTEGER)")
    c.executemany("INSERT INTO books(title,author,sold) VALUES(?,?,?)", [
        ("深度学习","Ian Goodfellow",5000),("Python入门","张三",20000),("SQL实战","李四",8000)
    ])
    conn.commit(); conn.close()

if __name__ == '__main__':
    create_sales(OUTDIR / 'sales.sqlite')
    create_hr(OUTDIR / 'hr.sqlite')
    create_books(OUTDIR / 'books.sqlite')
    print('Created sample DBs in', OUTDIR)

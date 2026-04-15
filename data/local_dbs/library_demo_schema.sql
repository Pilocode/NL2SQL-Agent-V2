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

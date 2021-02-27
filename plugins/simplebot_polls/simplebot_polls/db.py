
from typing import List, Optional
from enum import IntEnum
import sqlite3


class Status(IntEnum):
    OPEN = 0
    CLOSED = 1


class DBManager:
    def __init__(self, db_path: str) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute(
                '''CREATE TABLE IF NOT EXISTS polls
                (id INTEGER PRIMARY KEY,
                addr TEXT NOT NULL,
                question TEXT NOT NULL,
                date FLOAT NOT NULL,
                status INTEGER NOT NULL)''')
            self.db.execute(
                '''CREATE TABLE IF NOT EXISTS options
                (id INTEGER,
                poll INTEGER REFERENCES polls(id),
                text TEXT NOT NULL,
                PRIMARY KEY(id, poll))''')
            self.db.execute(
                '''CREATE TABLE IF NOT EXISTS votes
                (poll INTEGER REFERENCES polls(id),
                addr TEXT,
                option INTEGER NOT NULL,
                PRIMARY KEY(poll, addr))''')

            self.db.execute(
                '''CREATE TABLE IF NOT EXISTS gpolls
                (id INTEGER PRIMARY KEY,
                gid INTEGER NOT NULL,
                question TEXT NOT NULL,
                status INTEGER NOT NULL)''')
            self.db.execute(
                '''CREATE TABLE IF NOT EXISTS goptions
                (id INTEGER,
                poll INTEGER REFERENCES gpolls(id),
                text TEXT NOT NULL,
                PRIMARY KEY(id, poll))''')
            self.db.execute(
                '''CREATE TABLE IF NOT EXISTS gvotes
                (poll INTEGER REFERENCES gpolls(id),
                addr TEXT,
                option INTEGER NOT NULL REFERENCES goptions(id),
                PRIMARY KEY(poll, addr))''')

    def execute(self, statement: str, args=()) -> sqlite3.Cursor:
        return self.db.execute(statement, args)

    def commit(self, statement: str, args=()) -> sqlite3.Cursor:
        with self.db:
            return self.db.execute(statement, args)

    def close(self) -> None:
        self.db.close()

    # ====== gpolls =====

    def add_gpoll(self, gid: int, question: str) -> None:
        with self.db:
            self.db.execute(
                'INSERT INTO gpolls VALUES (?,?,?,?)',
                (None, gid, question, Status.OPEN))

    def remove_gpoll_by_id(self, pid: int) -> None:
        with self.db:
            self.db.execute(
                'DELETE FROM goptions WHERE poll=?', (pid,))
            self.db.execute(
                'DELETE FROM gvotes WHERE poll=?', (pid,))
            self.db.execute(
                'DELETE FROM gpolls WHERE id=?', (pid,))

    def end_gpoll(self, pid: int) -> None:
        with self.db:
            self.db.execute(
                'UPDATE gpolls SET status=? WHERE id=?',
                (Status.CLOSED, pid))

    def get_gpolls_by_gid(self, gid: int) -> List[sqlite3.Row]:
        return self.db.execute(
            'SELECT * FROM gpolls WHERE gid=?', (gid,)).fetchall()

    def get_gpoll_by_id(self, pid: int) -> Optional[sqlite3.Row]:
        q = 'SELECT * FROM gpolls WHERE id=?'
        return self.db.execute(q, (pid,)).fetchone()

    def get_gpoll_by_question(self, gid: int,
                              question: str) -> Optional[sqlite3.Row]:
        q = 'SELECT * FROM gpolls WHERE gid=? AND question=?'
        return self.db.execute(q, (gid, question)).fetchone()

    def add_goption(self, oid: int, pid: int, text: str) -> None:
        with self.db:
            self.db.execute(
                'INSERT INTO goptions VALUES (?,?,?)', (oid, pid, text))

    def get_goptions(self, pid: int) -> List[sqlite3.Row]:
        return self.db.execute(
            'SELECT * FROM goptions WHERE poll=?', (pid,)).fetchall()

    def get_gvotes(self, pid: int) -> List[sqlite3.Row]:
        return self.db.execute(
            'SELECT * FROM gvotes WHERE poll=?', (pid,)).fetchall()

    def get_gvote(self, pid: int, addr: str) -> Optional[sqlite3.Row]:
        q = 'SELECT * FROM gvotes WHERE poll=? AND addr=?'
        return self.db.execute(q, (pid, addr)).fetchone()

    def add_gvote(self, pid: int, addr: str, option: int) -> None:
        q = 'INSERT INTO gvotes VALUES (?,?,?)'
        with self.db:
            self.db.execute(q, (pid, addr, option)).fetchone()

    # ====== polls =====

    def add_poll(self, addr: str, question: str, date: float) -> None:
        with self.db:
            self.db.execute(
                'INSERT INTO polls VALUES (?,?,?,?,?)',
                (None, addr, question, date, Status.OPEN))

    def remove_poll_by_id(self, pid: int) -> None:
        with self.db:
            self.db.execute(
                'DELETE FROM options WHERE poll=?', (pid,))
            self.db.execute(
                'DELETE FROM votes WHERE poll=?', (pid,))
            self.db.execute(
                'DELETE FROM polls WHERE id=?', (pid,))

    def end_poll(self, pid: int) -> None:
        with self.db:
            self.db.execute(
                'UPDATE polls SET status=? WHERE id=?',
                (Status.CLOSED, pid))

    def get_polls_by_addr(self, addr: str) -> List[sqlite3.Row]:
        return self.db.execute(
            'SELECT * FROM polls WHERE addr=?', (addr,)).fetchall()

    def get_poll_by_id(self, pid: int) -> Optional[sqlite3.Row]:
        q = 'SELECT * FROM polls WHERE id=?'
        return self.db.execute(q, (pid,)).fetchone()

    def get_poll_by_question(self, addr: str,
                             question: str) -> Optional[sqlite3.Row]:
        q = 'SELECT * FROM polls WHERE addr=? AND question=?'
        return self.db.execute(q, (addr, question)).fetchone()

    def get_poll_participants(self, pid: int) -> List[str]:
        q = 'SELECT addr FROM votes WHERE poll=?'
        return [r[0] for r in self.db.execute(q, (pid,)).fetchall()]

    def add_option(self, oid: int, pid: int, text: str) -> None:
        with self.db:
            self.db.execute(
                'INSERT INTO options VALUES (?,?,?)', (oid, pid, text))

    def get_options(self, pid: int) -> List[sqlite3.Row]:
        return self.db.execute(
            'SELECT * FROM options WHERE poll=?', (pid,)).fetchall()

    def get_votes(self, pid: int) -> List[sqlite3.Row]:
        return self.db.execute(
            'SELECT * FROM votes WHERE poll=?', (pid,)).fetchall()

    def get_vote(self, pid: int, addr: str) -> Optional[sqlite3.Row]:
        q = 'SELECT * FROM votes WHERE poll=? AND addr=?'
        return self.db.execute(q, (pid, addr)).fetchone()

    def add_vote(self, pid: int, addr: str, option: int) -> None:
        q = 'INSERT INTO votes VALUES (?,?,?)'
        with self.db:
            self.db.execute(q, (pid, addr, option)).fetchone()

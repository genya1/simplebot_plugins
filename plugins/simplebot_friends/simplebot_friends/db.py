import sqlite3
from typing import Optional


class DBManager:
    def __init__(self, db_path: str) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            '''CREATE TABLE IF NOT EXISTS deltafriends
            (addr TEXT NOT NULL,
            bio TEXT,
            PRIMARY KEY(addr))''')

    def execute(self, statement: str, args=()) -> sqlite3.Cursor:
        return self.db.execute(statement, args)

    def commit(self, statement: str, args=()) -> sqlite3.Cursor:
        with self.db:
            return self.db.execute(statement, args)

    def close(self) -> None:
        self.db.close()

    def update_bio(self, addr: str, bio: str) -> None:
        self.commit('REPLACE INTO deltafriends VALUES (?,?)', (addr, bio))

    def get_bio(self, addr: str) -> Optional[str]:
        r = self.execute('SELECT bio FROM deltafriends WHERE addr=?',
                         (addr,)).fetchone()
        return r and r[0]

    def remove_user(self, addr: str) -> None:
        self.commit('DELETE FROM deltafriends WHERE addr=?', (addr,))

    def get_users(self) -> list:
        return self.execute(
            'SELECT * FROM deltafriends ORDER BY addr').fetchall()

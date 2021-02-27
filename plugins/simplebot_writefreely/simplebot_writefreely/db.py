
import sqlite3
from typing import Optional


class DBManager:
    def __init__(self, db_path: str) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute(
                '''CREATE TABLE IF NOT EXISTS accounts
                (addr TEXT PRIMARY KEY,
                host TEXT,
                token TEXT NOT NULL)''')
            self.db.execute(
                '''CREATE TABLE IF NOT EXISTS chats
                (id INTEGER PRIMARY KEY,
                blog TEXT,
                account TEXT NOT NULL REFERENCES accounts(addr))''')

    def add_account(self, addr: str, host: str, token: str) -> None:
        with self.db:
            self.db.execute(
                'INSERT INTO accounts VALUES (?,?,?)', (addr, host, token))

    def del_account(self, addr: str) -> None:
        with self.db:
            self.db.execute('DELETE FROM chats WHERE account=?', (addr,))
            self.db.execute('DELETE FROM accounts WHERE addr=?', (addr,))

    def get_account(self, addr: str) -> Optional[sqlite3.Row]:
        return self.db.execute(
            'SELECT * FROM accounts WHERE addr=?', (addr,)).fetchone()

    def add_chat(self, chat_id: int, blog: str, account: str) -> None:
        with self.db:
            self.db.execute(
                'REPLACE INTO chats VALUES (?,?,?)', (chat_id, blog, account))

    def del_chat(self, chat_id: int) -> None:
        with self.db:
            self.db.execute('DELETE FROM chats WHERE id=?', (chat_id,))

    def get_chat(self, chat_id: int) -> Optional[sqlite3.Row]:
        return self.db.execute(
            'SELECT * FROM chats WHERE id=?', (chat_id,)).fetchone()
        

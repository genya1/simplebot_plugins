
import sqlite3
from typing import Optional


class DBManager:
    def __init__(self, db_path: str) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute(
                '''CREATE TABLE IF NOT EXISTS games
                (p1 TEXT,
                p2 TEXT,
                gid INTEGER NOT NULL,
                black TEXT NOT NULL,
                board TEXT,
                PRIMARY KEY(p1,p2))''')

    def add_game(self, p1: str, p2: str, gid: str, board: str,
                 black: str) -> None:
        p1, p2 = sorted([p1, p2])
        args = (p1, p2, gid, black, board)
        q = 'INSERT INTO games VALUES ({})'.format(
            ','.join('?' for a in args))
        with self.db:
            self.db.execute(q, args)

    def delete_game(self, p1: str, p2: str) -> None:
        p1, p2 = sorted([p1, p2])
        with self.db:
            self.db.execute(
                'DELETE FROM games WHERE p1=? AND p2=?', (p1, p2))

    def set_game(self, p1: str, p2: str, black: Optional[str],
                 board: Optional[str]) -> None:
        p1, p2 = sorted([p1, p2])
        q = 'UPDATE games SET board=?, black=? WHERE p1=? AND p2=?'
        with self.db:
            self.db.execute(q, (board, black, p1, p2))

    def set_board(self, p1: str, p2: str, board: Optional[str]) -> None:
        p1, p2 = sorted([p1, p2])
        q = 'UPDATE games SET board=? WHERE p1=? AND p2=?'
        with self.db:
            self.db.execute(q, (board, p1, p2))

    def get_game_by_gid(self, gid: int) -> Optional[sqlite3.Row]:
        return self.db.execute(
            'SELECT * FROM games WHERE gid=?', (gid,)).fetchone()

    def get_game_by_players(self, p1: str, p2: str) -> Optional[sqlite3.Row]:
        p1, p2 = sorted([p1, p2])
        return self.db.execute(
            'SELECT * FROM games WHERE p1=? AND p2=?', (p1, p2)).fetchone()

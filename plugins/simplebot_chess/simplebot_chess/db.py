
import sqlite3
from typing import Optional


class DBManager:
    def __init__(self, db_path) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.commit('''CREATE TABLE IF NOT EXISTS games
                       (p1 TEXT,
                        p2 TEXT,
                        gid INTEGER NOT NULL,
                        game TEXT,
                        PRIMARY KEY(p1,p2))''')

    def execute(self, statement, args=()):
        return self.db.execute(statement, args)

    def commit(self, statement: str, args=()):
        with self.db:
            return self.db.execute(statement, args)

    def close(self) -> None:
        self.db.close()

    def get_game_by_gid(self, gid: int) -> Optional[sqlite3.Row]:
        return self.execute(
            'SELECT * FROM games WHERE gid=?', (gid,)).fetchone()

    def get_game_by_players(self, p1: str, p2: str) -> Optional[sqlite3.Row]:
        p1, p2 = sorted([p1, p2])
        return self.db.execute(
            'SELECT * FROM games WHERE p1=? AND p2=?',
            (p1, p2)).fetchone()

    def add_game(self, p1: str, p2: str, gid: int, game: str) -> None:
        p1, p2 = sorted([p1, p2])
        self.commit(
            'INSERT INTO games VALUES (?,?,?,?)', (p1, p2, gid, game))

    def set_game(self, p1: str, p2: str, game: Optional[str]) -> None:
        p1, p2 = sorted([p1, p2])
        self.commit(
            'UPDATE games SET game=? WHERE p1=? AND p2=?', (game, p1, p2))

    def delete_game(self, p1: str, p2: str) -> None:
        p1, p2 = sorted([p1, p2])
        self.commit('DELETE FROM games WHERE p1=? AND p2=?', (p1, p2))

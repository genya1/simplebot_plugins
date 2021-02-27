
import sqlite3
from typing import Optional


class DBManager:
    def __init__(self, db_path: str) -> None:
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self.commit('''CREATE TABLE IF NOT EXISTS games
                       (p1 TEXT,
                        p2 TEXT,
                        gid INTEGER NOT NULL,
                        board TEXT,
                        black TEXT,
                        PRIMARY KEY(p1,p2))''')

    def execute(self, statement: str, args=()) -> sqlite3.Cursor:
        return self._db.execute(statement, args)

    def commit(self, statement: str, args=()) -> sqlite3.Cursor:
        with self._db:
            return self._db.execute(statement, args)

    def close(self) -> None:
        self._db.close()

    def add_game(self, player1: str, player2: str, gid: str, board: str,
                 black: str) -> None:
        player1, player2 = sorted([player1, player2])
        self.commit('INSERT INTO games VALUES (?,?,?,?,?)',
                    (player1, player2, gid, board, black))

    def delete_game(self, player1: str, player2: str) -> None:
        player1, player2 = sorted([player1, player2])
        self.commit(
            'DELETE FROM games WHERE p1=? AND p2=?', (player1, player2))

    def set_game(self, player1: str, player2: str, board: str,
                 black: str) -> None:
        player1, player2 = sorted([player1, player2])
        self.commit(
            'UPDATE games SET board=?, black=? WHERE p1=? AND p2=?',
            (board, black, player1, player2))

    def set_board(self, player1: str, player2: str,
                  board: Optional[str]) -> None:
        player1, player2 = sorted([player1, player2])
        self.commit(
            'UPDATE games SET board=? WHERE p1=? AND p2=?',
            (board, player1, player2))

    def get_game_by_gid(self, gid: int) -> Optional[sqlite3.Row]:
        return self.execute(
            'SELECT * FROM games WHERE gid=?', (gid,)).fetchone()

    def get_game_by_players(self, player1: str,
                            player2: str) -> Optional[sqlite3.Row]:
        player1, player2 = sorted([player1, player2])
        return self._db.execute(
            'SELECT * FROM games WHERE p1=? AND p2=?',
            (player1, player2)).fetchone()

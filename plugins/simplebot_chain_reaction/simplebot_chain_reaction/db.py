
import sqlite3
from typing import Optional


class DBManager:
    def __init__(self, db_path: str) -> None:
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.execute(
                '''CREATE TABLE IF NOT EXISTS games
                (p1 TEXT,
                p2 TEXT,
                gid INTEGER NOT NULL,
                black TEXT NOT NULL,
                board TEXT,
                PRIMARY KEY(p1,p2))''')

    def add_game(self, player1: str, player2: str, gid: str, board: str,
                 black: str) -> None:
        player1, player2 = sorted([player1, player2])
        args = (player1, player2, gid, black, board)
        query = 'INSERT INTO games VALUES ({})'.format(
            ','.join('?' for a in args))
        with self._db:
            self._db.execute(query, args)

    def delete_game(self, player1: str, player2: str) -> None:
        player1, player2 = sorted([player1, player2])
        with self._db:
            self._db.execute(
                'DELETE FROM games WHERE p1=? AND p2=?', (player1, player2))

    def set_game(self, player1: str, player2: str, black: Optional[str],
                 board: Optional[str]) -> None:
        player1, player2 = sorted([player1, player2])
        query = 'UPDATE games SET board=?, black=? WHERE p1=? AND p2=?'
        with self._db:
            self._db.execute(query, (board, black, player1, player2))

    def set_board(self, player1: str, player2: str,
                  board: Optional[str]) -> None:
        player1, player2 = sorted([player1, player2])
        query = 'UPDATE games SET board=? WHERE p1=? AND p2=?'
        with self._db:
            self._db.execute(query, (board, player1, player2))

    def get_game_by_gid(self, gid: int) -> Optional[sqlite3.Row]:
        return self._db.execute(
            'SELECT * FROM games WHERE gid=?', (gid,)).fetchone()

    def get_game_by_players(
            self, player1: str, player2: str) -> Optional[sqlite3.Row]:
        player1, player2 = sorted([player1, player2])
        return self._db.execute(
            'SELECT * FROM games WHERE p1=? AND p2=?',
            (player1, player2)).fetchone()

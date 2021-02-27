
from typing import Optional, List
import sqlite3


class DBManager:
    def __init__(self, db_path: str) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute(
                '''CREATE TABLE IF NOT EXISTS games
                (gid INTEGER PRIMARY KEY,
                text TEXT,
                turn TEXT)''')
        self.db.execute(
                '''CREATE TABLE IF NOT EXISTS players
                (addr TEXT,
                game INTEGER NOT NULL REFERENCES games(gid),
                round INTEGER,
                PRIMARY KEY(addr, game))''')

    def execute(self, statement: str, args=()) -> sqlite3.Cursor:
        return self.db.execute(statement, args)

    def commit(self, statement: str, args=()) -> sqlite3.Cursor:
        with self.db:
            return self.db.execute(statement, args)

    def close(self) -> None:
        self.db.close()

    # ================ Games =================

    def add_game(self, gid: int) -> None:
        self.commit('INSERT INTO games VALUES (?,?,?)',
                    (gid, None, None))

    def delete_game(self, gid: int) -> None:
        with self.db:
            self.execute('DELETE FROM players WHERE game=?', (gid,))
            self.execute('DELETE FROM games WHERE gid=?', (gid,))

    def set_text(self, gid: int, text: Optional[str]) -> None:
        self.commit('UPDATE games SET text=? WHERE gid=?', (text, gid))

    def set_turn(self, gid: int, turn: str) -> None:
        self.commit('UPDATE games SET turn=? WHERE gid=?', (turn, gid))

    def get_game_by_gid(self, gid: int) -> Optional[sqlite3.Row]:
        return self.execute(
            'SELECT * FROM games WHERE gid=?', (gid,)).fetchone()

    def get_game_by_turn(self, turn: str) -> Optional[sqlite3.Row]:
        return self.execute(
            'SELECT * FROM games WHERE turn=?', (turn,)).fetchone()

    # =============== Players ================

    def add_player(self, addr: str, round: int, gid: int) -> None:
        self.commit('INSERT INTO players VALUES (?,?,?)',
                    (addr, gid, round))

    def delete_player(self, addr: str) -> None:
        self.commit('DELETE FROM players WHERE addr=?', (addr,))

    def set_player(self, addr: str, round: int, gid: int) -> None:
        self.commit('UPDATE players SET round=? WHERE addr=? AND game=?',
                    (round, addr, gid))

    def get_player_by_addr(self, addr: str) -> Optional[sqlite3.Row]:
        return self.execute(
            'SELECT * FROM players WHERE addr=?', (addr,)).fetchone()

    def get_player_by_round(self, gid: int,
                            round: int) -> Optional[sqlite3.Row]:
        return self.execute(
            'SELECT * FROM players WHERE game=? AND round=?',
            (gid, round)).fetchone()

    def get_players(self, gid: int) -> List[sqlite3.Row]:
        return self.execute(
            'SELECT * FROM players WHERE game=?', (gid,)).fetchall()

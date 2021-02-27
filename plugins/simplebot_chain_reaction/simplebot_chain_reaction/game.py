
from enum import IntEnum


class Atom(IntEnum):
    EMPTY = 0
    BLACK = 1
    BLACK2 = 2
    BLACK3 = 3
    WHITE = 4
    WHITE2 = 5
    WHITE3 = 6


COLS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
ROWS = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮']
ORBS = ['🔳', '🔴', '🟠', '🟡', '🟢', '🟣', '🔵']


class Board:
    def __init__(self, board=None):
        if board:
            lines = board.split('\n')
            self.fist_round = int(lines.pop(0))
            self.turn = Atom(int(lines.pop(0)))
            self._board = [[Atom(int(e)) for e in ln] for ln in lines]
            self.nrows, self.ncols,  = len(self._board), len(self._board[0])
        else:
            self.nrows, self.ncols = 9, 6
            self.fist_round = 2
            self.turn = Atom.BLACK
            self._board = [[Atom.EMPTY for y in range(self.ncols)]
                           for x in range(self.nrows)]

    def export(self) -> str:
        board = '\n'.join(''.join(
            map(lambda a: str(a.value), row)) for row in self._board)
        return '\n'.join((str(self.fist_round), str(self.turn.value), board))

    def __str__(self) -> str:
        text = '{}-{} {}-{} {}-{}\n'.format(
            COLS[0], ORBS[Atom.BLACK],
            COLS[1], ORBS[Atom.BLACK2],
            COLS[2], ORBS[Atom.BLACK3])
        text += '{}-{} {}-{} {}-{}\n\n'.format(
            COLS[0], ORBS[Atom.WHITE],
            COLS[1], ORBS[Atom.WHITE2],
            COLS[2], ORBS[Atom.WHITE3])

        text += '|'.join(COLS[:self.ncols]) + '\n'
        for i, row in enumerate(self._board):
            for atom in row:
                text += ORBS[atom] + '|'
            text += ROWS[i] + '\n'
        return text

    @staticmethod
    def get_orb(atom: Atom) -> str:
        return ORBS[atom]

    def is_on_board(self, i: int, j: int) -> bool:
        return 0 <= i < self.nrows and 0 <= j < self.ncols

    def is_valid_move(self, i: int, j: int) -> bool:
        if not self.is_on_board(i, j):
            return False
        atom = self._board[i][j]
        return not atom or atom in range(self.turn, self.turn+3)

    def move(self, coord: str) -> None:
        sorted_coord = sorted(coord.lower())
        i = 'abcdefghi'.find(sorted_coord[1])
        j = '123456789'.find(sorted_coord[0])
        if not self.is_valid_move(i, j):
            raise ValueError('Invalid move')

        self.expand(i, j)
        self.turn = Atom.WHITE if self.turn == Atom.BLACK else Atom.BLACK
        if self.fist_round:
            self.fist_round -= 1

    def expand(self, i: int, j: int) -> None:
        weight = 3 if self.turn == Atom.WHITE else 0
        chain = [(i, j)]
        while chain:
            i, j = chain.pop(0)
            max_mass = 4

            if i in (0, self.nrows - 1):
                max_mass -= 1
            if j in (0, self.ncols - 1):
                max_mass -= 1

            mass = self._board[i][j]
            mass = mass + 1 if mass < 4 else mass - 2

            if mass < max_mass:
                self._board[i][j] = Atom(mass + weight)
                if 0 in self.result().values():
                    break
            else:
                self._board[i][j] = Atom.EMPTY
                if i > 0:
                    chain.append((i-1, j))
                if i < self.nrows - 1:
                    chain.append((i+1, j))
                if j > 0:
                    chain.append((i, j-1))
                if j < self.ncols - 1:
                    chain.append((i, j+1))

    def result(self) -> dict:
        black, white = 0, 0
        for row in self._board:
            for atom in row:
                if atom == Atom.EMPTY:
                    continue
                if atom < Atom.WHITE:
                    black += atom
                else:
                    white += atom - 3
        return {Atom.BLACK: black, Atom.WHITE: white}

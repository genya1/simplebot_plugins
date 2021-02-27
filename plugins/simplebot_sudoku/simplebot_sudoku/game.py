
import random
import sys

from sudoku import Sudoku


CELL = ['⬜', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
COLS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
ROWS = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮']


class Board:
    def __init__(self, game: str = None) -> None:
        if game:
            lines = game.split('\n')
            self.base = list(map(int, lines[0].split()))
            board = [
                [int(lines[1][i*9 + j]) or None for j in range(9)]
                for i in range(9)
            ]
            self.game = Sudoku(3, board=board)
        else:
            seed = random.randrange(sys.maxsize)
            self.game = Sudoku(3, seed=seed).difficulty(0.5)
            self.base = []
            for i, row in enumerate(self.game.board):
                for j, n in enumerate(row):
                    if n:
                        self.base.append(i*9 + j)

    def export(self) -> str:
        board = ' '.join(map(str, self.base))
        board += '\n'
        for row in self.game.board:
            for n in row:
                if n:
                    board += str(n)
                else:
                    board += '0'
        return board

    def __str__(self) -> str:
        sep = '⬛'
        sep_line = '|'.join(sep*11)
        text = ''
        for i in range(9):
            text += COLS[i]
            if i in (2, 5):
                text += '|{}|'.format(CELL[0])
            elif i != 8:
                text += '|'
        text += '\n\n'

        board = [[CELL[n or 0] for j, n in enumerate(row)]
                 for i, row in enumerate(self.game.board)]

        for i, row in enumerate(board):
            if i in (3, 6):
                text += sep_line+'\n'
            for j, d in enumerate(row):
                text += d
                text += '|{}|'.format(sep) if j in (2, 5) else '|'
            text += '{}\n'.format(ROWS[i])
        return text

    def is_valid(self, i: int, j: int, value: int) -> bool:
        if i*9+j in self.base or not 0 <= i <= 8 or not 0 <= j <= 8 or not 0 <= value <= 9:
            return False
        board = self.game.board.copy()
        board[i][j] = value
        return Sudoku(3, 3, board=board).validate()

    def move(self, coords: str) -> None:
        sorted_coord = sorted(coords[:2].lower())
        i = 'abcdefghi'.find(sorted_coord[1])
        j = '123456789'.find(sorted_coord[0])
        value = '0123456789'.find(coords[2])

        if not self.is_valid(i, j, value):
            raise ValueError('Invalid move')

        self.game.board[i][j] = value

    def result(self) -> int:
        for row in self.game.board:
            for n in row:
                if not n:
                    return 0
        return 1 if self.game.validate() else -1

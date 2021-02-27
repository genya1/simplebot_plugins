
import random
from typing import Optional

BLACK = 'x'
WHITE = 'o'
EMPTY = '.'
BOARD_WIDTH = 7
BOARD_HEIGHT = 6
COLS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣']
DISCS = [
    {BLACK: '🔴', WHITE: '🔵', EMPTY: '⬜'},
    {BLACK: '🟠', WHITE: '🟣', EMPTY: '⬜'},
    {BLACK: '🟡', WHITE: '🟢', EMPTY: '⬜'},
]


class Board:
    def __init__(self, board=None) -> None:
        if board:
            lines = board.split('\n')
            self.theme = int(lines.pop(0))
            self.turn = lines.pop(0)
            self.last_move = int(lines.pop(0))
            self._board = [[e for e in ln] for ln in lines]
        else:
            self.theme = random.randint(0, len(DISCS) - 1)
            self.turn = BLACK
            self.last_move = -1
            self._board = [[EMPTY for y in range(BOARD_WIDTH)]
                           for x in range(BOARD_HEIGHT)]
        self.height = len(self._board)
        self.width = len(self._board[0])

    def export(self) -> str:
        b = '\n'.join(''.join(ln) for ln in self._board)
        return '\n'.join((str(self.theme), self.turn, str(self.last_move), b))

    def __str__(self) -> str:
        text = '|'.join(COLS) + '\n'
        for row in self._board:
            text += '|'.join(self.get_disc(d) for d in row) + '\n'
        return text

    def get_disc(self, disc: str) -> str:
        return DISCS[self.theme][disc]

    def is_on_board(self, x: int, y: int) -> bool:
        return 0 <= x < self.height and 0 <= y < self.width

    def is_valid_move(self, col: int) -> bool:
        return 0 <= col < self.width and self._board[0][col] == EMPTY

    def move(self, col: int) -> bool:
        col -= 1
        if not self.is_valid_move(col):
            return False

        for x in range(self.height):
            if self._board[x][col] != EMPTY:
                self._board[x - 1][col] = self.turn
                self.last_move = col
                break
        else:
            self._board[self.height - 1][col] = self.turn
            self.last_move = col

        self.turn = WHITE if self.turn == BLACK else BLACK
        return True

    def result(self) -> Optional[str]:
        if self.last_move == -1:
            return None

        y1 = self.last_move
        for x in range(self.height):
            if self._board[x][y1] != EMPTY:
                x1 = x
                break

        winner = self._board[x1][y1]
        for xdir, ydir in ((0, 1), (1, 1), (1, 0), (1, -1)):
            count = 1
            x2, y2 = x1 + xdir, y1 + ydir
            while self.is_on_board(x2, y2) and self._board[x2][y2] == winner:
                count += 1
                x2 += xdir
                y2 += ydir

            xdir *= -1
            ydir *= -1
            x2, y2 = x1 + xdir, y1 + ydir
            while self.is_on_board(x2, y2) and self._board[x2][y2] == winner:
                count += 1
                x2 += xdir
                y2 += ydir

            if count >= 4:
                return winner

        for y in range(self.width):
            if self._board[0][y] == EMPTY:
                return None
        return '-'

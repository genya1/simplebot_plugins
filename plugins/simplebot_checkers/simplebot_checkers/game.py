
from checkers.game import Game

BLACK = 1
BLACK2 = BLACK + 2
WHITE = 2
WHITE2 = WHITE + 2
EMPTY = 0
WCELL = -1
BCELL = -2

COLS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣']
ROWS = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭']
DISCS = [
    {
        BLACK: '🔴',
        BLACK2: '🟠',
        WHITE: '🔵',
        WHITE2: '🟢',
        WCELL: '⬜',
        BCELL: '⬛',
    },
]


class Board:
    def __init__(self, board: str = None) -> None:
        self.game = Game()
        if board:
            lines = board.split('\n')
            self.theme = int(lines.pop(0))
            for mov in lines.pop(0).split():
                self.game.move(list(map(int, mov.split(','))))
        else:
            self.theme = 0

    @property
    def turn(self):
        return self.game.board.player_turn

    def export(self):
        moves = ' '.join('{},{}'.format(*mv) for mv in self.game.moves)
        return '\n'.join((str(self.theme), moves))

    def __str__(self):
        board = [[BCELL if (i+j+1) % 2 == 0 else WCELL for j in range(8)]
                 for i in range(8)]
        for piece in self.game.board.pieces:
            if not piece.position:
                continue
            disc = piece.player + 2 if piece.king else piece.player
            i, j = self.position2coord(piece.position)
            board[i][j] = disc
        text = '|'.join(COLS) + '\n'
        for i, row in enumerate(board):
            for disc in row:
                text += self.get_disc(disc) + '|'
            text += ROWS[i] + '\n'
        return text

    @staticmethod
    def position2coord(position: int) -> tuple:
        pos = 1
        for i in range(8):
            for j in range(8):
                if (i+j+1) % 2 == 0:
                    if pos == position:
                        return (i, j)
                    pos += 1
        return (-1, -1)

    def get_disc(self, disc) -> str:
        return DISCS[self.theme][disc]

    @staticmethod
    def get_position(coord: str) -> int:
        sorted_coord = sorted(coord.lower())
        i = 'abcdefgh'.find(sorted_coord[1])
        j = '12345678'.find(sorted_coord[0])
        if i < 0 or j < 0 or (i + j + 1) % 2 != 0:
            return -1

        pos = 1
        for i2 in range(8):
            for j2 in range(8):
                if (i, j) == (i2, j2):
                    return pos
                if (i2 + j2 + 1) % 2 == 0:
                    pos += 1

        return -1  # impossible

    def move(self, coords: str) -> None:
        if len(coords) == 2:
            j = self.get_position(coords)
            moves = [m[0] for m in self.game.get_possible_moves() if m[1] == j]
            if j < 0 or len(moves) != 1:
                raise ValueError('Invalid move')
            i = moves[0]
        else:
            i = self.get_position(coords[:2])
            j = self.get_position(coords[2:])
        if i < 0 or j < 0:
            raise ValueError('Invalid move')

        self.game.move([i, j])

    def result(self) -> int:
        if not self.game.is_over():
            return -1
        return self.game.get_winner() or 0


import os

from deltachat import Chat, Contact, Message
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

from .db import DBManager
from .game import Atom, Board

__version__ = '1.0.0'
DBASE: DBManager
DBOT: DeltaBot


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global DBASE, DBOT
    DBOT = bot
    DBASE = get_db(bot)

    bot.filters.register(name=__name__, func=filter_messages)

    DBOT.commands.register('/chr_play', cmd_play)
    DBOT.commands.register('/chr_surrender', cmd_surrender)
    DBOT.commands.register('/chr_new', cmd_new)
    DBOT.commands.register('/chr_repeat', cmd_repeat)


@deltabot_hookimpl
def deltabot_member_removed(chat: Chat, contact: Contact) -> None:
    game = DBASE.get_game_by_gid(chat.id)
    if game:
        player1, player2 = game['p1'], game['p2']
        if contact.addr in (DBOT.self_contact.addr, player1, player2):
            DBASE.delete_game(player1, player2)
            if contact != DBOT.self_contact:
                chat.remove_contact(DBOT.self_contact)


# ======== Filters ===============

def filter_messages(message: Message, replies: Replies) -> None:
    """Process move coordinates in Chain Reaction game groups
    """
    if len(message.text) != 2 or not message.text.isalnum():
        return
    game = DBASE.get_game_by_gid(message.chat.id)
    if game is None or game['board'] is None:
        return

    board = Board(game['board'])
    player = message.get_sender_contact().addr
    player = Atom.BLACK if game['black'] == player else Atom.WHITE
    if board.turn == player:
        try:
            board.move(message.text)
            DBASE.set_board(game['p1'], game['p2'], board.export())
            replies.add(text=run_turn(message.chat.id))
        except (ValueError, AssertionError):
            replies.add(text='❌ Invalid move!')


# ======== Commands ===============

def cmd_play(command: IncomingCommand, replies: Replies) -> None:
    """Invite a friend to play Chain Reaction.

    Example: `/chr_play friend@example.com`
    """
    if not command.payload:
        replies.add(text="Missing address")
        return

    if command.payload == command.bot.self_contact.addr:
        replies.add(text="Sorry, I don't want to play")
        return

    player1 = command.message.get_sender_contact()
    player2 = command.bot.get_contact(command.payload)
    if player1 == player2:
        replies.add(text="You can't play with yourself")
        return

    game = DBASE.get_game_by_players(player1.addr, player2.addr)

    if game is None:  # first time playing with player2
        board = Board()
        chat = command.bot.create_group(
            '🧬 {} 🆚 {} [ChainReaction]'.format(
                player1.addr, player2.addr), [player1, player2])
        DBASE.add_game(player1.addr, player2.addr, chat.id,
                       Board().export(), player1.addr)
        text = 'Hello {1},' \
               'You have been invited by {0} to play Chain Reaction'
        text += '\n\n{2}: {0}\n{3}: {1}\n\n'
        text = text.format(
            player1.name, player2.name, board.get_orb(Atom.BLACK),
            board.get_orb(Atom.WHITE))
        replies.add(text=text + run_turn(chat.id), chat=chat)
    else:
        text = 'You already have a game group with {}'.format(player2.name)
        replies.add(text=text, chat=command.bot.get_chat(game['gid']))


def cmd_surrender(command: IncomingCommand, replies: Replies) -> None:
    """End Chain Reaction game in the group it is sent.
    """
    game = DBASE.get_game_by_gid(command.message.chat.id)
    loser = command.message.get_sender_contact()
    if game is None or loser.addr not in (game['p1'], game['p2']):
        replies.add(text='This is not your game group')
    elif game['board'] is None:
        replies.add(text='There is no game running')
    else:
        DBASE.set_board(game['p1'], game['p2'], None)
        text = '🏳️ Game Over.\n{} surrenders.\n\n▶️ Play again? /chr_new'
        replies.add(text=text.format(loser.name))


def cmd_new(command: IncomingCommand, replies: Replies) -> None:
    """Start a new Chain Reaction game in the current game group.
    """
    sender = command.message.get_sender_contact()
    game = DBASE.get_game_by_gid(command.message.chat.id)
    if game is None or sender.addr not in (game['p1'], game['p2']):
        replies.add(text='This is not your game group')
    elif game['board'] is None:
        board = Board()
        DBASE.set_game(game['p1'], game['p2'], sender.addr, board.export())
        player2 = command.bot.get_contact(
            game['p2'] if sender.addr == game['p1'] else game['p1'])
        text = '▶️ Game started!\n{}: {}\n{}: {}\n\n'.format(
            board.get_orb(Atom.BLACK), sender.name,
            board.get_orb(Atom.WHITE), player2.name)
        replies.add(text=text + run_turn(command.message.chat.id))
    else:
        replies.add(text='There is a game running already')


def cmd_repeat(command: IncomingCommand, replies: Replies) -> None:
    """Send game board again.
    """
    replies.add(text=run_turn(command.message.chat.id))


# ======== Utilities ===============

def run_turn(gid: int) -> str:
    game = DBASE.get_game_by_gid(gid)
    if not game:
        return 'This is not your game group'
    if not game['board']:
        return 'There is no game running'
    board = Board(game['board'])
    b_orb = board.get_orb(Atom.BLACK)
    w_orb = board.get_orb(Atom.WHITE)
    result = board.result()
    pboard = '{}\n\n{} {} – {} {}'.format(
        board, b_orb, result[Atom.BLACK], result[Atom.WHITE], w_orb)
    if 0 in result.values() and not board.fist_round:
        DBASE.set_board(game['p1'], game['p2'], None)
        if result[Atom.WHITE] == 0:
            winner = '{} {}'.format(board.get_orb(Atom.BLACK),
                                    DBOT.get_contact(game['black']).name)
        else:
            player2 = game['p2'] if game['black'] == game['p1'] else game['p1']
            winner = '{} {}'.format(
                board.get_orb(Atom.WHITE), DBOT.get_contact(player2).name)
        text = '🏆 Game over.\n{} Wins!!!\n\n{}'.format(winner, pboard)
        text += '\n\n▶️ Play again? /chr_new'
    else:
        if board.turn == Atom.BLACK:
            turn = DBOT.get_contact(game['black']).name
        else:
            turn = DBOT.get_contact(
                game['p2'] if game['black'] == game['p1'] else game['p1']).name
        text = "{} {} it's your turn...\n\n{}".format(
            board.get_orb(board.turn), turn, pboard)
    return text


def get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))

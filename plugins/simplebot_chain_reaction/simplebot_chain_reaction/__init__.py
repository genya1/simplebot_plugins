
import os

from .db import DBManager
from .game import Board, Atom
from simplebot.hookspec import deltabot_hookimpl

from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from deltachat import Chat, Contact, Message


version = '1.0.0'
db: DBManager
dbot: DeltaBot


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global db, dbot
    dbot = bot
    db = get_db(bot)

    bot.filters.register(name=__name__, func=filter_messages)

    dbot.commands.register('/chr_play', cmd_play)
    dbot.commands.register('/chr_surrender', cmd_surrender)
    dbot.commands.register('/chr_new', cmd_new)
    dbot.commands.register('/chr_repeat', cmd_repeat)


@deltabot_hookimpl
def deltabot_member_removed(chat: Chat, contact: Contact) -> None:
    game = db.get_game_by_gid(chat.id)
    if game:
        me = dbot.self_contact
        p1, p2 = game['p1'], game['p2']
        if contact.addr in (me.addr, p1, p2):
            db.delete_game(p1, p2)
            if contact != me:
                chat.remove_contact(me)


# ======== Filters ===============

def filter_messages(message: Message, replies: Replies):
    """Process move coordinates in Chain Reaction game groups
    """
    if len(message.text) != 2 or not message.text.isalnum():
        return
    game = db.get_game_by_gid(message.chat.id)
    if game is None or game['board'] is None:
        return

    b = Board(game['board'])
    player = message.get_sender_contact().addr
    player = Atom.BLACK if game['black'] == player else Atom.WHITE
    if b.turn == player:
        try:
            b.move(message.text)
            db.set_board(game['p1'], game['p2'], b.export())
            replies.add(text=run_turn(message.chat.id))
        except (ValueError, AssertionError):
            replies.add(text='❌ Invalid move!')
        return True


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

    p1 = command.message.get_sender_contact()
    p2 = command.bot.get_contact(command.payload)
    if p1 == p2:
        replies.add(text="You can't play with yourself")
        return

    g = db.get_game_by_players(p1.addr, p2.addr)

    if g is None:  # first time playing with p2
        b = Board()
        chat = command.bot.create_group(
            '🧬 {} 🆚 {} [ChainReaction]'.format(p1.addr, p2.addr), [p1, p2])
        db.add_game(p1.addr, p2.addr, chat.id, Board().export(), p1.addr)
        text = 'Hello {1},' \
               'You have been invited by {0} to play Chain Reaction'
        text += '\n\n{2}: {0}\n{3}: {1}\n\n'
        text = text.format(
            p1.name, p2.name, b.get_orb(Atom.BLACK), b.get_orb(Atom.WHITE))
        replies.add(text=text + run_turn(chat.id), chat=chat)
    else:
        text = 'You already have a game group with {}'.format(p2.name)
        replies.add(text=text, chat=command.bot.get_chat(g['gid']))


def cmd_surrender(command: IncomingCommand, replies: Replies) -> None:
    """End Chain Reaction game in the group it is sent.
    """
    game = db.get_game_by_gid(command.message.chat.id)
    loser = command.message.get_sender_contact()
    if game is None or loser.addr not in (game['p1'], game['p2']):
        replies.add(text='This is not your game group')
    elif game['board'] is None:
        replies.add(text='There is no game running')
    else:
        db.set_board(game['p1'], game['p2'], None)
        replies.add(text='🏳️ Game Over.\n{} surrenders.\n\n▶️ Play again? /chr_new'.format(loser.name))


def cmd_new(command: IncomingCommand, replies: Replies) -> None:
    """Start a new Chain Reaction game in the current game group.
    """
    sender = command.message.get_sender_contact()
    game = db.get_game_by_gid(command.message.chat.id)
    if game is None or sender.addr not in (game['p1'], game['p2']):
        replies.add(text='This is not your game group')
    elif game['board'] is None:
        board = Board()
        db.set_game(game['p1'], game['p2'], sender.addr, board.export())
        b = board.get_orb(Atom.BLACK)
        w = board.get_orb(Atom.WHITE)
        p2 = command.bot.get_contact(
            game['p2'] if sender.addr == game['p1'] else game['p1'])
        text = '▶️ Game started!\n{}: {}\n{}: {}\n\n'.format(
            b, sender.name, w, p2.name)
        replies.add(text=text + run_turn(command.message.chat.id))
    else:
        replies.add(text='There is a game running already')


def cmd_repeat(command: IncomingCommand, replies: Replies) -> None:
    """Send game board again.
    """
    replies.add(text=run_turn(command.message.chat.id))


# ======== Utilities ===============

def run_turn(gid: int) -> str:
    g = db.get_game_by_gid(gid)
    if not g:
        return 'This is not your game group'
    if not g['board']:
        return 'There is no game running'
    b = Board(g['board'])
    b_orb = b.get_orb(Atom.BLACK)
    w_orb = b.get_orb(Atom.WHITE)
    result = b.result()
    board = '{}\n\n{} {} – {} {}'.format(
        b, b_orb, result[Atom.BLACK], result[Atom.WHITE], w_orb)
    if 0 in result.values() and not b.fist_round:
        db.set_board(g['p1'], g['p2'], None)
        if result[Atom.WHITE] == 0:
            winner = '{} {}'.format(
                b.get_orb(Atom.BLACK), dbot.get_contact(g['black']).name)
        else:
            p2 = g['p2'] if g['black'] == g['p1'] else g['p1']
            winner = '{} {}'.format(
                b.get_orb(Atom.WHITE), dbot.get_contact(p2).name)
        text = '🏆 Game over.\n{} Wins!!!\n\n{}'.format(winner, board)
        text += '\n\n▶️ Play again? /chr_new'
    else:
        if b.turn == Atom.BLACK:
            turn = dbot.get_contact(g['black']).name
        else:
            turn = dbot.get_contact(
                g['p2'] if g['black'] == g['p1'] else g['p1']).name
        text = "{} {} it's your turn...\n\n{}".format(
            b.get_orb(b.turn), turn, board)
    return text


def get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))

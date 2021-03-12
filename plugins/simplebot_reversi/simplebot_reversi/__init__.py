
import os

import simplebot
from deltachat import Chat, Contact, Message
from simplebot import DeltaBot
from simplebot.bot import Replies

from .database import DBManager
from .reversi import BLACK, WHITE, Board

__version__ = '1.0.0'
db: DBManager


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global db
    db = _get_db(bot)


@simplebot.hookimpl
def deltabot_member_removed(bot: DeltaBot, chat: Chat, contact: Contact) -> None:
    game = db.get_game_by_gid(chat.id)
    if game:
        me = bot.self_contact
        p1, p2 = game['p1'], game['p2']
        if contact.addr in (me.addr, p1, p2):
            db.delete_game(p1, p2)
            if contact != me:
                chat.remove_contact(me)


@simplebot.filter(name=__name__)
def filter_messages(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Process move coordinates in Reversi game groups
    """
    if len(message.text) != 2 or not message.text.isalnum():
        return
    game = db.get_game_by_gid(message.chat.id)
    if game is None or game['board'] is None:
        return

    b = Board(game['board'])
    player = message.get_sender_contact().addr
    player = BLACK if game['black'] == player else WHITE
    if b.turn == player:
        try:
            b.move(message.text)
            db.set_board(game['p1'], game['p2'], b.export())
            replies.add(text=_run_turn(bot, message.chat.id))
        except (ValueError, AssertionError):
            replies.add(text='❌ Invalid move!')


@simplebot.command
def reversi_play(bot: DeltaBot, payload: str, message: Message,
                 replies: Replies) -> None:
    """Invite a friend to play Reversi.

    Example: `/reversi_play friend@example.com`
    """
    if not payload:
        replies.add(text="Missing address")
        return

    if payload == bot.self_contact.addr:
        replies.add(text="Sorry, I don't want to play")
        return

    p1 = message.get_sender_contact().addr
    p2 = payload
    if p1 == p2:
        replies.add(text="You can't play with yourself")
        return

    g = db.get_game_by_players(p1, p2)

    if g is None:  # first time playing with p2
        b = Board()
        chat = bot.create_group(
            '🔴 {} 🆚 {} [Reversi]'.format(p1, p2), [p1, p2])
        db.add_game(p1, p2, chat.id, b.export(), p1)
        text = 'Hello {1},\nYou have been invited by {0} to play Reversi'
        text += '\n\n{2}: {0}\n{3}: {1}\n\n'
        text = text.format(p1, p2, b.get_disk(BLACK), b.get_disk(WHITE))
        replies.add(text=text + _run_turn(bot, chat.id), chat=chat)
    else:
        text = 'You already have a game group with {}'.format(p2)
        replies.add(text=text, chat=bot.get_chat(g['gid']))


@simplebot.command
def reversi_surrender(message: Message, replies: Replies) -> None:
    """End the Reversi game in the group it is sent.
    """
    game = db.get_game_by_gid(message.chat.id)
    loser = message.get_sender_contact().addr
    # this is not your game group
    if game is None or loser not in (game['p1'], game['p2']):
        replies.add(text='This is not your game group')
    elif game['board'] is None:
        replies.add(text='There is no game running')
    else:
        db.set_board(game['p1'], game['p2'], None)
        text = '🏳️ Game Over.\n{} surrenders.\n\n▶️ Play again? /reversi_new'
        replies.add(text=text.format(loser))


@simplebot.command
def reversi_new(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Start a new Reversi game in the current game group.
    """
    sender = message.get_sender_contact().addr
    game = db.get_game_by_gid(message.chat.id)
    # this is not your game group
    if game is None or sender not in (game['p1'], game['p2']):
        replies.add(text='This is not your game group')
    elif game['board'] is None:
        b = Board()
        db.set_game(game['p1'], game['p2'], b.export(), sender)
        p2 = game['p2'] if sender == game['p1'] else game['p1']
        text = 'Game started!\n{}: {}\n{}: {}\n\n'.format(
            b.get_disk(BLACK), bot.get_contact(sender).name,
            b.get_disk(WHITE), bot.get_contact(p2).name)
        replies.add(text=text + _run_turn(bot, message.chat.id))
    else:
        replies.add(text='There is a game running already')


@simplebot.command
def reversi_repeat(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Send game board again.
    """
    replies.add(text=_run_turn(bot, message.chat.id))


def _run_turn(bot: DeltaBot, gid: int) -> str:
    g = db.get_game_by_gid(gid)
    if not g:
        return 'This is not your game group'
    if not g['board']:
        return 'There is no game running'
    b = Board(g['board'])
    result = b.result()
    if result['status'] in (0, 1):
        if result['status'] == 1:
            b.turn = BLACK if b.turn == WHITE else WHITE
            db.set_board(g['p1'], g['p2'], b.export())
        if b.turn == BLACK:
            disk = b.get_disk(BLACK)
            turn = '{} {}'.format(disk, g['black'])
        else:
            disk = b.get_disk(WHITE)
            p2 = g['p2'] if g['black'] == g['p1'] else g['p1']
            turn = '{} {}'.format(disk, p2)
        text = "{} it's your turn...\n\n{}\n\n{}".format(
            bot.get_contact(turn).name, b, b.get_score())
    else:
        db.set_board(g['p1'], g['p2'], None)
        black, white = result[BLACK], result[WHITE]
        if black == white:
            text = '🤝 Game over.\nIt is a draw!\n\n'
        else:
            if black > white:
                disk = b.get_disk(BLACK)
                winner = '{} {}'.format(disk, g['black'])
            else:
                disk = b.get_disk(WHITE)
                p2 = g['p2'] if g['black'] == g['p1'] else g['p1']
                winner = '{} {}'.format(disk, p2)
            text = '🏆 Game over.\n{} Wins!\n\n'.format(
                bot.get_contact(winner).name)
        text += '\n\n'.join((
            str(b), b.get_score(), '▶️ Play again? /reversi_new'))
    return text


def _get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))


import os

import simplebot
import simplebot_chess.game as chgame
from deltachat import Chat, Contact, Message
from simplebot import DeltaBot
from simplebot.bot import Replies

from .db import DBManager

__version__ = '1.0.0'
db: DBManager


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global db
    db = _get_db(bot)

    _getdefault(bot, 'theme', '0')


@simplebot.hookimpl
def deltabot_member_removed(bot: DeltaBot, chat: Chat, contact: Contact) -> None:
    game = db.get_game_by_gid(chat.id)
    if game:
        me = bot.self_contact
        if contact.addr in (me.addr, game['p1'], game['p2']):
            db.delete_game(game['p1'], game['p2'])
            if contact != me:
                chat.remove_contact(me)


@simplebot.filter(name=__name__)
def filter_messages(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Process move coordinates in Chess game groups
    """
    if not message.text.isalnum() and '-' not in message.text:
        return
    game = db.get_game_by_gid(message.chat.id)
    if game is None or game['game'] is None:
        return

    b = chgame.Board(game['game'])
    player = message.get_sender_contact().addr
    if b.turn == player:
        try:
            b.move(message.text)
            db.set_game(game['p1'], game['p2'], b.export())
            replies.add(text=_run_turn(bot, message.chat.id))
        except (ValueError, AssertionError):
            replies.add(text='❌ Invalid move!')


@simplebot.command
def chess_play(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
    """Invite a friend to play Chess.

    Example: `/chess_play friend@example.com`
    To move use Standard Algebraic Notation or Long Algebraic Notation
    (without hyphens), more info in Wikipedia.
    For example, to move pawn from e2 to e4, send a message: e4 or: e2e4,
    to move knight from g1 to f3, send a message: Nf3 or: g1f3
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
        chat = bot.create_group(
            '♞ {} 🆚 {} [Chess]'.format(p1, p2), [p1, p2])
        b = chgame.Board(p1=p1, p2=p2, theme=int(_getdefault(bot, 'theme')))
        db.add_game(p1, p2, chat.id, b.export())
        text = 'Hello {1},\nYou have been invited by {0} to play Chess'
        text += '\n\n{2} White: {0}\n{3} Black: {1}\n\n'
        text = text.format(p1, p2, b.theme['P'], b.theme['p'])
        text += _run_turn(bot, chat.id)
        replies.add(text=text, chat=chat)
    else:
        text = 'You already have a game group with {}'.format(p2)
        replies.add(text=text, chat=bot.get_chat(g['gid']))


@simplebot.command
def chess_surrender(message: Message, replies: Replies) -> None:
    """End the Chess game in the group it is sent.
    """
    game = db.get_game_by_gid(message.chat.id)
    loser = message.get_sender_contact().addr
    if game is None or loser not in (game['p1'], game['p2']):
        replies.add(text='This is not your game group')
    elif game['game'] is None:
        replies.add(text='There is no game running')
    else:
        db.set_game(game['p1'], game['p2'], None)
        text = '🏳️ Game Over.\n{} surrenders.\n\n▶️ Play again? /chess_new'
        replies.add(text=text.format(loser))


@simplebot.command
def chess_new(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Start a new Chess game in the current game group.
    """
    p1 = message.get_sender_contact().addr
    game = db.get_game_by_gid(message.chat.id)
    if game is None or p1 not in (game['p1'], game['p2']):
        replies.add(text='This is not your game group')
    elif game['game'] is None:
        p2 = game['p2'] if p1 == game['p1'] else game['p1']
        b = chgame.Board(p1=p1, p2=p2, theme=int(_getdefault(bot, 'theme')))
        db.set_game(p1, p2, b.export())
        text = 'Game started!\n{} White: {}\n{} Black: {}\n\n'.format(
            b.theme['P'], p1, b.theme['p'], p2)
        text += _run_turn(bot, message.chat.id)
        replies.add(text=text)
    else:
        replies.add(text='There is a game running already')


@simplebot.command
def chess_repeat(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Send game board again.
    """
    replies.add(text=_run_turn(bot, message.chat.id))


def _run_turn(bot: DeltaBot, gid: int) -> str:
    g = db.get_game_by_gid(gid)
    if not g:
        return 'This is not your game group'
    if not g['game']:
        return 'There is no game running'
    b = chgame.Board(g['game'], theme=int(_getdefault(bot, 'theme')))
    result = b.result()
    if result == '*':
        return "{} {} it's your turn...\n\n{}".format(
            b.theme['P'] if b.turn == b.white else b.theme['p'], b.turn, b)
    db.set_game(g['p1'], g['p2'], None)
    if result == '1/2-1/2':
        text = '🤝 Game over.\nIt is a draw!'
    else:
        if result == '1-0':
            winner = '{} {}'.format(b.theme['P'], b.white)
        else:
            winner = '{} {}'.format(b.theme['p'], b.black)
        text = '🏆 Game over.\n{} Wins!'.format(winner)
    return text + '\n\n{}\n\n▶️ Play again? /chess_new'.format(b)


def _getdefault(bot: DeltaBot, key: str, value: str = None) -> str:
    val = bot.get(key, scope=__name__)
    if val is None and value is not None:
        bot.set(key, value, scope=__name__)
        val = value
    return val


def _get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))


import os
import time

import simplebot
from deltachat import Chat, Contact, Message
from simplebot import DeltaBot
from simplebot.bot import Replies

from .db import DBManager
from .game import Board

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
        if contact.addr in (me.addr, game['addr']):
            db.delete_game(game['addr'])
            if contact != me:
                chat.remove_contact(me)


@simplebot.filter(name=__name__)
def filter_messages(message: Message, replies: Replies) -> None:
    """Process move coordinates in Sudoku game groups.
    """
    if not message.text.isalnum() or len(message.text) != 3:
        return

    game = db.get_game_by_gid(message.chat.id)
    if game is None or game['board'] is None:
        return

    try:
        b = Board(game['board'])
        b.move(message.text)
        db.set_board(game['addr'], b.export())
        replies.add(text=_run_turn(message.chat.id))
    except ValueError:
        replies.add(text='❌ Invalid move!')


@simplebot.command
def sudoku_play(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Start a new Sudoku game.

    Example: `/sudoku_play`
    """
    player = message.get_sender_contact()
    game = db.get_game_by_addr(player.addr)

    if game is None:  # make a new chat
        b = Board()
        chat = bot.create_group('#️⃣ Sudoku', [player.addr])
        db.add_game(player.addr, chat.id, b.export(), time.time())
        text = 'Hello {}, in this group you can play Sudoku.\n\n'.format(
            player.name)
        replies.add(text=text + _run_turn(chat.id), chat=chat)
    else:
        db.set_game(game['addr'], Board().export(), time.time())
        if message.chat.id == game['gid']:
            chat = message.chat
        else:
            chat = bot.get_chat(game['gid'])
        replies.add(
            text='Game started!\n\n' + _run_turn(game['gid']), chat=chat)


@simplebot.command
def sudoku_repeat(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Send Sudoku game board again.

    Example: `/sudoku_repeat`
    """
    game = db.get_game_by_addr(message.get_sender_contact().addr)
    if game:
        if message.chat.id == game['gid']:
            chat = message.chat
        else:
            chat = bot.get_chat(game['gid'])
        replies.add(text=_run_turn(game['gid']), chat=chat)
    else:
        replies.add(
            text="No active game, send /sudoku_play to start playing.")


def _run_turn(gid: int) -> str:
    g = db.get_game_by_gid(gid)
    assert g is not None
    if not g['board']:
        return "No active game, send /sudoku_play to start playing."
    b = Board(g['board'])
    result = b.result()
    if result == 1:
        db.set_board(g['addr'], None)
        text = '🏆 Game over. You Win!!!\n\n{}'.format(b)
        return text + '\n\n▶️ Play again? /sudoku_play'
    return str(b)


def _get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))


import os
import time

from deltachat import Chat, Contact, Message
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

from .db import DBManager
from .game import Board

__version__ = '1.0.0'
db: DBManager
dbot: DeltaBot


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global db, dbot
    dbot = bot
    db = get_db(bot)

    bot.filters.register(name=__name__, func=filter_messages)

    dbot.commands.register('/sudoku_play', cmd_play)
    dbot.commands.register('/sudoku_repeat', cmd_repeat)


@deltabot_hookimpl
def deltabot_member_removed(chat: Chat, contact: Contact) -> None:
    game = db.get_game_by_gid(chat.id)
    if game:
        me = dbot.self_contact
        if contact.addr in (me.addr, game['addr']):
            db.delete_game(game['addr'])
            if contact != me:
                chat.remove_contact(me)


# ======== Filters ===============

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
        replies.add(text=run_turn(message.chat.id))
    except ValueError:
        replies.add(text='❌ Invalid move!')


# ======== Commands ===============

def cmd_play(command: IncomingCommand, replies: Replies) -> None:
    """Start a new Sudoku game.

    Example: `/sudoku_play`
    """
    player = command.message.get_sender_contact()
    game = db.get_game_by_addr(player.addr)

    if game is None:  # make a new chat
        b = Board()
        chat = command.bot.create_group('#️⃣ Sudoku', [player.addr])
        db.add_game(player.addr, chat.id, b.export(), time.time())
        text = 'Hello {}, in this group you can play Sudoku.\n\n'.format(
            player.name)
        replies.add(text=text + run_turn(chat.id), chat=chat)
    else:
        db.set_game(game['addr'], Board().export(), time.time())
        if command.message.chat.id == game['gid']:
            chat = command.message.chat
        else:
            chat = command.bot.get_chat(game['gid'])
        replies.add(
            text='Game started!\n\n' + run_turn(game['gid']), chat=chat)


def cmd_repeat(command: IncomingCommand, replies: Replies) -> None:
    """Send Sudoku game board again.

    Example: `/sudoku_repeat`
    """
    game = db.get_game_by_addr(command.message.get_sender_contact().addr)
    if game:
        if command.message.chat.id == game['gid']:
            chat = command.message.chat
        else:
            chat = command.bot.get_chat(game['gid'])
        replies.add(text=run_turn(game['gid']), chat=chat)
    else:
        replies.add(
            text="No active game, send /sudoku_play to start playing.")


# ======== Utilities ===============

def run_turn(gid: int) -> str:
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


def get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))


import os

from .db import DBManager

from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

from deltachat import Message

version = '1.0.0'
dbot: DeltaBot
db: DBManager


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global dbot, db
    dbot = bot
    db = get_db(bot)

    getdefault('score_badge', '🎖️')

    bot.filters.register(name=__name__, func=filter_messages)

    bot.commands.register(name="/scoreSet", func=cmd_set, admin=True)
    bot.commands.register(name="/score", func=cmd_score)


# ======== Filters ===============

def filter_messages(message: Message, replies: Replies) -> None:
    """Detect messages like +1 or -1 to increase/decrease score.
    """
    if not message.quote:
        return
    score = _parse(message.text)
    if not score:
        return
    sender = message.get_sender_contact().addr
    is_admin = dbot.is_admin(sender)
    if score < 0 and not is_admin:
        return
    if not is_admin and db.get_score(sender) - score < 0:
        replies.add(text="❌ You can't give what you don't have...",
                    quote=message)
        return
    receiver = message.quote.get_sender_contact().addr
    if sender == receiver:
        return

    sender_score = _add_score(sender, -score)
    receiver_score = _add_score(receiver, score)
    if is_admin:
        text = '{0}: {1}{4}'
    else:
        text = '{0}: {1}{4}\n{2}: {3}{4}'
    text = text.format(
        dbot.get_contact(receiver).name,
        receiver_score,
        dbot.get_contact(sender).name,
        sender_score,
        getdefault('score_badge'))
    replies.add(text=text, quote=message)


# ======== Commands ===============

def cmd_set(command: IncomingCommand, replies: Replies) -> None:
    """Set score for given address.

    Example: `/score foo@example.com +100`
    """
    score = _parse(command.args[1])
    if not score:
        replies.add(
            text='❌ Invalid number, use + or -', quote=command.message)
    else:
        score = _add_score(command.args[0], score)
        name = dbot.get_contact(command.args[0]).name
        text = '{}: {}{}'.format(name, score, getdefault('score_badge'))
        replies.add(text=text, quote=command.message)



def cmd_score(command: IncomingCommand, replies: Replies) -> None:
    """Get score from given address or your current score if no address is given.

    Example: `/score`
    """
    addr = command.payload if command.payload else command.message.get_sender_contact().addr
    name = dbot.get_contact(addr).name
    badge = getdefault('score_badge')
    replies.add(text='{0}: {1}/{2}{3}'.format(
        name, db.get_score(addr), db.get_score(), badge))


# ======== Utilities ===============

def get_db(bot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))


def getdefault(key: str, value: str = None) -> str:
    val = dbot.get(key, scope=__name__)
    if val is None and value is not None:
        dbot.set(key, value, scope=__name__)
        val = value
    return val


def _parse(score: str) -> int:
    if not score.startswith(('-', '+')):
        return 0
    try:
        return int(score)
    except ValueError:
        return 0


def _add_score(addr: str, score: int) -> int:
    score = db.get_score(addr) + score
    if score == 0:
        db.delete_score(addr)
    else:
        db.set_score(addr, score)
    return score


import os

import simplebot
from deltachat import Message
from simplebot import DeltaBot
from simplebot.bot import Replies

from .db import DBManager

__version__ = '1.0.0'
db: DBManager


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global db
    db = _get_db(bot)

    _getdefault(bot, 'max_bio_len', '1000')


@simplebot.command
def friends_join(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
    """Add you to the list or update your bio.
    """
    if not payload:
        replies.add(text='You must provide a biography')
        return

    text = ' '.join(payload.split())
    max_len = int(_getdefault(bot, 'max_bio_len'))
    if len(text) > max_len:
        text = text[:max_len] + '...'

    addr = message.get_sender_contact().addr
    exists = db.get_bio(addr)
    db.update_bio(addr, text)
    if exists:
        replies.add(text='Bio updated')
    else:
        replies.add(text='Added to the list')


@simplebot.command
def friends_leave(message: Message, replies: Replies) -> None:
    """Remove you from the list.
    """
    addr = message.get_sender_contact().addr
    if db.get_bio(addr) is None:
        replies.add(text='You are not in the list yet')
    else:
        db.remove_user(addr)
        replies.add(text='You were removed from the list')


@simplebot.command
def friends_list(bot: DeltaBot, replies: Replies) -> None:
    """Get the list of users and their biography.
    """
    users = []
    for row in db.get_users():
        contact = bot.get_contact(row['addr'])
        users.append('{}:\n{}... /friends_profile_{}'.format(
            row['addr'], row['bio'][:100], contact.id))
    if users:
        while users:
            replies.add(text='\n\n―――――――――――――――\n\n'.join(users[:50]))
            users = users[50:]
    else:
        replies.add(text='Empty List')


@simplebot.command
def friends_profile(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
    """See the biography of the given address or your own in no address provided.
    """
    if payload.isnumeric():
        contact = bot.get_contact(int(payload))
    elif '@' not in payload:
        contact = message.get_sender_contact()
    else:
        contact = bot.get_contact(payload)
    bio = db.get_bio(contact.addr)
    if bio is None:
        replies.add(text='No biography found for {}'.format(contact.addr))
    else:
        replies.add(filename=contact.get_profile_image(),
                    text='{}:\n{}'.format(contact.addr, bio))


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


import os

from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

from .db import DBManager

version = '1.0.0'
dbot: DeltaBot
db: DBManager


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global dbot, db
    dbot = bot
    db = get_db(bot)

    getdefault('max_bio_len', '1000')

    dbot.commands.register('/friends_join', cmd_join)
    dbot.commands.register('/friends_leave', cmd_leave)
    dbot.commands.register('/friends_list', cmd_list)
    dbot.commands.register('/friends_profile', cmd_profile)


# ======== Commands ===============

def cmd_join(command: IncomingCommand, replies: Replies) -> None:
    """Add you to the list or update your bio.
    """
    if not command.payload:
        replies.add(text='You must provide a biography')
        return

    text = ' '.join(command.payload.split())
    max_len = int(getdefault('max_bio_len'))
    if len(text) > max_len:
        text = text[:max_len] + '...'

    addr = command.message.get_sender_contact().addr
    exists = db.get_bio(addr)
    db.update_bio(addr, text)
    if exists:
        replies.add(text='Bio updated')
    else:
        replies.add(text='Added to the list')


def cmd_leave(command: IncomingCommand, replies: Replies) -> None:
    """Remove you from the list.
    """
    addr = command.message.get_sender_contact().addr
    if db.get_bio(addr) is None:
        replies.add(text='You are not in the list yet')
    else:
        db.remove_user(addr)
        replies.add(text='You was removed from the list')


def cmd_list(command: IncomingCommand, replies: Replies) -> None:
    """Get the list of users and their biography.
    """
    users = []
    for row in db.get_users():
        contact = command.bot.get_contact(row['addr'])
        users.append('{}:\n{}... /friends_profile_{}'.format(
            row['addr'], row['bio'][:100], contact.id))
    if users:
        while users:
            replies.add(text='\n\n―――――――――――――――\n\n'.join(users[:50]))
            users = users[50:]
    else:
        replies.add(text='Empty List')


def cmd_profile(command: IncomingCommand, replies: Replies) -> None:
    """See the biography of the given address or your own in no address provided.
    """
    if command.payload.isnumeric():
        contact = command.bot.get_contact(int(command.payload))
    elif '@' not in command.payload:
        contact = command.message.get_sender_contact()
    else:
        contact = command.bot.get_contact(command.payload)
    bio = db.get_bio(contact.addr)
    if bio is None:
        replies.add(text='No biography found for {}'.format(contact.addr))
    else:
        replies.add(filename=contact.get_profile_image(),
                    text='{}:\n{}'.format(contact.addr, bio))


# ======== Utilities ===============

def getdefault(key: str, value: str = None) -> str:
    val = dbot.get(key, scope=__name__)
    if val is None and value is not None:
        dbot.set(key, value, scope=__name__)
        val = value
    return val


def get_db(bot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))

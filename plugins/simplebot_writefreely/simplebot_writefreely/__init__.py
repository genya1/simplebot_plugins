import os

from .db import DBManager

from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

from deltachat import Chat, Contact, Message

import writefreely as wf

version = '1.0.0'
dbot: DeltaBot
db: DBManager


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global dbot, db
    dbot = bot
    db = get_db(bot)

    bot.filters.register(name=__name__, func=filter_messages)

    bot.commands.register(name="/wf_login", func=cmd_login, admin=getdefault('allow_login', '1') != '1')
    bot.commands.register(name="/wf_logout", func=cmd_logout)
    bot.commands.register(name="/wf_bridge", func=cmd_bridge, admin=True)
    bot.commands.register(name="/wf_unbridge", func=cmd_unbridge, admin=True)


@deltabot_hookimpl
def deltabot_member_removed(chat: Chat, contact: Contact) -> None:
    me = dbot.self_contact
    if me == contact or len(chat.get_contacts()) <= 1:
        if db.get_chat(chat.id):
            db.del_chat(chat.id)


# ======== Filters ===============

def filter_messages(message: Message, replies: Replies) -> None:
    """Process messages sent to WriteFreely groups.
    """
    chat = db.get_chat(message.chat.id)
    if not chat or not message.text:
        return

    if message.text.startswith('# '):
        args = message.text.split('\n', maxsplit=1)
        title = args.pop(0)[2:] if len(args) == 2 else None
        body = args.pop(0).strip()
    else:
        title, body = None, message.text

    acc = db.get_account(chat['account'])
    client = wf.client(host=acc['host'], token=acc['token'])
    post = client.create_post(
        collection=chat['blog'], title=title, body=body)
    replies.add(text=post['collection']['url'] + post['slug'])


# ======== Commands ===============

def cmd_login(command: IncomingCommand, replies: Replies) -> None:
    """Login to your WriteFreely instance.

    Example: `/wf_login https://write.as YourUser YourPassword` or
    `/wf_login https://write.as YourToken`
    """
    sender = command.message.get_sender_contact()
    args = command.payload.split(maxsplit=2)
    if len(args) == 3:
        client = wf.client(host=args[0], user=args[1], password=args[2])
    else:
        client = wf.client(host=args[0], token=args[1])
    db.add_account(sender.addr, client.host, client.token)
    for blog in client.get_collections():
        g = command.bot.create_group(
            '{} [WF]'.format(blog['title'] or blog['alias']), [sender])
        db.add_chat(g.id, blog['alias'], sender.addr)
        replies.add(text='All messages sent here will be published to blog:\nAlias: {}\nDescription: {}'.format(
            blog['alias'], blog['description']), chat=g)
    replies.add(text='✔️Logged in')

def cmd_logout(command: IncomingCommand, replies: Replies) -> None:
    """Logout from your WriteFreely instance.

    Example: `/wf_logout`
    """
    addr = command.message.get_sender_contact().addr
    acc = db.get_account(addr)
    db.del_account(addr)
    wf.client(host=acc['host'], token=acc['token']).logout()
    replies.add(text='✔️Logged out')

def cmd_bridge(command: IncomingCommand, replies: Replies) -> None:
    """Bridge chat with a WriteFreely blog.

    Example: `/wf_bridge myblog`
    """
    addr = command.message.get_sender_contact().addr
    acc = db.get_account(addr)
    if not acc:
        replies.add(text='❌ You are not logged in.')
        return

    client = wf.client(host=acc['host'], token=acc['token'])
    blogs = [blog['alias'] for blog in client.get_collections()]
    if command.payload not in blogs:
        replies.add(
            text='❌ Invalid blog name, your blogs:\n{}'.format('\n'.join(blogs)))
        return
    db.add_chat(command.message.chat.id, command.payload, addr)
    replies.add(text='✔️All messages sent here will be published in {}/{}'.format(acc['host'], command.payload))


def cmd_unbridge(command: IncomingCommand, replies: Replies) -> None:
    """Remove bridge with the WriteFreely blog in the chat it is sent.

    Example: `/wf_unbridge`
    """
    db.del_chat(command.message.chat.id)
    replies.add(text='✔️Removed bridge.')


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

import os

import simplebot
import writefreely as wf
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

    bot.commands.register(
        name="/wf_login", func=cmd_login,
        admin=_getdefault(bot, 'allow_login', '1') != '1')


@simplebot.hookimpl
def deltabot_member_removed(bot: DeltaBot, chat: Chat, contact: Contact) -> None:
    me = bot.self_contact
    if me == contact or len(chat.get_contacts()) <= 1:
        if db.get_chat(chat.id):
            db.del_chat(chat.id)


@simplebot.filter(name=__name__)
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
    assert acc
    client = wf.client(host=acc['host'], token=acc['token'])
    post = client.create_post(
        collection=chat['blog'], title=title, body=body)
    replies.add(
        text=post['collection']['url'] + post['slug'], quote=message)


def cmd_login(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
    """Login to your WriteFreely instance.

    Example: `/wf_login https://write.as YourUser YourPassword` or
    `/wf_login https://write.as YourToken`
    """
    sender = message.get_sender_contact()
    args = payload.split(maxsplit=2)
    if len(args) == 3:
        client = wf.client(host=args[0], user=args[1], password=args[2])
    else:
        client = wf.client(host=args[0], token=args[1])
    db.add_account(sender.addr, client.host, client.token)
    for blog in client.get_collections():
        g = bot.create_group(
            '{} [WF]'.format(blog['title'] or blog['alias']), [sender])
        db.add_chat(g.id, blog['alias'], sender.addr)
        replies.add(text='All messages sent here will be published to'
                    ' blog:\nAlias: {}\nDescription: {}'.format(
                        blog['alias'], blog['description']), chat=g)
    replies.add(text='✔️Logged in')


@simplebot.command
def wf_logout(message: Message, replies: Replies) -> None:
    """Logout from your WriteFreely instance.

    Example: `/wf_logout`
    """
    addr = message.get_sender_contact().addr
    acc = db.get_account(addr)
    if acc:
        db.del_account(addr)
        wf.client(host=acc['host'], token=acc['token']).logout()
        replies.add(text='✔️Logged out')
    else:
        replies.add(text='❌ You are not logged in.')


@simplebot.command(admin=True)
def wf_bridge(payload: str, message: Message, replies: Replies) -> None:
    """Bridge chat with a WriteFreely blog.

    Example: `/wf_bridge myblog`
    """
    addr = message.get_sender_contact().addr
    acc = db.get_account(addr)
    if not acc:
        replies.add(text='❌ You are not logged in.')
        return

    client = wf.client(host=acc['host'], token=acc['token'])
    blogs = [blog['alias'] for blog in client.get_collections()]
    if payload not in blogs:
        replies.add(
            text='❌ Invalid blog name, your blogs:\n{}'.format(
                '\n'.join(blogs)))
        return
    db.add_chat(message.chat.id, payload, addr)
    text = '✔️All messages sent here will be published in {}/{}'
    replies.add(text=text.format(acc['host'], payload))


@simplebot.command(admin=True)
def wf_unbridge(message: Message, replies: Replies) -> None:
    """Remove bridge with the WriteFreely blog in the chat it is sent.

    Example: `/wf_unbridge`
    """
    db.del_chat(message.chat.id)
    replies.add(text='✔️Removed bridge.')


def _get_db(bot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))


def _getdefault(bot: DeltaBot, key: str, value: str = None) -> str:
    val = bot.get(key, scope=__name__)
    if val is None and value is not None:
        bot.set(key, value, scope=__name__)
        val = value
    return val

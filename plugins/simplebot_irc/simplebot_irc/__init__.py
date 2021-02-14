# -*- coding: utf-8 -*-
from threading import Thread
from time import sleep
from typing import Generator
import re
import os

from .irc import IRCBot
from .database import DBManager
from deltabot.hookspec import deltabot_hookimpl
# typing:
from deltabot import DeltaBot
from deltabot.bot import Replies
from deltabot.commands import IncomingCommand
from deltachat import Chat, Contact, Message


version = '1.0.0'
nick_re = re.compile(r'[a-zA-Z0-9]{1,30}$')
dbot: DeltaBot
db: DBManager
irc_bridge: IRCBot


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global dbot
    dbot = bot

    getdefault('nick', 'SimpleBot')
    getdefault('host', 'irc.freenode.net')
    getdefault('port', '6667')
    getdefault('max_group_size', '20')
    allow_bridging = getdefault('allow_bridging', '0') == '1'

    bot.filters.register(name=__name__, func=filter_messages)

    dbot.commands.register('/irc_join', cmd_join)
    dbot.commands.register(
        '/irc_bridge', cmd_bridge, admin=not allow_bridging)
    dbot.commands.register('/irc_remove', cmd_remove)
    dbot.commands.register('/irc_topic', cmd_topic)
    dbot.commands.register('/irc_members', cmd_members)
    dbot.commands.register('/irc_nick', cmd_nick)


@deltabot_hookimpl
def deltabot_start(bot: DeltaBot) -> None:
    global db, irc_bridge

    db = get_db(bot)

    nick = getdefault('nick')
    host = getdefault('host')
    port = int(getdefault('port'))
    irc_bridge = IRCBot(host, port, nick, db, bot)
    Thread(target=run_irc, daemon=True).start()


@deltabot_hookimpl
def deltabot_member_removed(chat: Chat, contact: Contact) -> None:
    channel = db.get_channel_by_gid(chat.id)
    if channel:
        me = dbot.self_contact
        if me == contact or len(chat.get_contacts()) <= 1:
            db.remove_cchat(chat.id)
            if next(db.get_cchats(channel), None) is None:
                db.remove_channel(channel)
                irc_bridge.leave_channel(channel)


# ======== Filters ===============

def filter_messages(message: Message, replies: Replies):
    """Process messages sent to an IRC channel.
    """
    chan = db.get_channel_by_gid(message.chat.id)
    if not chan:
        return

    if not message.text or message.filename:
        replies.add(text='Unsupported message')
        return

    nick = db.get_nick(message.get_sender_contact().addr)

    for line in message.text.split('\n'):
        irc_bridge.send_message(chan, '{}[dc]: {}'.format(nick, line))

    text = '{}[dc]: {}'.format(nick, message.text)
    for g in get_cchats(chan):
        if g.id != message.chat.id:
            replies.add(text=text, chat=g)
    return True


# ======== Commands ===============

def cmd_topic(command: IncomingCommand, replies: Replies) -> None:
    """Show IRC channel topic.
    """
    chan = db.get_channel_by_gid(command.message.chat.id)
    if not chan:
        replies.add(text='This is not an IRC channel')
    else:
        replies.add(text='Topic:\n{}'.format(irc_bridge.get_topic(chan)))


def cmd_members(command: IncomingCommand, replies: Replies) -> None:
    """Show list of IRC channel members.
    """
    me = command.bot.self_contact

    chan = db.get_channel_by_gid(command.message.chat.id)
    if not chan:
        replies.add(text='This is not an IRC channel')
        return

    members = 'Members:\n'
    for g in get_cchats(chan):
        for c in g.get_contacts():
            if c != me:
                members += '• {}[dc]\n'.format(db.get_nick(c.addr))

    for m in irc_bridge.get_members(chan):
        members += '• {}[irc]\n'.format(m)

    replies.add(text=members)


def cmd_nick(command: IncomingCommand, replies: Replies) -> None:
    """Set your IRC nick or display your current nick if no new nick is given.
    """
    addr = command.message.get_sender_contact().addr
    if command.payload:
        new_nick = '_'.join(command.args)
        if not nick_re.match(new_nick):
            replies.add(text='** Invalid nick, only letters and numbers are allowed, and nick should be less than 30 characters')
        elif db.get_addr(new_nick):
            replies.add(text='** Nick already taken')
        else:
            db.set_nick(addr, new_nick)
            replies.add(text='** Nick: {}'.format(new_nick))
    else:
        replies.add(text='** Nick: {}'.format(db.get_nick(addr)))


def cmd_join(command: IncomingCommand, replies: Replies) -> None:
    """Join the given IRC channel.
    """
    sender = command.message.get_sender_contact()
    if not command.payload:
        replies.add(text="Wrong syntax")
        return
    if not db.is_whitelisted(command.payload):
        replies.add(text="That channel isn't in the whitelist")
        return

    if not db.channel_exists(command.payload):
        db.add_channel(command.payload)
        irc_bridge.join_channel(command.payload)

    chats = get_cchats(command.payload)
    g = None
    gsize = int(getdefault('max_group_size'))
    for group in chats:
        contacts = group.get_contacts()
        if sender in contacts:
            replies.add(
                text='You are already a member of this group', chat=group)
            return
        if len(contacts) < gsize:
            g = group
            gsize = len(contacts)
    if g is None:
        chat = dbot.create_group(command.payload, [sender])
        db.add_cchat(chat.id, command.payload)
    else:
        add_contact(g, sender)
        chat = dbot.get_chat(sender)

    nick = db.get_nick(sender.addr)
    text = '** You joined {} as {}'.format(command.payload, nick)
    replies.add(text=text, chat=chat)


def cmd_bridge(command: IncomingCommand, replies: Replies) -> None:
    """Bridge current group to the given IRC channel.
    """
    if not command.payload:
        replies.add(text="Wrong syntax")
        return
    if not command.message.chat.is_group():
        replies.add(text="This is not a group")
        return
    addr = command.message.get_sender_contact().addr
    if not dbot.is_admin(addr) and not db.is_whitelisted(command.payload):
        replies.add(text="That channel isn't in the whitelist")
        return
    channel = db.get_channel_by_gid(command.message.chat.id)
    if channel:
        replies.add(
            text="This chat is already bridged to channel: {}".format(channel))
        return

    if not db.channel_exists(command.payload):
        db.add_channel(command.payload)
        irc_bridge.join_channel(command.payload)

    db.add_cchat(command.message.chat.id, command.payload)
    text = '** This chat is now bridged with IRC channel: {}'.format(
        command.payload)
    replies.add(text=text)


def cmd_remove(command: IncomingCommand, replies: Replies) -> None:
    """Remove the member with the given nick from the IRC channel, if no nick is given remove yourself.
    """
    sender = command.message.get_sender_contact()

    text = command.payload
    channel = db.get_channel_by_gid(command.message.chat.id)
    if not channel:
        args = command.payload.split(maxsplit=1)
        channel = args[0]
        text = args[1] if len(args) == 2 else ''
        for g in get_cchats(channel):
            if sender in g.get_contacts():
                break
        else:
            replies.add(text='You are not a member of that channel')
            return

    if not text:
        text = sender.addr
    if '@' not in text:
        t = db.get_addr(text)
        if not t:
            replies.add(text='Unknow user: {}'.format(text))
            return
        text = t

    for g in get_cchats(channel):
        for c in g.get_contacts():
            if c.addr == text:
                g.remove_contact(c)
                if c == sender:
                    return
                s_nick = db.get_nick(sender.addr)
                nick = db.get_nick(c.addr)
                text = '** {} removed by {}'.format(nick, s_nick)
                for g in get_cchats(channel):
                    g.send_text(text)
                text = 'Removed from {} by {}'.format(channel, s_nick)
                replies.add(text=text, chat=dbot.get_chat(c))
                return


# ======== Utilities ===============

def run_irc() -> None:
    while True:
        try:
            irc_bridge.start()
        except Exception as ex:
            dbot.logger.exception('Error on IRC bridge: %s', ex)
            sleep(5)


def getdefault(key: str, value: str = None) -> str:
    val = dbot.get(key, scope=__name__)
    if val is None and value is not None:
        dbot.set(key, value, scope=__name__)
        val = value
    return val


def get_cchats(channel: str) -> Generator:
    for gid in db.get_cchats(channel):
        yield dbot.get_chat(gid)


def get_db(bot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))


def add_contact(chat: Chat, contact: Contact) -> None:
    img_path = chat.get_profile_image()
    if img_path and not os.path.exists(img_path):
        chat.remove_profile_image()
    chat.add_contact(contact)


import asyncio
import os
import re
from threading import Event, Thread
from typing import Generator

from deltachat import Chat, Contact, Message
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

from .database import DBManager
from .xmpp import XMPPBot

__version__ = '1.0.0'
nick_re = re.compile(r'[a-zA-Z0-9]{1,30}$')
dbot: DeltaBot = None
db: DBManager
xmpp_bridge: XMPPBot


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global dbot, db
    dbot = bot
    db = get_db(bot)

    getdefault('nick', 'DC-Bridge')
    getdefault('max_group_size', '20')
    allow_bridging = getdefault('allow_bridging', '1')

    bot.filters.register(name=__name__, func=filter_messages)

    dbot.commands.register('/xmpp_join', cmd_join)
    if allow_bridging:
        dbot.commands.register('/xmpp_bridge', cmd_bridge)
    dbot.commands.register('/xmpp_remove', cmd_remove)
    dbot.commands.register('/xmpp_members', cmd_members)
    dbot.commands.register('/xmpp_nick', cmd_nick)


@deltabot_hookimpl
def deltabot_start(bot: DeltaBot) -> None:
    jid = bot.get('jid', scope=__name__)
    password = bot.get('password', scope=__name__)
    nick = getdefault('nick')

    assert jid is not None, 'Missing "{}/jid" setting'.format(__name__)
    assert password is not None, 'Missing "{}/password" setting'.format(
        __name__)

    bridge_init = Event()
    Thread(target=listen_to_xmpp,
           args=(jid, password, nick, bridge_init), daemon=True).start()
    bridge_init.wait()


@deltabot_hookimpl
def deltabot_member_removed(chat: Chat, contact: Contact) -> None:
    me = dbot.self_contact
    if me == contact or len(chat.get_contacts()) <= 1:
        channel = db.get_channel_by_gid(chat.id)
        if channel:
            db.remove_cchat(chat.id)
            if next(db.get_cchats(channel), None) is None:
                db.remove_channel(channel)
                xmpp_bridge.leave_channel(channel)


# ======== Filters ===============

def filter_messages(message: Message, replies: Replies):
    """Process messages sent to XMPP channels.
    """
    chan = db.get_channel_by_gid(message.chat.id)
    if not chan:
        return

    if not message.text or message.filename:
        replies.add(text='Unsupported message')
        return

    nick = db.get_nick(message.get_sender_contact().addr)
    text = '{}[dc]:\n{}'.format(nick, message.text)

    dbot.logger.debug('Sending message to XMPP: %r', text)
    xmpp_bridge.send_message(chan, text, mtype='groupchat')
    for g in get_cchats(chan):
        if g.id != message.chat.id:
            replies.add(text=text, chat=g)
    return True


# ======== Commands ===============

def cmd_members(command: IncomingCommand, replies: Replies) -> None:
    """Show list of XMPP channel members.
    """
    me = command.bot.self_contact

    chan = db.get_channel_by_gid(command.message.chat.id)
    if not chan:
        replies.add(text='This is not an XMPP channel')
        return

    members = 'Members:\n'
    for g in get_cchats(chan):
        for c in g.get_contacts():
            if c != me:
                members += '• {}[dc]\n'.format(db.get_nick(c.addr))

    for m in xmpp_bridge.get_members(chan):
        if m != xmpp_bridge.nick:
            members += '• {}[xmpp]\n'.format(m)

    replies.add(text=members)


def cmd_nick(command: IncomingCommand, replies: Replies) -> None:
    """Set your XMPP nick or display your current nick if no new nick is given.
    """
    addr = command.message.get_sender_contact().addr
    new_nick = ' '.join(command.payload.split())
    if new_nick:
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
    """Join the given XMPP channel.
    """
    sender = command.message.get_sender_contact()
    if not command.payload:
        replies.add(text="Wrong syntax")
        return
    if not db.is_whitelisted(command.payload):
        replies.add(text="That channel isn't in the whitelist")
        return

    if not db.channel_exists(command.payload):
        xmpp_bridge.join_channel(command.payload)
        db.add_channel(command.payload)

    chats = get_cchats(command.payload)
    g = None
    gsize = int(getdefault('max_group_size'))
    for group in chats:
        contacts = group.get_contacts()
        if sender in contacts:
            replies.add(text='You are already a member of this channel',
                        chat=group)
            return
        if len(contacts) < gsize:
            g = group
            gsize = len(contacts)
    if g is None:
        g = dbot.create_group(command.payload, [sender])
        db.add_cchat(g.id, command.payload)
    else:
        add_contact(g, sender)

    nick = db.get_nick(sender.addr)
    replies.add(text='** You joined {} as {}'.format(
        command.payload, nick))


def cmd_bridge(command: IncomingCommand, replies: Replies) -> None:
    """Bridge current group to the given XMPP channel.
    """
    if not command.payload:
        replies.add(text="Wrong syntax")
        return
    if not db.is_whitelisted(command.payload):
        replies.add(text="That channel isn't in the whitelist")
        return
    channel = db.get_channel_by_gid(command.message.chat.id)
    if channel:
        replies.add(text="This chat is already bridged with channel: {}".format(channel))
        return

    if not db.channel_exists(command.payload):
        db.add_channel(command.payload)
        xmpp_bridge.join_channel(command.payload)

    db.add_cchat(command.message.chat.id, command.payload)
    text = '** This chat is now bridged with XMPP channel: {}'.format(
        command.payload)
    replies.add(text=text)


def cmd_remove(command: IncomingCommand, replies: Replies) -> None:
    """Remove the DC member with the given nick from the XMPP channel, if no nick is given remove yourself.
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
                    return None
                s_nick = db.get_nick(sender.addr)
                nick = db.get_nick(c.addr)
                text = '** {} removed by {}'.format(nick, s_nick)
                for g in get_cchats(channel):
                    replies.add(text=text, chat=g)
                text = 'Removed from {} by {}'.format(channel, s_nick)
                dbot.get_chat(c).send_text(text)
                return


# ======== Utilities ===============

def listen_to_xmpp(jid: str, password: str, nick: str,
                   bridge_initialized: Event) -> None:
    global xmpp_bridge
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    xmpp_bridge = XMPPBot(jid, password, nick, db, dbot)
    bridge_initialized.set()
    while True:
        try:
            dbot.logger.info('Starting XMPP bridge')
            xmpp_bridge.connect()
            xmpp_bridge.process(forever=False)
        except Exception as ex:
            dbot.logger.exception(ex)


def get_cchats(channel: str) -> Generator:
    for gid in db.get_cchats(channel):
        yield dbot.get_chat(gid)


def getdefault(key: str, value: str = None) -> str:
    val = dbot.get(key, scope=__name__)
    if val is None and value is not None:
        dbot.set(key, value, scope=__name__)
        val = value
    return val


def get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))


def add_contact(chat: Chat, contact: Contact) -> None:
    img_path = chat.get_profile_image()
    if img_path and not os.path.exists(img_path):
        chat.remove_profile_image()
    chat.add_contact(contact)

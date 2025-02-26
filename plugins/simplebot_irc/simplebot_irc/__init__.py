
import os
import re
from threading import Thread
from time import sleep

import simplebot
from deltachat import Chat, Contact, Message
from simplebot import DeltaBot
from simplebot.bot import Replies

from .database import DBManager
from .irc import IRCBot

__version__ = '1.0.0'
nick_re = re.compile(r'[-_a-zA-Z0-9]{1,30}$')
db: DBManager
irc_bridge: IRCBot


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    _getdefault(bot, 'nick', 'SimpleBot')
    _getdefault(bot, 'host', 'irc.freenode.net')
    _getdefault(bot, 'port', '6667')


@simplebot.hookimpl
def deltabot_start(bot: DeltaBot) -> None:
    global db, irc_bridge
    db = _get_db(bot)
    nick = _getdefault(bot, 'nick')
    host = _getdefault(bot, 'host')
    port = int(_getdefault(bot, 'port'))
    irc_bridge = IRCBot(host, port, nick, db, bot)
    Thread(target=_run_irc, args=(bot,), daemon=True).start()


@simplebot.hookimpl
def deltabot_member_added(chat: Chat, contact: Contact) -> None:
    channel = db.get_channel_by_gid(chat.id)
    if channel:
        irc_bridge.preactor.join_channel(contact.addr, channel)


@simplebot.hookimpl
def deltabot_member_removed(bot: DeltaBot, chat: Chat, contact: Contact) -> None:
    channel = db.get_channel_by_gid(chat.id)
    if channel:
        me = bot.self_contact
        if me == contact or len(chat.get_contacts()) <= 1:
            db.remove_channel(channel)
            irc_bridge.leave_channel(channel)
        else:
            irc_bridge.preactor.leave_channel(contact.addr, channel)


@simplebot.filter(name=__name__)
def filter_messages(message: Message, replies: Replies) -> None:
    """Process messages sent to an IRC channel.
    """
    chan = db.get_channel_by_gid(message.chat.id)
    if not chan:
        return

    if message.quoted_text:
        text = '<{}> '.format(' '.join(message.quoted_text.split('\n')))
    else:
        text = ''
    if message.filename:
        text += '[File] '
    text += message.text
    if not text:
        return

    addr = message.get_sender_contact().addr
    irc_bridge.preactor.send_message(
        addr, chan, ' '.join(text.split('\n')))


@simplebot.command
def me(payload: str, message: Message, replies: Replies) -> None:
    """Send a message to IRC using the /me IRC command.
    """
    chan = db.get_channel_by_gid(message.chat.id)
    if not chan:
        return

    addr = message.get_sender_contact().addr
    text = ' '.join(payload.split('\n'))
    irc_bridge.preactor.send_action(addr, chan, text)


@simplebot.command
def topic(message: Message, replies: Replies) -> None:
    """Show IRC channel topic.
    """
    chan = db.get_channel_by_gid(message.chat.id)
    if not chan:
        replies.add(text='This is not an IRC channel')
    else:
        replies.add(text='Topic:\n{}'.format(irc_bridge.get_topic(chan)))


@simplebot.command
def names(message: Message, replies: Replies) -> None:
    """Show list of IRC channel members.
    """
    chan = db.get_channel_by_gid(message.chat.id)
    if not chan:
        replies.add(text='This is not an IRC channel')
        return

    members = 'Members:\n'
    for m in sorted(irc_bridge.get_members(chan)):
        members += '• {}\n'.format(m)

    replies.add(text=members)


@simplebot.command
def nick(args: list, message: Message, replies: Replies) -> None:
    """Set your IRC nick or display your current nick if no new nick is given.
    """
    addr = message.get_sender_contact().addr
    if args:
        new_nick = '_'.join(args)
        if not nick_re.match(new_nick):
            replies.add(
                text='** Invalid nick, only letters and numbers are'
                ' allowed, and nick should be less than 30 characters')
        elif db.get_addr(new_nick):
            replies.add(text='** Nick already taken')
        else:
            db.set_nick(addr, new_nick)
            irc_bridge.preactor.puppets[addr].nick(new_nick + '[dc]')
            replies.add(text='** Nick: {}'.format(new_nick))
    else:
        replies.add(text='** Nick: {}'.format(db.get_nick(addr)))


@simplebot.command
def join(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
    """Join the given IRC channel."""
    sender = message.get_sender_contact()
    if not payload:
        replies.add(text="Wrong syntax")
        return
    if not bot.is_admin(sender.addr) and \
       not db.is_whitelisted(payload):
        replies.add(text="That channel isn't in the whitelist")
        return

    g = bot.get_chat(db.get_chat(payload))
    if g and sender in g.get_contacts():
        replies.add(
            text='You are already a member of this group', chat=g)
        return
    if g is None:
        chat = bot.create_group(payload, [sender])
        db.add_channel(payload, chat.id)
        irc_bridge.join_channel(payload)
        irc_bridge.preactor.join_channel(sender.addr, payload)
    else:
        _add_contact(g, sender)
        chat = bot.get_chat(sender)

    nick = db.get_nick(sender.addr)
    text = '** You joined {} as {}'.format(payload, nick)
    replies.add(text=text, chat=chat)


@simplebot.command
def remove(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
    """Remove the member with the given nick from the IRC channel, if no nick is given remove yourself.
    """
    sender = message.get_sender_contact()

    channel = db.get_channel_by_gid(message.chat.id)
    if not channel:
        args = payload.split(maxsplit=1)
        channel = args[0]
        payload = args[1] if len(args) == 2 else ''
        g = bot.get_chat(db.get_chat(channel))
        if not g or sender not in g.get_contacts():
            replies.add(text='You are not a member of that channel')
            return

    if not payload:
        payload = sender.addr
    if '@' not in payload:
        t = db.get_addr(payload)
        if not t:
            replies.add(text='Unknow user: {}'.format(payload))
            return
        payload = t

    g = bot.get_chat(db.get_chat(channel))
    for c in g.get_contacts():
        if c.addr == payload:
            g.remove_contact(c)
            if c == sender:
                return
            s_nick = db.get_nick(sender.addr)
            nick = db.get_nick(c.addr)
            text = '** {} removed by {}'.format(nick, s_nick)
            bot.get_chat(db.get_chat(channel)).send_text(text)
            text = 'Removed from {} by {}'.format(channel, s_nick)
            replies.add(text=text, chat=bot.get_chat(c))
            return


def _run_irc(bot: DeltaBot) -> None:
    while True:
        try:
            irc_bridge.start()
        except Exception as ex:
            bot.logger.exception('Error on IRC bridge: %s', ex)
            sleep(5)


def _getdefault(bot: DeltaBot, key: str, value: str = None) -> str:
    val = bot.get(key, scope=__name__)
    if val is None and value is not None:
        bot.set(key, value, scope=__name__)
        val = value
    return val


def _get_db(bot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))


def _add_contact(chat: Chat, contact: Contact) -> None:
    img_path = chat.get_profile_image()
    if img_path and not os.path.exists(img_path):
        chat.remove_profile_image()
    chat.add_contact(contact)

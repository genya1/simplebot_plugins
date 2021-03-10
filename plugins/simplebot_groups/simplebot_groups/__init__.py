
import io
import os
import queue
import time
from threading import Thread
from typing import Generator

import qrcode
from deltachat import Chat, Contact, Message
from deltachat.capi import lib, ffi
from deltachat.cutil import as_dc_charpointer, from_dc_charpointer
from jinja2 import Template
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

from .db import DBManager

__version__ = '1.0.0'
dbot: DeltaBot
db: DBManager
channel_posts: queue.Queue = queue.Queue()


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global dbot
    dbot = bot

    getdefault('max_group_size', '999999')
    getdefault('max_topic_size', '500')
    getdefault('allow_groups', '1')
    getdefault('max_file_size', '504800')
    allow_channels = getdefault('allow_channels', '1')

    bot.filters.register(name=__name__, func=filter_messages)

    bot.commands.register('/group_info', cmd_info)
    bot.commands.register('/group_list', cmd_list)
    bot.commands.register('/group_me', cmd_me)
    bot.commands.register('/group_join', cmd_join)
    bot.commands.register('/group_topic', cmd_topic)
    bot.commands.register('/group_remove', cmd_remove)
    bot.commands.register(
        '/group_chan', cmd_chan, admin=(allow_channels != '1'))
    bot.commands.register('/group_adminchan', cmd_adminchan, admin=True)


@deltabot_hookimpl
def deltabot_start(bot: DeltaBot) -> None:
    global db
    db = get_db(bot)

    Thread(target=_process_channels, daemon=True).start()


@deltabot_hookimpl
def deltabot_member_added(chat: Chat, contact: Contact,
                          actor: Contact) -> None:
    if contact == dbot.self_contact and not db.get_channel(chat.id):
        add_group(chat.id, as_admin=dbot.is_admin(actor.addr))


@deltabot_hookimpl
def deltabot_member_removed(chat: Chat, contact: Contact) -> None:
    me = dbot.self_contact
    if me == contact or len(chat.get_contacts()) <= 1:
        g = db.get_group(chat.id)
        if g:
            db.remove_group(chat.id)
            return

        ch = db.get_channel(chat.id)
        if ch:
            if ch['admin'] == chat.id:
                for cchat in get_cchats(ch['id']):
                    try:
                        cchat.remove_contact(me)
                    except ValueError:
                        pass
                db.remove_channel(ch['id'])
            else:
                db.remove_cchat(chat.id)


@deltabot_hookimpl
def deltabot_ban(contact: Contact) -> None:
    me = dbot.self_contact
    for g in db.get_groups():
        chat = dbot.get_chat(g['id'])
        if chat:
            contacts = chat.get_contacts()
            if contact in contacts and me in contacts:
                chat.remove_contact(contact)

    for ch in db.get_channels():
        for chat in get_cchats(ch['id']):
            contacts = chat.get_contacts()
            if contact in contacts and me in contacts:
                chat.remove_contact(contact)


# ======== Filters ===============

def filter_messages(message: Message, replies: Replies) -> None:
    """Process messages sent to channels.
    """
    ch = db.get_channel(message.chat.id)
    if ch and ch['admin'] == message.chat.id:
        max_size = int(getdefault('max_file_size'))
        if message.filename and os.path.getsize(message.filename) > max_size:
            replies.add(
                text='❌ File too big, up to {} Bytes are allowed'.format(
                    max_size))
            return

        db.set_channel_last_pub(ch['id'], time.time())
        channel_posts.put((message, get_cchats(ch['id'])))
    elif ch:
        replies.add(text='❌ Only channel operators can do that.')


# ======== Commands ===============

def cmd_info(command: IncomingCommand, replies: Replies) -> None:
    """Show the group/channel info.
    """
    if not command.message.chat.is_group():
        replies.add(text='❌ This is not a group')
        return

    text = '{0}\n👤 {1}\n{2}\n\n'
    text += '⬅️ /group_remove_{3}{4}\n➡️ /group_join_{3}{4}'

    ch = db.get_channel(command.message.chat.id)
    if ch:
        count = sum(map(
            lambda g: len(g.get_contacts()) - 1, get_cchats(ch['id'])))
        replies.add(text=text.format(
            ch['name'], count, ch['topic'] or '-', 'c', ch['id']))
        return

    g = db.get_group(command.message.chat.id)
    if not g:
        addr = command.message.get_sender_contact().addr
        add_group(command.message.chat.id, as_admin=dbot.is_admin(addr))
        g = db.get_group(command.message.chat.id)
        assert g is not None

    chat = dbot.get_chat(g['id'])
    img = qrcode.make(chat.get_join_qr())
    buffer = io.BytesIO()
    img.save(buffer, format='jpeg')
    buffer.seek(0)
    count = len(dbot.get_chat(g['id']).get_contacts())
    replies.add(text=text.format(
        chat.get_name(), count, g['topic'] or '-', 'g', g['id']),
                filename='img.jpg', bytefile=buffer)


def cmd_list(command: IncomingCommand, replies: Replies) -> None:
    """Show the list of public groups and channels.
    """
    def get_list(chats):
        return Template('''
<style>
.w3-card-2{box-shadow:0 2px 4px 0 rgba(0,0,0,0.16),0 2px 10px 0 rgba(0,0,0,0.12) !important; margin-bottom: 15px;}
.w3-btn{border:none;display:inline-block;outline:0;padding:6px 16px;vertical-align:middle;overflow:hidden;text-decoration:none !important;color:#fff;background-color:#5a6f78;text-align:center;cursor:pointer;white-space:nowrap}
.w3-container:after,.w3-container:before{content:"";display:table;clear:both}
.w3-container{padding:0.01em 16px}
.w3-right{float:right !important}
.w3-large{font-size:18px !important}
.w3-delta,.w3-hover-delta:hover{color:#fff !important;background-color:#5a6f78 !important}
</style>
{% for name, topic, gid, last_pub, bot_addr, count in chats %}
<div class="w3-card-2">
<header class="w3-container w3-delta">
<h2>{{ name }}</h2>
</header>
<div class="w3-container">
<p>👤 {{ count }}</p>
{% if last_pub %}
📝 {{ last_pub }}
{% endif %}
<p>{{ topic }}</p>
</div>
<a class="w3-btn w3-large" href="mailto:{{ bot_addr }}?body=/group_remove_{{ gid }}">« Leave</a>
<a class="w3-btn w3-large w3-right" href="mailto:{{ bot_addr }}?body=/group_join_{{ gid }}">Join »</a>
</div>
{% endfor %}
''').render(chats=chats)

    groups = []
    for g in db.get_groups():
        chat = command.bot.get_chat(g['id'])
        if not chat:
            db.remove_group(g['id'])
            continue
        groups.append((chat.get_name(),
                       g['topic'] or '-',
                       'g{}'.format(chat.id),
                       None,
                       dbot.self_contact.addr,
                       len(chat.get_contacts())))
    total_groups = len(groups)
    if groups:
        groups.sort(key=lambda g: g[-1], reverse=True)
        text = '⬇️ Groups ({}) ⬇️'.format(total_groups)
        replies.add(text=text, html=get_list(groups))

    channels = []
    for ch in db.get_channels():
        count = sum(
            map(lambda g: len(g.get_contacts())-1, get_cchats(ch['id'])))
        if ch['last_pub']:
            last_pub = time.strftime(
                '%d-%m-%Y', time.gmtime(ch['last_pub']))
        else:
            last_pub = '-'
        channels.append((ch['name'],
                         ch['topic'] or '-',
                         'c{}'.format(ch['id']),
                         last_pub,
                         dbot.self_contact.addr,
                         count))
    total_channels = len(channels)
    if channels:
        channels.sort(key=lambda g: g[-1], reverse=True)
        text = '⬇️ Channels ({}) ⬇️'.format(total_channels)
        replies.add(text=text, html=get_list(channels))

    if 0 == total_groups == total_channels:
        replies.add(text='❌ Empty List')


def cmd_me(command: IncomingCommand, replies: Replies) -> None:
    """Show the list of groups and channels you are in.
    """
    sender = command.message.get_sender_contact()
    groups = []
    for group in db.get_groups():
        g = command.bot.get_chat(group['id'])
        contacts = g.get_contacts()
        if command.bot.self_contact not in contacts:
            db.remove_group(group['id'])
            continue
        if sender in contacts:
            groups.append((g.get_name(), 'g{}'.format(g.id)))

    for ch in db.get_channels():
        for c in get_cchats(ch['id']):
            if sender in c.get_contacts():
                groups.append(
                    (ch['name'], 'c{}'.format(ch['id'])))
                break

    text = '{0}:\n⬅️ /group_remove_{1}\n\n'
    replies.add(text=''.join(
        text.format(*g) for g in groups) or 'Empty list')


def cmd_join(command: IncomingCommand, replies: Replies) -> None:
    """Join the given group/channel.
    """
    sender = command.message.get_sender_contact()
    is_admin = command.bot.is_admin(sender.addr)
    text = '{}\n\n{}\n\n⬅️ /group_remove_{}'
    if command.payload.startswith('g'):
        gid = int(command.args[0][1:])
        gr = db.get_group(gid)
        if gr:
            g = command.bot.get_chat(gr['id'])
            contacts = g.get_contacts()
            if sender in contacts:
                replies.add(
                    text='❌ {}, you are already a member of this group'.format(sender.addr), chat=g)
            elif len(contacts) < int(getdefault('max_group_size')) or is_admin:
                add_contact(g, sender)
                replies.add(chat=dbot.get_chat(sender), text=text.format(
                    g.get_name(), gr['topic'] or '-', command.payload))
            else:
                replies.add(text='❌ Group is full')
            return
    elif command.payload.startswith('c'):
        gid = int(command.args[0][1:])
        ch = db.get_channel_by_id(gid)
        if ch:
            g = command.bot.get_chat(ch['admin'])
            if sender in g.get_contacts():
                replies.add(
                    text='❌ {}, you are already a member of this channel'.format(sender.addr),
                    chat=g)
                return
            for g in get_cchats(ch['id']):
                if sender in g.get_contacts():
                    replies.add(
                        text='❌ {}, you are already a member of this channel'.format(sender.addr),
                        chat=g)
                    return
            g = command.bot.create_group(ch['name'], [sender])
            db.add_cchat(g.id, ch['id'])
            replies.add(text=text.format(
                ch['name'], ch['topic'] or '-', command.payload), chat=g)
            return

    replies.add(text='❌ Invalid ID')


def cmd_adminchan(command: IncomingCommand, replies: Replies) -> None:
    """Join the admin group of the given channel.
    """
    sender = command.message.get_sender_contact()
    text = '{}\n\n{}\n\n⬅️ /group_remove_{}'
    gid = int(command.args[0])
    ch = db.get_channel_by_id(gid)
    if ch:
        add_contact(dbot.get_chat(ch['admin']), sender)
        text = text.format(ch['name'], ch['topic'] or '-', command.payload)
        replies.add(text=text, chat=dbot.get_chat(sender))
        return

    replies.add(text='❌ Invalid ID')


def cmd_topic(command: IncomingCommand, replies: Replies) -> None:
    """Show or change group/channel topic.
    """
    if not command.message.chat.is_group():
        replies.add(text='❌ This is not a group')
        return

    if command.payload:
        new_topic = ' '.join(command.payload.split())
        max_size = int(getdefault('max_topic_size'))
        if len(new_topic) > max_size:
            new_topic = new_topic[:max_size]+'...'

        text = '** {} changed topic to:\n{}'

        ch = db.get_channel(command.message.chat.id)
        if ch and ch['admin'] == command.message.chat.id:
            name = get_name(command.message.get_sender_contact())
            text = text.format(name, new_topic)
            db.set_channel_topic(ch['id'], new_topic)
            for chat in get_cchats(ch['id']):
                replies.add(text=text, chat=chat)
            replies.add(text=text)
            return
        if ch:
            replies.add(text='❌ Only channel operators can do that.')
            return

        addr = command.message.get_sender_contact().addr
        g = db.get_group(command.message.chat.id)
        if not g:
            add_group(command.message.chat.id, as_admin=dbot.is_admin(addr))
            g = db.get_group(command.message.chat.id)
            assert g is not None
        db.upsert_group(g['id'], new_topic)
        replies.add(text=text.format(addr, new_topic))
        return

    g = db.get_channel(command.message.chat.id) or db.get_group(
        command.message.chat.id)
    if not g:
        addr = command.message.get_sender_contact().addr
        add_group(command.message.chat.id, as_admin=dbot.is_admin(addr))
        g = db.get_group(command.message.chat.id)
        assert g is not None
    replies.add(text=g['topic'] or '-', quote=command.message)


def cmd_remove(command: IncomingCommand, replies: Replies) -> None:
    """Remove the member with the given address from the group with the given id. If no address is provided, removes yourself from group/channel.
    """
    sender = command.message.get_sender_contact()

    if not command.payload:
        replies.add(text='❌ Invalid ID')
        return

    type_, gid = command.args[0][0], int(command.args[0][1:])
    if type_ == 'c':
        ch = db.get_channel_by_id(gid)
        if not ch:
            replies.add(text='❌ Invalid ID')
            return
        for g in get_cchats(ch['id'], include_admin=True):
            if sender in g.get_contacts():
                g.remove_contact(sender)
                return
        replies.add(text='❌ You are not a member of that channel')
    elif type_ == 'g':
        gr = db.get_group(gid)
        if not gr:
            replies.add(text='❌ Invalid ID')
            return
        g = command.bot.get_chat(gr['id'])
        if sender not in g.get_contacts():
            replies.add(text='❌ You are not a member of that group')
            return
        addr = command.args[-1] if '@' in command.args[-1] else ''
        if addr:
            if addr == command.bot.self_contact.addr:
                replies.add(
                    text='❌ You can not remove me from the group')
                return
            contact = command.bot.get_contact(addr)
            g.remove_contact(contact)
            if not contact.is_blocked():
                chat = command.bot.get_chat(contact)
                replies.add(text='❌ Removed from {} by {}'.format(
                    g.get_name(), sender.addr), chat=chat)
            replies.add(text='✔️{} removed'.format(addr))
        else:
            g.remove_contact(sender)


def cmd_chan(command: IncomingCommand, replies: Replies) -> None:
    """Create a new channel with the given name.
    """
    if not command.payload:
        replies.add(text='❌ You must provide a channel name')
        return
    if db.get_channel_by_name(command.payload):
        replies.add(text='❌ There is already a channel with that name')
        return
    g = command.bot.create_group(
        command.payload, [command.message.get_sender_contact()])
    db.add_channel(command.payload, None, g.id)
    replies.add(text='✔️Channel created', chat=g)


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


def get_cchats(cgid: int, include_admin: bool = False) -> Generator:
    if include_admin:
        ch = db.get_channel_by_id(cgid)
        if ch:
            g = dbot.get_chat(ch['admin'])
            if g:
                yield g
            else:
                db.remove_channel(cgid)
    for gid in db.get_cchats(cgid):
        g = dbot.get_chat(gid)
        if g and dbot.self_contact in g.get_contacts():
            yield g
        else:
            db.remove_cchat(gid)


def add_group(gid: int, as_admin=False) -> None:
    if as_admin or getdefault('allow_groups') == '1':
        db.upsert_group(gid, None)
    else:
        dbot.get_chat(gid).remove_contact(dbot.self_contact)


def add_contact(chat: Chat, contact: Contact) -> None:
    img_path = chat.get_profile_image()
    if img_path and not os.path.exists(img_path):
        chat.remove_profile_image()
    chat.add_contact(contact)


def get_name(c: Contact) -> str:
    if c.name == c.addr:
        return c.addr
    return '{}({})'.format(c.name, c.addr)


def _process_channels() -> None:
    while True:
        _send_diffusion(*channel_posts.get())


def _send_diffusion(message: Message, chats: list) -> None:
    log = "diffusion: id={} chat={} sent with text: {!r}"
    text = message.text
    if lib.dc_msg_has_html(message._dc_msg):
        html = from_dc_charpointer(
            lib.dc_get_msg_html(dbot.account._dc_context, message.id))
    else:
        html = None
    filename = message.filename
    quote = message.quote
    sender = get_name(message.get_sender_contact())
    for chat in chats:
        msg = Message(dbot.account, ffi.gc(
            lib.dc_msg_new(dbot.account._dc_context, message._view_type),
            lib.dc_msg_unref
        ))
        if text:
            msg.set_text(text)
        if html:
            lib.dc_msg_set_html(msg._dc_msg, as_dc_charpointer(html))
        if filename:
            msg.set_file(filename)
        if quote:
            msg.quote = quote
        lib.dc_msg_set_override_sender_name(
            msg._dc_msg, as_dc_charpointer(sender))
        try:
            msg = chat.send_msg(msg)
            dbot.logger.info(log.format(msg.id, msg.chat, msg.text[:50]))
        except ValueError as err:
            dbot.logger.exception(err)

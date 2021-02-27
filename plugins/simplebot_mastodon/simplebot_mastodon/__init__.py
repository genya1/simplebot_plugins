
import os
import tempfile
import time
from enum import Enum
from threading import Thread
from typing import Generator

import mastodon
import requests
from bs4 import BeautifulSoup
from deltachat import Chat, Contact, Message
from html2text import html2text
from pydub import AudioSegment
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

from .db import DBManager


class Visibility(str, Enum):
    DIRECT = 'direct'  # visible only to mentioned users
    PRIVATE = 'private'  # visible only to followers
    UNLISTED = 'unlisted'  # public but not appear on the public timeline
    PUBLIC = 'public'  # post will be public


__version__ = '1.0.0'
MASTODON_LOGO = os.path.join(
    os.path.dirname(__file__), 'mastodon-logo.png')
v2emoji = {Visibility.DIRECT: '✉', Visibility.PRIVATE: '🔒',
           Visibility.UNLISTED: '🔓', Visibility.PUBLIC: '🌎'}
TOOT_SEP = '\n\n―――――――――――――――\n\n'
STRFORMAT = '%Y-%m-%d %H:%M'
dbot: DeltaBot
db: DBManager


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global dbot
    dbot = bot

    getdefault('delay', '30')
    getdefault('max_users', '-1')
    getdefault('max_users_instance', '-1')

    bot.filters.register(name=__name__, func=filter_messages)

    dbot.commands.register('/m_login', cmd_login)
    dbot.commands.register('/m_logout', cmd_logout)
    dbot.commands.register('/m_accounts', cmd_accounts)
    dbot.commands.register('/m_bio', cmd_bio)
    dbot.commands.register('/m_avatar', cmd_avatar)
    dbot.commands.register('/m_dm', cmd_dm)
    dbot.commands.register('/m_reply', cmd_reply)
    dbot.commands.register('/m_star', cmd_star)
    dbot.commands.register('/m_boost', cmd_boost)
    dbot.commands.register('/m_cntx', cmd_cntx)
    dbot.commands.register('/m_follow', cmd_follow)
    dbot.commands.register('/m_unfollow', cmd_unfollow)
    dbot.commands.register('/m_mute', cmd_mute)
    dbot.commands.register('/m_unmute', cmd_unmute)
    dbot.commands.register('/m_block', cmd_block)
    dbot.commands.register('/m_unblock', cmd_unblock)
    dbot.commands.register('/m_profile', cmd_profile)
    dbot.commands.register('/m_local', cmd_local)
    dbot.commands.register('/m_public', cmd_public)
    dbot.commands.register('/m_tag', cmd_tag)
    dbot.commands.register('/m_search', cmd_search)


@deltabot_hookimpl
def deltabot_start(bot: DeltaBot) -> None:
    global db
    db = get_db(bot)

    Thread(target=listen_to_mastodon, daemon=True).start()


@deltabot_hookimpl
def deltabot_member_removed(chat: Chat, contact: Contact,
                            replies: Replies) -> None:
    me = dbot.self_contact
    if me == contact or len(chat.get_contacts()) <= 1:
        acc = db.get_account(chat.id)
        if acc:
            if chat.id in (acc['home'], acc['notif']):
                logout(acc, replies)
            else:
                db.remove_pchat(chat.id)


# ======== Filters ===============

def filter_messages(message: Message, replies: Replies):
    """Process messages sent to a Mastodon chat.
    """
    acc = db.get_account_by_home(message.chat.id)
    if acc:
        toot(get_session(acc), message.text, message.filename)
        return True

    pchat = db.get_pchat(message.chat.id)
    if pchat:
        acc = db.get_account_by_id(pchat['account'])
        text = '@{} {}'.format(pchat['contact'], message.text)
        toot(get_session(acc), text, message.filename,
             visibility=Visibility.DIRECT)
        return True


# ======== Commands ===============

def cmd_login(command: IncomingCommand, replies: Replies) -> None:
    """Login on Mastodon. Example: /m_login mastodon.social me@example.com myPassw0rd
    """
    api_url, email, passwd = command.payload.split(maxsplit=2)
    api_url = normalize_url(api_url)

    max = int(getdefault('max_users'))
    if max >= 0 and len(db.get_accounts()) >= max:
        replies.add(text='No more accounts allowed.')
        return
    max = int(getdefault('max_users_instance'))
    if max >= 0 and len(db.get_accounts(url=api_url)) >= max:
        replies.add(
            text='No more accounts allowed from {}'.format(api_url))
        return

    m = mastodon.Mastodon(api_base_url=api_url, ratelimit_method='throw')
    m.log_in(email, passwd)
    uname = m.me().acct.lower()

    old_user = db.get_account_by_user(uname, api_url)
    if old_user:
        replies.add(text='Account already in use')
        return

    n = m.notifications(limit=1)
    last_notif = n[0].id if n else None
    n = m.timeline_home(limit=1)
    last_home = n[0].id if n else None

    addr = command.message.get_sender_contact().addr
    url = rmprefix(api_url, 'https://')
    hgroup = command.bot.create_group(
        'Home ({}@{})'.format(uname, url), [addr])
    ngroup = command.bot.create_group(
        'Notifications ({}@{})'.format(uname, url), [addr])

    db.add_account(email, passwd, api_url, uname, addr, hgroup.id,
                   ngroup.id, last_home, last_notif)

    hgroup.set_profile_image(MASTODON_LOGO)
    ngroup.set_profile_image(MASTODON_LOGO)
    text = 'Messages sent here will be tooted to {}'.format(api_url)
    replies.add(text=text, chat=hgroup)
    text = 'Here you will receive notifications from {}'.format(api_url)
    replies.add(text=text, chat=ngroup)


def cmd_logout(command: IncomingCommand, replies: Replies) -> None:
    """Logout from Mastodon.
    """
    if command.payload:
        acc = db.get_account_by_id(int(command.payload))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]

    if acc:
        logout(acc, replies)
    else:
        replies.add(text='Unknow account')


def cmd_accounts(command: IncomingCommand, replies: Replies) -> None:
    """Show your Mastodon accounts.
    """
    accs = db.get_accounts(addr=command.message.get_sender_contact().addr)
    if not accs:
        replies.add(text='Empty list')
        return
    text = ''
    for acc in accs:
        url = rmprefix(acc['api_url'], 'https://')
        text += '{}@{}: /m_logout_{}\n\n'.format(
            acc['accname'], url, acc['id'])
    replies.add(text=text)


def cmd_bio(command: IncomingCommand, replies: Replies) -> None:
    """Update your Mastodon biography.
    """
    acc = db.get_account(command.message.chat.id)
    if not acc:
        accs = db.get_accounts(
            addr=command.message.get_sender_contact().addr)
        if len(accs) == 1:
            acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return
    if not command.payload:
        replies.add(text='You must provide a biography')
        return

    m = get_session(acc)
    try:
        m.account_update_credentials(note=command.payload)
        replies.add(text='Biography updated')
    except mastodon.MastodonAPIError as err:
        replies.add(text=err.args[-1])


def cmd_avatar(command: IncomingCommand, replies: Replies) -> None:
    """Update your Mastodon avatar.
    """
    acc = db.get_account(command.message.chat.id)
    if not acc:
        accs = db.get_accounts(
            addr=command.message.get_sender_contact().addr)
        if len(accs) == 1:
            acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return
    if not command.message.filename:
        replies.add(
            text='You must send an avatar attached to your messagee')
        return

    m = get_session(acc)
    try:
        m.account_update_credentials(avatar=command.message.filename)
        replies.add(text='Avatar updated')
    except mastodon.MastodonAPIError:
        replies.add(text='Failed to update avatar')


def cmd_dm(command: IncomingCommand, replies: Replies) -> None:
    """Start a private chat with the given Mastodon user.
    """
    if len(command.args) == 2:
        acc = db.get_account_by_id(int(command.args[0]))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
        command.payload = command.args[1]
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return
    command.payload = command.payload.lstrip('@').lower()
    if not command.payload:
        replies.add(text='Wrong Syntax')
        return

    user = get_user(get_session(acc), command.payload)
    if not user:
        replies.add(text='Account not found: ' + command.payload)
        return

    pv = db.get_pchat_by_contact(acc['id'], user.acct)
    if pv:
        chat = command.bot.get_chat(pv['id'])
        replies.add(
            text='Chat already exists, send messages here', chat=chat)
    else:
        title = '🇲 {} ({})'.format(
            user.acct, rmprefix(acc['api_url'], 'https://'))
        g = command.bot.create_group(title, [acc['addr']])
        db.add_pchat(g.id, command.payload, acc['id'])

        r = requests.get(user.avatar_static)
        with tempfile.NamedTemporaryFile(suffix='.jpg') as fp:
            fp.write(r.content)
            try:
                g.set_profile_image(fp.name)
            except ValueError as err:
                command.bot.logger.exception(err)
        replies.add(
            text='Private chat with: ' + user.acct, chat=g)


def cmd_reply(command: IncomingCommand, replies: Replies) -> None:
    """Reply to a toot with the given id.
    """
    acc_id, toot_id, text = command.payload.split(maxsplit=2)
    if not text and not command.message.filename:
        replies.add(text='Wrong Syntax')
        return

    addr = command.message.get_sender_contact().addr

    acc = db.get_account_by_id(acc_id)
    if not acc or acc['addr'] != addr:
        replies.add(text='Invalid toot or account id')
        return

    toot(get_session(acc), text=text, filename=command.message.filename,
         in_reply_to=toot_id)


def cmd_star(command: IncomingCommand, replies: Replies) -> None:
    """Mark as favourite the toot with the given id.
    """
    acc_id, toot_id = command.args
    addr = command.message.get_sender_contact().addr

    acc = db.get_account_by_id(acc_id)
    if not acc or acc['addr'] != addr:
        replies.add(text='Invalid toot or account id')
        return

    m = get_session(acc)
    m.status_favourite(toot_id)


def cmd_boost(command: IncomingCommand, replies: Replies) -> None:
    """Boost the toot with the given id.
    """
    acc_id, toot_id = command.args
    addr = command.message.get_sender_contact().addr

    acc = db.get_account_by_id(acc_id)
    if not acc or acc['addr'] != addr:
        replies.add(text='Invalid toot or account id')
        return

    m = get_session(acc)
    m.status_reblog(toot_id)


def cmd_cntx(command: IncomingCommand, replies: Replies) -> None:
    """Get the context of the toot with the given id.
    """
    acc_id, toot_id = command.args
    addr = command.message.get_sender_contact().addr

    acc = db.get_account_by_id(acc_id)
    if not acc or acc['addr'] != addr:
        replies.add(text='Invalid toot or account id')
        return

    m = get_session(acc)
    toots = m.status_context(toot_id)['ancestors']
    if toots:
        replies.add(text=TOOT_SEP.join(
            toots2text(toots[-3:], acc['id'])))
    else:
        replies.add(text='Nothing found')


def cmd_follow(command: IncomingCommand, replies: Replies) -> None:
    """Follow the user with the given id.
    """
    if len(command.args) == 2:
        acc = db.get_account_by_id(int(command.args[0]))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
        command.payload = command.args[1]
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return
    if not command.payload:
        replies.add(text='Wrong Syntax')
        return

    m = get_session(acc)
    if command.payload.isdigit():
        user_id = command.payload
    else:
        user_id = get_user(m, command.payload)
        if user_id is None:
            replies.add(text='Invalid user')
            return
    m.account_follow(user_id)
    replies.add(text='User followed')


def cmd_unfollow(command: IncomingCommand, replies: Replies) -> None:
    """Unfollow the user with the given id.
    """
    if len(command.args) == 2:
        acc = db.get_account_by_id(int(command.args[0]))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
        command.payload = command.args[1]
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return
    if not command.payload:
        replies.add(text='Wrong Syntax')
        return

    m = get_session(acc)
    if command.payload.isdigit():
        user_id = command.payload
    else:
        user_id = get_user(m, command.payload)
        if user_id is None:
            replies.add(text='Invalid user')
            return
    m.account_unfollow(user_id)
    replies.add(text='User unfollowed')


def cmd_mute(command: IncomingCommand, replies: Replies) -> None:
    """Mute the user with the given id.
    """
    if len(command.args) == 2:
        acc = db.get_account_by_id(int(command.args[0]))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
        command.payload = command.args[1]
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return
    if not command.payload:
        replies.add(text='Wrong Syntax')
        return

    m = get_session(acc)
    if command.payload.isdigit():
        user_id = command.payload
    else:
        user_id = get_user(m, command.payload)
        if user_id is None:
            replies.add(text='Invalid user')
            return
    m.account_mute(user_id)
    replies.add(text='User muted')


def cmd_unmute(command: IncomingCommand, replies: Replies) -> None:
    """Unmute the user with the given id.
    """
    if len(command.args) == 2:
        acc = db.get_account_by_id(int(command.args[0]))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
        command.payload = command.args[1]
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return
    if not command.payload:
        replies.add(text='Wrong Syntax')
        return

    m = get_session(acc)
    if command.payload.isdigit():
        user_id = command.payload
    else:
        user_id = get_user(m, command.payload)
        if user_id is None:
            replies.add(text='Invalid user')
            return
    m.account_unmute(user_id)
    replies.add(text='User unmuted')


def cmd_block(command: IncomingCommand, replies: Replies) -> None:
    """Block the user with the given id.
    """
    if len(command.args) == 2:
        acc = db.get_account_by_id(int(command.args[0]))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
        command.payload = command.args[1]
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return
    if not command.payload:
        replies.add(text='Wrong Syntax')
        return

    m = get_session(acc)
    if command.payload.isdigit():
        user_id = command.payload
    else:
        user_id = get_user(m, command.payload)
        if user_id is None:
            replies.add(text='Invalid user')
            return
    m.account_block(user_id)
    replies.add(text='User blocked')


def cmd_unblock(command: IncomingCommand, replies: Replies) -> None:
    """Unblock the user with the given id.
    """
    if len(command.args) == 2:
        acc = db.get_account_by_id(int(command.args[0]))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
        command.payload = command.args[1]
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return
    if not command.payload:
        replies.add(text='Wrong Syntax')
        return

    m = get_session(acc)
    if command.payload.isdigit():
        user_id = command.payload
    else:
        user_id = get_user(m, command.payload)
        if user_id is None:
            replies.add(text='Invalid user')
            return
    m.account_unblock(user_id)
    replies.add(text='User unblocked')


def cmd_profile(command: IncomingCommand, replies: Replies) -> None:
    """See the profile of the given user.
    """
    if len(command.args) == 2:
        acc = db.get_account_by_id(int(command.args[0]))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
        command.payload = command.args[1]
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return

    m = get_session(acc)
    me = m.me()
    if not command.payload:
        user = me
    else:
        user = get_user(m, command.payload)
        if user is None:
            replies.add(text='Invalid user')
            return

    rel = m.account_relationships(user)[0] if user.id != me.id else None
    text = '{}:\n\n'.format(get_name(user))
    fields = ''
    for f in user.fields:
        fields += '{}: {}\n'.format(
            html2text(f.name).strip(), html2text(f.value).strip())
    if fields:
        text += fields+'\n\n'
    text += html2text(user.note).strip()
    text += '\n\nToots: {}\nFollowing: {}\nFollowers: {}'.format(
        user.statuses_count, user.following_count, user.followers_count)
    if user.id != me.id:
        if rel['followed_by']:
            text += '\n[follows you]'
        elif rel['blocked_by']:
            text += '\n[blocked you]'
        text += '\n'
        if rel['following'] or rel['requested']:
            action = 'unfollow'
        else:
            action = 'follow'
        text += '\n/m_{}_{}_{}'.format(action, acc['id'], user.id)
        action = 'unmute' if rel['muting'] else 'mute'
        text += '\n/m_{}_{}_{}'.format(action, acc['id'], user.id)
        action = 'unblock' if rel['blocking'] else 'block'
        text += '\n/m_{}_{}_{}'.format(action, acc['id'], user.id)
        text += '\n/m_dm_{}_{}'.format(acc['id'], user.id)
    text += TOOT_SEP
    toots = m.account_statuses(user, limit=10)
    text += TOOT_SEP.join(toots2text(toots, acc['id']))
    replies.add(text=text)


def cmd_local(command: IncomingCommand, replies: Replies) -> None:
    """Get latest entries from the local timeline.
    """
    if command.payload:
        acc = db.get_account_by_id(int(command.payload))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return

    m = get_session(acc)
    toots = m.timeline_local()
    if toots:
        replies.add(text=TOOT_SEP.join(toots2text(toots, acc['id'])))
    else:
        replies.add(text='Nothing found')


def cmd_public(command: IncomingCommand, replies: Replies) -> None:
    """Get latest entries from the public timeline.
    """
    if command.payload:
        acc = db.get_account_by_id(int(command.payload))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return

    m = get_session(acc)
    toots = m.timeline_public()
    if toots:
        replies.add(text=TOOT_SEP.join(toots2text(toots, acc['id'])))
    else:
        replies.add(text='Nothing found')


def cmd_tag(command: IncomingCommand, replies: Replies) -> None:
    """Get latest entries with the given hashtags.
    """
    if len(command.args) == 2:
        acc = db.get_account_by_id(int(command.args[0]))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
        command.payload = command.args[1]
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]
    command.payload = command.payload.lstrip('#')
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return
    if not command.payload:
        replies.add(text='Wrong Syntax')
        return

    m = get_session(acc)
    toots = m.timeline_hashtag(command.payload)
    if toots:
        replies.add(text=TOOT_SEP.join(toots2text(toots, acc['id'])))
    else:
        replies.add(text='Nothing found')


def cmd_search(command: IncomingCommand, replies: Replies) -> None:
    """Search for users and hashtags matching the given text.
    """
    if len(command.args) == 2:
        acc = db.get_account_by_id(int(command.args[0]))
        if acc and acc['addr'] != command.message.get_sender_contact().addr:
            replies.add(text='That is not your account')
            return
        command.payload = command.args[1]
    else:
        acc = db.get_account(command.message.chat.id)
        if not acc:
            accs = db.get_accounts(
                addr=command.message.get_sender_contact().addr)
            if len(accs) == 1:
                acc = accs[0]
    if not acc:
        replies.add(
            text='You must send that command in you Mastodon chats')
        return
    if not command.payload:
        replies.add(text='Wrong Syntax')
        return

    m = get_session(acc)
    res = m.search(command.payload)
    text = ''
    if res['accounts']:
        text += '👤 Accounts:'
        for a in res['accounts']:
            text += '\n@{} /m_profile_{}_{}'.format(
                a.acct, acc['id'], a.id)
        text += '\n\n'
    if res['hashtags']:
        text += '#️⃣ Hashtags:'
        for tag in res['hashtags']:
            text += '\n#{0} /m_tag_{1}_{0}'.format(tag.name, acc['id'])
    if text:
        replies.add(text=text)
    else:
        replies.add(text='Nothing found')


# ======== Utilities ===============

def get_session(acc) -> mastodon.Mastodon:
    m = mastodon.Mastodon(api_base_url=acc['api_url'],
                          ratelimit_method='throw')
    m.log_in(acc['email'], acc['password'])
    return m


def get_user(m, user_id):
    user = None
    if user_id.isdigit():
        user = m.account(user_id)
    else:
        user_id = user_id.lstrip('@').lower()
        ids = (user_id, user_id.split('@')[0])
        for a in m.account_search(user_id):
            if a.acct.lower() in ids:
                user = a
                break
    return user


def get_name(macc) -> str:
    isbot = '[BOT] ' if macc.bot else ''
    if macc.display_name:
        return isbot + '{} (@{})'.format(macc.display_name, macc.acct)
    return isbot + macc.acct


def toots2text(toots: list, acc_id: int,
               notifications: bool = False) -> Generator:
    for t in reversed(toots):
        if notifications:
            is_mention = False
            timestamp = t.created_at.strftime(STRFORMAT)
            if t.type == 'reblog':
                text = '🔁 {} boosted your toot. ({})\n\n'.format(
                    get_name(t.account), timestamp)
            elif t.type == 'favourite':
                text = '⭐ {} favorited your toot. ({})\n\n'.format(
                    get_name(t.account), timestamp)
            elif t.type == 'follow':
                yield '👤 {} followed you. ({})'.format(
                    get_name(t.account), timestamp)
                continue
            elif t.type == 'mention':
                is_mention = True
                text = '{}:\n\n'.format(get_name(t.account))
            else:
                continue
            t = t.status
        elif t.reblog:
            text = '{}:\n🔁 {}\n\n'.format(
                get_name(t.reblog.account), get_name(t.account))
            t = t.reblog
        else:
            text = '{}:\n\n'.format(get_name(t.account))

        media_urls = '\n'.join(
            media.url for media in t.media_attachments)
        if media_urls:
            text += media_urls + '\n\n'

        soup = BeautifulSoup(
            t.content, 'html.parser')
        if t.mentions:
            accts = {e.url: '@' + e.acct
                     for e in t.mentions}
            for a in soup('a', class_='u-url'):
                name = accts.get(a['href'])
                if name:
                    a.string = name
        for br in soup('br'):
            br.replace_with('\n')
        for p in soup('p'):
            p.replace_with(p.get_text()+'\n\n')
        text += soup.get_text()

        text += '\n\n[{} {}]\n'.format(
            v2emoji[t.visibility], t.created_at.strftime(STRFORMAT))
        if not notifications or is_mention:
            text += '↩️ /m_reply_{}_{}\n'.format(acc_id, t.id)
            text += '⭐ /m_star_{}_{}\n'.format(acc_id, t.id)
            if t.visibility in (Visibility.PUBLIC, Visibility.UNLISTED):
                text += '🔄 /m_boost_{}_{}\n'.format(acc_id, t.id)
            text += '⏫ /m_cntx_{}_{}\n'.format(acc_id, t.id)

        yield text


def toot(masto: mastodon.Mastodon, text: str = None, filename: str = None,
         visibility: str = None, in_reply_to: str = None) -> None:
    if filename:
        if filename.endswith('.aac'):
            aac_file = AudioSegment.from_file(filename, 'aac')
            filename = filename[:-4] + '.mp3'
            aac_file.export(filename, format='mp3')
        media = [masto.media_post(filename).id]
        if in_reply_to:
            masto.status_reply(masto.status(in_reply_to), text,
                               media_ids=media, visibility=visibility)
        else:
            masto.status_post(
                text, media_ids=media, visibility=visibility)
    elif text:
        if in_reply_to:
            masto.status_reply(
                masto.status(in_reply_to), text, visibility=visibility)
        else:
            masto.status_post(text, visibility=visibility)


def normalize_url(url: str) -> str:
    if url.startswith('http://'):
        url = 'https://' + url[4:]
    elif not url.startswith('https://'):
        url = 'https://' + url
    return url.rstrip('/')


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


def rmprefix(text, prefix):
    return text[text.startswith(prefix) and len(prefix):]


def logout(acc, replies: Replies) -> None:
    me = dbot.self_contact
    for pchat in db.get_pchats(acc['id']):
        g = dbot.get_chat(pchat['id'])
        try:
            g.remove_contact(me)
        except ValueError:
            pass
    try:
        dbot.get_chat(acc['home']).remove_contact(me)
    except ValueError:
        pass
    try:
        dbot.get_chat(acc['notif']).remove_contact(me)
    except ValueError:
        pass
    db.remove_account(acc['id'])
    replies.add(text='You have logged out from: ' + acc['api_url'],
                chat=dbot.get_chat(acc['addr']))


def _check_notifications(acc, m: mastodon.Mastodon) -> None:
    max_id = None
    dmsgs = []
    notifications = []
    while True:
        ns = m.notifications(
            max_id=max_id, since_id=acc['last_notif'])
        if not ns:
            break
        if max_id is None:
            db.set_last_notif(acc['id'], ns[0].id)
        max_id = ns[-1]
        for n in ns:
            if n.type == 'mention' and n.status.visibility == Visibility.DIRECT and len(n.status.mentions) == 1:
                dmsgs.append(n.status)
            else:
                notifications.append(n)
    for dm in reversed(dmsgs):
        text = '{}:\n\n'.format(get_name(dm.account))

        media_urls = '\n'.join(
            media.url for media in dm.media_attachments)
        if media_urls:
            text += media_urls + '\n\n'

        soup = BeautifulSoup(dm.content, 'html.parser')
        accts = {e.url: '@'+e.acct
                 for e in dm.mentions}
        for a in soup('a', class_='u-url'):
            name = accts.get(a['href'])
            if name:
                a.string = name
        for br in soup('br'):
            br.replace_with('\n')
        for p in soup('p'):
            p.replace_with(p.get_text()+'\n\n')
        text += soup.get_text()
        text += '\n\n[{} {}]\n'.format(
            v2emoji[dm.visibility], dm.created_at.strftime(STRFORMAT))
        text += '⭐ /m_star_{}_{}\n'.format(
            acc['id'], dm.id)

        pv = db.get_pchat_by_contact(acc['id'], dm.account.acct)
        if pv:
            g = dbot.get_chat(pv['id'])
            if g is None:
                db.remove_pchat(pv['id'])
            else:
                g.send_text(text)
        else:
            url = rmprefix(acc['api_url'], 'https://')
            g = dbot.create_group(
                '🇲 {} ({})'.format(dm.account.acct, url), [acc['addr']])
            db.add_pchat(g.id, dm.account.acct, acc['id'])

            r = requests.get(dm.account.avatar_static)
            with tempfile.NamedTemporaryFile(suffix='.jpg') as fp:
                fp.write(r.content)
                try:
                    g.set_profile_image(fp.name)
                except ValueError as err:
                    dbot.logger.exception(err)

            g.send_text(text)

    dbot.logger.debug('Notifications: %s new entries (last id: %s)',
                      len(notifications), acc['last_notif'])
    if notifications:
        dbot.get_chat(acc['notif']).send_text(TOOT_SEP.join(
            toots2text(notifications, acc['id'], True)))


def _check_home(acc, m: mastodon.Mastodon) -> None:
    me = m.me()
    max_id = None
    toots: list = []
    while True:
        ts = m.timeline_home(max_id=max_id, since_id=acc['last_home'])
        if not ts:
            break
        if max_id is None:
            db.set_last_home(acc['id'], ts[0].id)
        max_id = ts[-1]
        for t in ts:
            for a in t.mentions:
                if a.id == me.id:
                    break
            else:
                toots.append(t)
    dbot.logger.debug('Home: %s new entries (last id: %s)',
                      len(toots), acc['last_home'])
    if toots:
        dbot.get_chat(acc['home']).send_text(TOOT_SEP.join(
            toots2text(toots, acc['id'])))


def listen_to_mastodon() -> None:
    while True:
        dbot.logger.info('Checking Mastodon')
        instances: dict = {}
        for acc in db.get_accounts():
            instances.setdefault(acc['api_url'], []).append(acc)
        while instances:
            for key in list(instances.keys()):
                if not instances[key]:
                    instances.pop(key)
                    continue
                acc = instances[key].pop()
                try:
                    m = get_session(acc)
                    _check_notifications(acc, m)
                    _check_home(acc, m)
                except mastodon.MastodonUnauthorizedError:
                    db.remove_account(acc['id'])
                    dbot.get_chat(acc['addr']).send_text(
                        'You have logged out from: ' + acc['api_url'])
                except Exception as ex:
                    dbot.logger.exception(ex)
            time.sleep(2)
        time.sleep(int(getdefault('delay')))

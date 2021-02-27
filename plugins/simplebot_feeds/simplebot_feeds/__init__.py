
import os
from threading import Thread
from time import sleep
from typing import Optional

import feedparser
import html2text
from deltachat import Chat, Contact, Message
from deltachat.capi import lib
from deltachat.cutil import as_dc_charpointer
from feedparser.exceptions import CharacterEncodingOverride
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

from .db import DBManager

__version__ = '1.0.0'
feedparser.USER_AGENT = 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0)'
feedparser.USER_AGENT += ' Gecko/20100101 Firefox/60.0'
html2text.config.WRAP_LINKS = False
dbot: DeltaBot
db: DBManager


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global dbot, db
    dbot = bot
    db = get_db(bot)

    getdefault('delay', 60*5)
    getdefault('max_feed_count', -1)

    dbot.commands.register('/feed_sub', cmd_sub)
    dbot.commands.register('/feed_unsub', cmd_unsub)
    dbot.commands.register('/feed_list', cmd_list)


@deltabot_hookimpl
def deltabot_start(bot: DeltaBot) -> None:
    Thread(target=check_feeds, daemon=True).start()


@deltabot_hookimpl
def deltabot_member_removed(chat: Chat, contact: Contact) -> None:
    me = dbot.self_contact
    if me == contact or len(chat.get_contacts()) <= 1:
        feeds = db.get_feeds(chat.id)
        if feeds:
            db.remove_fchat(chat.id)
            for feed in feeds:
                if not db.get_fchats(feed['url']):
                    db.remove_feed(feed['url'])


# ======== Commands ===============

def cmd_sub(command: IncomingCommand, replies: Replies) -> None:
    """Subscribe current chat to the given feed.
    """
    url = db.normalize_url(command.payload)
    feed = db.get_feed(url)

    if feed:
        d = feedparser.parse(feed['url'])
    else:
        max_fc = int(getdefault('max_feed_count'))
        if 0 <= max_fc <= len(db.get_feeds()):
            replies.add(text='Sorry, maximum number of feeds reached')
            return
        d = feedparser.parse(url)
        bozo_exception = d.get('bozo_exception', '')
        if (d.get('bozo') == 1 and not isinstance(
                bozo_exception, CharacterEncodingOverride)) or not d.entries:
            replies.add(text='Invalid feed url: {}'.format(url))
            command.bot.logger.warning(
                'Invalid feed %s: %s', url, bozo_exception)
            return
        feed = dict(
            url=url,
            etag=d.get('etag'),
            modified=d.get('modified') or d.get('updated'),
            latest=get_latest_date(d.entries),
        )
        db.add_feed(url, feed['etag'], feed['modified'], feed['latest'])

    if command.message.chat.is_group():
        chat = command.message.chat
    else:
        chat = command.bot.create_group(
            d.feed.get('title') or url,
            [command.message.get_sender_contact()])

    if chat.id in db.get_fchats(feed['url']):
        replies.add(text='Chat alredy subscribed to that feed.', chat=chat)
        return

    db.add_fchat(chat.id, feed['url'])
    title = d.feed.get('title') or '-'
    desc = d.feed.get('description') or '-'
    text = 'Title: {}\n\nURL: {}\n\nDescription: {}'.format(
        title, feed['url'], desc)

    if d.entries and feed['latest']:
        latest = tuple(map(int, feed['latest'].split()))
        html = format_entries(get_old_entries(d.entries, latest)[:5])
        replies.add(text=text, html=html, chat=chat)
    else:
        replies.add(text=text, chat=chat)


def cmd_unsub(command: IncomingCommand, replies: Replies) -> None:
    """Unsubscribe current chat from the given feed.
    """
    url = command.payload
    feed = db.get_feed(url)
    if not feed:
        replies.add(text='Unknow feed: {}'.format(url))
        return

    if command.message.chat.id not in db.get_fchats(feed['url']):
        replies.add(
            text='This chat is not subscribed to: {}'.format(feed['url']))
        return

    db.remove_fchat(command.message.chat.id, feed['url'])
    if not db.get_fchats(feed['url']):
        db.remove_feed(feed['url'])
    replies.add(text='Chat unsubscribed from: {}'.format(feed['url']))


def cmd_list(command: IncomingCommand, replies: Replies) -> None:
    """List feed subscriptions for the current chat.
    """
    feeds = db.get_feeds(command.message.chat.id)
    text = '\n\n'.join(f['url'] for f in feeds)
    replies.add(text=text or 'No feed subscriptions in this chat')


# ======== Utilities ===============

def check_feeds() -> None:
    while True:
        dbot.logger.debug('Checking feeds')
        for f in db.get_feeds():
            try:
                _check_feed(f)
            except Exception as err:
                dbot.logger.exception(err)
        sleep(int(getdefault('delay')))


def _check_feed(f) -> None:
    fchats = db.get_fchats(f['url'])

    if not fchats:
        db.remove_feed(f['url'])
        return

    dbot.logger.debug('Checking feed: %s', f['url'])
    d = feedparser.parse(
        f['url'], etag=f['etag'], modified=f['modified'])

    bozo_exception = d.get('bozo_exception', '')
    if d.get('bozo') == 1 and not isinstance(
            bozo_exception, CharacterEncodingOverride):
        dbot.logger.exception(bozo_exception)
        return

    if d.entries and f['latest']:
        d.entries = get_new_entries(
            d.entries, tuple(map(int, f['latest'].split())))
    if not d.entries:
        return

    html = format_entries(d.entries[:50])
    for gid in fchats:
        try:
            msg = Message.new_empty(dbot.account, "text")
            lib.dc_msg_set_html(msg._dc_msg, as_dc_charpointer(html))
            dbot.get_chat(gid).send_msg(msg)
        except ValueError:
            db.remove_fchat(gid)

    latest = get_latest_date(d.entries) or f['latest']
    modified = d.get('modified') or d.get('updated')
    db.update_feed(f['url'], d.get('etag'), modified, latest)


def format_entries(entries: list) -> str:
    entries_text = []
    for e in entries:
        t = '<a href="{}"><h3>{}</h3></a>'.format(
            e.get('link') or '', e.get('title') or 'NO TITLE')
        pub_date = e.get('published')
        if pub_date:
            t += '<p>📆 <small><em>{}</em></small></p>'.format(pub_date)
        desc = e.get('description') or ''
        if not desc and e.get('content'):
            for c in e.get('content'):
                if c.get('type') == 'text/html':
                    desc += c['value']
        if desc and desc != e.get('title'):
            t += desc
        entries_text.append(t)
    return '<br><hr>'.join(entries_text)


def get_new_entries(entries: list, date: tuple) -> list:
    new_entries = []
    for e in entries:
        d = e.get('published_parsed') or e.get('updated_parsed')
        if d is not None and d > date:
            new_entries.append(e)
    return new_entries


def get_old_entries(entries: list, date: tuple) -> list:
    old_entries = []
    for e in entries:
        d = e.get('published_parsed') or e.get('updated_parsed')
        if d is not None and d <= date:
            old_entries.append(e)
    return old_entries


def get_latest_date(entries: list) -> Optional[str]:
    dates = []
    for e in entries:
        d = e.get('published_parsed') or e.get('updated_parsed')
        if d:
            dates.append(d)
    return ' '.join(map(str, max(dates))) if dates else None


def getdefault(key: str, value=None) -> str:
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

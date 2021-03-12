
import os
import time

import simplebot
from deltachat import Chat, Contact, Message
from simplebot import DeltaBot
from simplebot.bot import Replies

from .db import DBManager, Status

__version__ = '1.0.0'
BARS = ['🟩', '🟥', '🟦', '🟪', '🟧', '🟨', '🟫', '⬛']
db: DBManager


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global db
    db = _get_db(bot)


@simplebot.hookimpl
def deltabot_member_removed(bot: DeltaBot, chat: Chat, contact: Contact) -> None:
    me = bot.self_contact
    if me == contact or len(chat.get_contacts()) <= 1:
        for poll in db.get_gpolls_by_gid(chat.id):
            db.remove_gpoll_by_id(poll['id'])


@simplebot.command
def poll_new(bot: DeltaBot, payload: str, message: Message,
             replies: Replies) -> None:
    """Create a new poll in the group it is sent, or a public poll if sent in private.

    Example:
    /poll_new Do you like polls?
    yes
    no
    maybe
    """
    lns = payload.split('\n')
    if len(lns) < 3:
        replies.add(text='Invalid poll, at least two options needed')
        return

    lines = []
    for ln in lns:
        ln = ln.strip()
        if ln:
            lines.append(ln)

    question = lines.pop(0)
    if len(question) > 255:
        replies.add(text='Question can have up to 255 characters')
        return
    for opt in lines:
        if len(opt) > 150:
            replies.add(
                text='Up to 150 characters per option are allowed')
            return

    if message.chat.is_group():
        gid = message.chat.id
        poll = db.get_gpoll_by_question(gid, question)
        if poll:
            replies.add(text='Group already has a poll with that name')
            return
        db.add_gpoll(gid, question)
        poll = db.get_gpoll_by_question(gid, question)
        assert poll is not None
        for i, opt in enumerate(lines):
            db.add_goption(i, poll['id'], opt)
        replies.add(text=format_gpoll(poll))
    else:
        addr = message.get_sender_contact().addr
        poll = db.get_poll_by_question(addr, question)
        if poll:
            replies.add(text='You already have a poll with that name')
            return
        db.add_poll(addr, question, time.time())
        poll = db.get_poll_by_question(addr, question)
        assert poll is not None
        for i, opt in enumerate(lines):
            db.add_option(i, poll['id'], opt)
        replies.add(text=_format_poll(bot, poll))


@simplebot.command
def poll_get(bot: DeltaBot, payload: str, message: Message,
             replies: Replies) -> None:
    """Get poll with given id.
    """
    args = payload.split()
    if len(args) not in (1, 2):
        replies.add(text='Invalid syntax')
        return
    if len(args) == 2:
        chat = bot.get_chat(int(args[0]))
        payload = args[1]
        if message.get_sender_contact() not in chat.get_contacts():
            replies.add(text='You are not a member of that group')
            return
    else:
        chat = message.chat

    pid = int(payload)
    poll = db.get_gpoll_by_id(pid)
    if poll and chat.id == poll['gid']:
        closed = poll['status'] == Status.CLOSED
        replies.add(text=format_gpoll(poll, closed=closed))
    elif len(args) == 1:
        poll = db.get_poll_by_id(pid)
        if poll:
            closed = poll['status'] == Status.CLOSED
            replies.add(text=_format_poll(bot, poll, closed=closed))
        else:
            replies.add(text='Invalid poll id')
    else:
        replies.add(text='Invalid poll id')


@simplebot.command
def poll_status(bot: DeltaBot, payload: str, message: Message,
                replies: Replies) -> None:
    """Get poll status.
    """
    args = payload.split()
    if len(args) not in (1, 2):
        replies.add(text='Invalid syntax')
        return
    if len(args) == 2:
        chat = bot.get_chat(int(args[0]))
        payload = args[1]
        if message.get_sender_contact() not in chat.get_contacts():
            replies.add(text='You are not a member of that group')
            return
    else:
        chat = message.chat

    pid = int(payload)
    addr = message.get_sender_contact().addr
    poll = db.get_gpoll_by_id(pid)
    if poll and chat.id == poll['gid']:
        voted = db.get_gvote(poll['id'], addr) is not None
        if voted:
            closed = poll['status'] == Status.CLOSED
            replies.add(
                text=format_gpoll(poll, voted=voted, closed=closed))
        else:
            replies.add(text="You can't see poll status until you vote")
    elif len(args) == 1:
        poll = db.get_poll_by_id(pid)
        if poll:
            is_admin = addr == poll['addr']
            voted = is_admin or db.get_vote(poll['id'], addr) is not None
            if voted:
                closed = poll['status'] == Status.CLOSED
                replies.add(text=_format_poll(
                    bot, poll, voted=voted, closed=closed, is_admin=is_admin))
            else:
                replies.add(
                    text="You can't see poll status until you vote")
        else:
            replies.add(text='Invalid poll id')
    else:
        replies.add(text='Invalid poll id')


@simplebot.command
def poll_settings(bot: DeltaBot, payload: str, message: Message,
                  replies: Replies) -> None:
    """Get poll advanced settings.
    """
    args = payload.split()
    if len(args) not in (1, 2):
        replies.add(text='Invalid syntax')
        return
    if len(args) == 2:
        chat = bot.get_chat(int(args[0]))
        payload = args[1]
        if message.get_sender_contact() not in chat.get_contacts():
            replies.add(text='You are not a member of that group')
            return
    else:
        chat = message.chat

    pid = int(payload)
    poll = db.get_gpoll_by_id(pid)
    if poll and chat.id == poll['gid']:
        gid = '{}_{}'.format(poll['gid'], poll['id'])
        text = '📊 /poll_get_{}\n{}\n\n'.format(gid, poll['question'])
        text += '🛑 /poll_end_{}\n\n'.format(gid)
        replies.add(text=text)
    elif len(args) == 1:
        addr = message.get_sender_contact().addr
        poll = db.get_poll_by_id(pid)
        if poll and addr == poll['addr']:
            text = '📊 /poll_get_{}\n{}\n\n'.format(
                poll['id'], poll['question'])
            text += '🛑 /poll_end_{}\n\n'.format(poll['id'])
            replies.add(text=text)
        else:
            replies.add(text='Invalid poll id')
    else:
        replies.add(text='Invalid poll id')


@simplebot.command
def poll_list(message: Message, replies: Replies) -> None:
    """Show group poll list or your public polls if sent in private.
    """
    if message.chat.is_group():
        polls = db.get_gpolls_by_gid(message.chat.id)
        if polls:
            text = ''
            for poll in polls:
                if len(poll['question']) > 100:
                    q = poll['question'][:100]+'...'
                else:
                    q = poll['question']
                text += '📊 /poll_get_{}_{} {}\n\n'.format(
                    poll['gid'], poll['id'], q)
            replies.add(text=text)
        else:
            replies.add(text='Empty list')
    else:
        polls = db.get_polls_by_addr(
            message.get_sender_contact().addr)
        if polls:
            text = ''
            for poll in polls:
                if len(poll['question']) > 100:
                    q = poll['question'][:100]+'...'
                else:
                    q = poll['question']
                text += '📊 /poll_get_{} {}\n\n'.format(poll['id'], q)
            replies.add(text=text)
        else:
            replies.add(text='Empty list')


@simplebot.command
def poll_end(bot: DeltaBot, payload: str, message: Message,
            replies: Replies) -> None:
    """Close the poll with the given id.
    """
    args = payload.split()
    if len(args) not in (1, 2):
        replies.add(text='Invalid syntax')
        return
    if len(args) == 2:
        chat = bot.get_chat(int(args[0]))
        payload = args[1]
        if message.get_sender_contact() not in chat.get_contacts():
            replies.add(text='You are not a member of that group')
            return
    else:
        chat = message.chat

    pid = int(payload)
    poll = db.get_gpoll_by_id(pid)
    addr = message.get_sender_contact().addr
    if poll and chat.id == poll['gid']:
        db.end_gpoll(poll['id'])
        text = format_gpoll(poll, closed=True)
        text += '\n\n(Poll closed by {})'.format(addr)
        replies.add(text=text, chat=chat)
        db.remove_gpoll_by_id(pid)
    elif len(args) == 1:
        poll = db.get_poll_by_id(pid)
        if poll and addr == poll['addr']:
            db.end_poll(poll['id'])
            text = _format_poll(bot, poll, closed=True)
            for addr in db.get_poll_participants(poll['id']):
                contact = bot.get_contact(addr)
                if not contact.is_blocked():
                    replies.add(
                        text=text, chat=bot.get_chat(contact))
            db.remove_poll_by_id(poll['id'])
        else:
            replies.add(text='Invalid poll id')
    else:
        replies.add(text='Invalid poll id')


@simplebot.command
def vote(bot: DeltaBot, payload: str, message: Message,
         replies: Replies) -> None:
    """Vote in polls.
    """
    args = payload.split()
    if len(args) not in (2, 3):
        replies.add(text='Invalid syntax')
        return
    if len(args) == 3:
        chat = bot.get_chat(int(args[0]))
        if message.get_sender_contact() not in chat.get_contacts():
            replies.add(text='You are not a member of that group')
            return
        pid = int(args[1])
        oid = int(args[2]) - 1
    else:
        chat = message.chat
        pid = int(args[0])
        oid = int(args[1]) - 1

    addr = message.get_sender_contact().addr
    poll = db.get_gpoll_by_id(pid)
    if poll and chat.id == poll['gid']:
        if poll['status'] == Status.CLOSED:
            replies.add(text='That poll is closed')
        elif db.get_gvote(pid, addr):
            replies.add(text='You already voted')
        elif oid not in [opt['id'] for opt in db.get_goptions(pid)]:
            replies.add(text='Invalid option number')
        else:
            db.add_gvote(poll['id'], addr, oid)
            replies.add(text=format_gpoll(poll, voted=True))
    elif len(args) == 2:
        poll = db.get_poll_by_id(pid)
        if poll:
            if poll['status'] == Status.CLOSED:
                replies.add(text='That poll is closed')
            elif db.get_vote(pid, addr):
                replies.add(text='You already voted')
            elif oid not in [opt['id'] for opt in db.get_options(pid)]:
                replies.add(text='Invalid option number')
            else:
                is_admin = addr == poll['addr']
                db.add_vote(poll['id'], addr, oid)
                replies.add(text=_format_poll(
                    bot, poll, voted=True, is_admin=is_admin))
        else:
            replies.add(text='Invalid poll id')
    else:
        replies.add(text='Invalid poll id')


def format_gpoll(poll, voted: bool = False, closed: bool = False) -> str:
    gid = '{}_{}'.format(poll['gid'], poll['id'])
    if closed:
        status = 'Finished'
        text = '📊 POLL RESULTS\n'
    else:
        status = 'Ongoing'
        text = '📊 /poll_get_{0} | /poll_status_{0}\n'.format(gid)
        text += '⚙️ /poll_settings_{}\n'.format(gid)
    text += '\n{}\n\n'.format(poll['question'])
    options = db.get_goptions(poll['id'])
    votes = db.get_gvotes(poll['id'])
    vcount = len(votes)
    if voted or closed:
        for opt in options:
            p = len([v for v in votes if v['option'] == opt['id']])/vcount
            text += '{}% {}\n|{}\n\n'.format(
                round(p*100), opt['text'], BARS[opt['id'] % len(BARS)] * round(10*p))
    else:
        for opt in options:
            text += '/vote_{}_{} {}\n\n'.format(
                gid, opt['id']+1, opt['text'])
    text += '[{} - {} votes]'.format(status, vcount)
    return text


def _format_poll(bot:DeltaBot, poll, voted: bool = False,
                 closed: bool = False, is_admin: bool = False) -> str:
    if closed:
        text = '📊 POLL RESULTS\n'
        status = 'Finished'
    else:
        text = '📊 /poll_get_{0} | /poll_status_{0}\n'.format(poll['id'])
        if is_admin:
            text += '⚙️ /poll_settings_{}\n'.format(poll['id'])
        status = 'Ongoing'
    text += '\n{}\n\n'.format(poll['question'])
    options = db.get_options(poll['id'])
    votes = db.get_votes(poll['id'])
    vcount = len(votes)
    if voted or closed:
        for opt in options:
            p = len([v for v in votes if v['option'] == opt['id']])/vcount
            text += '{}% {}\n|{}\n\n'.format(
                round(p*100), opt['text'], BARS[opt['id'] % len(BARS)] * round(10*p))
    else:
        for opt in options:
            text += '/vote_{}_{} {}\n\n'.format(
                poll['id'], opt['id']+1, opt['text'])
    text += '[{} - {} votes]\nPoll by {}'.format(
        status, vcount, bot.self_contact.addr)
    return text


def _get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))

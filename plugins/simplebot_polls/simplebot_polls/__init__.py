
import os
import time

from deltachat import Chat, Contact
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

from .db import DBManager, Status

version = '1.0.0'
BARS = ['🟩', '🟥', '🟦', '🟪', '🟧', '🟨', '🟫', '⬛']
db: DBManager
dbot: DeltaBot


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global db, dbot
    dbot = bot
    db = get_db(bot)

    dbot.commands.register('/poll_new', cmd_new)
    dbot.commands.register('/poll_end', cmd_end)
    dbot.commands.register('/poll_get', cmd_get)
    dbot.commands.register('/poll_status', cmd_status)
    dbot.commands.register('/poll_list', cmd_list)
    dbot.commands.register('/poll_settings', cmd_settings)
    dbot.commands.register('/vote', cmd_vote)


@deltabot_hookimpl
def deltabot_member_removed(chat: Chat, contact: Contact) -> None:
    me = dbot.self_contact
    if me == contact or len(chat.get_contacts()) <= 1:
        for poll in db.get_gpolls_by_gid(chat.id):
            db.remove_gpoll_by_id(poll['id'])


# ======== Commands ===============

def cmd_new(command: IncomingCommand, replies: Replies) -> None:
    """Create a new poll in the group it is sent, or a public poll if sent in private.

    Example:
    /poll_new Do you like polls?
    yes
    no
    maybe
    """
    lns = command.payload.split('\n')
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

    if command.message.chat.is_group():
        gid = command.message.chat.id
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
        addr = command.message.get_sender_contact().addr
        poll = db.get_poll_by_question(addr, question)
        if poll:
            replies.add(text='You already have a poll with that name')
            return
        db.add_poll(addr, question, time.time())
        poll = db.get_poll_by_question(addr, question)
        assert poll is not None
        for i, opt in enumerate(lines):
            db.add_option(i, poll['id'], opt)
        replies.add(text=format_poll(poll))


def cmd_get(command: IncomingCommand, replies: Replies) -> None:
    """Get poll with given id.
    """
    if len(command.args) not in (1, 2):
        replies.add(text='Invalid syntax')
        return
    if len(command.args) == 2:
        chat = command.bot.get_chat(int(command.args[0]))
        command.payload = command.args[1]
        if command.message.get_sender_contact() not in chat.get_contacts():
            replies.add(text='You are not a member of that group')
            return
    else:
        chat = command.message.chat

    pid = int(command.payload)
    poll = db.get_gpoll_by_id(pid)
    if poll and chat.id == poll['gid']:
        closed = poll['status'] == Status.CLOSED
        replies.add(text=format_gpoll(poll, closed=closed))
    elif len(command.args) == 1:
        poll = db.get_poll_by_id(pid)
        if poll:
            closed = poll['status'] == Status.CLOSED
            replies.add(text=format_poll(poll, closed=closed))
        else:
            replies.add(text='Invalid poll id')
    else:
        replies.add(text='Invalid poll id')


def cmd_status(command: IncomingCommand, replies: Replies) -> None:
    """Get poll status.
    """
    if len(command.args) not in (1, 2):
        replies.add(text='Invalid syntax')
        return
    if len(command.args) == 2:
        chat = command.bot.get_chat(int(command.args[0]))
        command.payload = command.args[1]
        if command.message.get_sender_contact() not in chat.get_contacts():
            replies.add(text='You are not a member of that group')
            return
    else:
        chat = command.message.chat

    pid = int(command.payload)
    addr = command.message.get_sender_contact().addr
    poll = db.get_gpoll_by_id(pid)
    if poll and chat.id == poll['gid']:
        voted = db.get_gvote(poll['id'], addr) is not None
        if voted:
            closed = poll['status'] == Status.CLOSED
            replies.add(
                text=format_gpoll(poll, voted=voted, closed=closed))
        else:
            replies.add(text="You can't see poll status until you vote")
    elif len(command.args) == 1:
        poll = db.get_poll_by_id(pid)
        if poll:
            is_admin = addr == poll['addr']
            voted = is_admin or db.get_vote(poll['id'], addr) is not None
            if voted:
                closed = poll['status'] == Status.CLOSED
                replies.add(text=format_poll(
                    poll, voted=voted, closed=closed, is_admin=is_admin))
            else:
                replies.add(
                    text="You can't see poll status until you vote")
        else:
            replies.add(text='Invalid poll id')
    else:
        replies.add(text='Invalid poll id')


def cmd_settings(command: IncomingCommand, replies: Replies) -> None:
    """Get poll advanced settings.
    """
    if len(command.args) not in (1, 2):
        replies.add(text='Invalid syntax')
        return
    if len(command.args) == 2:
        chat = command.bot.get_chat(int(command.args[0]))
        command.payload = command.args[1]
        if command.message.get_sender_contact() not in chat.get_contacts():
            replies.add(text='You are not a member of that group')
            return
    else:
        chat = command.message.chat

    pid = int(command.payload)
    poll = db.get_gpoll_by_id(pid)
    if poll and chat.id == poll['gid']:
        gid = '{}_{}'.format(poll['gid'], poll['id'])
        text = '📊 /poll_get_{}\n{}\n\n'.format(gid, poll['question'])
        text += '🛑 /poll_end_{}\n\n'.format(gid)
        replies.add(text=text)
    elif len(command.args) == 1:
        addr = command.message.get_sender_contact().addr
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


def cmd_list(command: IncomingCommand, replies: Replies) -> None:
    """Show group poll list or your public polls if sent in private.
    """
    if command.message.chat.is_group():
        polls = db.get_gpolls_by_gid(command.message.chat.id)
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
            command.message.get_sender_contact().addr)
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


def cmd_end(command: IncomingCommand, replies: Replies) -> None:
    """Close the poll with the given id.
    """
    if len(command.args) not in (1, 2):
        replies.add(text='Invalid syntax')
        return
    if len(command.args) == 2:
        chat = command.bot.get_chat(int(command.args[0]))
        command.payload = command.args[1]
        if command.message.get_sender_contact() not in chat.get_contacts():
            replies.add(text='You are not a member of that group')
            return
    else:
        chat = command.message.chat

    pid = int(command.payload)
    poll = db.get_gpoll_by_id(pid)
    addr = command.message.get_sender_contact().addr
    if poll and chat.id == poll['gid']:
        db.end_gpoll(poll['id'])
        text = format_gpoll(poll, closed=True)
        text += '\n\n(Poll closed by {})'.format(addr)
        replies.add(text=text, chat=chat)
        db.remove_gpoll_by_id(pid)
    elif len(command.args) == 1:
        poll = db.get_poll_by_id(pid)
        if poll and addr == poll['addr']:
            db.end_poll(poll['id'])
            text = format_poll(poll, closed=True)
            for addr in db.get_poll_participants(poll['id']):
                contact = command.bot.get_contact(addr)
                if not contact.is_blocked():
                    replies.add(
                        text=text, chat=command.bot.get_chat(contact))
            db.remove_poll_by_id(poll['id'])
        else:
            replies.add(text='Invalid poll id')
    else:
        replies.add(text='Invalid poll id')


def cmd_vote(command: IncomingCommand, replies: Replies) -> None:
    """Vote in polls.
    """
    if len(command.args) not in (2, 3):
        replies.add(text='Invalid syntax')
        return
    if len(command.args) == 3:
        chat = command.bot.get_chat(int(command.args[0]))
        if command.message.get_sender_contact() not in chat.get_contacts():
            replies.add(text='You are not a member of that group')
            return
        pid = int(command.args[1])
        oid = int(command.args[2]) - 1
    else:
        chat = command.message.chat
        pid = int(command.args[0])
        oid = int(command.args[1]) - 1

    addr = command.message.get_sender_contact().addr
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
    elif len(command.args) == 2:
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
                replies.add(text=format_poll(
                    poll, voted=True, is_admin=is_admin))
        else:
            replies.add(text='Invalid poll id')
    else:
        replies.add(text='Invalid poll id')


# ======== Utilities ===============

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


def format_poll(poll, voted: bool = False, closed: bool = False,
                is_admin: bool = False) -> str:
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
        status, vcount, dbot.self_contact.addr)
    return text


def get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))

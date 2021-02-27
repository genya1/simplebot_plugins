
import os
import sqlite3
from typing import Optional

from deltachat import Chat, Contact, Message
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

from .db import DBManager

__version__ = '1.0.0'
db: DBManager
dbot: DeltaBot
ec = '💀 Exquisite Corpse\n\n'


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global db, dbot
    dbot = bot
    db = get_db(bot)

    bot.filters.register(name=__name__, func=filter_messages)

    dbot.commands.register('/corpse_new', cmd_new)
    dbot.commands.register('/corpse_join', cmd_join)
    dbot.commands.register('/corpse_start', cmd_start)
    dbot.commands.register('/corpse_end', cmd_end)
    dbot.commands.register('/corpse_leave', cmd_leave)
    dbot.commands.register('/corpse_status', cmd_status)


@deltabot_hookimpl
def deltabot_member_removed(chat: Chat, contact: Contact,
                            replies: Replies) -> None:
    g = db.get_game_by_gid(chat.id)
    if not g:
        return
    if dbot.self_contact == contact or len(chat.get_contacts()) <= 1:
        db.delete_game(chat.id)
        return

    p = db.get_player_by_addr(contact.addr)
    if p is not None and p['game'] == g['gid']:
        remove_from_game(p, g)


# ======== Filters ===============

def filter_messages(message: Message, replies: Replies):
    """Process turns in Exquisite Corpse game groups
    """
    if not message.chat.is_group():
        sender = message.get_sender_contact()
        g = db.get_game_by_turn(sender.addr)

        if g is None:
            return

        if len(message.text.split()) < 10:
            text = '❌ Text too short. Send a message with at least 10 words'
            replies.add(text=text)
        else:
            paragraph = g['text'] + ' ' + message.text
            db.set_text(g['gid'], paragraph)

            p = db.get_player_by_addr(sender.addr)
            assert p is not None
            if p['round'] == 3:
                db.delete_player(p['addr'])
            else:
                db.set_player(p['addr'], p['round'] + 1, g['gid'])

            p = get_by_round(g['gid'])

            if p is None:  # End Game
                text = end_game(g['gid'])
                replies.add(text=text, chat=dbot.get_chat(g['gid']))
            else:
                db.set_turn(g['gid'], p['addr'])
                run_turn(p, dbot.get_chat(g['gid']), paragraph)
        return True


# ======== Commands ===============

def cmd_new(command: IncomingCommand, replies: Replies) -> None:
    """Start a new game of Exquisite Corpse.

    Example: `/corpse_new`
    """
    sender = command.message.get_sender_contact()

    if not command.message.chat.is_group():
        replies.add(text='❌ This is not a group.')
        return
    if db.get_player_by_addr(sender.addr):
        text = "❌ You are already playing another game.\n"
        replies.add(text=text)
        return

    gid = command.message.chat.id
    g = db.get_game_by_gid(gid)
    if g:
        replies.add(
            text='❌ There is a game already running in this group.')
        return

    db.add_game(gid)
    db.add_player(sender.addr, 1, gid)
    replies.add(text=show_status(gid))


def cmd_join(command: IncomingCommand, replies: Replies) -> None:
    """Join in a Exquisite Corpse game

    Example: `/corpse_join`
    """
    sender = command.message.get_sender_contact()
    gid = command.message.chat.id
    g = db.get_game_by_gid(gid)

    if not command.message.chat.is_group():
        replies.add(text='❌ This is not a group.')
        return
    if g is None:
        replies.add(text='❌ There is not a game running in this group.')
        return

    player = db.get_player_by_addr(sender.addr)
    if player:
        if player['game'] == g['gid']:
            replies.add(text='❌ You already joined this game.')
        else:
            replies.add(
                text='❌ You are already playing in another group.')
        return

    if g['turn'] and db.get_player_by_addr(g['turn'])['round'] != 1:
        replies.add(
            text="⌛ Too late!!! You can't join the game at this time")
        return

    db.add_player(sender.addr, 1, gid)
    replies.add(text=show_status(gid, g['turn']))


def cmd_start(command: IncomingCommand, replies: Replies) -> None:
    """Start Exquisite Corpse game

    Example: `/corpse_start`
    """
    gid = command.message.chat.id
    g = db.get_game_by_gid(gid)

    if not command.message.chat.is_group():
        replies.add(text='❌ This is not a group.')
        return
    if g is None:
        replies.add(text='❌ There is not game created in this group.')
        return
    if g['turn']:
        text = '❌ Game already started.'
        replies.add(text=text)
        return
    if len(db.get_players(gid)) <= 1:
        replies.add(text='❌ There is not sufficient players')
        return

    db.set_text(gid, '')
    player = get_by_round(gid)
    assert player is not None
    db.set_turn(gid, player['addr'])
    run_turn(player, command.message.chat, '')


def cmd_end(command: IncomingCommand, replies: Replies) -> None:
    """End Exquisite Corpse game

    Example: `/corpse_end`
    """
    replies.add(text=end_game(command.message.chat.id))


def cmd_leave(command: IncomingCommand, replies: Replies) -> None:
    """Leave Exquisite Corpse game in current group.

    Example: `/corpse_leave`
    """
    p = db.get_player_by_addr(command.message.get_sender_contact().addr)
    if p:
        remove_from_game(p, db.get_game_by_gid(p['game']))
    else:
        replies.add(text='❌ You are not playing Exquisite Corpse.')



def cmd_status(command: IncomingCommand, replies: Replies) -> None:
    """Show the game status.

    Example: `/corpse_status`
    """
    if not command.message.chat.is_group():
        replies.add(text='❌ This is not a group.')
        return

    g = db.get_game_by_gid(command.message.chat.id)
    if g:
        replies.add(text=show_status(g['gid'], g['turn']))
    else:
        replies.add(text='❌ No game running in this group.')


# ======== Utilities ===============

def get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))


def run_turn(player: sqlite3.Row, group: Chat, paragraph: str) -> None:
    contact = dbot.get_contact(player['addr'])
    text = ec + "⏳ Round {}/3\n\n{}, it's your turn...".format(
        player['round'], contact.name)
    group.send_text(text)

    if paragraph:
        text = ec + '📝 Complete the phrase:\n...{}\n\n'.format(
            ' '.join(paragraph.rsplit(maxsplit=5)[-5:]))
    else:
        text = ec + '📝 You are the first!\nSend a message with at least 10 words.'

    dbot.get_chat(contact).send_text(text)


def show_status(gid: int, turn: str = None) -> str:
    contacts = db.get_players(gid)
    text = ec + '👤 Players({}):\n'.format(len(contacts))

    if turn:
        fstr = '• {} ({})\n'
    else:
        fstr = '• {0}\n'
    for c in contacts:
        text += fstr.format(dbot.get_contact(c['addr']).name, c['round'])

    text += '\n'
    if turn:
        text += "Turn: {}".format(dbot.get_contact(turn).name)
    else:
        text += 'Waiting for players...\n\n/corpse_join  /corpse_start'

    return text


def get_by_round(gid: int) -> Optional[sqlite3.Row]:
    round = 1
    p = db.get_player_by_round(gid, round)
    while p is None and round < 3:
        round += 1
        p = db.get_player_by_round(gid, round)
    return p


def end_game(gid: int) -> str:
    g = db.get_game_by_gid(gid)
    assert g is not None
    text = ec
    if g['text']:
        text += '⌛ Game finished!\n📜 The result is:\n' + g['text']
    else:
        text += '❌ Game aborted'
    db.delete_game(gid)
    return text + '\n\n▶️ Play again? /corpse_new'


def remove_from_game(player, game) -> None:
    db.delete_player(player['addr'])
    if player['addr'] == game['turn']:
        p = get_by_round(player['game'])
        chat = dbot.get_chat(player['game'])
        if p is None or len(db.get_players(player['game'])) <= 1:
            chat.send_text(end_game(player['game']))
        else:
            db.set_turn(player['game'], p['addr'])
            run_turn(p, chat, game['text'])
    else:
        chat.send_text(game['gid'], game['turn'])

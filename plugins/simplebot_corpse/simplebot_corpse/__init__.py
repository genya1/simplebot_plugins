
import os
import sqlite3
from typing import Optional

import simplebot
from deltachat import Chat, Contact, Message
from simplebot import DeltaBot
from simplebot.bot import Replies

from .db import DBManager

__version__ = '1.0.0'
db: DBManager
ec = '💀 Exquisite Corpse\n\n'


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global db
    db = _get_db(bot)


# pylama:ignore=W0613
@simplebot.hookimpl
def deltabot_member_removed(bot: DeltaBot, chat: Chat, contact: Contact,
                            replies: Replies) -> None:
    g = db.get_game_by_gid(chat.id)
    if not g:
        return
    if bot.self_contact == contact or len(chat.get_contacts()) <= 1:
        db.delete_game(chat.id)
        return

    p = db.get_player_by_addr(contact.addr)
    if p is not None and p['game'] == g['gid']:
        _remove_from_game(bot, p, g)


@simplebot.filter(name=__name__)
def filter_messages(bot: DeltaBot, message: Message, replies: Replies) -> None:
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

            p = _get_by_round(g['gid'])

            if p is None:  # End Game
                text = _end_game(g['gid'])
                replies.add(text=text, chat=bot.get_chat(g['gid']))
            else:
                db.set_turn(g['gid'], p['addr'])
                _run_turn(bot, p, bot.get_chat(g['gid']), paragraph)


@simplebot.command
def corpse_new(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Start a new game of Exquisite Corpse.

    Example: `/corpse_new`
    """
    sender = message.get_sender_contact()

    if not message.chat.is_group():
        replies.add(text='❌ This is not a group.')
        return
    if db.get_player_by_addr(sender.addr):
        text = "❌ You are already playing another game.\n"
        replies.add(text=text)
        return

    gid = message.chat.id
    g = db.get_game_by_gid(gid)
    if g:
        replies.add(
            text='❌ There is a game already running in this group.')
        return

    db.add_game(gid)
    db.add_player(sender.addr, 1, gid)
    replies.add(text=_show_status(bot, gid))


@simplebot.command
def corpse_join(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Join in a Exquisite Corpse game

    Example: `/corpse_join`
    """
    sender = message.get_sender_contact()
    gid = message.chat.id
    g = db.get_game_by_gid(gid)

    if not message.chat.is_group():
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
    replies.add(text=_show_status(bot, gid, g['turn']))


@simplebot.command
def corpse_start(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Start Exquisite Corpse game

    Example: `/corpse_start`
    """
    gid = message.chat.id
    g = db.get_game_by_gid(gid)

    if not message.chat.is_group():
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
    player = _get_by_round(gid)
    assert player is not None
    db.set_turn(gid, player['addr'])
    _run_turn(bot, player, message.chat, '')


@simplebot.command
def corpse_end(message: Message, replies: Replies) -> None:
    """End Exquisite Corpse game

    Example: `/corpse_end`
    """
    replies.add(text=_end_game(message.chat.id))


@simplebot.command
def corpse_leave(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Leave Exquisite Corpse game in current group.

    Example: `/corpse_leave`
    """
    p = db.get_player_by_addr(message.get_sender_contact().addr)
    if p:
        _remove_from_game(bot, p, db.get_game_by_gid(p['game']))
    else:
        replies.add(text='❌ You are not playing Exquisite Corpse.')


@simplebot.command
def corpse_status(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Show the game status.

    Example: `/corpse_status`
    """
    if not message.chat.is_group():
        replies.add(text='❌ This is not a group.')
        return

    g = db.get_game_by_gid(message.chat.id)
    if g:
        replies.add(text=_show_status(bot, g['gid'], g['turn']))
    else:
        replies.add(text='❌ No game running in this group.')


def _get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))


def _run_turn(bot: DeltaBot, player: sqlite3.Row, group: Chat, paragraph: str) -> None:
    contact = bot.get_contact(player['addr'])
    text = ec + "⏳ Round {}/3\n\n{}, it's your turn...".format(
        player['round'], contact.name)
    group.send_text(text)

    if paragraph:
        text = ec + '📝 Complete the phrase:\n...{}\n\n'.format(
            ' '.join(paragraph.rsplit(maxsplit=5)[-5:]))
    else:
        text = '📝 You are the first!\nSend a message with at least 10 words.'
        text = ec + text

    bot.get_chat(contact).send_text(text)


def _show_status(bot: DeltaBot, gid: int, turn: str = None) -> str:
    contacts = db.get_players(gid)
    text = ec + '👤 Players({}):\n'.format(len(contacts))

    if turn:
        fstr = '• {} ({})\n'
    else:
        fstr = '• {0}\n'
    for c in contacts:
        text += fstr.format(bot.get_contact(c['addr']).name, c['round'])

    text += '\n'
    if turn:
        text += "Turn: {}".format(bot.get_contact(turn).name)
    else:
        text += 'Waiting for players...\n\n/corpse_join  /corpse_start'

    return text


def _get_by_round(gid: int) -> Optional[sqlite3.Row]:
    turn = 1
    p = db.get_player_by_round(gid, turn)
    while p is None and turn < 3:
        turn += 1
        p = db.get_player_by_round(gid, turn)
    return p


def _end_game(gid: int) -> str:
    g = db.get_game_by_gid(gid)
    assert g is not None
    text = ec
    if g['text']:
        text += '⌛ Game finished!\n📜 The result is:\n' + g['text']
    else:
        text += '❌ Game aborted'
    db.delete_game(gid)
    return text + '\n\n▶️ Play again? /corpse_new'


def _remove_from_game(bot: DeltaBot, player: sqlite3.Row, game: sqlite3.Row) -> None:
    db.delete_player(player['addr'])
    if player['addr'] == game['turn']:
        p = _get_by_round(player['game'])
        chat = bot.get_chat(player['game'])
        if p is None or len(db.get_players(player['game'])) <= 1:
            chat.send_text(_end_game(player['game']))
        else:
            db.set_turn(player['game'], p['addr'])
            _run_turn(bot, p, chat, game['text'])
    else:
        chat.send_text(game['gid'], game['turn'])

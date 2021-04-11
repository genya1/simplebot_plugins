
import os
import re

import simplebot
from deltachat import Chat, Contact, Message
from simplebot import DeltaBot
from simplebot.bot import Replies

from .db import DBManager
from .game import BLACK, WHITE, Board

__version__ = '1.0.0'
DBASE: DBManager


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global DBASE
    DBASE = _get_db(bot)


@simplebot.hookimpl
def deltabot_member_removed(bot: DeltaBot, chat: Chat, contact: Contact) -> None:
    game = DBASE.get_game_by_gid(chat.id)
    if game:
        player1, player2 = game['p1'], game['p2']
        if contact.addr in (bot.self_contact.addr, player1, player2):
            DBASE.delete_game(player1, player2)
            if contact != bot.self_contact:
                chat.remove_contact(bot.self_contact)

@staticmethod
def valid_message_text(message_text) -> bool:
    """Utility method to check whether inputted message text is valid
    """
    message_text_length = len(message_text)
    return message_text_length < 2 or message_text_length > 14 or not message_text_length % 2 == 0 or \
       not message_text.isalnum() or message_text.isalpha() or message_text.isdigit()

@simplebot.filter(name=__name__)
def filter_messages(message: Message, replies: Replies) -> None:
    """Process move coordinates in Checkers game groups
    """
    if not valid_message_text(message.text):
        return
    game = DBASE.get_game_by_gid(message.chat.id)
    if game is None or game['board'] is None:
        return

    board = Board(game['board'])
    player = message.get_sender_contact().addr
    player = BLACK if game['black'] == player else WHITE
    if board.turn == player:
        try:
            input_positions = re.findall('..?', message.text)
            input_positions_len = len(input_positions)
            for index, position in enumerate(input_positions):
                next_index = index + 1
                if input_positions_len == 2:
                    board.move(position)
                elif next_index < input_positions_len:
                    board.move("{}{}".format(position, input_positions[next_index]))

            DBASE.set_board(game['p1'], game['p2'], board.export())
            replies.add(text=_run_turn(message.chat.id))
        except ValueError:
            replies.add(text='❌ Invalid move!')


@simplebot.command
def checkers_play(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
    """Invite a friend to play Checkers.

    Example: `/checkers_play friend@example.com`
    """
    if not payload:
        replies.add(text="Missing address")
        return

    if payload == bot.self_contact.addr:
        replies.add(text="Sorry, I don't want to play")
        return

    player1 = message.get_sender_contact().addr
    player2 = payload
    if player1 == player2:
        replies.add(text="You can't play with yourself")
        return

    game = DBASE.get_game_by_players(player1, player2)

    if game is None:  # first time playing with player2
        board = Board()
        chat = bot.create_group('🔴 {} 🆚 {} [checkers]'.format(
            player1, player2), [player1, player2])
        DBASE.add_game(player1, player2, chat.id, board.export(), player1)
        text = 'Hello {1},\nYou have been invited by {0} to play Checkers'
        text += '\n\n{2}: {0}\n{3}: {1}\n\n'
        text = text.format(player1, player2, board.get_disc(BLACK),
                           board.get_disc(WHITE))
        replies.add(text=text + _run_turn(chat.id), chat=chat)
    else:
        text = 'You already have a game group with {}'.format(player2)
        replies.add(text=text, chat=bot.get_chat(game['gid']))


@simplebot.command
def checkers_surrender(message: Message, replies: Replies) -> None:
    """End the Checkers game in the group it is sent.
    """
    game = DBASE.get_game_by_gid(message.chat.id)
    loser = message.get_sender_contact().addr
    # this is not your game group
    if game is None or loser not in (game['p1'], game['p2']):
        replies.add(text='This is not your game group')
    elif game['board'] is None:
        replies.add(text='There is no game running')
    else:
        DBASE.set_board(game['p1'], game['p2'], None)
        text = '🏳️ Game Over.\n{} surrenders.\n\n▶️ Play again? /checkers_new'
        replies.add(text=text.format(loser))


@simplebot.command
def checkers_new(message: Message, replies: Replies) -> None:
    """Start a new Checkers game in the current game group.
    """
    sender = message.get_sender_contact().addr
    game = DBASE.get_game_by_gid(message.chat.id)
    if game is None or sender not in (game['p1'], game['p2']):
        replies.add(text='This is not your game group')
    elif game['board'] is None:
        board = Board()
        DBASE.set_game(game['p1'], game['p2'], board.export(), sender)
        player2 = game['p2'] if sender == game['p1'] else game['p1']
        text = 'Game started!\n{}: {}\n{}: {}\n\n'.format(
            board.get_disc(BLACK), sender, board.get_disc(WHITE), player2)
        replies.add(text=text + _run_turn(message.chat.id))
    else:
        replies.add(text='There is a game running already')


@simplebot.command
def checkers_repeat(message: Message, replies: Replies) -> None:
    """Send game board again.
    """
    replies.add(text=_run_turn(message.chat.id))


def _run_turn(gid: int) -> str:
    game = DBASE.get_game_by_gid(gid)
    if not game:
        return 'This is not your game group'
    board = Board(game['board'])
    if not game['board']:
        return 'There is no game running'
    result = board.result()
    if result == -1:
        if board.turn == BLACK:
            turn = '{} {}'.format(board.get_disc(BLACK), game['black'])
        else:
            player2 = game['p2'] if game['black'] == game['p1'] else game['p1']
            turn = '{} {}'.format(board.get_disc(WHITE), player2)
        text = "{} it's your turn...\n\n{}".format(turn, board)
    else:
        DBASE.set_board(game['p1'], game['p2'], None)
        if result == 0:
            text = '🤝 Game over.\nIt is a draw!'
        else:
            if result == BLACK:
                winner = '{} {}'.format(board.get_disc(BLACK), game['black'])
            else:
                if game['black'] == game['p1']:
                    player2 = game['p2']
                else:
                    player2 = game['p1']
                winner = '{} {}'.format(board.get_disc(WHITE), player2)
            text = '🏆 Game over.\n{} Wins!!!'.format(winner)
        text += '\n\n{}\n\n▶️ Play again? /checkers_new'.format(board)
    return text


def _get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, 'sqlite.db'))

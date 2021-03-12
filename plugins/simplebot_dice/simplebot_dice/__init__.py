import random

import simplebot
from deltachat import Message
from simplebot.bot import Replies

__version__ = '1.0.0'
DICES = ('⚀', '⚁', '⚂', '⚃', '⚄', '⚅')


@simplebot.command
def dice(payload: str, message: Message, replies: Replies) -> None:
    """Roll a dice.
    """
    _roll_dice(int(payload or 1), message, replies)


@simplebot.command
def dice2(message: Message, replies: Replies) -> None:
    """Roll two dices.
    """
    _roll_dice(2, message, replies)


@simplebot.command
def dice5(message: Message, replies: Replies) -> None:
    """Roll five dices.
    """
    _roll_dice(5, message, replies)


def _roll_dice(count: int, quote: Message, replies: Replies) -> None:
    dices = []
    total = 0
    for _ in range(count):
        rand = random.randrange(0, 6)
        total += rand + 1
        dices.append(DICES[rand])
    replies.add(
        text='{} ({})'.format(' '.join(dices), total), quote=quote)

import random

from deltachat import Message
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

version = '1.0.0'
DICES = ('⚀', '⚁', '⚂', '⚃', '⚄', '⚅')


@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    bot.commands.register(name="/dice", func=cmd_dice)
    bot.commands.register(name="/dice2", func=cmd_dice2)
    bot.commands.register(name="/dice5", func=cmd_dice5)


def cmd_dice(command: IncomingCommand, replies: Replies) -> None:
    """Roll a dice.
    """
    _roll_dice(int(command.payload or 1), command.message, replies)


def cmd_dice2(command: IncomingCommand, replies: Replies) -> None:
    """Roll two dices.
    """
    _roll_dice(2, command.message, replies)


def cmd_dice5(command: IncomingCommand, replies: Replies) -> None:
    """Roll five dices.
    """
    _roll_dice(5, command.message, replies)


def _roll_dice(count: int, quote: Message, replies: Replies) -> None:
    dices = []
    total = 0
    for i in range(count):
        rand = random.randrange(0, 6)
        total += rand + 1
        dices.append(DICES[rand])
    replies.add(
        text='{} ({})'.format(' '.join(dices), total), quote=quote)

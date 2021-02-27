import json
from threading import Thread

from howdoi.howdoi import howdoi
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

__version__ = '1.0.0'


@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    bot.commands.register(name="/howdoi", func=cmd_howdoi)


def cmd_howdoi(command: IncomingCommand, replies: Replies) -> None:
    """Instant coding answers. Example: /howdoi format date bash
    """
    Thread(target=_howdoi, args=(command,), daemon=True).start()


def _howdoi(command: IncomingCommand) -> None:
    try:
        res = json.loads(howdoi("{} -j".format(command.payload)))[0]
        text = '{}\n\n↗️ {}'.format(res['answer'], res['link'])
    except Exception as ex:
        command.bot.logger.exception(ex)
        text = 'Something went wrong.'
    command.message.chat.send_text(text)

import json
from threading import Thread

from simplebot.hookspec import deltabot_hookimpl

from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand

from howdoi.howdoi import howdoi

version = '1.0.0'


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

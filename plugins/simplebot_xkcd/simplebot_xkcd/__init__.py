
import io
from urllib.request import urlopen

import xkcd
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

version = '1.0.0'


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    bot.commands.register(name='/xkcd', func=cmd_xkcd)
    bot.commands.register(name='/xkcdlatest', func=cmd_latest)


# ======== Commands ===============

def cmd_xkcd(command: IncomingCommand, replies: Replies) -> None:
    """Show the comic with the given number or a ramdom comic if no number is provided.
    """
    if command.payload:
        comic = xkcd.getComic(int(command.payload))
    else:
        comic = xkcd.getRandomComic()
    replies.add(**get_reply(comic))


def cmd_latest(command: IncomingCommand, replies: Replies) -> None:
    """Get the latest comic released in xkcd.com.
    """
    replies.add(**get_reply(xkcd.getLatestComic()))


# ======== Utilities ===============

def get_reply(comic: xkcd.Comic) -> dict:
    image = urlopen(comic.imageLink).read()
    text = '#{} - {}\n\n{}'.format(
        comic.number, comic.title, comic.altText)
    return dict(text=text, filename=comic.imageName,
                bytefile=io.BytesIO(image))

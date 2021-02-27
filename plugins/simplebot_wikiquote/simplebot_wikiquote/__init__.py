
from random import choice

from simplebot.hookspec import deltabot_hookimpl
import wikiquote as wq

from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand


version = '1.0.0'


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    bot.commands.register(name="/quote", func=cmd_quote)


# ======== Commands ===============

def cmd_quote(command: IncomingCommand, replies: Replies) -> None:
    """Get Wikiquote quotes.

    Search in Wikiquote or get the quote of the day if no text is given.
    Example: `/quote Richard Stallman`
    """
    locale = get_locale(
        command.bot, command.message.get_sender_contact().addr)
    if locale in wq.supported_languages():
        lang = locale
    else:
        lang = None
    if command.payload:
        authors = wq.search(command.payload, lang=lang)
        if authors:
            if command.payload.lower() == authors[0].lower():
                author = authors[0]
            else:
                author = choice(authors)
            quote = '"{}"\n\n― {}'.format(
                choice(wq.quotes(author, max_quotes=200, lang=lang)), author)
        else:
            quote = 'No quote found for: {}'.format(command.payload)
    else:
        quote = '"{}"\n\n― {}'.format(*wq.quote_of_the_day(lang=lang))

    replies.add(text=quote)


# ======== Utilities ===============

def get_locale(bot, addr: str) -> str:
    return bot.get('locale', scope=addr) or bot.get('locale') or 'en'

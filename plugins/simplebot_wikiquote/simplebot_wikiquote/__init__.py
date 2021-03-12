
from random import choice

import simplebot
import wikiquote as wq
from deltachat import Message
from simplebot import DeltaBot
from simplebot.bot import Replies

__version__ = '1.0.0'


@simplebot.command(name='/quote')
def cmd_quote(bot: DeltaBot, payload: str, message: Message,
              replies: Replies) -> None:
    """Get Wikiquote quotes.

    Search in Wikiquote or get the quote of the day if no text is given.
    Example: `/quote Richard Stallman`
    """
    locale = _get_locale(bot, message.get_sender_contact().addr)
    if locale in wq.supported_languages():
        lang = locale
    else:
        lang = None
    if payload:
        authors = wq.search(payload, lang=lang)
        if authors:
            if payload.lower() == authors[0].lower():
                author = authors[0]
            else:
                author = choice(authors)
            quote = '"{}"\n\n― {}'.format(
                choice(wq.quotes(author, max_quotes=200, lang=lang)), author)
        else:
            quote = 'No quote found for: {}'.format(payload)
    else:
        quote = '"{}"\n\n― {}'.format(*wq.quote_of_the_day(lang=lang))

    replies.add(text=quote)


def _get_locale(bot, addr: str) -> str:
    return bot.get('locale', scope=addr) or bot.get('locale') or 'en'

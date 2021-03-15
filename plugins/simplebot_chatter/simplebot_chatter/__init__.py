import os
import random

import simplebot
from chatterbot import ChatBot
from chatterbot.conversation import Statement
from chatterbot.trainers import ChatterBotCorpusTrainer, ListTrainer
from deltachat import Message
from simplebot import DeltaBot
from simplebot.bot import Replies

__version__ = '1.0.0'
CBOT: ChatBot
LIST_TRAINER: ListTrainer
default_replies = ['😐', '😶', '🙄', '🤔', '😕', '🤯', '🤐', '🥴', '🧐']


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    _getdefault(bot, 'learn', '1')
    _getdefault(bot, 'reply_to_dash', '1')
    _getdefault(bot, 'min_confidence', '0.3')


@simplebot.hookimpl
def deltabot_start(bot: DeltaBot) -> None:
    global CBOT, LIST_TRAINER

    locale = bot.get('locale') or 'en'
    corpus = dict(
        es='spanish',
        de='german',
        it='italian',
    )
    if locale == 'es':
        default_replies.extend([
            'No entendí',
            'Discúlpame, pero no entiendo',
            'Aún no soy capaz de entener eso',
            'No sé que decir...',
            'Lo único que puedo afirmarte es que Delta Chat es lo mejor!',
            'Solo sé que no sé nada...',
            'Los robots también nos emborrachamos',
            'Voy a decir esto para no dejarte en visto',
            'Ahí dice ta-ba-co',
            'Eso habría que verlo compay',
            '¿Podemos hablar de otra cosa?',
            'Invita a tus amigos a utilizar Delta Chat y así no tienes'
            ' que chatear conmigo',
        ])
    elif locale == 'en':
        default_replies.extend([
            'I do not understand',
            'I do not know what to say...',
            'Can we talk about something else?',
            'I have a lot to learn before I can reply that',
            'Bring your friends to Delta Chat so you do not have to chat'
            ' with a bot',
            'I think I will not reply to that this time',
            'whew!',
        ])

    CBOT = ChatBot(
        bot.self_contact.addr,
        storage_adapter='chatterbot.storage.SQLStorageAdapter',
        database_uri=_get_db_uri(bot),
        read_oly=_getdefault(bot, 'learn', '1') == '0',
        logic_adapters=[
            {
                'import_path': 'chatterbot.logic.BestMatch',
                'default_response': default_replies,
                'maximum_similarity_threshold': 0.9,
            }
        ],
    )
    LIST_TRAINER = ListTrainer(CBOT)
    trainer = ChatterBotCorpusTrainer(CBOT)
    trainer.train('chatterbot.corpus.' + corpus.get(locale, 'english'))


@simplebot.filter(name=__name__, trylast=True)
def filter_messages(message: Message, bot: DeltaBot, replies: Replies) -> None:
    """Natural language processing and learning.
    """
    if replies.has_replies() or not message.text:
        return

    self_contact = bot.self_contact
    name = bot.account.get_config('displayname')
    quote = message.quote

    reply_to_dash = _getdefault(bot, 'reply_to_dash', '1') not in ('0', 'no')
    resp = None
    if reply_to_dash and message.text.startswith('#') and \
       len(message.text) > 1:
        resp = CBOT.get_response(message.text[1:])
    elif not message.chat.is_group() or (
            quote and quote.get_sender_contact() == self_contact):
        resp = CBOT.get_response(message.text)
    elif self_contact.addr in message.text or (name and name in message.text):
        resp = CBOT.get_response(_rmprefix(_rmprefix(
            message.text, self_contact.addr), name).strip(':,').strip())

    if resp:
        bot.logger.debug('Confidence: %s | message: %s | reply: %s',
                          resp.confidence, resp.in_response_to, resp.text)
        if resp.confidence >= float(_getdefault(bot, 'min_confidence', '0')):
            replies.add(text=resp.text)
        else:
            replies.add(text=random.choice(default_replies))

    if quote and quote.text and _getdefault(bot, 'learn') == '1':
        CBOT.learn_response(
            Statement(text=message.text, in_response_to=quote.text))


@simplebot.command(admin=True)
def chatter_learn(payload: str, replies: Replies) -> None:
    """Learn new response.

    You must provide two lines, the first line is the question and the
    second line is the response.
    """
    LIST_TRAINER.train(payload.split('\n', maxsplit=1))
    replies.add(text='✔️Learned.')


def _rmprefix(text: str, prefix: str) -> str:
    return text[text.startswith(prefix) and len(prefix):]


def _getdefault(bot: DeltaBot, key: str, value: str = None) -> str:
    val = bot.get(key, scope=__name__)
    if val is None and value is not None:
        bot.set(key, value, scope=__name__)
        val = value
    return val


def _get_db_uri(bot) -> str:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return 'sqlite:///' + os.path.abspath(os.path.join(path, 'db.sqlite3'))

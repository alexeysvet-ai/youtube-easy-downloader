from config import BOT_CODE
from bot_core.utils import log
from texts import TEXTS
from bot_core.user_settings import get_user_lang

user_lang = {}


def t(key, user_id):
    lang = user_lang.get(user_id)

    if not lang:
        try:
            lang = get_user_lang(BOT_CODE, user_id)
            if lang:
                user_lang[user_id] = lang
                log(f"[DB LANG LOAD OK] bot_code={BOT_CODE} user_id={user_id} lang={lang}")
        except Exception as e:
            log(f"[DB LANG LOAD ERROR] bot_code={BOT_CODE} user_id={user_id} error={e}")

    return TEXTS[key][lang or "ru"]
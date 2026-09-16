import asyncio
import base64
import hashlib
import logging
import re
import time
import unicodedata
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from .config import Settings
from .models import (
    ModerationAction,
    ModerationContext,
    ModerationDecision,
    Signal,
)

logger = logging.getLogger(__name__)


ADULT_TERMS = (
    "18+",
    "🔞",
    "seks",
    "sex",
    "sexual",
    "porno",
    "porn",
    "xxx",
    "nude",
    "nudes",
    "yalang'och",
    "yalangoch",
    "behayo",
    "intim",
    "erotik",
    "escort",
    "onlyfans",
    "секс",
    "порно",
    "интим",
    "голая",
    "обнажен",
    "эротик",
)

# Xabarning o'zida ishlatilgan haqorat va so'kishlar. Har bir ifodaning yonidagi
# nom faqat admin panelida sababni tushunarli ko'rsatish uchun ishlatiladi.
# So'z chegaralari oddiy so'zlarning ichidan tasodifiy moslik chiqishini kamaytiradi.
PROFANITY_PATTERNS = (
    (r"\bharom(?:i|ilar|isan|isiz|ijon|ijonlar)?\b", "harom/haromi"),
    (r"\b(?:kot|qot)(?:ing|ingiz|san|siz|lar)?\b", "qo'pol haqorat"),
    (r"\b(?:ahmoq|tentak|ablah|landovur|itvachcha|lanati|yaramas)\w*\b", "haqorat"),
    (r"\b(?:qanjiq|fohisha)\w*\b", "og'ir haqorat"),
    (r"\b(?:gandini|gandingni|gandinga)\b", "og'ir haqorat"),
    (r"\b(?:onangni|onangga|onangdan)\b", "oilaga qaratilgan haqorat"),
    (
        r"\b(?:pidar|pidor|dalban|zaybal|zaybl|zaebal|yeban|d+i+n+a+xuy|xuy)\w*\b",
        "so'kish",
    ),
    (r"\b(?:пидор|ебан|хуй|шлюх)\w*\b", "ruscha so'kish"),
    (r"\b(?:fuck|bitch|asshole|motherfucker)\w*\b", "inglizcha so'kish"),
)

# Qo'lda tekshirilgan variantlar faqat to'liq so'z yoki to'liq ibora sifatida
# qidiriladi. Masalan, alohida "am" bu ro'yxatda yo'q: u "ham", "salom" yoki
# "amaliyot" kabi begunoh so'zlarni noto'g'ri belgilamasligi kerak.
PROFANITY_VARIANTS = (
    ("siktir", ("siktir", "siktr", "sktir", "sktr", "siktirr", "siiktir", "s1ktir", "sikt1r", "s1kt1r", "s!ktir", "s.i.k.t.i.r", "s-i-k-t-i-r")),
    ("siktim", ("siktim", "siktm", "sktim", "sktm", "siktimm", "siiktim", "s1ktim", "sikt1m", "s1kt1m", "s!ktim", "s.i.k.t.i.m", "s-i-k-t-m")),
    ("sikdim", ("sikdim", "sikdm", "skdim", "skdm", "sikdimm", "siikdim", "s1kdim", "sikd1m", "s1kd1m", "s!kdim", "s.i.k.d.i.m", "s-i-k-d-m")),
    ("sikaman", ("sikaman", "sikamn", "sikman", "skaman", "skamn", "sikamann", "siikaman", "s1kaman", "s!kaman", "s.i.k.a.m.a.n", "s-i-k-a-m-a-n")),
    ("sikish", ("sikish", "siksh", "skish", "sksh", "sikishh", "siikish", "s1kish", "sik1sh", "s1k1sh", "s!kish", "s.i.k.i.s.h", "s-i-k-i-sh")),
    ("sikib", ("sikib", "sikb", "skib", "skb", "sikibb", "siikib", "s1kib", "sik1b", "s1k1b", "s!kib", "s.i.k.i.b", "s-i-k-i-b")),
    ("sikilgan", ("sikilgan", "sikilgn", "siklgan", "skilgan", "sikilgann", "s1kilgan", "sik1lgan", "s!kilgan", "s.i.k.i.l.g.a.n")),
    ("sikey", ("sikey", "sikeyy", "siikey", "skey", "sike", "sikeyin", "sikeyn", "s1key", "s!key", "s.i.k.e.y")),
    ("sikay", ("sikay", "sikayy", "siikay", "skay", "sikayin", "sikayn", "s1kay", "s!kay", "s.i.k.a.y")),
    ("sikvoraman", ("sikvoraman", "sikvoramn", "skvoraman", "skvoramn", "sikvoramann", "s1kvoraman", "sikv0raman", "s!kvoraman", "s.i.k.v.o.r.a.m.a.n")),
    ("sikvordim", ("sikvordim", "sikvordm", "skvordim", "skvordm", "sikvordimm", "s1kvordim", "sikv0rdim", "sikvord1m", "s.i.k.v.o.r.d.i.m")),
    ("siktirvor", ("siktirvor", "siktrvor", "sktirvor", "sktrvor", "siktirvorr", "s1ktirvor", "sikt1rvor", "siktirv0r", "s.i.k.t.i.r.v.o.r")),
    ("siktirib", ("siktirib", "siktrib", "sktirib", "sktrib", "siktiribb", "s1ktirib", "sikt1rib", "s1kt1r1b", "s.i.k.t.i.r.i.b")),
    ("amingni", ("amingni", "amingniii", "amngni", "amingn", "amigni", "am1ngni", "amingn1", "@mingni", "a.m.i.n.g.n.i", "a-m-i-n-g-n-i")),
    ("am yalagich", ("am yalagich", "amyalagich", "am yalagch", "amyalagch", "am yalag'ich", "am yalag‘ich", "@m yalagich", r"am y\@lagich")),
    ("jalab", ("jalab", "jalap", "jallab", "jallap", "jlab", "jalb", "jlap", "jalabb", "jalaab", "j4lab", r"j\@lab", r"jal\@b", r"j\@l@b", "j.a.l.a.b")),
    ("jalabcha", ("jalabcha", "jalapcha", "jalabch", "jalapch", "jlabcha", "jalabchaa", "j4labcha", r"j\@labcha", "j.a.l.a.b.c.h.a")),
    ("jalabvachcha", ("jalabvachcha", "jalabvacha", "jalapvachcha", "jalapvacha", "jalabvach", "jalapvach", "jalabvch", "jalapvch", "jlbvch", r"j\@labvachcha")),
    ("qotoq", ("qotoq", "qutoq", "qo'toq", "qo‘toq", "qoʻtoq", "kotok", "kotoq", "qtoq", "qotoqq", "qootoq", "q0toq", "qot0q", "q0t0q", "q.o.t.o.q")),
    ("qotoging", ("qotoging", "qotog'ing", "qotog‘ing", "qo'tog'ing", "qotogng", "qtoging", "qotogingg", "q0toging", "qot0ging", "qotog1ng")),
    ("qotogim", ("qotogim", "qotog'im", "qotog‘im", "qo'tog'im", "qotogm", "qtogim", "qotogimm", "q0togim", "qot0gim", "qotog1m")),
    ("qotoqbosh", ("qotoqbosh", "qotoq bosh", "qutoqbosh", "kotokbosh", "qtoqbosh", "qotoqbsh", "q0toqbosh", "qotoqb0sh", "q.o.t.o.q.b.o.s.h")),
    (
        "blyat",
        (
            "blyat", "bilyat", "bilyad", "bilya", "blyad", "blya", "blat",
            "blayt", "blayat", "bli yat", "bliat", "bliyat", "blyt", "blyatt",
            "blyadd", "bilyatt", "bilyadd", "blyaat", "b1yat", "bl1yat", "bly4t",
            "bly@t", r"bly\@t", "bl*at", "b.lyat", "b.l.y.a.t", "b-lyat",
            "b_l_y_a_t", "b lyat", "бля", "блядь", "блять", "блиат",
        ),
    ),
    ("suka", ("suka", "suuka", "sukaa", "sukaaa", "sukkа", "suk4", "suk@", "s.u.k.a", "s-u-k-a", "сука")),
    ("nahuy", ("nahuy", "naxuy", "nahui", "naxui", "nhuy", "nxuy", "naxuyy", "naaxuy", "n4xuy", r"n\@xuy", "n.a.x.u.y", "нахуй")),
    ("pizda", ("pizda", "pzda", "pizdaa", "piizda", "p1zda", "pizd4", "pizd@", "p.i.z.d.a", "p-i-z-d-a", "пизда")),
    ("pizdets", ("pizdets", "pizdes", "pizdec", "pizdet", "pzdets", "pizdts", "pizdess", "pizdeeets", "p1zdets", "pizd3ts", "пиздец")),
    ("pizdabol", ("pizdabol", "pizdabal", "pzdbol", "pizdbol", "pizdaboll", "p1zdabol", "pizdab0l", "p.i.z.d.a.b.o.l", "пиздабол", "пиздобол")),
    ("yebat", ("yebat", "ebat", "yebatt", "ebatt", "yebaat", "y3bat", r"eb\@t", "y.e.b.a.t", "e.b.a.t", "ебать")),
    ("dolbayob", ("dolbayob", "dalbayob", "dolbayop", "dalbayop", "dolboyob", "dalboyob", "dolboyop", "dalboyop", "dolboeb", "dolbaeb", "dalbaeb", "dlbayob", "dlbyob", "d0lbayob", "dolbay0b", "долбоёб", "долбоеб")),
    (
        "oilaga qaratilgan behayo haqorat",
        (
            "onangni sikay",
            "onangni sikayin",
            "onangni sikey",
            "onangni sikeyin",
            "onangni sikaman",
            "onangni siktim",
            "onangni sikdim",
            "onangni sikib tashlayman",
            "onangni sikvoraman",
            "onangni sikvordim",
            "onangni amini",
            "onangni amiga",
            "onangning ami",
            "onangning amini",
            "onang jalab",
            "onang jalap",
            "onang jallab",
            "jalab onang",
            "jalap onang",
            "onangni sikay jalab",
            "oneni sikay",
            "oneni sikey",
            "oneni sikaman",
            "oneni siktim",
            "oneni sikdim",
            "oneni amini",
            "oneni amiga",
            "oneni ami",
            "onangni skay",
            "onangni skey",
            "onangni sikamn",
            "onangni siktm",
            "onangni sikdm",
            "onangni sktm",
            "onangni skdm",
            "onani sikay",
            "onani sikey",
            "onani sikaman",
            "onani siktim",
            "onani sikdim",
            "onani amini",
            "onani amiga",
            "onangni s1kay",
            "onangni s1key",
            "onangni s1kaman",
            "onangni s1ktim",
            "onangni sikt1m",
            "onangni s1kdim",
            "onangni sikd1m",
            "onangni s!kay",
            "onangni s!ktim",
            "onangni s.i.k.a.y",
            "onangni s.i.k.t.i.m",
            "onangni s-i-k-a-y",
            "onangni s-i-k-t-i-m",
            "onangni s i k a y",
            "onangni s i k t i m",
            r"onang j\@lab",
            r"onang j\@l@b",
            "onang j4lab",
            "onangni @mini",
            "onangni am1ni",
            "онангни сикай",
            "онангни сикайин",
            "онангни сикей",
            "онангни сикейин",
            "онангни сикаман",
            "онангни сиктим",
            "онангни сикдим",
            "онангни сикиб ташлайман",
            "онангни сиквораман",
            "онангни сиквордим",
            "онангни амини",
            "онангни амига",
            "онангнинг ами",
            "онангнинг амини",
            "онанг жалаб",
            "онанг жалап",
            "онени сикай",
            "онени сикей",
            "онени сикаман",
            "онени сиктим",
            "онени сикдим",
            "онени амини",
            "онени амига",
        ),
    ),
)

SOLICITATION_PATTERNS = (
    r"\b(shaxsiy|lichka|личк[ау]|лс)\s*(ga|da|yoz|пиши|жду)",
    r"\b(profilim|профил[ье]|profile)\b.{0,25}\b(kir|link|ссылк|look|check)",
    r"\b(tanishamiz|tanishmoqchiman|знакомств|познакомимся|meet me|dm me)\b",
    r"\b(bugungi|сегодняшн)\b.{0,25}\b(obraz|образ|outfit)\b",
    r"\b(obrazi?m?|образ)\b.{0,25}\b(ma.?qulmi|yoqdimi|оцени|нравится|rate)\b",
)

KNOWN_SPAM_PATTERNS = (
    r"senga\s+qarab.{0,30}bugungi\s+obraz.{0,20}ma.?qulmi",
    r"тебе\s+нравится.{0,30}(мой|сегодняшний)\s+образ",
    r"оцени.{0,20}(мой|сегодняшний)\s+образ",
    r"check.{0,20}(my\s+)?profile.{0,20}(baby|dear|love)",
)

SCAM_PATTERNS = (
    r"\b(100\s*%|kafolatlangan|garant|гарантир)\b.{0,35}\b(foyda|daromad|прибыл|доход)\b",
    r"\b(tez|oson|быстр|л[её]гк)\w*\b.{0,20}\b(pul|daromad|деньг|заработ)\w*\b",
    r"\b(pul|деньг)\w*\b.{0,30}\b(ko.?paytir|ikki\s+baravar|удво|умнож)\w*\b",
    r"\b(seed phrase|recovery phrase|wallet|кошел[её]к)\b.{0,30}\b(yubor|send|отправ)\w*\b",
)

# Yuqori aniqlikdagi zararli fayl va ommaviy spam belgilari. Oddiy havola
# o'zicha bloklashga sabab emas; faqat xavfli fayl yoki aniq firibgarlik qolipi.
DANGEROUS_FILE_EXTENSIONS = (
    "apk", "xapk", "apks", "exe", "msi", "dmg", "bat", "cmd", "scr",
)
BINARY_LINK_RE = re.compile(
    r"\b[\w.-]+\.(?:"
    + "|".join(DANGEROUS_FILE_EXTENSIONS)
    + r")(?=$|[?#\s)\]}>!,;:]|\.(?:\s|$))",
    re.I,
)
DANGEROUS_FILE_NAME_RE = re.compile(
    r"\.(?:" + "|".join(DANGEROUS_FILE_EXTENSIONS) + r")$",
    re.I,
)
HIGH_SIGNAL_SPAM_PATTERNS = (
    r"t\.me/(?:\+|joinchat/)\S+",
    r"\b(?:free|claim|grab)\b.{0,35}\b(?:airdrop|giveaway|token|reward|bonus)\b",
    r"\b(?:btc|usdt|ton|solana|ethereum|crypto)\b.{0,35}\b(?:airdrop|claim|bonus|reward)\b",
)

PROFILE_BAIT_PATTERNS = (
    r"\b(maxfiy|yashirin|private|секретн|приватн)\w*\b.{0,35}\b(video|foto|rasm|видео|фото)\w*\b",
    r"\b(video|видео)\w*\b.{0,35}\b(shu\s+yerda|bosing|tomosha|смотри|нажми|жми)\w*\b",
    r"\b(ushbu|shu)\s+(video|видео)\w*\b.{0,45}\b(diqqat|bosing|tomosha)\w*\b",
    r"\b(profil|канал)\w*\b.{0,30}\b(kir|bosing|yoz|переход|жми|смотри)\w*\b",
)

LINK_RE = re.compile(r"(?i)(?:https?://|tg://|t\.me/|telegram\.me/|www\.)\S+")
BARE_DOMAIN_RE = re.compile(
    r"(?i)(?<![@\w])"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    # Ixtiyoriy 2+ harfli qo'shimcha gap chegarasini domen deb tanirdi:
    # "edim.Osha" va "edi.Agar". Protokolsiz domen uchun haqiqiy,
    # keng ishlatiladigan TLD bilan cheklanamiz; https:// URL alohida topiladi.
    r"(?:com|net|org|uz|ru|edu|gov|io|me|ai|app|site|online|info|biz|xyz|"
    r"dev|tech|shop|store|blog|tv|co|uk|us|de|fr|kz|in|tr|cn|jp|xn--[a-z0-9-]{2,59})"
    r"(?![\w-])"
    r"(?:/[^\s]*)?"
)
USERNAME_RE = re.compile(r"(?<!\w)@[a-zA-Z][a-zA-Z0-9_]{3,}")

PROHIBITED_EMOJI_SINGLES = (
    "🍆", "🍑", "🍌", "🌭", "🌶", "🥕", "🍒", "🍈", "🥜", "🥥",
    "🍩", "🍯", "🖕", "👅", "👄", "💋", "💦", "🕳", "👉", "🤏",
    "🥵", "😈", "😏", "🤤", "🤬", "👿", "💢", "💩", "🚽", "🧻",
    "🗑", "🤡", "🐓", "🐖", "🐕", "🫏", "🐐", "🐍", "🐀", "🪳",
    "🫦", "🔞", "🛏", "🚫", "🧠", "❌", "🦂", "☠",
    "🤢", "🤮", "🥴",
)
PROHIBITED_EMOJI_COMBINATIONS = (
    "👉🤏💦", "🤤🤬👿", "👅💦", "🍑💦", "😏🍑", "😈🍆",
    "🚫🤬", "🧠❌", "🚫🍑", "🚫🍆", "🤬🖕",
)
PROHIBITED_EMOJI_PATTERNS = tuple(
    sorted(
        set(PROHIBITED_EMOJI_COMBINATIONS + PROHIBITED_EMOJI_SINGLES),
        key=len,
        reverse=True,
    )
)
EMOJI_BAN_AFTER_COUNT = 3

# Bu belgilar o'zicha qoidabuzarlik emas. Ular faqat haqiqiy spam, 18+ yoki
# haqorat signali topilganda umumiy riskni kuchaytiradi.
SUPPORTING_SIGNAL_CODES = frozenset(
    {
        "duplicate",
        "mass_duplicate",
        "coordinated_spam",
        "rapid_comment",
        "random_personal_channel",
    }
)


def _matched_patterns(text: str, patterns: Tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def is_dangerous_file_name(value: str) -> bool:
    return bool(DANGEROUS_FILE_NAME_RE.search((value or "").strip()))


def contains_dangerous_file_link(value: str) -> bool:
    return bool(BINARY_LINK_RE.search(value or ""))


def contains_link_or_username(value: str) -> bool:
    """Oddiy URL, protokolsiz domen yoki Telegram @username'ini topadi."""
    text = value or ""
    return bool(
        LINK_RE.search(text)
        or BARE_DOMAIN_RE.search(text)
        or USERNAME_RE.search(text)
    )


def _mentions(text: str) -> List[str]:
    return sorted({match.group(0) for match in USERNAME_RE.finditer(text)})


def prohibited_emoji_count(value: str) -> int:
    """Taqiqlangan emoji va kombinatsiyalarni ustma-ust sanamasdan hisoblaydi."""
    text = (value or "").replace("\ufe0f", "")
    text = re.sub(r"[\U0001F3FB-\U0001F3FF]", "", text)
    count = 0
    index = 0
    while index < len(text):
        matched = False
        for pattern in PROHIBITED_EMOJI_PATTERNS:
            if text.startswith(pattern, index):
                count += 1
                index += len(pattern)
                matched = True
                break
        if not matched:
            index += 1
    return count


def _looks_random_channel_title(value: str) -> bool:
    compact = re.sub(r"[^a-z0-9]", "", normalize(value), flags=re.I)
    if not 5 <= len(compact) <= 20:
        return False
    letters = sum(character.isalpha() for character in compact)
    digits = sum(character.isdigit() for character in compact)
    return letters >= 1 and digits >= 2 and " " not in normalize(value)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = value.replace("’", "'").replace("ʻ", "'").replace("‘", "'")
    return " ".join(value.split())


def normalize_for_profanity(value: str) -> str:
    """So'kishni belgilar, leetspeak yoki ajratilgan harflar orasidan topish."""
    value = normalize(value).translate(
        str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
    )
    tokens: List[str] = []
    single_letters: List[str] = []

    def flush_single_letters() -> None:
        if single_letters:
            tokens.append("".join(single_letters))
            single_letters.clear()

    for raw_token in value.split():
        # s.u.k.a va ko't kabi yozuvlardan ajratuvchi belgilarni olib tashlaymiz.
        token = re.sub(r"[^0-9a-zа-яёқғҳў]+", "", raw_token, flags=re.I)
        if not token:
            continue
        if len(token) == 1 and token.isalpha():
            single_letters.append(token)
        else:
            flush_single_letters()
            tokens.append(token)
    flush_single_letters()
    return " ".join(tokens)


@lru_cache(maxsize=1)
def _explicit_profanity_patterns() -> Tuple[Tuple[re.Pattern[str], str], ...]:
    compiled: List[Tuple[re.Pattern[str], str]] = []
    for label, raw_variants in PROFANITY_VARIANTS:
        normalized_variants = {
            normalize_for_profanity(variant)
            for variant in raw_variants
            if normalize_for_profanity(variant)
        }
        alternatives = sorted(
            (
                re.escape(variant).replace(r"\ ", r"\s+")
                for variant in normalized_variants
            ),
            key=len,
            reverse=True,
        )
        # (?<!\w)/(?!\w) ibora boshqa so'zning ichida bo'lmasligini kafolatlaydi.
        pattern = re.compile(
            r"(?<!\w)(?:" + "|".join(alternatives) + r")(?!\w)",
            re.I,
        )
        compiled.append((pattern, label))
    return tuple(compiled)


def _find_profanity(text: str) -> List[str]:
    matches = {
        label
        for pattern, label in PROFANITY_PATTERNS
        if re.search(pattern, text, re.I)
    }
    matches.update(
        label
        for pattern, label in _explicit_profanity_patterns()
        if pattern.search(text)
    )
    return sorted(matches)


def _contains_term(text: str, terms: Tuple[str, ...]) -> List[str]:
    return sorted({term for term in terms if term in text})


class HeuristicChecker:
    def signals(self, context: ModerationContext) -> List[Signal]:
        signals: List[Signal] = []
        text = normalize(context.text)
        profanity_text = normalize_for_profanity(context.text)
        full_name = normalize(context.profile.full_name)
        bio = normalize(context.profile.bio)
        username = normalize(context.profile.username.replace("_", " "))
        personal_channel_title = normalize(context.profile.personal_channel_title)
        personal_channel_username = normalize(
            context.profile.personal_channel_username.replace("_", " ")
        )
        personal_channel_text = normalize(
            "\n".join(
                part
                for part in (
                    context.profile.personal_channel_title,
                    context.profile.personal_channel_username,
                    context.profile.personal_channel_description,
                    context.profile.personal_channel_recent_text,
                )
                if part
            )
        )
        profile_and_message = "\n".join(
            part for part in (text, bio, personal_channel_text) if part
        )

        known_matches = [p for p in KNOWN_SPAM_PATTERNS if re.search(p, text, re.I)]
        if known_matches:
            signals.append(
                Signal("known_spam_template", 65, "Taniqli jalb qiluvchi spam shabloni")
            )

        adult_in_text = _contains_term(text, ADULT_TERMS)
        if adult_in_text:
            signals.append(
                Signal(
                    "adult_text",
                    55,
                    "Xabarda 18+ ibora: " + ", ".join(adult_in_text[:4]),
                )
            )

        profanity_matches = _find_profanity(profanity_text)
        # Yulduz bilan to'silgan juda qisqa shakllarni raw matnda tekshiramiz.
        # Ularni umumiy normalizatsiyaga qo'shish oddiy "bl" qisqartmasini ham
        # noto'g'ri bloklashi mumkin edi.
        if re.search(r"(?<!\w)bl\*{3,}(?:t)?(?!\w)", text, re.I):
            profanity_matches = sorted(set(profanity_matches) | {"blyat"})
        if profanity_matches:
            signals.append(
                Signal(
                    "profanity_text",
                    65,
                    "Xabarda so'kish yoki haqorat: " + ", ".join(profanity_matches[:3]),
                )
            )

        solicitation = [p for p in SOLICITATION_PATTERNS if re.search(p, text, re.I)]
        if solicitation:
            signals.append(
                Signal("solicitation", 30, "Shaxsiy profilga jalb qiluvchi ibora")
            )

        if any(re.search(pattern, text, re.I) for pattern in SCAM_PATTERNS):
            signals.append(
                Signal("scam_pattern", 55, "Firibgarlikka o'xshash va'da yoki so'rov")
            )

        if any(re.search(pattern, text, re.I) for pattern in HIGH_SIGNAL_SPAM_PATTERNS):
            signals.append(
                Signal("high_signal_spam", 65, "Yuqori xavfli spam havolasi yoki taklifi")
            )
        if BINARY_LINK_RE.search(text):
            signals.append(
                Signal("malware_message_link", 75, "Xabarda yuklanadigan xavfli fayl havolasi")
            )

        if LINK_RE.search(text):
            signals.append(Signal("message_link", 18, "Xabarda tashqi havola"))
        if USERNAME_RE.search(text):
            signals.append(Signal("message_username", 10, "Xabarda boshqa username"))
        if adult_in_text and (LINK_RE.search(text) or USERNAME_RE.search(text)):
            signals.append(
                Signal("explicit_message_destination", 40, "Xabar 18+ manzilga yo'naltiradi")
            )

        adult_in_bio = _contains_term(bio, ADULT_TERMS)
        if adult_in_bio:
            signals.append(
                Signal(
                    "adult_bio",
                    40,
                    "Bio'da 18+ ibora: " + ", ".join(adult_in_bio[:4]),
                )
            )
        if bio and LINK_RE.search(bio):
            signals.append(Signal("bio_link", 15, "Bio'da tashqi havola"))
        if BINARY_LINK_RE.search(bio):
            signals.append(
                Signal("malware_bio_link", 90, "Bio yuklanadigan xavfli faylga yo'naltiradi")
            )
        if adult_in_bio and (LINK_RE.search(bio) or USERNAME_RE.search(bio)):
            signals.append(
                Signal("explicit_bio_destination", 45, "Bio 18+ manzilga yo'naltiradi")
            )
        bio_mentions = _mentions(bio)
        if bio_mentions:
            signals.append(
                Signal(
                    "bio_destination",
                    20,
                    "Bio boshqa bot yoki kanalga yo'naltiradi: "
                    + ", ".join(bio_mentions[:3]),
                )
            )
        if bio and _matched_patterns(bio, PROFILE_BAIT_PATTERNS):
            signals.append(
                Signal(
                    "bio_private_content_bait",
                    45,
                    "Bio maxfiy video/rasm ko'rishga jalb qilmoqda",
                )
            )
        if bio and any(re.search(p, bio, re.I) for p in SOLICITATION_PATTERNS):
            signals.append(Signal("bio_solicitation", 25, "Bio'da jalb qiluvchi ibora"))

        adult_in_personal_channel = _contains_term(personal_channel_text, ADULT_TERMS)
        if adult_in_personal_channel:
            signals.append(
                Signal(
                    "adult_personal_channel",
                    55,
                    "Biriktirilgan kanal yoki postida 18+ belgi: "
                    + ", ".join(adult_in_personal_channel[:4]),
                )
            )
        if BINARY_LINK_RE.search(personal_channel_text):
            signals.append(
                Signal(
                    "malware_personal_channel_link",
                    90,
                    "Biriktirilgan kanal xavfli faylga yo'naltiradi",
                )
            )
        if adult_in_personal_channel and (
            LINK_RE.search(personal_channel_text)
            or USERNAME_RE.search(personal_channel_text)
        ):
            signals.append(
                Signal(
                    "explicit_personal_channel_destination",
                    45,
                    "Biriktirilgan kanal 18+ manzilga yo'naltiradi",
                )
            )
        if personal_channel_text and _matched_patterns(
            personal_channel_text, PROFILE_BAIT_PATTERNS
        ):
            signals.append(
                Signal(
                    "personal_channel_bait",
                    45,
                    "Biriktirilgan kanal maxfiy video/rasm ko'rishga jalb qilmoqda",
                )
            )
        channel_mentions = _mentions(personal_channel_text)
        if channel_mentions:
            signals.append(
                Signal(
                    "personal_channel_destination",
                    15,
                    "Biriktirilgan kanal boshqa manzilga yo'naltiradi",
                )
            )
        if _looks_random_channel_title(context.profile.personal_channel_title):
            signals.append(
                Signal(
                    "random_personal_channel",
                    10,
                    "Biriktirilgan kanal nomi tasodifiy harf-raqamlarga o'xshaydi",
                )
            )

        adult_in_username = _contains_term(username, ADULT_TERMS)
        if adult_in_username:
            signals.append(Signal("adult_username", 35, "Shubhali username"))

        adult_in_name = _contains_term(full_name, ADULT_TERMS)
        if adult_in_name:
            signals.append(Signal("adult_name", 35, "Profil nomida 18+ ibora"))

        adult_in_channel_username = _contains_term(
            personal_channel_username, ADULT_TERMS
        )
        if adult_in_channel_username:
            signals.append(
                Signal("adult_personal_channel_username", 35, "Profil kanalida shubhali username")
            )

        learned_matches = sorted(
            {
                pattern
                for pattern in context.learned_patterns
                if len(pattern) >= 3 and normalize(pattern) in profile_and_message
            }
        )
        if learned_matches:
            signals.append(
                Signal(
                    "learned_spam_pattern",
                    65,
                    "Admin o'rgatgan spam belgisi: " + ", ".join(learned_matches[:3]),
                )
            )

        if context.coordinated_user_count >= 3:
            signals.append(
                Signal(
                    "coordinated_spam",
                    15,
                    "Bir xil xabarni "
                    f"{context.coordinated_user_count} ta profil yubordi "
                    "(faqat yordamchi signal)",
                )
            )

        if context.duplicate_count >= 2:
            signals.append(Signal("mass_duplicate", 45, "Bir xil xabar ko'p takrorlangan"))
        elif context.duplicate_count == 1:
            signals.append(Signal("duplicate", 30, "Bir xil xabar qayta yuborilgan"))

        if (
            context.seconds_after_post is not None
            and 0 <= context.seconds_after_post <= 180
        ):
            signals.append(
                Signal("rapid_comment", 10, "Kanal postidan keyin juda tez yozilgan")
            )

        return signals


class _FixedWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = max(1, limit)
        self.window_seconds = max(1, window_seconds)
        self._hits: Dict[object, Tuple[float, int]] = {}

    def allow(self, key: object) -> bool:
        now = time.monotonic()
        started, count = self._hits.get(key, (now, 0))
        if now - started >= self.window_seconds:
            started, count = now, 0
        count += 1
        self._hits[key] = (started, count)
        return count <= self.limit


class OpenAIModerationChecker:
    def __init__(
        self,
        api_key: Optional[str],
        enabled: bool,
        ttl_seconds: int,
        user_limit: int = 10,
        user_window_seconds: int = 30,
        global_limit: int = 120,
        global_window_seconds: int = 60,
    ) -> None:
        self.enabled = bool(api_key and enabled)
        self.client = AsyncOpenAI(api_key=api_key) if self.enabled else None
        self.ttl_seconds = ttl_seconds
        self._profile_cache: Dict[str, Tuple[float, List[Signal], Dict[str, float]]] = {}
        self._profile_inflight: Dict[
            str,
            asyncio.Task[Tuple[List[Signal], Dict[str, float]]],
        ] = {}
        self._user_limiter = _FixedWindowRateLimiter(user_limit, user_window_seconds)
        self._global_limiter = _FixedWindowRateLimiter(global_limit, global_window_seconds)

    async def signals(
        self, context: ModerationContext
    ) -> Tuple[List[Signal], Dict[str, float]]:
        if not self.client:
            return [], {}
        rate_key = (context.chat_id, context.profile.user_id)
        if not self._user_limiter.allow(rate_key):
            logger.info("OpenAI moderatsiya user limiti: %s", rate_key)
            return [], {}
        if not self._global_limiter.allow("global"):
            logger.warning("OpenAI moderatsiya global limiti ishga tushdi")
            return [], {}

        async def profile_result() -> Tuple[List[Signal], Dict[str, float]]:
            profile_key = self._profile_key(context)
            cached = self._profile_cache.get(profile_key)
            now = time.monotonic()
            if cached and cached[0] > now:
                return cached[1], cached[2]
            existing = self._profile_inflight.get(profile_key)
            if existing:
                return await existing
            task = asyncio.create_task(self._check_profile(context))
            self._profile_inflight[profile_key] = task
            try:
                result = await task
                self._profile_cache[profile_key] = (
                    time.monotonic() + self.ttl_seconds,
                    result[0],
                    result[1],
                )
                return result
            finally:
                if self._profile_inflight.get(profile_key) is task:
                    self._profile_inflight.pop(profile_key, None)

        async def message_result() -> Tuple[List[Signal], Dict[str, float]]:
            if not context.text.strip():
                return [], {}
            return await self._moderate(
                text=context.text,
                image_bytes=None,
                source="message",
            )

        (profile_signals, profile_categories), (
            text_signals,
            text_categories,
        ) = await asyncio.gather(profile_result(), message_result())

        categories = dict(profile_categories)
        for name, score in text_categories.items():
            categories[name] = max(categories.get(name, 0.0), score)
        return profile_signals + text_signals, categories

    def _profile_key(self, context: ModerationContext) -> str:
        digest = hashlib.sha256()
        digest.update(context.profile.username.encode("utf-8"))
        digest.update(context.profile.bio.encode("utf-8"))
        digest.update(context.profile.personal_channel_title.encode("utf-8"))
        digest.update(context.profile.personal_channel_username.encode("utf-8"))
        digest.update(context.profile.personal_channel_description.encode("utf-8"))
        digest.update(context.profile.personal_channel_recent_text.encode("utf-8"))
        photo_samples = context.profile.photo_samples
        if not photo_samples and context.profile.photo_bytes:
            photo_samples = (context.profile.photo_bytes,)
        for photo in photo_samples:
            digest.update(photo)
        return digest.hexdigest()

    async def _check_profile(
        self, context: ModerationContext
    ) -> Tuple[List[Signal], Dict[str, float]]:
        profile_text = "\n".join(
            part
            for part in (
                "Name: " + context.profile.full_name,
                "Username: @" + context.profile.username if context.profile.username else "",
                "Bio: " + context.profile.bio if context.profile.bio else "",
                (
                    "Personal channel: " + context.profile.personal_channel_title
                    if context.profile.personal_channel_title
                    else ""
                ),
                (
                    "Personal channel username: @"
                    + context.profile.personal_channel_username
                    if context.profile.personal_channel_username
                    else ""
                ),
                (
                    "Personal channel description: "
                    + context.profile.personal_channel_description
                    if context.profile.personal_channel_description
                    else ""
                ),
                (
                    "Personal channel recent posts: "
                    + context.profile.personal_channel_recent_text
                    if context.profile.personal_channel_recent_text
                    else ""
                ),
            )
            if part
        )
        photo_samples = context.profile.photo_samples
        if not photo_samples and context.profile.photo_bytes:
            photo_samples = (context.profile.photo_bytes,)
        # Profil matni va barcha rasmlar parallel tekshiriladi. Spamchi birinchi
        # rasmini toza, keyingi rasmlarini behayo qilib yashira olmaydi.
        checks = [
            self._moderate(
                text=profile_text,
                image_bytes=None,
                source="profile_text",
            )
        ]
        checks.extend(
            self._moderate(
                text="",
                image_bytes=photo,
                source=f"profile_photo_{index}",
            )
            for index, photo in enumerate(photo_samples, start=1)
        )
        results = await asyncio.gather(*checks)
        text_signals, text_categories = results[0]
        photo_signals: List[Signal] = []
        photo_categories: Dict[str, float] = {}
        for current_signals, current_categories in results[1:]:
            photo_signals.extend(current_signals)
            for name, score in current_categories.items():
                photo_categories[name] = max(photo_categories.get(name, 0.0), score)

        categories = dict(text_categories)
        for name, score in photo_categories.items():
            categories[name] = max(categories.get(name, 0.0), score)
        return text_signals + photo_signals, categories

    async def _moderate(
        self, text: str, image_bytes: Optional[bytes], source: str
    ) -> Tuple[List[Signal], Dict[str, float]]:
        inputs = []
        if text.strip():
            inputs.append({"type": "text", "text": text[:4000]})
        if image_bytes:
            encoded = base64.b64encode(image_bytes).decode("ascii")
            inputs.append(
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64," + encoded},
                }
            )
        if not inputs:
            return [], {}

        try:
            response = await self.client.moderations.create(
                model="omni-moderation-latest",
                input=inputs,
            )
            result = response.results[0].model_dump()
        except Exception as exc:
            logger.warning("OpenAI moderatsiya ishlamadi (%s): %s", source, exc)
            return [], {}

        raw_scores = result.get("category_scores", {})
        categories = {str(k): float(v) for k, v in raw_scores.items()}
        sexual = max(
            categories.get("sexual", 0.0),
            categories.get("sexual/minors", 0.0),
            categories.get("sexual_minors", 0.0),
        )
        minors = max(
            categories.get("sexual/minors", 0.0),
            categories.get("sexual_minors", 0.0),
        )

        signals: List[Signal] = []
        labels = {
            "profile_photo": "profil rasmi",
            "profile_text": "profil nomi/biosi",
            "message": "xabar",
        }
        label = "profil rasmi" if source.startswith("profile_photo") else labels.get(source, source)
        if minors >= 0.01:
            signals.append(
                Signal("ai_sexual_minors_" + source, 100, "AI: voyaga yetmaganlarga oid 18+ " + label)
            )
        elif sexual >= 0.70:
            signals.append(Signal("ai_sexual_high_" + source, 70, "AI: kuchli 18+ " + label))
        elif sexual >= 0.35:
            signals.append(Signal("ai_sexual_medium_" + source, 50, "AI: ehtimoliy 18+ " + label))
        elif sexual >= 0.15:
            signals.append(Signal("ai_sexual_low_" + source, 25, "AI: shubhali 18+ " + label))

        return signals, categories


class ModerationEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.heuristic = HeuristicChecker()
        self.ai = OpenAIModerationChecker(
            settings.openai_api_key,
            settings.openai_moderation_enabled,
            settings.profile_cache_ttl_seconds,
            getattr(settings, "ai_user_limit", 10),
            getattr(settings, "ai_user_window_seconds", 30),
            getattr(settings, "ai_global_limit", 120),
            getattr(settings, "ai_global_window_seconds", 60),
        )

    async def evaluate(self, context: ModerationContext) -> ModerationDecision:
        signals = self.heuristic.signals(context)
        ai_signals, categories = await self.ai.signals(context)
        signals.extend(ai_signals)

        return self._decision(signals, categories)

    def evaluate_local(self, context: ModerationContext) -> ModerationDecision:
        return self._decision(self.heuristic.signals(context), {})

    def _decision(
        self,
        signals: List[Signal],
        categories: Dict[str, float],
    ) -> ModerationDecision:

        # Bir-birini takrorlovchi ko'p signallar ballni cheksiz oshirmasligi uchun
        # umumiy ballni 120 bilan cheklaymiz.
        score = min(120, sum(signal.points for signal in signals))
        has_real_violation = any(
            signal.code not in SUPPORTING_SIGNAL_CODES for signal in signals
        )
        if not has_real_violation:
            action = ModerationAction.ALLOW
        elif score >= self.settings.ban_threshold:
            action = ModerationAction.BAN
        elif score >= self.settings.delete_threshold:
            action = ModerationAction.DELETE
        elif score >= self.settings.review_threshold:
            action = ModerationAction.REVIEW
        else:
            action = ModerationAction.ALLOW
        return ModerationDecision(score, action, signals, categories)

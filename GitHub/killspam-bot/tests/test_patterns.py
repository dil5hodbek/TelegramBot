"""Run: python -m tests.test_patterns  (or pytest). No DB required."""
from spam_bot.core import patterns


def test_normalize_folds_cyrillic_homoglyphs():
    # "zаrаbоtоk" written with Cyrillic а/о should fold to ASCII.
    assert patterns.normalize("ZАRАBОTОK") == "zarabotok"


def test_seed_regex_flags_high_signal_links_only():
    # High-signal: private invite links still flag as ads.
    assert patterns.classify("join here t.me/+AbCdEf") == "advertisement"
    # v1.7.0 scope: generic promo vocabulary no longer flags (it blocked normal talk).
    assert patterns.classify("Сегодня большая скидка!") is None      # "big discount today"
    assert patterns.classify("я работаю программистом") is None       # "I work as a programmer"
    assert patterns.classify("how do I fix this python bug?") is None


def test_seed_regex_catches_crypto_airdrop():
    assert patterns.classify("🪙🪙🪙 Free Solana Case Drop — open yours now") == "advertisement"
    assert patterns.classify("claim your free crypto reward today") == "advertisement"
    assert patterns.classify("anyone built a Solana program in Rust?") is None


def test_harmless_messages_are_not_flagged():
    # Regression (v1.7.0): everyday Uzbek words that the old [flirting]/[inappropriate]
    # seed sections flagged — and permanently banned people over — must now pass clean.
    for msg in ("salom", "salom qizlar qayerdasiz?", "menga bu loyiha yoqdi",
                "sizga rahmat", "mol narxi qancha?"):
        assert patterns.classify(msg) is None, msg
        assert patterns.is_flirting(msg) is False, msg


def test_learned_keyword_matches_after_fold(monkeypatch=None):
    # Inject a global (NULL) learned keyword without touching the DB.
    patterns._learned = {None: {"ads": ["zarabotok"]}}
    assert patterns.classify("Easy zаrаbоtоk online") == "advertisement"
    patterns._learned = {}


def test_extract_keywords_pulls_urls_and_words():
    kws = patterns.extract_keywords("Zarabotok online! t.me/xyz qo'shiling")
    assert "t.me/xyz" in kws
    assert "zarabotok" in kws


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")

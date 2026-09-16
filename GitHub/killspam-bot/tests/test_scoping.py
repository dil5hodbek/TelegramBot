"""Run: python -m tests.test_scoping  (or pytest). No DB/network required.

Verifies the core isolation guarantee of Phase 2a:
  - Global (NULL) learned keywords fire in every group.
  - Group-A keyword does NOT fire in group B.
  - Watchlist: global entry hits everywhere; group-scoped entry only hits its group.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")

from spam_bot.core import patterns, watchlist


# ---------------------------------------------------------------------------
# Learned-pattern scoping
# ---------------------------------------------------------------------------

def test_global_keyword_fires_in_any_group():
    patterns._learned = {None: {"ads": ["globalword"]}}
    assert patterns.classify("buy globalword now", group_id=111) == "advertisement"
    assert patterns.classify("buy globalword now", group_id=222) == "advertisement"
    assert patterns.classify("buy globalword now", group_id=None) == "advertisement"


def test_group_keyword_fires_only_in_its_group():
    patterns._learned = {111: {"ads": ["groupaword"]}}
    assert patterns.classify("buy groupaword now", group_id=111) == "advertisement"
    assert patterns.classify("buy groupaword now", group_id=222) is None
    assert patterns.classify("buy groupaword now", group_id=None) is None


def test_global_and_group_keywords_coexist():
    patterns._learned = {
        None: {"ads": ["globalword"]},
        111: {"ads": ["groupaword"]},
    }
    # global fires in group 111
    assert patterns.classify("buy globalword now", group_id=111) == "advertisement"
    # group 111 keyword fires in group 111
    assert patterns.classify("buy groupaword now", group_id=111) == "advertisement"
    # group 111 keyword does NOT fire in group 222
    assert patterns.classify("buy groupaword now", group_id=222) is None
    # global fires in group 222
    assert patterns.classify("buy globalword now", group_id=222) == "advertisement"


def test_cleanup():
    patterns._learned = {}


# ---------------------------------------------------------------------------
# Watchlist scoping
# ---------------------------------------------------------------------------

def test_global_watchlist_entry_hits_any_group():
    watchlist._watched = {(None, 1)}
    assert watchlist.is_watched(1, group_id=999) is True
    assert watchlist.is_watched(1, group_id=None) is True


def test_group_watchlist_entry_hits_only_its_group():
    watchlist._watched = {(111, 2)}
    assert watchlist.is_watched(2, group_id=111) is True
    assert watchlist.is_watched(2, group_id=222) is False
    assert watchlist.is_watched(2, group_id=None) is False


def test_unknown_user_not_watched():
    watchlist._watched = {(None, 1), (111, 2)}
    assert watchlist.is_watched(999, group_id=111) is False


def test_watchlist_add_global():
    watchlist._watched = set()
    watchlist.add(42, None)
    assert (None, 42) in watchlist._watched
    assert watchlist.is_watched(42, group_id=111)


def test_watchlist_add_group_scoped():
    watchlist._watched = set()
    watchlist.add(43, 111)
    assert (111, 43) in watchlist._watched
    assert not watchlist.is_watched(43, group_id=222)


def test_watchlist_cleanup():
    watchlist._watched = set()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")

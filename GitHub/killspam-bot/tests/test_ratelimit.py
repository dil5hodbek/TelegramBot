"""Run: python -m tests.test_ratelimit"""
from spam_bot.core.ratelimit import RateLimiter


def test_blocks_over_limit_within_window():
    rl = RateLimiter(limit=2, window=100)
    assert rl.allow("k")        # 1st
    assert rl.allow("k")        # 2nd
    assert not rl.allow("k")    # 3rd -> over limit


def test_keys_are_independent():
    rl = RateLimiter(limit=1, window=100)
    assert rl.allow("a")
    assert rl.allow("b")        # different key, own budget
    assert not rl.allow("a")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")

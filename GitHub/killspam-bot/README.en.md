<div align="center">

# 🛡️ Spam Protection Bot

**A self-serve Telegram bot that keeps learning communities clean — explicit content, nude profile photos, malware/APK links, and coordinated spam bursts, removed automatically.**

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Built for @ertagakech](https://img.shields.io/badge/built%20for-%40ertagakech-26A5E4?logo=telegram&logoColor=white)](https://t.me/ertagakech)

🇺🇿 [O‘zbekcha](README.md) · 🇬🇧 **English** · 🇷🇺 [Русский](README.ru.md)

</div>

> ### 🤖 Built for the [@ertagakech](https://t.me/ertagakech) Telegram channel
> This bot was created for **[@ertagakech](https://t.me/ertagakech)** — join the channel to learn more about AI, automation, and building things like this. 👉 **https://t.me/ertagakech**

---

## What it is

A Telegram moderation bot for IT/learning communities. Anyone can add it to their group, run `/enable`, and get protection instantly. It is **multi-tenant** and **bring-your-own-key (BYOK)**: each group plugs in its own Google Gemini key for AI moderation, so no shared cost and no central key to leak. Without a key, the free rule-based layer still protects the group.

## ✨ Features

- **Multi-tenant, self-serve** — add the bot, `/enable` in the group, done. Each group's own admins receive its alerts.
- **BYOK AI moderation** — `/setkey` opens a one-time HTTPS form to store the group's own Gemini key, encrypted at rest. No key → keyword rules still run.
- **Explicit / adult detection** — the AI layer flags sexual/adult content and openly flirtatious spam-bot bait, tuned to leave ordinary conversation, ads, and off-topic chatter alone.
- **Nude profile-photo scanning** — new members' profile photos are checked locally with NudeNet (no cloud call). A clearly-explicit photo → the account is banned and its message deleted.
- **Malware & explicit-link defense** — a downloadable-binary link (`.apk`, `.exe`, …) or an explicit-channel link in a profile bio is a hard ban, checked before any keyword.
- **First-message + join scanning** — profiles are vetted both when a member joins and on their first message, so link-joiners in public groups are covered too.
- **Coordinated-burst detection** — the same message from several accounts within a short window is deleted and banned in one shot.
- **Graduated actions** — clearly-severe signals ban + delete; softer signals give a recoverable 24h mute + admin review; admins can Ban/Unmute from the alert.
- **Admin tooling** — `/ban`, `/mute`, teach-keywords, flag-account, and misclassification feedback, all from Telegram.
- **Usage & activity reporting** — `/tokens` shows Gemini token usage and cost; `/stats` shows the group roster and spam caught; the operator gets a morning report.
- **Tidy by design** — the bot's own notices and admin command messages auto-clean from the group after a few seconds.

## 🧠 How it works

Every message in a protected group runs through a cheap-to-expensive pipeline; the first hit wins:

1. **Profile scan (once per member)** — on join and on first message, the bot checks the bio and profile photos.
   - Downloadable-binary link, explicit-channel link, or a clearly-explicit photo (NudeNet) → **ban + delete** (severe, priority over everything else).
   - Ambiguous photos take **no action** — the bot only acts on a clear verdict, to avoid muting real users.
2. **Keyword layer (free)** — a small, high-signal regex list (`patterns/seed_patterns.txt`) plus per-group admin-taught keywords.
3. **AI layer (BYOK, optional)** — if the group set a Gemini key, a clean message is classified by Gemini 2.5 Flash for adult/flirt-bait spam. Rate-limited as a cost guard.
4. **Burst detector** — identical messages from 3+ accounts in 2 minutes are treated as a coordinated ring.

Detected spam is deleted; the sender is muted (24h, recoverable) or banned (severe / bot rings), and the group's admins get an alert with Ban/Unmute buttons. Everything is scoped per group, and the bot stays completely silent in groups that haven't run `/enable`.

**Privacy:** each group's Gemini key is encrypted at rest with Fernet; there is no shared key. Spam-report text and usage rows are purged after 90 days.

## 🚀 Setup & deployment

The bot runs as a single long-polling worker plus a small HTTPS endpoint for the key-entry form. It's designed for [Railway](https://railway.app/), but any host that runs a Python worker + PostgreSQL works.

### 1. Create the bot
In Telegram, talk to [@BotFather](https://t.me/BotFather): `/newbot`, then **disable privacy mode** (`/setprivacy` → Disable) so the bot can read group messages.

### 2. Clone & install
```bash
git clone <your-fork-url>
cd spam-bot
pip install -r requirements.txt
```

### 3. Configure environment
Copy `.env.example` to `.env` and fill it in:

| Variable | Required | What it is |
|---|---|---|
| `BOT_TOKEN` | ✅ | Telegram bot token from @BotFather |
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `ADMIN_TELEGRAM_IDS` | ✅ | Comma-separated operator IDs (system alerts + `/stats`) |
| `KEY_ENCRYPTION_SECRET` | ✅ | Fernet key encrypting each group's Gemini key. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `BASE_URL` | ✅ | Public HTTPS URL of the bot (builds the `/setkey` link) |
| `GEMINI_PRICE_IN` / `GEMINI_PRICE_OUT` | ➖ | $/1M tokens for `/tokens` cost estimates (default `0.30` / `2.50`) |
| `REPORT_HOUR` | ➖ | Local hour (Asia/Tashkent) for the morning report (default `9`) |
| `MAX_GROUPS_PER_OWNER` | ➖ | Abuse guard: max groups one non-operator may `/enable` (default `20`) |

> ⚠️ Never commit your real `.env`. It is gitignored — keep it that way.

### 4. Deploy
On Railway: create a project, add a PostgreSQL plugin, set the variables above, and deploy. The start command (see `Procfile`) is:
```bash
python init_db.py && python -m spam_bot.main
```
`init_db.py` creates/migrates tables on every boot. Locally you can run the same two commands.

### 5. Protect a group
1. Add the bot to your group and make it an **admin** with **Delete messages** + **Ban users**.
2. Run `/enable` inside the group.
3. (Optional, for AI) Run `/setkey` and follow the one-time link to store the group's Gemini key.

### Rollback
Each release is a git tag (`vX.Y.Z`). To roll back, redeploy the previous tag; the DB schema is additive, so older code runs against a newer DB.

## 💬 Commands

| Command | Who | What |
|---|---|---|
| `/enable` · `/disable` | Group admins | Turn protection on/off for the group |
| `/setkey` | Group admins | Store the group's Gemini key (private, one-time link) |
| `/ban` · `/mute` | Group admins | Moderate the replied-to user |
| `/tokens` | Group admins / operator | Gemini token usage + cost (yesterday / 7d / 30d) |
| `/stats` | Operator (DM) | Group roster + spam/ban activity |
| `/help` · `/privacy` | Everyone | Usage guide / data policy |

## 🛠️ Tech stack

Python 3.11 · [aiogram 3](https://docs.aiogram.dev/) · SQLAlchemy 2 + PostgreSQL · Google Gemini 2.5 Flash (BYOK) · [NudeNet](https://github.com/notAI-tech/NudeNet) (local NSFW model) · aiohttp.

## 📄 License

Licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE). You may use, modify, and share it freely for **any non-commercial purpose**. **Commercial use is not permitted.**

## 🙌 Credits

Created for the **[@ertagakech](https://t.me/ertagakech)** Telegram channel. Join to learn more about AI 👉 **https://t.me/ertagakech**

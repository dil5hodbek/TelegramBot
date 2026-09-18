# TelegramBot — AI Moderation for Telegram Discussion Groups

Telegram kanaliga bog'langan muhokama guruhlarida spam, 18+ kontent va haqoratli
xabarlarni avtomatik aniqlab, o'chiradigan yoki bloklaydigan moderatsiya boti.
Har bir xabar matn, foydalanuvchi ismi, username, bio va profil rasmi bo'yicha
birgalikda baholanadi, so'ng qoidalarga asoslangan risk balli chiqariladi.

## Nima uchun yaratilgan

Faol Telegram kanallarining muhokama guruhlarida spam, 18+ reklama va
koordinatsiyalashgan bot hujumlari qo'lda moderatsiya qilib bo'lmaydigan
tezlikda keladi. Bot bu jarayonni avtomatlashtiradi va xavfli holatlarda
adminni real vaqtda xabardor qiladi.

## Asosiy imkoniyatlar

| Imkoniyat | Tavsif |
|---|---|
| **Ko'p signalli baholash** | Xabar matni, ism, username, bio va profil rasmi birgalikda tekshiriladi |
| **AI moderatsiya** | OpenAI Moderation API orqali matn va rasm mazmuni tahlil qilinadi (ixtiyoriy) |
| **Qoidaga asoslangan filtrlar** | O'zbek/rus/ingliz tilidagi spam va 18+ iboralar, havolalar, xavfli fayl kengaytmalari (`.apk`, `.exe` va h.k.) |
| **Koordinatsiyalashgan spam aniqlash** | Qisqa vaqt oralig'ida bir nechta profildan kelgan bir xil xabarni signal sifatida baholaydi |
| **Risk balli tizimi** | 0–100 oralig'ida ball hisoblanadi, chegaralar `.env` orqali sozlanadi |
| **Xavfsiz sinov rejimi (`DRY_RUN`)** | Ishga tushirishdan oldin adminning `Ha`/`Yo'q` tasdig'i bilan sinash imkoniyati |
| **Ko'p guruhni boshqarish** | Bitta bot bir nechta guruhni admin panelidan (`/groups`) boshqaradi |
| **Tarix va hisobot** | SQLite'da qoidabuzarliklar tarixi, `/report` orqali Excel hisobot |

## Qanday ishlaydi

1. Yangi xabar keladi → matn, profil ma'lumotlari va (mavjud bo'lsa) profil rasmi yig'iladi.
2. Mahalliy qoidalar (kalit so'zlar, havolalar, takrorlanish, taqiqlangan fayllar) baholanadi.
3. Yoqilgan bo'lsa, OpenAI Moderation matn va rasmni qo'shimcha tekshiradi.
4. Signallar birlashtirilib yagona risk balli hisoblanadi:

   | Ball | Amal |
   |---|---|
   | 0–34 | Xabar qoldiriladi |
   | 35–59 | Admin jurnaliga tekshirish uchun yuboriladi |
   | 60–84 | Xabar o'chiriladi |
   | 85+ | Xabar o'chiriladi va foydalanuvchi bloklanadi |

5. `DRY_RUN=true` bo'lsa, avtomatik amal o'rniga adminga tasdiq so'rovi yuboriladi.

## Texnologiyalar

- **Python 3.9+**, [aiogram](https://docs.aiogram.dev/) — Telegram Bot API uchun asinxron freymvork
- **OpenAI Moderation API** — matn va rasm mazmunini tekshirish
- **SQLite** — qoidabuzarliklar tarixi va profil keshi
- **openpyxl** — Excel hisobotlarni generatsiya qilish

## O'rnatish

```bash
git clone https://github.com/dil5hodbek/TelegramBot.git
cd TelegramBot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` faylida kamida `BOT_TOKEN` ni to'ldiring (BotFather orqali olinadi).
`OPENAI_API_KEY` bo'lmasa, mahalliy qoidalar bilan ishlashda davom etadi —
faqat AI orqali rasm/matn tahlili o'chadi.

```bash
python -m izoh_posbon
```

## Admin buyruqlari

| Buyruq | Vazifasi |
|---|---|
| `/status` | Bot holatini tekshirish |
| `/groups` | Boshqariladigan guruhni tanlash |
| `/recent` | So'nggi shubhali hodisalar |
| `/unban` | Foydalanuvchini blokdan chiqarish |
| `/report` | Excel hisobot olish |
| `/dbstats` | Ma'lumotlar bazasi statistikasi |
| `/position` | Sinov / to'liq avtomatik rejim almashtirish |

To'liq o'rnatish va sozlash bo'yicha qo'llanma uchun kod ichidagi qo'shimcha
hujjatlarga qarang.

## Test

```bash
python -m unittest discover -s tests -v
```

---

Litsenziya va uchinchi tomon eslatmalari: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)

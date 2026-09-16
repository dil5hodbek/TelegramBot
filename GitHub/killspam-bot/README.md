<div align="center">

# 🛡️ Spam Protection Bot

**O‘quv hamjamiyatlarini toza saqlaydigan o‘z-o‘ziga xizmat ko‘rsatuvchi Telegram boti — ochiq-sochiq kontent, behayo profil rasmlari, zararli dastur/APK havolalari va muvofiqlashtirilgan spam hujumlari avtomatik ravishda o‘chirib tashlanadi.**

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Built for @ertagakech](https://img.shields.io/badge/built%20for-%40ertagakech-26A5E4?logo=telegram&logoColor=white)](https://t.me/ertagakech)

🇺🇿 **O‘zbekcha** · 🇬🇧 [English](README.en.md) · 🇷🇺 [Русский](README.ru.md)

</div>

> ### 🤖 [@ertagakech](https://t.me/ertagakech) Telegram kanali uchun yaratilgan
> Ushbu bot **[@ertagakech](https://t.me/ertagakech)** uchun yaratilgan — sun’iy intellekt, avtomatlashtirish va shunga o‘xshash loyihalarni yaratish haqida ko‘proq bilish uchun kanalga qo‘shiling. 👉 **https://t.me/ertagakech**

---

## Bu nima

IT va o‘quv hamjamiyatlari uchun mo‘ljallangan Telegram moderatsiya boti. Har kim uni o‘z guruhiga qo‘shishi, `/enable` buyrug‘ini ishga tushirishi va darhol himoyaga ega bo‘lishi mumkin. U **ko‘p foydalanuvchili (multi-tenant)** va **o‘z kalitingni olib kel (BYOK)** tamoyili asosida ishlaydi: har bir guruh sun’iy intellekt moderatsiyasi uchun o‘zining Google Gemini kalitidan foydalanadi, bu esa umumiy xarajatlarning yo‘qligini va kalitlar sizib chiqmasligini ta’minlaydi. Kalit bo‘lmagan taqdirda ham, bepul qoidalarga asoslangan qatlam guruhni himoya qilishda davom etadi.

## ✨ Xususiyatlari

- **Ko‘p foydalanuvchili, o‘z-o‘ziga xizmat ko‘rsatuvchi** — botni qo‘shing, guruhda `/enable` buyrug‘ini bering, tamom. Har bir guruhning o‘z adminlari ogohlantirishlarni qabul qiladi.
- **BYOK sun’iy intellekt moderatsiyasi** — `/setkey` buyrug‘i guruhning shaxsiy Gemini kalitini saqlash uchun bir martalik HTTPS shaklini ochadi, kalit saqlash vaqtida shifrlanadi. Kalit bo‘lmasa — kalit so‘z qoidalari baribir ishlayveradi.
- **Ochiq-sochiq / kattalar uchun kontentni aniqlash** — sun’iy intellekt qatlami shahvoniy/kattalar uchun kontentni va ochiqdan-ochiq flirt ko‘rinishidagi spam-bot tuzoqlarini belgilaydi; u oddiy suhbatlar, reklamalar va mavzudan tashqari gaplarga tegmaslikka sozlangan.
- **Behayo profil rasmlarini skanerlash** — yangi a’zolarning profil rasmlari NudeNet yordamida mahalliy darajada tekshiriladi (bulutga so‘rov yuborilmaydi). Agar rasm aniq behayo bo‘lsa — akkaunt bloklanadi va xabari o‘chiriladi.
- **Zararli dasturlar va behayo havolalardan himoya** — yuklab olinadigan binar fayl havolasi (`.apk`, `.exe`, …) yoki profil tavsifidagi behayo kanal havolasi qat’iy bloklanishga sabab bo‘ladi, bu har qanday kalit so‘zdan oldin tekshiriladi.
- **Birinchi xabar + qo‘shilish vaqtidagi skanerlash** — profillar a’zo qo‘shilganda ham, birinchi xabarini yozganda ham tekshiriladi, shuning uchun ochiq guruhlarga havola orqali kirganlar ham nazoratda bo‘ladi.
- **Muvofiqlashtirilgan ommaviy hujumlarni aniqlash** — qisqa vaqt ichida bir nechta akkauntdan kelgan bir xil xabarlar birdaniga o‘chiriladi va akkauntlar bloklanadi.
- **Tabaqalashtirilgan choralar** — aniq jiddiy signallar uchun bloklash + o‘chirish; unchalik jiddiy bo‘lmagan signallar uchun 24 soatlik ovozini o‘chirish (mute) + admin tekshiruvi; adminlar ogohlantirish xabarining o‘zidan Bloklash/Ovozini yoqish amallarini bajarishi mumkin.
- **Admin asboblari** — `/ban`, `/mute`, kalit so‘zlarni o‘rgatish, akkauntni belgilash va noto‘g‘ri tasniflash bo‘yicha teskari aloqa — barchasi Telegram’ning o‘zida.
- **Foydalanish va faollik hisoboti** — `/tokens` Gemini tokenlaridan foydalanish va xarajatlarni ko‘rsatadi; `/stats` guruh ro‘yxati va tutilgan spamlar haqida ma’lumot beradi; operatorga har kuni ertalabki hisobot yuboriladi.
- **Tabiatan tartibli** — botning o‘z bildirishnomalari va admin buyruqlari bir necha soniyadan so‘ng guruhdan avtomatik ravishda o‘chiriladi.

## 🧠 Qanday ishlaydi

Himoyalangan guruhdagi har bir xabar arzondan qimmatga qarab boruvchi zanjir orqali o‘tadi; birinchi mos kelgan qoida ishga tushadi:

1. **Profilni skanerlash (har bir a’zo uchun bir marta)** — qo‘shilish vaqtida va birinchi xabarda bot profil tavsifi va rasmlarini tekshiradi.
   - Yuklab olinadigan binar fayl havolasi, behayo kanal havolasi yoki aniq behayo rasm (NudeNet) → **bloklash + o‘chirish** (jiddiy holat, hamma narsadan ustun turadi).
   - Shubhali rasmlar bo‘yicha chora ko‘rilmaydi — haqiqiy foydalanuvchilarning ovozini noto‘g‘ri o‘chirib qo‘ymaslik uchun bot faqat aniq xulosa bo‘lgandagina harakat qiladi.
2. **Kalit so‘z qatlami (bepul)** — kichik, yuqori aniqlikdagi regex ro‘yxati (`patterns/seed_patterns.txt`) va har bir guruh uchun adminlar tomonidan o‘rgatilgan kalit so‘zlar.
3. **Sun’iy intellekt qatlami (BYOK, ixtiyoriy)** — agar guruh Gemini kalitini o‘rnatgan bo‘lsa, shubhali xabarlar Gemini 2.5 Flash tomonidan kattalar uchun/flirt ko‘rinishidagi spamga tekshiriladi. Xarajatlarni nazorat qilish uchun so‘rovlar tezligi cheklangan.
4. **Ommaviy hujum detektori** — 2 daqiqa ichida 3 tadan ortiq akkauntdan kelgan bir xil xabarlar muvofiqlashtirilgan guruh deb hisoblanadi.

Aniqlangan spam o‘chiriladi; yuboruvchining ovozi o‘chiriladi (24 soat, qayta tiklash mumkin) yoki bloklanadi (jiddiy holatlar / bot guruhlari), guruh adminlari esa Bloklash/Ovozini yoqish tugmalari bo‘lgan ogohlantirish oladi. Hamma narsa har bir guruh uchun alohida ishlaydi va bot `/enable` buyrug‘i berilmagan guruhlarda mutlaqo jim turadi.

**Maxfiylik:** har bir guruhning Gemini kaliti Fernet yordamida saqlash vaqtida shifrlanadi; umumiy kalit mavjud emas. Spam-hisobot matnlari va foydalanish qatorlari 90 kundan keyin tozalab tashlanadi.

## 🚀 O‘rnatish va joylashtirish

Bot bitta long-polling ishchi jarayoni va kalit kiritish shakli uchun kichik HTTPS endpoint sifatida ishlaydi. U [Railway](https://railway.app/) uchun mo‘ljallangan, lekin Python ishchi jarayoni + PostgreSQL’ni qo‘llab-quvvatlaydigan har qanday xostda ishlaydi.

### 1. Botni yaratish
Telegram’da [@BotFather](https://t.me/BotFather) bilan bog‘laning: `/newbot`, so‘ngra **maxfiylik rejimini o‘chiring** (`/setprivacy` → Disable), shunda bot guruh xabarlarini o‘qiy oladi.

### 2. Klonlash va o‘rnatish
```bash
git clone <your-fork-url>
cd spam-bot
pip install -r requirements.txt
```

### 3. Muhitni sozlash
`.env.example` faylini `.env` ga nusxalang va uni to‘ldiring:

| O‘zgaruvchi | Majburiy | Tavsifi |
|---|---|---|
| `BOT_TOKEN` | ✅ | @BotFather’dan olingan Telegram bot tokeni |
| `DATABASE_URL` | ✅ | PostgreSQL ulanish qatori |
| `ADMIN_TELEGRAM_IDS` | ✅ | Vergul bilan ajratilgan operator ID-lari (tizim ogohlantirishlari + `/stats`) |
| `KEY_ENCRYPTION_SECRET` | ✅ | Har bir guruhning Gemini kalitini shifrlash uchun Fernet kaliti. Yaratish: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `BASE_URL` | ✅ | Botning ommaviy HTTPS URL manzili (`/setkey` havolasini yaratadi) |
| `GEMINI_PRICE_IN` / `GEMINI_PRICE_OUT` | ➖ | `/tokens` xarajatlar smetasi uchun $/1 mln token (standart `0.30` / `2.50`) |
| `REPORT_HOUR` | ➖ | Ertalabki hisobot uchun mahalliy vaqt (Asia/Tashkent) (standart `9`) |
| `MAX_GROUPS_PER_OWNER` | ➖ | Suiiste’mol qilishdan himoya: bitta operator bo‘lmagan foydalanuvchi `/enable` qilishi mumkin bo‘lgan maksimal guruhlar soni (standart `20`) |

> ⚠️ Hech qachon haqiqiy `.env` faylingizni commit qilmang. U gitignore qilingan — shundayligicha qoldiring.

### 4. Joylashtirish
Railway’da: loyiha yarating, PostgreSQL plaginini qo‘shing, yuqoridagi o‘zgaruvchilarni o‘rnating va joylashtiring. Ishga tushirish buyrug‘i (`Procfile`’ga qarang):
```bash
python init_db.py && python -m spam_bot.main
```
`init_db.py` har bir ishga tushishda jadvallarni yaratadi/migratsiya qiladi. Mahalliy kompyuterda ham shu ikkita buyruqni bajarishingiz mumkin.

### 5. Guruhni himoya qilish
1. Botni guruhingizga qo‘shing va uni **Xabarlarni o‘chirish** + **Foydalanuvchilarni bloklash** huquqlariga ega **admin** qiling.
2. Guruh ichida `/enable` buyrug‘ini bering.
3. (Ixtiyoriy, sun’iy intellekt uchun) `/setkey` buyrug‘ini bering va guruhning Gemini kalitini saqlash uchun bir martalik havolaga o‘ting.

### Oldingi holatga qaytarish (Rollback)
Har bir reliz git tegi (`vX.Y.Z`) hisoblanadi. Orqaga qaytarish uchun oldingi tegni qayta joylashtiring; ma’lumotlar bazasi sxemasi qo‘shimcha xususiyatga ega, shuning uchun eski kod yangi baza bilan ishlayveradi.

## 💬 Buyruqlar

| Buyruq | Kim uchun | Vazifasi |
|---|---|---|
| `/enable` · `/disable` | Guruh adminlari | Guruh uchun himoyani yoqish/o‘chirish |
| `/setkey` | Guruh adminlari | Guruhning Gemini kalitini saqlash (shaxsiy, bir martalik havola) |
| `/ban` · `/mute` | Guruh adminlari | Javob berilgan (reply) foydalanuvchini moderatsiya qilish |
| `/tokens` | Guruh adminlari / operator | Gemini tokenlaridan foydalanish + xarajat (kecha / 7 kun / 30 kun) |
| `/stats` | Operator (Shaxsiy xabar) | Guruh ro‘yxati + spam/bloklash faolligi |
| `/help` · `/privacy` | Hamma | Foydalanish bo‘yicha qo‘llanma / ma’lumotlar siyosati |

## 🛠️ Texnologiyalar to‘plami

Python 3.11 · [aiogram 3](https://docs.aiogram.dev/) · SQLAlchemy 2 + PostgreSQL · Google Gemini 2.5 Flash (BYOK) · [NudeNet](https://github.com/notAI-tech/NudeNet) (mahalliy NSFW modeli) · aiohttp.

## 📄 Litsenziya

[PolyForm Noncommercial License 1.0.0](LICENSE) litsenziyasi asosida litsenziyalangan. Siz undan har qanday **notijorat maqsadlarda** erkin foydalanishingiz, o‘zgartirishingiz va baham ko‘rishingiz mumkin. **Tijorat maqsadlarida foydalanishga ruxsat berilmaydi.**

## 🙌 Mualliflar

**[@ertagakech](https://t.me/ertagakech)** Telegram kanali uchun yaratilgan. Sun’iy intellekt haqida ko‘proq bilish uchun qo‘shiling 👉 **https://t.me/ertagakech**

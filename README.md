# Izoh Posbon Bot

Telegram kanaliga ulangan muhokama guruhidagi spam va 18+ izohlarni avtomatik
baholaydi. Bot xabar matni, ism, username, mavjud bo'lsa bio va profil rasmini
birgalikda tekshiradi. Yuqori riskli izohni o'chiradi, juda yuqori riskda esa
foydalanuvchini bloklaydi.

## Imkoniyatlar

- o'zbek, rus va ingliz tilidagi 18+ hamda jalb qiluvchi spam iboralari;
- havola, username va takroriy xabarlarni aniqlash;
- post e'lon qilingach tez yozilgan izohni qo'shimcha signal sifatida baholash;
- OpenAI Moderation orqali matn va profil rasmini tekshirish (ixtiyoriy);
- SQLite'da qoidabuzarliklar tarixini saqlash;
- adminlar, botlar va anonim kanal xabarlarini moderatsiyadan chiqarish;
- `DRY_RUN` rejimida adminning `Ha`/`Yo'q` tasdig'i bilan xavfsiz sinov;
- bir nechta guruhni bitta bot orqali boshqarish va `/groups` panelida tanlash;
- alohida admin chatiga tushunarli hisobot yuborish.

## 1. Xavfsizlik

Chatda yoki boshqa ochiq joyda yuborilgan BotFather tokenini ishlatmang. BotFather'da
`/revoke` buyrug'i bilan tokenni almashtiring. Token faqat `.env` faylida turishi
kerak; `.env` Git'ga qo'shilmaydi.

## 2. O'rnatish

Python 3.9 yoki yangiroq versiya talab qilinadi.

```bash
cd /Users/macstore.uz/Desktop/Maxsus_Bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

`.env` faylida kamida `BOT_TOKEN` qiymatini kiriting. Profil rasmi va matnning AI
moderatsiyasi uchun `OPENAI_API_KEY` ham kiriting. OpenAI kaliti bo'lmasa botning
mahalliy spam qoidalari, takroriy xabar nazorati va avtomatik amallari ishlashda
davom etadi; faqat rasm mazmunini AI orqali baholash o'chadi.

Profil rasmi mavjud bo'lsa bot eng yangi 5 tagacha rasmning katta nusxasini
Telegram'dan yuklaydi. Ism, username va bio matn sifatida, har bir profil rasmi alohida
rasm sifatida AI moderatsiyadan o'tadi. Shu sababli oddiy ism-familiya rasmning 18+
bahosiga aralashmaydi. Natijalar qisqa muddat keshlanadi va rasm diskka saqlanmaydi.

## 3. Telegram sozlamasi

1. Botni kanalga bog'langan **muhokama guruhiga** qo'shing.
2. Uni administrator qiling.
3. `Delete messages` va `Ban users` huquqlarini yoqing.
4. Avval `.env` ichida `DRY_RUN=true` bilan sinang.
5. Shubhali xabar topilganda adminning private chatiga tasdiq so'rovi keladi.
   `Ha` xabarni o'chirib userni bloklaydi, `Yo'q` esa hech narsani o'zgartirmaydi.
6. Keyin `DRY_RUN=false` qilib botni qayta ishga tushiring.

Bot administrator bo'lsa, guruhdagi yangi xabarlarni qabul qiladi. Bio Telegram
tomonidan berilmagan holatlarda u bo'sh qoladi va qaror boshqa signallarga tayanadi.
Profil rasmi doimiy faylga saqlanmaydi: tekshiruv va qisqa muddatli xotira keshi
uchun ishlatiladi. AI yoqilsa, tekshiriladigan matn va rasm OpenAI Moderation
xizmatiga yuboriladi.

## 4. Ishga tushirish

```bash
source .venv/bin/activate
python -m izoh_posbon
```

Buyruqlar:

- `/stats` — foydalanuvchining shaxsiy moderatsiya statistikasi;
- `/status` — admin uchun private chatda va guruhda bot holatini tekshirish;
- `/groups` — adminning private chatida boshqariladigan guruhni tanlash;
- `/recent` — adminning private chatida so'nggi 10 ta shubhali hodisa;
- `/unban` — adminning private chatida foydalanuvchi ID sini so'rab, uni blokdan
  chiqarish;
- `/position` — tanlangan guruh uchun tasdiqli sinov va to'liq avtomatik
  moderatsiya rejimlarini almashtirish;
- `/report` — adminning private chatida Excel hisobotni olish.
- `/dbstats` — kengaytirilgan ma'lumotlar bazasi statistikasini ko'rish.
- `/leave` — tasdiqdan keyin botni tanlangan guruhdan chiqarish.
- `/del_bot` — tanlangan guruhdagi boshqa admin botni tanlab, Izoh Posbon kuzatgan
  oxirgi 1, 5 yoki 10 ta xabarini o'chirish.

`/stats` barcha foydalanuvchilar uchun botning private chatida ishlaydi. Boshqaruv
buyruqlari faqat `ADMIN_IDS` ro'yxatidagi foydalanuvchilarga private menyuda
ko'rinadi. Bot qo'shilgan guruhlar avtomatik ro'yxatga olinadi. Admin `/groups`
orqali guruhni tanlaydi; private `/status`, `/recent`, `/unban` va `/report` shu
guruh bo'yicha ishlaydi. `PROTECTED_CHAT_ID` birinchi/fallback guruh sifatida qoladi.
`/status` bundan tashqari guruh ichida ham ishlaydi, lekin anonim admin rejimida
haqiqiy user ID ko'rinmaydi.

## Risk balli

- `0-34`: xabar qoldiriladi;
- `35-59`: admin jurnaliga tekshirish uchun yuboriladi;
- `60-84`: xabar o'chiriladi;
- `85+`: xabar o'chiriladi va foydalanuvchi bloklanadi.

Chegaralarni `.env` orqali o'zgartirish mumkin. Profil rasmi odatda boshqa spam
signallari bilan birgalikda baholanadi. AI juda yuqori ishonch bilan ochiq 18+
rasm yoki `sexual/minors` toifasini topsa, rasmning o'zi ham o'chirish uchun
yetarli signal bo'lishi mumkin.

## Test

```bash
python -m unittest discover -s tests -v
```
## Kengaytirilgan himoya

- Profilning eng yangi 5 ta rasmi alohida OpenAI moderatsiyasidan o'tadi.
- Bio, shaxsiy kanal va xabardagi xavfli `.apk`, `.exe`, `.dmg` kabi havolalar
  yuqori xavf sifatida belgilanadi.
- 2 daqiqada kamida 3 xil profil yuborgan bir xil uzun xabar faqat yordamchi signal
  hisoblanadi. Bu qoida konkurs, grant yoki muayyan kalit so'zga bog'lanmagan:
  mavzusi qanday bo'lishidan qat'i nazar, bitta yoki ko'p foydalanuvchi yozgan
  takroriy xabarning o'zi o'chirish yoki bloklashga sabab bo'lmaydi. Buning uchun
  18+, haqorat, scam yoki boshqa aniq xavf ham topilishi kerak.
- Bloklash tarixi, profil tekshiruvlari va AI auditlari SQLite bazasida saqlanadi;
  `/dbstats` baza holatini ko'rsatadi.
- Bot kodi o'zgargan har bir yangilanishdan keyin adminlarga versiya va faqat
  aynan shu versiyada o'zgargan eng so'nggi bandlar private xabarda bir marta
  yuboriladi; eski yangilanishlar qayta takrorlanmaydi.
- Avtomatik moderatsiya xabarni o'chirgan, profilni bloklagan yoki amal xatoga
  uchragan holatda natija barcha boshqaruvchi adminlarga private yuboriladi.
- Taqiqlangan emoji yoki unga mos Telegram sticker qatnashgan har bir xabar
  darhol o'chiriladi va bitta urinish sanaladi. Foydalanuvchi 4-chi alohida
  qoidabuzar xabar/stickerda avtomatik bloklanadi; `/unban` hisobni tozalaydi.
- `🤢`, `🤮` va `🥴` emojilari ham taqiqlangan emoji/sticker ro'yxatiga kiradi.
- `.apk`, `.xapk`, `.apks`, `.exe`, `.msi`, `.dmg`, `.bat`, `.cmd`, `.scr`
  bilan tugaydigan Telegram fayli yoki havolasi qat'iy taqiqlanadi: xabar
  darhol o'chiriladi va yuborgan profil bloklanadi.
- Adminlar, botlar va kanalning o'zidan kelgan xabarlardan tashqari oddiy
  foydalanuvchi yuborgan `https://`, `t.me/`, `sayt.uz/yo'l`, `@username` yoki
  yashirin matnli havola darhol o'chiriladi. Shu foydalanuvchining 1-, 2- va
  3-havolali xabari o'chiriladi; 4-havolali xabarda esa xabar o'chirilib, profil
  guruhdan bloklanadi. Hisob har bir guruhda alohida yuritiladi va `/unban`
  qilinganda tozalanadi.
- `/leave` orqali bot tanlangan begona guruhdan masofadan chiqariladi; amal
  oldidan aniq guruh nomi va ID tasdiqlanadi.
- Guruhga a'zo qo'shilgani yoki a'zo chiqib ketgani haqidagi Telegram xizmat
  xabarlari avtomatik o'chiriladi.
- `/del_bot` guruhdagi admin botlar ro'yxatini ko'rsatadi. Bot tanlangach 1, 5
  yoki 10 ta oxirgi kuzatilgan xabar o'chiriladi va natija adminga ko'rsatiladi.
  Telegram Bot API boshqa bot-administratorlarni tayyor ro'yxatda va eski chat
  tarixini o'qishga bermaydi. Shu sababli admin bot Izoh Posbon ishlayotgan paytda
  kamida bir marta xabar yozgach ro'yxatda paydo bo'ladi; faqat kuzatilib bazaga
  yozilgan xabarlar mavjud bo'ladi.

Moslashtirilgan g'oyalar litsenziyasi `THIRD_PARTY_NOTICES.md` faylida ko'rsatilgan.

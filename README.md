# 🎬 Abdurakhmanjaan | MovieBot

Kod, nom va inline qidiruv orqali film, serial va multfilm yuboradigan Telegram bot. VIP obuna (Telegram Stars va Click), kunlik limit, majburiy obuna, seriallar, TMDB ma'lumotlari, reyting va izohlar, to'liq admin panel.

Texnologiyalar: Python 3.11+, aiogram 3, SQLite (aiosqlite, WAL), aiohttp (TMDB), rapidfuzz, APScheduler.

## Tuzilma

```
main.py            ishga tushirish, middleware, xatolar handleri
config.py          env o'zgaruvchilar
texts.py           barcha matnlar (o'zbekcha)
database/          ulanish, sxema, moslashuvchan migratsiya, so'rovlar
handlers/          foydalanuvchi bo'limlari; handlers/admin/ — admin panel
middlewares/       foydalanuvchini yozish, ban, anti-spam
services/          yuborish, limit, obuna, TMDB, qidiruv, tarqatish, backup, rejalashtiruvchi
keyboards/         callback ma'lumotlari va tugmalar
tools/             migrate_old_db.py, enrich_movies.py
```

## 1. BotFather sozlamalari

1. `/setinline` → botingiz → placeholder: **Kino nomi yoki kodini kiriting**
2. `/setcommands` → bot ishga tushganda buyruqlarni o'zi o'rnatadi (`/start`, `/top`, `/new`, `/saved`, `/vip`); qo'lda kiritish shart emas.
3. To'lovlar: `/mybots` → bot → **Payments** → **Click** → avval **Test** token, keyin **Live** token. Tokenni `CLICK_PROVIDER_TOKEN` ga yozing. Telegram Stars uchun hech narsa kerak emas.
   - Eslatma: Telegram kartadan to'lovda juda kichik summalarni (~1$ dan kam) rad etishi mumkin. Bunday tarifni Click orqali ochib bo'lmasa, bot foydalanuvchiga xabar beradi; narxni oshiring yoki Stars narxini qo'ying.

## 2. Botni kanallarga admin qilish

| Kanal | Huquq |
|---|---|
| Saqlash kanali (`STORAGE_CHANNEL_ID`, yopiq) | admin (xabar yuborish) |
| Zaxira kanal (ixtiyoriy) | admin (xabar yuborish) |
| Majburiy obuna kanallari/guruhlari | admin, **"Havola orqali taklif qilish"** huquqi bilan |
| Ochiq kanal (yangi kino postlari) | admin, **xabar yuborish** huquqi bilan |

Zayavkali yopiq kanalda bot zayavkalarni **qabul qilmaydi**, faqat qayd etadi: zayavka tashlagan foydalanuvchi obuna bo'lgan hisoblanadi. Zayavkalarni admin qo'lda qabul qiladi.

## 3. Railway

1. Repozitoriyni Railway'ga ulang (`railway.json`: start buyrug'i `python main.py`, 1 instans).
2. Servisga **Volume** qo'shing, mount path: `/data`. Baza `/data/kinobot.db` da saqlanadi — konteyner qayta ishga tushsa ham yo'qolmaydi.
3. **Variables**:

| O'zgaruvchi | Majburiy | Izoh |
|---|---|---|
| `BOT_TOKEN` | ✅ | BotFather tokeni |
| `ADMIN_ID` | ✅ | asosiy admin (default `5751975734`) |
| `STORAGE_CHANNEL_ID` | ✅ | saqlash kanali (default `-1004446986274`) |
| `TMDB_API_KEY` | tavsiya | v3 api_key yoki v4 token |
| `CLICK_PROVIDER_TOKEN` | — | Click to'lovi uchun |
| `DB_PATH` | — | default `/data/kinobot.db` |
| `BACKUP_CHANNEL_ID` | — | zaxira kanal |
| `PUBLIC_CHANNEL_ID`, `PUBLIC_CHANNEL_URL` | — | ochiq kanal |
| `SUPPORT_USERNAME` | — | to'lov va yordam uchun |

Env faqat boshlang'ich qiymat: support, kanallar, limitlar va tariflar keyin **⚙️ Admin panel** orqali o'zgaradi.

> Bot `drop_pending_updates` siz ishga tushadi — o'chiq turgan paytdagi to'lovlar yo'qolmaydi.

## 4. Eski bazani ko'chirish

Eski bot PostgreSQL ishlatgan. Yangi bot SQLite'da ishlaydi, shuning uchun bir martalik ko'chirish kerak:

1. Railway'da yangi botni Volume bilan deploy qiling (eski Postgres servisini **o'chirmang**).
2. Bot servisiga vaqtincha `OLD_DATABASE_URL=${{Postgres.DATABASE_URL}}` qo'shing.
3. Servis shell'ida (yoki lokal, `DB_PATH` ni ko'rsatib):
   ```bash
   python tools/migrate_old_db.py
   ```
   Kinolar (kod, nom, VIP belgisi, kanal posti, ko'rishlar), foydalanuvchilar va majburiy obuna kanallari ko'chiriladi. Eski baza faqat o'qiladi, hech narsa o'chmaydi. Takror ishga tushirish xavfsiz.
4. Eski kinolar `film` turi va bo'sh tillar bilan keladi: **Admin panel → 🧩 To'ldirilmaganlar** orqali tur va tilni belgilang.

Eski SQLite baza bo'lsa: `python tools/migrate_old_db.py /yo'l/eski.db`. Agar eski SQLite fayl to'g'ridan-to'g'ri `DB_PATH` da tursa, bot ishga tushganda o'zi migratsiya qiladi: ustunlarni `PRAGMA table_info` orqali aniqlaydi (`kod/code`, `nom/name/title`, `vip/is_vip`, `msg_id/message_id`, `file_id`), faqat yangi ustun va jadvallar qo'shadi; mos kelmaydigan eski jadval `*_legacy_*` nomi bilan saqlanib qoladi.

## 5. TMDB bilan to'ldirish

```bash
python tools/enrich_movies.py --dry-run      # faqat hisobot (tmdb_report.csv)
python tools/enrich_movies.py                # to'ldirish
```

Ishonchli (≥85%) va yagona natija avtomatik yoziladi: poster, yil, janr, davlat, davomiylik, tavsif, TMDB/IMDb ID. **Kod, nom va VIP belgisiga tegilmaydi.** Shubhali natijalarni **Admin panel → 🪄 TMDB bilan to'ldirish → Shubhalilarni ko'rib chiqish** da qo'lda tanlaysiz.

## 6. Admin panel

`/admin` yoki menyudagi **⚙️ Admin panel**. Rollar:

- **Moderator:** kino/serial qo'shish (`/add`), tahrirlash, qismlar, so'rovlar, shikoyatlar, izohlarni o'chirish.
- **Admin:** + statistika, xabar yuborish, bloklash, promo-kodlar, rejalashtirilgan postlar, to'ldirilmaganlar, TMDB.
- **Asosiy admin:** + adminlar, tariflar, limitlar, majburiy obuna, sozlamalar, backup, `/export`, `/import`, `/refund user_id charge_id`.

Kino qo'shish: tur → saqlash kanalidagi postni **forward** qiling (yoki videoni yuboring) → nom → TMDB'dan tanlang → sifat → til → VIP/Bepul → tavsif → kod → preview → saqlash → bildirishnoma va ochiq kanal posti (hozir yoki rejalashtirib). Serial uchun qismlarni ketma-ket yuborasiz.

Baza nusxasi har kuni 03:00 da asosiy adminga yuboriladi.

## Lokal ishga tushirish

```bash
pip install -r requirements.txt
cp .env.example .env      # qiymatlarni to'ldiring, DB_PATH=./kinobot.db
python main.py
```

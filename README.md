<<<<<<< HEAD
# 🎬 KinoBot

Kod orqali kino yuboradigan Telegram bot. Unda majburiy obuna, pullik kontent (Telegram Stars), admin panel va reklama yuborish bor.

## Kinolar qayerda saqlanadi?

Kinolar **serverda emas**, yopiq Telegram kanalda ("ombor") saqlanadi. Bazada faqat xabar raqami turadi, shuning uchun Railway diski to'lmaydi. Bot tokeni o'zgarsa ham, yangi botni ombor kanalga admin qilsangiz, barcha kinolar ishlayveradi.

## Railway'ga joylash

1. **Bot yarating:** @BotFather → `/newbot` → tokenni oling.
2. **Ombor kanal:** Telegram'da **yopiq (private)** kanal oching va botni unga **admin** qiling.
3. Kodni GitHub'ga yuklang (`.env` fayli yuklanmaydi, bu to'g'ri).
4. [railway.com](https://railway.com) → **New Project** → **Deploy from GitHub repo**.
5. Loyiha ichida **+ New → Database → PostgreSQL** qo'shing.
6. Bot servisi → **Variables**:
   - `BOT_TOKEN` = BotFather bergan token
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
   - `ADMIN_IDS` = sizning ID (botga `/id` yozib bilasiz)
   - `STORAGE_CHANNEL_ID` = ombor kanal ID si
7. ID larni bilish: avval `BOT_TOKEN` va `DATABASE_URL` bilan ishga tushiring. Botga `/id` yozing, keyin ombor kanaldan biror xabarni botga forward qiling, bot kanal ID sini aytadi. Ikkala ID ni Variables'ga qo'shing.

## Foydalanish

- `/admin` → admin panel
- **➕ Kino qo'shish:** video yuborasiz → nomini yozasiz → 🆓 Bepul / 💎 Pullik tanlaysiz → bot kod va havola beradi
- Havola (`t.me/bot?start=125`) ni Instagram yoki TikTok'ga qo'ying: odam bosganda kino darhol keladi
- **📢 Kanallar:** majburiy obuna kanallari (bot u kanalda admin bo'lishi shart)
- **📨 Xabar yuborish:** barcha foydalanuvchilarga reklama yuborish

## Pullik kontent

Pullik kinoga foydalanuvchi to'lov usulini tanlaydi: **💳 Click**, **💳 Payme** yoki **⭐ Telegram Stars**. Admin kino qo'shayotganda narxni so'mda va Stars'da alohida yozadi. `0` yozilsa, kino shu usulda sotilmaydi.

### Click / Payme ulash (so'mda to'lov)

1. @BotFather → `/mybots` → botingiz → **Payments**.
2. Ro'yxatdan **Click** yoki **Payme** ni tanlang. Avval **Test** tokenni oling: bunda pul yechilmaydi, sinab ko'rish uchun.
3. Tokenni Railway Variables'ga qo'ying: `CLICK_PROVIDER_TOKEN` yoki `PAYME_PROVIDER_TOKEN`.
4. Sinov to'lovi ishlagach, provayderda (Click/Payme) **merchant** sifatida ro'yxatdan o'ting (YaTT yoki MChJ kerak). Keyin **Live** tokenni oling va test tokenning o'rniga qo'ying.

- Pul to'g'ridan-to'g'ri Click/Payme merchant hisobingizga tushadi, Telegram komissiya olmaydi.
- Telegram ~1$ dan kam to'lovni qabul qilmaydi, shuning uchun bot minimal narxni 15 000 so'm qilib qo'ygan.
- Har bir sotuvda adminga Telegram cheki va provayder cheki raqami keladi. Muammo bo'lsa, shu raqam bilan Click/Payme kabinetidan tekshirasiz.

### Telegram Stars

- Shartnoma kerak emas. Yig'ilgan Stars'ni @BotFather → bot → Balance orqali Fragment'da yechib olasiz.

### Umumiy

- Pullik video `protect_content` bilan yuboriladi, uni forward qilib yoki saqlab bo'lmaydi.
- Sotib olgan foydalanuvchi kodni qayta yuborsa, kino qayta to'lovsiz keladi.

⚠️ Pullik qilib faqat **huquqi sizda bo'lgan** kontentni qo'ying: o'z filmlaringiz, rejissyorlar bilan kelishilgan filmlar, kurslar va hokazo.

## Lokal ishga tushirish

```bash
pip install -r requirements.txt
cp .env.example .env   # qiymatlarni to'ldiring
python main.py
```
=======
# kinobot
>>>>>>> 9a42091912ce01307e7b65ed0e216628a997c988

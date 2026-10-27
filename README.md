# 🤖 Ko'p Funksiyali Telegram Bot (@instaminoriy_bot)

Ushbu bot **Python 3.12**, **aiogram 3**, **yt-dlp**, **SpeechRecognition** va maxsus hujjat vositalari yordamida yaratilgan ko'p funksiyali Telegram yordamchisidir.

---

## 🌟 Asosiy 3 ta Katta Funksiya

### 1️⃣ Video Yuklash (Instagram & YouTube)
- **Instagram:** Reels, Post, IGTV, Video havolalari.
- **YouTube:** Shorts, Video havolalari (`youtu.be`, `youtube.com/watch`, `shorts/`).
- **Xususiyat:** Video sifati 720p gacha avtomatik moslanadi va Telegram limitlariga (50 MB) mos holda tezkor yuklanadi. Video bilan birga audio avtomatik ravishda birlashtiriladi (FFmpeg).

### 2️⃣ Hujjatlar Konvertatsiyasi (Word, Excel, PDF, Rasm)
Foydalanuvchi hujjat yuborganda, bot avtomatik ravishda interaktiv tugmalar (Inline Buttons) orqali kerakli formatni tanlash imkonini beradi:
- **PDF (.pdf)** ➔ **Word (.docx)** yoki **Matn (.txt)**
- **Word (.docx)** ➔ **PDF (.pdf)** yoki **Matn (.txt)**
- **Excel (.xlsx)** ➔ **PDF (.pdf)** yoki **CSV (.csv)**
- **CSV** ➔ **Excel (.xlsx)**
- **Rasm (JPG, PNG)** ➔ **PDF (.pdf)**

### 3️⃣ Ovozli Xabarlarni Matnga O'girish (Speech-to-Text)
- Ovozli xabar (Voice) yoki audio fayl kelganda, bot ovozni eshitib, uni avtomatik ravishda matn ko'rinishida yozib beradi.
- **Tillar:** O'zbek tili 🇺🇿, Rus tili 🇷🇺, Ingliz tili 🇬🇧 (Avtomatik aniqlanadi).

---

## 🛠 Fayllar Strukturasi

- [bot.py](file:///d:/N31/bot.py) — Asosiy bot fayli, buyruqlar, xabar boshqaruvi va inline tugmalar.
- [converters.py](file:///d:/N31/converters.py) — Word, Excel, PDF, CSV va rasmlarni konvertatsiya qilish funksiyalari.
- [transcriber.py](file:///d:/N31/transcriber.py) — Ovozli xabarlarni matnga o'giruvchi Speech-to-Text moduli.
- [requirements.txt](file:///d:/N31/requirements.txt) — Barcha kerakli Python kutubxonalari.
- [.env](file:///d:/N31/.env) — Bot tokeni sozlamasi.

---

## 🚀 Qanday Ishlatish Kerak?

1. Telegram ilovasida **[@instaminoriy_bot](https://t.me/instaminoriy_bot)** ga kiring.
2. **/start** tugmasini bosing.
3. Istalgan amalni bajaring:
   - Instagram yoki YouTube havolasini yuboring ➔ **Video olasiz**;
   - Word, Excel yoki PDF hujjat yuboring ➔ **Tugma orqali formatini o'zgartirasiz**;
   - Mikrofon orqali ovozli xabar yuboring ➔ **Matn ko'rinishida qabul qilasiz**!

FROM python:3.12-slim

# Tizim paketlarini (ffmpeg va shriftlar) o'rnatish
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Kutubxonalarni o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Loyiha fayllarini nusxalash
COPY . .

# Render porti
EXPOSE 10000

# Botni ishga tushirish
CMD ["python", "bot.py"]

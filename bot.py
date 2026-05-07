from telegram.ext import ApplicationBuilder, CommandHandler
import requests
from datetime import datetime
import time
import os

TOKEN = os.getenv("TOKEN")
WB_TOKEN = os.getenv("WB_TOKEN")

stocks_cache = {
    "time": 0,
    "data": None
}

async def start(update, context):
    await update.message.reply_text("Бот работает 24/7 🚀")

def wb_get(url, params):
    global stocks_cache
    now = time.time()

    if "stocks" in url:
        if stocks_cache["data"] and now - stocks_cache["time"] < 60:
            return stocks_cache["data"]

    headers = {"Authorization": WB_TOKEN}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 429:
        raise Exception("Слишком много запросов, подожди")

    data = response.json()

    if "stocks" in url:
        stocks_cache["data"] = data
        stocks_cache["time"] = now

    return data


async def stocks(update, context):
    url = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"
    params = {"dateFrom": "2024-01-01T00:00:00"}

    try:
        data = wb_get(url, params)
        total = sum(x.get("quantity", 0) for x in data)

        text = f"📦 Остатки: {total} шт\n\n"

        for item in data[:10]:
            text += f"{item.get('supplierArticle')} — {item.get('quantity')} шт\n"

        await update.message.reply_text(text)

    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stocks", stocks))

print("Бот запущен...")
app.run_polling()

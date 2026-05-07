from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler
)

import requests
from datetime import datetime, timedelta
import time
import os

TOKEN = os.getenv("TOKEN")
WB_TOKEN = os.getenv("WB_TOKEN")

CACHE_SECONDS = 300

stocks_cache = {
    "time": 0,
    "data": None
}


async def start(update, context):
    keyboard = [
        [
            InlineKeyboardButton(
                "📦 Остатки",
                callback_data="stocks"
            ),
            InlineKeyboardButton(
                "💰 Продажи",
                callback_data="sales"
            ),
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "WB Бот 24/7 🚀\n\nВыберите действие:",
        reply_markup=reply_markup
    )


def wb_get(url, params):
    global stocks_cache

    now = time.time()

    # Кэш для остатков
    if "stocks" in url:
        if (
            stocks_cache["data"]
            and now - stocks_cache["time"] < CACHE_SECONDS
        ):
            return stocks_cache["data"]

    headers = {
        "Authorization": WB_TOKEN
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30
    )

    if response.status_code == 429:
        raise Exception(
            "⚠️ Слишком много запросов к WB.\nПодождите 5–10 минут."
        )

    response.raise_for_status()

    data = response.json()

    # Сохраняем остатки в кэш
    if "stocks" in url:
        stocks_cache["data"] = data
        stocks_cache["time"] = now

    return data


async def stocks(update, context):
    url = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"

    params = {
        "dateFrom": "2024-01-01T00:00:00"
    }

    try:
        data = wb_get(url, params)

        total = sum(
            item.get("quantity", 0)
            for item in data
        )

        text = f"📦 Остатки WB: {total} шт\n\n"

        for item in data[:20]:
            article = item.get(
                "supplierArticle",
                "Без артикула"
            )

            quantity = item.get("quantity", 0)

            warehouse = item.get(
                "warehouseName",
                "-"
            )

            text += (
                f"{article}\n"
                f"Остаток: {quantity} шт\n"
                f"Склад: {warehouse}\n\n"
            )

        if update.callback_query:
            await update.callback_query.message.reply_text(
                text[:4000]
            )
        else:
            await update.message.reply_text(
                text[:4000]
            )

    except Exception as e:
        error_text = f"Ошибка /stocks: {e}"

        if update.callback_query:
            await update.callback_query.message.reply_text(
                error_text
            )
        else:
            await update.message.reply_text(
                error_text
            )


async def sales(update, context):
    url = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"

    date_from = (
        datetime.now() - timedelta(days=1)
    ).strftime("%Y-%m-%dT00:00:00")

    params = {
        "dateFrom": date_from
    }

    try:
        data = wb_get(url, params)

        if not data:
            text = "Продаж за последние 24 часа не найдено."

            if update.callback_query:
                await update.callback_query.message.reply_text(text)
            else:
                await update.message.reply_text(text)

            return

        total_sum = 0
        total_count = 0

        article_stats = {}

        for item in data:
            price = item.get("finishedPrice", 0)

            article = item.get(
                "supplierArticle",
                "Без артикула"
            )

            total_sum += price
            total_count += 1

            if article not in article_stats:
                article_stats[article] = {
                    "count": 0,
                    "sum": 0
                }

            article_stats[article]["count"] += 1
            article_stats[article]["sum"] += price

        top_articles = sorted(
            article_stats.items(),
            key=lambda x: x[1]["sum"],
            reverse=True
        )

        text = (
            f"💰 Продажи WB за 24 часа\n\n"
            f"Сумма продаж: {round(total_sum, 2)} ₽\n"
            f"Количество продаж: {total_count}\n\n"
            f"🔥 Топ товаров:\n\n"
        )

        for article, stats in top_articles[:10]:
            text += (
                f"{article}\n"
                f"Продаж: {stats['count']} шт\n"
                f"Сумма: {round(stats['sum'], 2)} ₽\n\n"
            )

        if update.callback_query:
            await update.callback_query.message.reply_text(
                text[:4000]
            )
        else:
            await update.message.reply_text(
                text[:4000]
            )

    except Exception as e:
        error_text = f"Ошибка /sales: {e}"

        if update.callback_query:
            await update.callback_query.message.reply_text(
                error_text
            )
        else:
            await update.message.reply_text(
                error_text
            )


async def button_handler(update, context):
    query = update.callback_query

    await query.answer()

    if query.data == "stocks":
        await stocks(update, context)

    elif query.data == "sales":
        await sales(update, context)


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(
    CommandHandler("start", start)
)

app.add_handler(
    CommandHandler("stocks", stocks)
)

app.add_handler(
    CommandHandler("sales", sales)
)

app.add_handler(
    CallbackQueryHandler(button_handler)
)

print("Бот запущен...")

app.run_polling()

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
import requests
import time
import os

TOKEN = os.getenv("TOKEN")
WB_TOKEN = os.getenv("WB_TOKEN")

CACHE_SECONDS = 300
LOW_STOCK_LIMIT = 5

ARTICLE_GROUPS = [
    "18298",
    "6758",
    "18298-1",
    "18892",
    "18321",
    "18047",
    "2372",
    "18688",
    "18550-1",
    "2371-1",
    "18550",
    "550",
    "2372-1",
    "8801"
]

stocks_cache = {
    "time": 0,
    "data": None
}


async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("📦 Остатки по артикулам", callback_data="articles_menu")],
        [InlineKeyboardButton("📦 Все остатки", callback_data="stocks")]
    ]

    await update.message.reply_text(
        "WB Бот 24/7 🚀\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


def get_base_article(article):
    # Важно: длинные артикулы проверяем первыми, чтобы 18298-1 не попал в 18298
    for group in sorted(ARTICLE_GROUPS, key=len, reverse=True):
        if article.startswith(group):
            return group
    return None


def wb_get_stocks():
    global stocks_cache

    now = time.time()

    if stocks_cache["data"] and now - stocks_cache["time"] < CACHE_SECONDS:
        return stocks_cache["data"]

    url = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"

    headers = {
        "Authorization": WB_TOKEN
    }

    params = {
        "dateFrom": "2024-01-01T00:00:00"
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30
    )

    if response.status_code == 429:
        raise Exception("Слишком много запросов к WB. Подождите 5–10 минут.")

    response.raise_for_status()

    data = response.json()

    stocks_cache["data"] = data
    stocks_cache["time"] = now

    return data


async def articles_menu(update, context):
    keyboard = []

    row = []

    for article in ARTICLE_GROUPS:
        row.append(
            InlineKeyboardButton(
                article,
                callback_data=f"article_{article}"
            )
        )

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append(
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
    )

    text = "Выберите артикул для проверки остатков меньше 5 шт:"

    if update.callback_query:
        await update.callback_query.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def stocks(update, context):
    try:
        data = wb_get_stocks()

        total = sum(item.get("quantity", 0) for item in data)

        grouped = {}

        for item in data:
            article = item.get("supplierArticle", "Без артикула")
            quantity = item.get("quantity", 0)

            base = get_base_article(article)

            if not base:
                continue

            grouped[base] = grouped.get(base, 0) + quantity

        text = f"📦 Остатки WB по 14 артикулам\n\nВсего: {total} шт\n\n"

        for article in ARTICLE_GROUPS:
            text += f"{article}: {grouped.get(article, 0)} шт\n"

        if update.callback_query:
            await update.callback_query.message.reply_text(text[:4000])
        else:
            await update.message.reply_text(text[:4000])

    except Exception as e:
        error_text = f"Ошибка /stocks: {e}"

        if update.callback_query:
            await update.callback_query.message.reply_text(error_text)
        else:
            await update.message.reply_text(error_text)


async def article_detail(update, context, base_article):
    try:
        data = wb_get_stocks()

        items = []

        for item in data:
            supplier_article = item.get("supplierArticle", "")
            quantity = item.get("quantity", 0)

            if get_base_article(supplier_article) != base_article:
                continue

            if quantity >= LOW_STOCK_LIMIT:
                continue

            items.append({
                "article": supplier_article,
                "quantity": quantity,
                "barcode": item.get("barcode", "-"),
                "size": item.get("techSize", "-"),
                "warehouse": item.get("warehouseName", "-")
            })

        if not items:
            text = (
                f"✅ Артикул {base_article}\n\n"
                f"Нет размеров/цветов с остатком меньше {LOW_STOCK_LIMIT} шт."
            )
        else:
            items = sorted(
                items,
                key=lambda x: (x["quantity"], x["article"], x["size"])
            )

            text = (
                f"⚠️ Артикул {base_article}\n"
                f"Остатки меньше {LOW_STOCK_LIMIT} шт:\n\n"
            )

            for item in items[:40]:
                text += (
                    f"{item['article']}\n"
                    f"Размер: {item['size']}\n"
                    f"Баркод: {item['barcode']}\n"
                    f"Остаток: {item['quantity']} шт\n"
                    f"Склад: {item['warehouse']}\n\n"
                )

            if len(items) > 40:
                text += f"Показано 40 из {len(items)} строк."

        keyboard = [
            [InlineKeyboardButton("⬅️ К артикулам", callback_data="articles_menu")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]

        await update.callback_query.message.reply_text(
            text[:4000],
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        await update.callback_query.message.reply_text(
            f"Ошибка по артикулу {base_article}: {e}"
        )


async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("📦 Остатки по артикулам", callback_data="articles_menu")],
            [InlineKeyboardButton("📦 Все остатки", callback_data="stocks")]
        ]

        await query.message.reply_text(
            "Главное меню:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "articles_menu":
        await articles_menu(update, context)

    elif query.data == "stocks":
        await stocks(update, context)

    elif query.data.startswith("article_"):
        base_article = query.data.replace("article_", "")
        await article_detail(update, context, base_article)


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stocks", stocks))
app.add_handler(CallbackQueryHandler(button_handler))

print("Бот запущен...")
app.run_polling()

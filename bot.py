from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

import requests
import time
import os
import json
import asyncio

TOKEN = os.getenv("TOKEN")
WB_TOKEN = os.getenv("WB_TOKEN")

CACHE_FILE = "stocks_cache.json"
REFRESH_SECONDS = 900  # 15 минут
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
    "data": []
}


def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(stocks_cache, f, ensure_ascii=False)


def load_cache():
    global stocks_cache

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            stocks_cache = json.load(f)
    except FileNotFoundError:
        stocks_cache = {
            "time": 0,
            "data": []
        }


def get_base_article(article):
    for group in sorted(ARTICLE_GROUPS, key=len, reverse=True):
        if article.startswith(group):
            return group
    return None


def fetch_stocks_from_wb():
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
        print("WB API: лимит запросов 429")
        return None

    response.raise_for_status()
    return response.json()


async def update_stocks_cache():
    global stocks_cache

    data = await asyncio.to_thread(fetch_stocks_from_wb)

    if data is None:
        return False

    stocks_cache = {
        "time": time.time(),
        "data": data
    }

    save_cache()

    print("Остатки WB обновлены")
    return True


async def periodic_update(application):
    load_cache()

    await update_stocks_cache()

    while True:
        await asyncio.sleep(REFRESH_SECONDS)
        await update_stocks_cache()


async def post_init(application):
    application.create_task(periodic_update(application))


async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("📦 Остатки по артикулам", callback_data="articles_menu")],
        [InlineKeyboardButton("📦 Сводка остатков", callback_data="stocks_summary")],
        [InlineKeyboardButton("🔄 Обновить из WB", callback_data="refresh_stocks")]
    ]

    await update.message.reply_text(
        "WB Бот 24/7 🚀\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def main_menu(query):
    keyboard = [
        [InlineKeyboardButton("📦 Остатки по артикулам", callback_data="articles_menu")],
        [InlineKeyboardButton("📦 Сводка остатков", callback_data="stocks_summary")],
        [InlineKeyboardButton("🔄 Обновить из WB", callback_data="refresh_stocks")]
    ]

    await query.message.reply_text(
        "Главное меню:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


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

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")])

    text = f"Выберите артикул.\nПокажу размеры/цвета, где остаток меньше {LOW_STOCK_LIMIT} шт."

    await update.callback_query.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def stocks_summary(update, context):
    data = stocks_cache.get("data", [])

    if not data:
        await update.callback_query.message.reply_text(
            "Кэш остатков пока пустой. Подождите обновления или нажмите 🔄 Обновить из WB."
        )
        return

    grouped = {}

    for item in data:
        article = item.get("supplierArticle", "")
        quantity = item.get("quantity", 0)

        base = get_base_article(article)

        if not base:
            continue

        grouped[base] = grouped.get(base, 0) + quantity

    total = sum(grouped.values())

    updated_at = time.strftime(
        "%d.%m.%Y %H:%M",
        time.localtime(stocks_cache.get("time", 0))
    )

    text = (
        f"📦 Сводка остатков по 14 артикулам\n\n"
        f"Всего: {total} шт\n"
        f"Обновлено: {updated_at}\n\n"
    )

    for article in ARTICLE_GROUPS:
        text += f"{article}: {grouped.get(article, 0)} шт\n"

    await update.callback_query.message.reply_text(text[:4000])


async def article_detail(update, context, base_article):
    data = stocks_cache.get("data", [])

    if not data:
        await update.callback_query.message.reply_text(
            "Кэш остатков пока пустой. Подождите обновления или нажмите 🔄 Обновить из WB."
        )
        return

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

    updated_at = time.strftime(
        "%d.%m.%Y %H:%M",
        time.localtime(stocks_cache.get("time", 0))
    )

    if not items:
        text = (
            f"✅ Артикул {base_article}\n\n"
            f"Нет размеров/цветов с остатком меньше {LOW_STOCK_LIMIT} шт.\n\n"
            f"Обновлено: {updated_at}"
        )
    else:
        items = sorted(
            items,
            key=lambda x: (x["quantity"], x["article"], x["size"])
        )

        text = (
            f"⚠️ Артикул {base_article}\n"
            f"Остатки меньше {LOW_STOCK_LIMIT} шт\n"
            f"Обновлено: {updated_at}\n\n"
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


async def refresh_stocks(update, context):
    await update.callback_query.message.reply_text("🔄 Обновляю остатки из WB...")

    ok = await update_stocks_cache()

    if ok:
        await update.callback_query.message.reply_text("✅ Остатки обновлены.")
    else:
        await update.callback_query.message.reply_text(
            "⚠️ WB временно ограничил запросы. Показываю старые данные из кэша."
        )


async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "main_menu":
        await main_menu(query)

    elif query.data == "articles_menu":
        await articles_menu(update, context)

    elif query.data == "stocks_summary":
        await stocks_summary(update, context)

    elif query.data == "refresh_stocks":
        await refresh_stocks(update, context)

    elif query.data.startswith("article_"):
        base_article = query.data.replace("article_", "")
        await article_detail(update, context, base_article)


app = (
    ApplicationBuilder()
    .token(TOKEN)
    .post_init(post_init)
    .build()
)

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))

print("Бот запущен...")
app.run_polling()

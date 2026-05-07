from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

import requests
import time
import os
import json
import asyncio
from datetime import datetime, timedelta

TOKEN = os.getenv("TOKEN")
WB_TOKEN = os.getenv("WB_TOKEN")

STOCKS_CACHE_FILE = "stocks_cache.json"
SALES_CACHE_FILE = "sales_cache.json"

STOCKS_REFRESH_SECONDS = 900      # 15 минут
SALES_REFRESH_SECONDS = 3600      # 1 час

LOW_STOCK_LIMIT = 5
TOP_SALES_LIMIT = 20

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

sales_cache = {
    "time": 0,
    "data": []
}


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def load_all_cache():
    global stocks_cache, sales_cache

    stocks_cache = load_json(
        STOCKS_CACHE_FILE,
        {"time": 0, "data": []}
    )

    sales_cache = load_json(
        SALES_CACHE_FILE,
        {"time": 0, "data": []}
    )


def get_base_article(article):
    for group in sorted(ARTICLE_GROUPS, key=len, reverse=True):
        if article.startswith(group):
            return group
    return None


def get_color_from_article(article):
    base = get_base_article(article)

    if not base:
        return "-"

    color = article.replace(base, "", 1)

    if not color:
        return "-"

    return color.strip("-_ ")


def wb_request(url, params):
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
        print("WB API: лимит запросов 429")
        return None

    response.raise_for_status()
    return response.json()


def fetch_stocks_from_wb():
    url = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"

    params = {
        "dateFrom": "2024-01-01T00:00:00"
    }

    return wb_request(url, params)


def fetch_sales_from_wb():
    url = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"

    date_from = (
        datetime.now() - timedelta(days=1)
    ).strftime("%Y-%m-%dT00:00:00")

    params = {
        "dateFrom": date_from
    }

    return wb_request(url, params)


async def update_stocks_cache():
    global stocks_cache

    data = await asyncio.to_thread(fetch_stocks_from_wb)

    if data is None:
        return False

    stocks_cache = {
        "time": time.time(),
        "data": data
    }

    save_json(STOCKS_CACHE_FILE, stocks_cache)

    print("Остатки WB обновлены")
    return True


async def update_sales_cache():
    global sales_cache

    data = await asyncio.to_thread(fetch_sales_from_wb)

    if data is None:
        return False

    sales_cache = {
        "time": time.time(),
        "data": data
    }

    save_json(SALES_CACHE_FILE, sales_cache)

    print("Продажи WB обновлены")
    return True


async def periodic_update(application):
    load_all_cache()

    await update_stocks_cache()
    await update_sales_cache()

    last_stocks_update = time.time()
    last_sales_update = time.time()

    while True:
        await asyncio.sleep(60)

        now = time.time()

        if now - last_stocks_update >= STOCKS_REFRESH_SECONDS:
            await update_stocks_cache()
            last_stocks_update = now

        if now - last_sales_update >= SALES_REFRESH_SECONDS:
            await update_sales_cache()
            last_sales_update = now


async def post_init(application):
    application.create_task(periodic_update(application))


def format_time(timestamp):
    if not timestamp:
        return "нет данных"

    return time.strftime(
        "%d.%m.%Y %H:%M",
        time.localtime(timestamp)
    )


async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("📦 Остатки по артикулам", callback_data="articles_menu")],
        [InlineKeyboardButton("📦 Сводка остатков", callback_data="stocks_summary")],
        [InlineKeyboardButton("💰 Продажи ТОП-20", callback_data="sales_summary")],
        [InlineKeyboardButton("🔄 Обновить остатки", callback_data="refresh_stocks")],
        [InlineKeyboardButton("🔄 Обновить продажи", callback_data="refresh_sales")]
    ]

    await update.message.reply_text(
        "WB Бот 24/7 🚀\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def main_menu(query):
    keyboard = [
        [InlineKeyboardButton("📦 Остатки по артикулам", callback_data="articles_menu")],
        [InlineKeyboardButton("📦 Сводка остатков", callback_data="stocks_summary")],
        [InlineKeyboardButton("💰 Продажи ТОП-20", callback_data="sales_summary")],
        [InlineKeyboardButton("🔄 Обновить остатки", callback_data="refresh_stocks")],
        [InlineKeyboardButton("🔄 Обновить продажи", callback_data="refresh_sales")]
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

    text = f"Выберите артикул.\nПокажу цвета/размеры, где остаток меньше {LOW_STOCK_LIMIT} шт."

    await update.callback_query.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def stocks_summary(update, context):
    data = stocks_cache.get("data", [])

    if not data:
        await update.callback_query.message.reply_text(
            "Кэш остатков пока пустой. Подождите обновления или нажмите 🔄 Обновить остатки."
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
    updated_at = format_time(stocks_cache.get("time", 0))

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
            "Кэш остатков пока пустой. Подождите обновления или нажмите 🔄 Обновить остатки."
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
            "color": get_color_from_article(supplier_article),
            "quantity": quantity,
            "barcode": item.get("barcode", "-"),
            "size": item.get("techSize", "-"),
            "warehouse": item.get("warehouseName", "-")
        })

    updated_at = format_time(stocks_cache.get("time", 0))

    if not items:
        text = (
            f"✅ Артикул {base_article}\n\n"
            f"Нет цветов/размеров с остатком меньше {LOW_STOCK_LIMIT} шт.\n\n"
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
                f"Цвет: {item['color']}\n"
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


async def sales_summary(update, context):
    data = sales_cache.get("data", [])

    if not data:
        await update.callback_query.message.reply_text(
            "Кэш продаж пока пустой. Подождите обновления или нажмите 🔄 Обновить продажи."
        )
        return

    grouped = {}

    for item in data:
        article = item.get("supplierArticle", "Без артикула")
        base = get_base_article(article)

        if not base:
            continue

        size = item.get("techSize", "-")
        barcode = item.get("barcode", "-")
        color = get_color_from_article(article)

        key = (article, color, size, barcode)

        price = (
            item.get("finishedPrice")
            or item.get("forPay")
            or item.get("totalPrice")
            or 0
        )

        if key not in grouped:
            grouped[key] = {
                "article": article,
                "color": color,
                "size": size,
                "barcode": barcode,
                "count": 0,
                "sum": 0
            }

        grouped[key]["count"] += 1
        grouped[key]["sum"] += price

    items = sorted(
        grouped.values(),
        key=lambda x: x["sum"],
        reverse=True
    )

    total_sum = sum(x["sum"] for x in items)
    total_count = sum(x["count"] for x in items)
    updated_at = format_time(sales_cache.get("time", 0))

    text = (
        f"💰 Продажи WB за 24 часа\n"
        f"Обновлено: {updated_at}\n\n"
        f"Сумма продаж: {round(total_sum, 2)} ₽\n"
        f"Количество продаж: {total_count}\n\n"
        f"🔥 ТОП-{TOP_SALES_LIMIT} позиций:\n\n"
    )

    for index, item in enumerate(items[:TOP_SALES_LIMIT], start=1):
        text += (
            f"{index}. {item['article']}\n"
            f"Цвет: {item['color']}\n"
            f"Размер: {item['size']}\n"
            f"Баркод: {item['barcode']}\n"
            f"Продаж: {item['count']} шт\n"
            f"Сумма: {round(item['sum'], 2)} ₽\n\n"
        )

    if not items:
        text = (
            f"Продаж по выбранным 14 артикулам за последние 24 часа не найдено.\n"
            f"Обновлено: {updated_at}"
        )

    await update.callback_query.message.reply_text(text[:4000])


async def refresh_stocks(update, context):
    await update.callback_query.message.reply_text("🔄 Обновляю остатки из WB...")

    ok = await update_stocks_cache()

    if ok:
        await update.callback_query.message.reply_text("✅ Остатки обновлены.")
    else:
        await update.callback_query.message.reply_text(
            "⚠️ WB временно ограничил запросы. Показываю старые остатки из кэша."
        )


async def refresh_sales(update, context):
    await update.callback_query.message.reply_text("🔄 Обновляю продажи из WB...")

    ok = await update_sales_cache()

    if ok:
        await update.callback_query.message.reply_text("✅ Продажи обновлены.")
    else:
        await update.callback_query.message.reply_text(
            "⚠️ WB временно ограничил запросы. Показываю старые продажи из кэша."
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

    elif query.data == "sales_summary":
        await sales_summary(update, context)

    elif query.data == "refresh_stocks":
        await refresh_stocks(update, context)

    elif query.data == "refresh_sales":
        await refresh_sales(update, context)

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

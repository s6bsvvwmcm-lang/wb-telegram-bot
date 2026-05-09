from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

import requests
import time
import os
import json
import asyncio
from datetime import datetime, timedelta

TOKEN = os.getenv("TOKEN")

WB_ACCOUNTS = {
    "main": {
        "name": "Кабинет Эльвиры",
        "token": os.getenv("WB_TOKEN_MAIN")
    },
    "second": {
        "name": "Кабинет Рината",
        "token": os.getenv("WB_TOKEN_SECOND")
    }
}

ARTICLE_GROUPS = {
    "main": [
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
    ],
     "second": [
        "1997",
        "1997-1",
        "8269-1",
        "8269",
        "18816",
        "118502",
        "2136",
        "18295"
    ]
}

STOCKS_REFRESH_SECONDS = 900
SALES_REFRESH_SECONDS = 3600

LOW_STOCK_LIMIT = 5
TOP_SALES_LIMIT = 10

stocks_cache = {}
sales_cache = {}


def cache_file(data_type, account_key):
    return f"{data_type}_cache_{account_key}.json"


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

    for account_key in WB_ACCOUNTS:
        stocks_cache[account_key] = load_json(
            cache_file("stocks", account_key),
            {"time": 0, "data": []}
        )

        sales_cache[account_key] = load_json(
            cache_file("sales", account_key),
            {"time": 0, "data": []}
        )


def format_time(timestamp):
    if not timestamp:
        return "нет данных"

    return time.strftime(
        "%d.%m.%Y %H:%M",
        time.localtime(timestamp)
    )


def get_base_article(article, account_key):
    groups = ARTICLE_GROUPS.get(account_key, [])

    for group in sorted(groups, key=len, reverse=True):
        if str(article).startswith(group):
            return group

    return None


def get_color_from_article(article, account_key):
    base = get_base_article(article, account_key)

    if not base:
        return "-"

    color = str(article).replace(base, "", 1)

    if not color:
        return "-"

    return color.strip("-_ ")


def wb_request(token, url, params):
    headers = {
        "Authorization": token
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


def fetch_stocks_from_wb(account_key):
    token = WB_ACCOUNTS[account_key]["token"]

    if not token:
        print(f"Нет токена для {account_key}")
        return None

    url = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"

    params = {
        "dateFrom": "2024-01-01T00:00:00"
    }

    return wb_request(token, url, params)


def fetch_sales_from_wb(account_key):
    token = WB_ACCOUNTS[account_key]["token"]

    if not token:
        print(f"Нет токена для {account_key}")
        return None

    url = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"

    date_from = (
        datetime.now() - timedelta(days=1)
    ).strftime("%Y-%m-%dT00:00:00")

    params = {
        "dateFrom": date_from
    }

    return wb_request(token, url, params)


async def update_stocks_cache(account_key):
    global stocks_cache

    data = await asyncio.to_thread(fetch_stocks_from_wb, account_key)

    if data is None:
        return False

    stocks_cache[account_key] = {
        "time": time.time(),
        "data": data
    }

    save_json(
        cache_file("stocks", account_key),
        stocks_cache[account_key]
    )

    print(f"Остатки обновлены: {WB_ACCOUNTS[account_key]['name']}")
    return True


async def update_sales_cache(account_key):
    global sales_cache

    data = await asyncio.to_thread(fetch_sales_from_wb, account_key)

    if data is None:
        return False

    sales_cache[account_key] = {
        "time": time.time(),
        "data": data
    }

    save_json(
        cache_file("sales", account_key),
        sales_cache[account_key]
    )

    print(f"Выкупы обновлены: {WB_ACCOUNTS[account_key]['name']}")
    return True


async def update_all_stocks():
    results = []

    for account_key in WB_ACCOUNTS:
        ok = await update_stocks_cache(account_key)
        results.append(ok)

    return any(results)


async def update_all_sales():
    results = []

    for account_key in WB_ACCOUNTS:
        ok = await update_sales_cache(account_key)
        results.append(ok)

    return any(results)


async def periodic_update(application):
    load_all_cache()

    await update_all_stocks()
    await update_all_sales()

    last_stocks_update = time.time()
    last_sales_update = time.time()

    while True:
        await asyncio.sleep(60)

        now = time.time()

        if now - last_stocks_update >= STOCKS_REFRESH_SECONDS:
            await update_all_stocks()
            last_stocks_update = now

        if now - last_sales_update >= SALES_REFRESH_SECONDS:
            await update_all_sales()
            last_sales_update = now


async def post_init(application):
    application.create_task(periodic_update(application))


def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Остатки по артикулам", callback_data="articles_menu")],
        [InlineKeyboardButton("📦 Сводка остатков", callback_data="stocks_summary")],
        [InlineKeyboardButton("💰 Выкупы ТОП-10", callback_data="sales_menu")],
        [InlineKeyboardButton("🔄 Обновить остатки", callback_data="refresh_stocks")],
        [InlineKeyboardButton("🔄 Обновить выкупы", callback_data="refresh_sales")]
    ])


async def start(update, context):
    await update.message.reply_text(
        "WB Бот 24/7 🚀\n\nВыберите действие:",
        reply_markup=main_keyboard()
    )


async def main_menu(query):
    await query.message.reply_text(
        "Главное меню:",
        reply_markup=main_keyboard()
    )


async def sales_menu(update, context):
    keyboard = [
        [InlineKeyboardButton("🏬 Кабинет Эльвиры", callback_data="sales_account_main")],
        [InlineKeyboardButton("🏬 Кабинет Рината", callback_data="sales_account_second")],
        [InlineKeyboardButton("📊 Общий итог", callback_data="sales_account_all")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
    ]

    await update.callback_query.message.reply_text(
        "Выберите кабинет для просмотра выкупов:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def articles_menu(update, context):
    keyboard = []

    for account_key, account in WB_ACCOUNTS.items():
        articles = ARTICLE_GROUPS.get(account_key, [])

        if not articles:
            continue

        keyboard.append([
            InlineKeyboardButton(
                f"🏬 {account['name']}",
                callback_data=f"noop_{account_key}"
            )
        ])

        row = []

        for article in articles:
            row.append(
                InlineKeyboardButton(
                    article,
                    callback_data=f"article_{account_key}_{article}"
                )
            )

            if len(row) == 2:
                keyboard.append(row)
                row = []

        if row:
            keyboard.append(row)

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")])

    await update.callback_query.message.reply_text(
        f"Выберите артикул.\nПокажу цвета/размеры, где остаток меньше {LOW_STOCK_LIMIT} шт.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def stocks_summary(update, context):
    text = "📦 Сводка остатков\n\n"
    total_all = 0

    for account_key, account in WB_ACCOUNTS.items():
        cache = stocks_cache.get(account_key, {"time": 0, "data": []})
        data = cache.get("data", [])
        articles = ARTICLE_GROUPS.get(account_key, [])

        account_grouped = {}
        account_total = 0

        for item in data:
            article = item.get("supplierArticle", "")
            quantity = item.get("quantity", 0)
            base = get_base_article(article, account_key)

            if not base:
                continue

            account_grouped[base] = account_grouped.get(base, 0) + quantity
            account_total += quantity
            total_all += quantity

        text += f"🏬 {account['name']}\n"
        text += f"Обновлено: {format_time(cache.get('time', 0))}\n"
        text += f"Итого: {account_total} шт\n"

        if not articles:
            text += "Артикулы не добавлены\n\n"
            continue

        for article in articles:
            text += f"{article}: {account_grouped.get(article, 0)} шт\n"

        text += "\n"

    text += f"✅ Общий итог: {total_all} шт"

    await update.callback_query.message.reply_text(text[:4000])


async def article_detail(update, context, account_key, base_article):
    account = WB_ACCOUNTS[account_key]
    cache = stocks_cache.get(account_key, {"time": 0, "data": []})
    data = cache.get("data", [])

    items = []

    for item in data:
        supplier_article = item.get("supplierArticle", "")
        quantity = item.get("quantity", 0)

        if get_base_article(supplier_article, account_key) != base_article:
            continue

        if quantity >= LOW_STOCK_LIMIT:
            continue

        items.append({
            "article": supplier_article,
            "color": get_color_from_article(supplier_article, account_key),
            "quantity": quantity,
            "barcode": item.get("barcode", "-"),
            "size": item.get("techSize", "-"),
            "warehouse": item.get("warehouseName", "-")
        })

    if not items:
        text = (
            f"✅ {account['name']}\n"
            f"Артикул {base_article}\n\n"
            f"Нет цветов/размеров с остатком меньше {LOW_STOCK_LIMIT} шт.\n\n"
            f"Обновлено: {format_time(cache.get('time', 0))}"
        )
    else:
        items = sorted(
            items,
            key=lambda x: (x["quantity"], x["article"], x["size"])
        )

        text = (
            f"⚠️ {account['name']}\n"
            f"Артикул {base_article}\n"
            f"Остатки меньше {LOW_STOCK_LIMIT} шт\n"
            f"Обновлено: {format_time(cache.get('time', 0))}\n\n"
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


def build_stock_lookup(account_key):
    lookup = {}

    cache = stocks_cache.get(account_key, {"time": 0, "data": []})
    data = cache.get("data", [])

    for item in data:
        article = item.get("supplierArticle", "")
        size = item.get("techSize", "-")
        barcode = item.get("barcode", "-")
        quantity = item.get("quantity", 0)

        key = (article, size, barcode)
        lookup[key] = lookup.get(key, 0) + quantity

    return lookup


def build_buyout_items(account_filter):
    grouped = {}

    account_keys = []

    if account_filter == "all":
        account_keys = list(WB_ACCOUNTS.keys())
    else:
        account_keys = [account_filter]

    for account_key in account_keys:
        account = WB_ACCOUNTS[account_key]
        cache = sales_cache.get(account_key, {"time": 0, "data": []})
        data = cache.get("data", [])
        stock_lookup = build_stock_lookup(account_key)

        for item in data:
            article = item.get("supplierArticle", "Без артикула")
            size = item.get("techSize", "-")
            barcode = item.get("barcode", "-")

            price = (
                item.get("finishedPrice")
                or item.get("forPay")
                or item.get("totalPrice")
                or 0
            )

            color = get_color_from_article(article, account_key)
            stock_qty = stock_lookup.get((article, size, barcode), 0)

            key = (
                account_key,
                article,
                size,
                barcode
            )

            if key not in grouped:
                grouped[key] = {
                    "account": account["name"],
                    "article": article,
                    "color": color,
                    "size": size,
                    "barcode": barcode,
                    "count": 0,
                    "sum": 0,
                    "stock": stock_qty
                }

            grouped[key]["count"] += 1
            grouped[key]["sum"] += price

    return sorted(
        grouped.values(),
        key=lambda x: x["count"],
        reverse=True
    )


async def sales_summary(update, context, account_filter):
    items = build_buyout_items(account_filter)

    if account_filter == "all":
        title = "📊 Общие выкупы за 24 часа"
    else:
        title = f"💰 Выкупы за 24 часа\n{WB_ACCOUNTS[account_filter]['name']}"

    total_sum = sum(x["sum"] for x in items)
    total_count = sum(x["count"] for x in items)

    if not items:
        text = (
            f"{title}\n\n"
            f"Выкупов за последние 24 часа не найдено."
        )
    else:
        text = (
            f"{title}\n\n"
            f"Сумма выкупов: {round(total_sum, 2)} ₽\n"
            f"Количество выкупленных товаров: {total_count}\n\n"
            f"🔥 ТОП-{TOP_SALES_LIMIT} по количеству выкупов:\n\n"
        )

        for index, item in enumerate(items[:TOP_SALES_LIMIT], start=1):
            stock_warning = " ⚠️" if item["stock"] < LOW_STOCK_LIMIT else ""

            text += (
                f"{index}. {item['article']}\n"
                f"Кабинет: {item['account']}\n"
                f"Цвет: {item['color']}\n"
                f"Размер: {item['size']}\n"
                f"Баркод: {item['barcode']}\n"
                f"Выкуплено: {item['count']} шт\n"
                f"Выручка: {round(item['sum'], 2)} ₽\n"
                f"Остаток: {item['stock']} шт{stock_warning}\n\n"
            )

    keyboard = [
        [InlineKeyboardButton("⬅️ К выкупам", callback_data="sales_menu")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ]

    await update.callback_query.message.reply_text(
        text[:4000],
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def refresh_stocks(update, context):
    await update.callback_query.message.reply_text("🔄 Обновляю остатки по кабинетам...")

    ok = await update_all_stocks()

    if ok:
        await update.callback_query.message.reply_text("✅ Остатки обновлены.")
    else:
        await update.callback_query.message.reply_text(
            "⚠️ WB временно ограничил запросы. Показываю старые остатки из кэша."
        )


async def refresh_sales(update, context):
    await update.callback_query.message.reply_text("🔄 Обновляю выкупы по кабинетам...")

    ok = await update_all_sales()

    if ok:
        await update.callback_query.message.reply_text("✅ Выкупы обновлены.")
    else:
        await update.callback_query.message.reply_text(
            "⚠️ WB временно ограничил запросы. Показываю старые выкупы из кэша."
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

    elif query.data == "sales_menu":
        await sales_menu(update, context)

    elif query.data == "sales_account_main":
        await sales_summary(update, context, "main")

    elif query.data == "sales_account_second":
        await sales_summary(update, context, "second")

    elif query.data == "sales_account_all":
        await sales_summary(update, context, "all")

    elif query.data == "refresh_stocks":
        await refresh_stocks(update, context)

    elif query.data == "refresh_sales":
        await refresh_sales(update, context)

    elif query.data.startswith("article_"):
        parts = query.data.split("_", 2)
        account_key = parts[1]
        base_article = parts[2]
        await article_detail(update, context, account_key, base_article)

    elif query.data.startswith("noop_"):
        await query.message.reply_text("Выберите артикул ниже.")


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

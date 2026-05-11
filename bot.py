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
        "18298", "6758", "18298-1", "18892", "18321", "18047",
        "2372", "18688", "18550-1", "2371-1", "18550", "550",
        "2372-1", "8801"
    ],
    "second": [
        "1997", "1997-1", "8269-1", "8269",
        "18816", "118502", "2136", "18295"
    ]
}

SALES_PERIOD_DAYS = 7
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

    return time.strftime("%d.%m.%Y %H:%M", time.localtime(timestamp))


def get_base_article(article, account_key):
    groups = ARTICLE_GROUPS.get(account_key, [])

    for group in sorted(groups, key=len, reverse=True):
        if str(article).startswith(group):
            return group

    return None


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
        return {
            "ok": False,
            "error": "429 Too Many Requests — WB ограничил частые запросы"
        }

    if response.status_code == 401:
        return {
            "ok": False,
            "error": "401 Unauthorized — неверный токен"
        }

    if response.status_code == 403:
        return {
            "ok": False,
            "error": "403 Forbidden — у токена нет нужного доступа"
        }

    try:
        response.raise_for_status()
        return {
            "ok": True,
            "data": response.json()
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }


def fetch_stocks_from_wb(account_key):
    token = WB_ACCOUNTS[account_key]["token"]

    if not token:
        return {
            "ok": False,
            "error": f"Нет токена для {WB_ACCOUNTS[account_key]['name']}"
        }

    url = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"

    params = {
        "dateFrom": "2024-01-01T00:00:00"
    }

    return wb_request(token, url, params)


def fetch_sales_from_wb(account_key):
    token = WB_ACCOUNTS[account_key]["token"]

    if not token:
        return {
            "ok": False,
            "error": f"Нет токена для {WB_ACCOUNTS[account_key]['name']}"
        }

    url = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"

    date_from = (
        datetime.now() - timedelta(days=SALES_PERIOD_DAYS)
    ).strftime("%Y-%m-%dT00:00:00")

    params = {
        "dateFrom": date_from
    }

    return wb_request(token, url, params)


async def update_stocks_cache(account_key):
    global stocks_cache

    result = await asyncio.to_thread(fetch_stocks_from_wb, account_key)

    if not result["ok"]:
        return result

    data = result["data"]

    stocks_cache[account_key] = {
        "time": time.time(),
        "data": data
    }

    save_json(
        cache_file("stocks", account_key),
        stocks_cache[account_key]
    )

    return {
        "ok": True,
        "count": len(data)
    }


async def update_sales_cache(account_key):
    global sales_cache

    result = await asyncio.to_thread(fetch_sales_from_wb, account_key)

    if not result["ok"]:
        return result

    data = result["data"]

    sales_cache[account_key] = {
        "time": time.time(),
        "data": data
    }

    save_json(
        cache_file("sales", account_key),
        sales_cache[account_key]
    )

    return {
        "ok": True,
        "count": len(data)
    }


async def post_init(application):
    load_all_cache()


def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Остатки по артикулам", callback_data="articles_menu")],
        [InlineKeyboardButton("📦 Сводка остатков", callback_data="stocks_summary")],
        [InlineKeyboardButton("💰 Выкупы ТОП-10", callback_data="sales_menu")],
        [InlineKeyboardButton("🔄 Обновление данных", callback_data="refresh_menu")]
    ])


def refresh_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Остатки Эльвиры", callback_data="refresh_stocks_main")],
        [InlineKeyboardButton("🔄 Остатки Рината", callback_data="refresh_stocks_second")],
        [InlineKeyboardButton("🔄 Выкупы Эльвиры", callback_data="refresh_sales_main")],
        [InlineKeyboardButton("🔄 Выкупы Рината", callback_data="refresh_sales_second")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
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


async def refresh_menu(update, context):
    await update.callback_query.message.reply_text(
        "Выберите, что обновить.",
        reply_markup=refresh_keyboard()
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

    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")
    ])

    await update.callback_query.message.reply_text(
        f"Выберите артикул.\nПокажу размеры, где остаток меньше {LOW_STOCK_LIMIT} шт.",
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

            account_grouped[base] = (
                account_grouped.get(base, 0) + quantity
            )

            account_total += quantity
            total_all += quantity

        text += f"🏬 {account['name']}\n"
        text += f"Обновлено: {format_time(cache.get('time', 0))}\n"
        text += f"Итого: {account_total} шт\n"

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
            "quantity": quantity,
            "barcode": item.get("barcode", "-"),
            "size": item.get("techSize", "-"),
            "warehouse": item.get("warehouseName", "-")
        })

    if not items:
        text = (
            f"✅ {account['name']}\n"
            f"Артикул {base_article}\n\n"
            f"Нет размеров с остатком меньше {LOW_STOCK_LIMIT} шт.\n\n"
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
                f"Размер: {item['size']}\n"
                f"Баркод: {item['barcode']}\n"
                f"Остаток: {item['quantity']} шт\n"
                f"Склад: {item['warehouse']}\n\n"
            )

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

            base = get_base_article(article, account_key)

            if not base:
                continue

            size = item.get("techSize", "-")
            barcode = item.get("barcode", "-")

            price = (
                item.get("finishedPrice")
                or item.get("forPay")
                or item.get("totalPrice")
                or 0
            )

            stock_qty = stock_lookup.get(
                (article, size, barcode),
                0
            )

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
        title = f"📊 Общие выкупы за {SALES_PERIOD_DAYS} дней"
    else:
        title = (
            f"💰 Выкупы за {SALES_PERIOD_DAYS} дней\n"
            f"{WB_ACCOUNTS[account_filter]['name']}"
        )

    total_sum = sum(x["sum"] for x in items)
    total_count = sum(x["count"] for x in items)

    if not items:
        text = (
            f"{title}\n\n"
            f"Выкупов за последние {SALES_PERIOD_DAYS} дней не найдено."
        )
    else:
        text = (
            f"{title}\n\n"
            f"Сумма выкупов: {round(total_sum, 2)} ₽\n"
            f"Количество выкупленных товаров: {total_count}\n\n"
            f"🔥 ТОП-{TOP_SALES_LIMIT} по количеству выкупов:\n\n"
        )

        for index, item in enumerate(items[:TOP_SALES_LIMIT], start=1):
            stock_warning = (
                " ⚠️"
                if item["stock"] < LOW_STOCK_LIMIT
                else ""
            )

            text += (
                f"{index}. {item['article']}\n"
                f"Кабинет: {item['account']}\n"
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


async def refresh_one_stocks(update, context, account_key):
    account_name = WB_ACCOUNTS[account_key]["name"]

    await update.callback_query.message.reply_text(
        f"🔄 Обновляю остатки: {account_name}..."
    )

    result = await update_stocks_cache(account_key)

    if result["ok"]:
        await update.callback_query.message.reply_text(
            f"✅ Остатки обновлены: {account_name}\n"
            f"Строк из WB: {result['count']}"
        )
    else:
        await update.callback_query.message.reply_text(
            f"⚠️ Остатки не обновлены: {account_name}\n"
            f"Причина: {result['error']}"
        )


async def refresh_one_sales(update, context, account_key):
    account_name = WB_ACCOUNTS[account_key]["name"]

    await update.callback_query.message.reply_text(
        f"🔄 Обновляю выкупы: {account_name}..."
    )

    result = await update_sales_cache(account_key)

    if result["ok"]:
        await update.callback_query.message.reply_text(
            f"✅ Выкупы обновлены: {account_name}\n"
            f"Строк из WB: {result['count']}"
        )
    else:
        await update.callback_query.message.reply_text(
            f"⚠️ Выкупы не обновлены: {account_name}\n"
            f"Причина: {result['error']}"
        )


async def button_handler(update, context):
    query = update.callback_query

    await query.answer()

    if query.data == "main_menu":
        await main_menu(query)

    elif query.data == "refresh_menu":
        await refresh_menu(update, context)

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

    elif query.data == "refresh_stocks_main":
        await refresh_one_stocks(update, context, "main")

    elif query.data == "refresh_stocks_second":
        await refresh_one_stocks(update, context, "second")

    elif query.data == "refresh_sales_main":
        await refresh_one_sales(update, context, "main")

    elif query.data == "refresh_sales_second":
        await refresh_one_sales(update, context, "second")

    elif query.data.startswith("article_"):
        parts = query.data.split("_", 2)

        account_key = parts[1]
        base_article = parts[2]

        await article_detail(
            update,
            context,
            account_key,
            base_article
        )

    elif query.data.startswith("noop_"):
        await query.message.reply_text(
            "Выберите артикул ниже."
        )


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

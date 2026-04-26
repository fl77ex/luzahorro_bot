from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import gspread
import telebot
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup


BASE_DIR = Path(__file__).resolve().parent
LANGUAGES_DIR = BASE_DIR / "languages"
START_COUNT_FILE = BASE_DIR / "bot_start_count.txt"
SHEET_NAME = "Luz"
WORKSHEET_NAME = "bot"
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
SUPPORTED_LANGUAGES = {
    "valencian": "Valencià",
    "spanish": "Español",
    "russian": "Русский",
}


load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

user_sessions: dict[int, dict[str, Any]] = {}


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


TOKEN = require_env("TELEGRAM_BOT_TOKEN")
GOOGLE_CREDENTIALS = require_env("GOOGLE_CREDENTIALS")

bot = telebot.TeleBot(TOKEN)

credentials = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS, SCOPE)
client = gspread.authorize(credentials)
sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)


def increment_start_count() -> None:
    count = 0
    if START_COUNT_FILE.exists():
        raw_value = START_COUNT_FILE.read_text(encoding="utf-8").strip()
        if raw_value.isdigit():
            count = int(raw_value)

    START_COUNT_FILE.write_text(str(count + 1), encoding="utf-8")


def load_language(lang: str) -> dict[str, str]:
    language_path = LANGUAGES_DIR / f"{lang}.json"
    with language_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_tariffs() -> list[dict[str, Any]]:
    return sheet.get_all_records()


def build_language_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for lang_code, label in SUPPORTED_LANGUAGES.items():
        markup.add(InlineKeyboardButton(label, callback_data=f"lang_{lang_code}"))
    return markup


def parse_float_value(value: str) -> float:
    return float(value.replace(",", ".").strip())


@bot.message_handler(commands=["start"])
def start(message: telebot.types.Message) -> None:
    increment_start_count()
    bot.send_message(
        message.chat.id,
        "Select your language / Seleccione su idioma / Выберите язык",
        reply_markup=build_language_keyboard(),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
def choose_language(call: telebot.types.CallbackQuery) -> None:
    lang = call.data.split("_", maxsplit=1)[1]
    if lang not in SUPPORTED_LANGUAGES:
        bot.answer_callback_query(call.id, "Unsupported language")
        return

    user_sessions[call.message.chat.id] = {"lang": lang}

    texts = load_language(lang)
    bot.edit_message_text(texts["info"], call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, texts["enter_power"])
    bot.register_next_step_handler(call.message, process_power)


def process_power(message: telebot.types.Message) -> None:
    user_id = message.chat.id
    lang = user_sessions[user_id]["lang"]
    texts = load_language(lang)

    try:
        power = parse_float_value(message.text)
        if not 0 < power <= 15:
            raise ValueError
    except (AttributeError, ValueError):
        bot.send_message(user_id, texts["invalid_power"])
        bot.register_next_step_handler(message, process_power)
        return

    user_sessions[user_id]["power"] = power
    bot.send_message(user_id, texts["enter_consumption"])
    bot.register_next_step_handler(message, process_consumption)


def process_consumption(message: telebot.types.Message) -> None:
    user_id = message.chat.id
    lang = user_sessions[user_id]["lang"]
    texts = load_language(lang)

    try:
        consumption = int(message.text)
        if not 0 < consumption <= 5000:
            raise ValueError
    except (TypeError, ValueError):
        bot.send_message(user_id, texts["invalid_consumption"])
        bot.register_next_step_handler(message, process_consumption)
        return

    user_sessions[user_id]["consumption"] = consumption
    send_tariff_results(user_id)


def calculate_tariff_total(
    power: float,
    consumption: int,
    tariff: dict[str, Any],
) -> dict[str, Any]:
    punta = float(tariff["Punta"])
    valle = float(tariff["Valle"])
    other_costs = float(tariff["Otros"])
    electricity_tax = float(tariff["Imp electr"]) / 100
    vat = float(tariff["IVA"]) / 100
    kwh_price = float(tariff["KWh"])

    power_cost = kwh_price * consumption
    energy_cost = (punta + valle) * power * 30
    tax_amount = (power_cost + energy_cost) * electricity_tax
    total = (power_cost + energy_cost + tax_amount + other_costs) * (1 + vat)

    return {
        "name": tariff["Name"],
        "link": tariff["Link"],
        "total": total,
        "punta": punta,
        "valle": valle,
        "otros": other_costs,
        "power_c": kwh_price,
        "imp_electr": electricity_tax * 100,
        "iva": vat * 100,
        "contrato": tariff["Contrato"] or "-",
        "actualizacion": tariff["Actual"],
    }


def send_tariff_results(user_id: int) -> None:
    power = user_sessions[user_id]["power"]
    consumption = user_sessions[user_id]["consumption"]
    texts = load_language(user_sessions[user_id]["lang"])

    tariff_list = [
        calculate_tariff_total(power, consumption, tariff)
        for tariff in get_tariffs()
    ]
    tariff_list.sort(key=lambda item: item["total"])

    results = "".join(
        texts["plan_template"].format(
            name=f"[{tariff['name']}]({tariff['link']})",
            total=tariff["total"],
            punta=tariff["punta"],
            valle=tariff["valle"],
            otros=tariff["otros"],
            power_c=tariff["power_c"],
            imp_electr=tariff["imp_electr"],
            iva=tariff["iva"],
            contrato=tariff["contrato"],
            actualizacion=tariff["actualizacion"],
        )
        for tariff in tariff_list
    )

    bot.send_message(
        user_id,
        results,
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )
    bot.send_message(user_id, texts["calculate_again"])


def run_bot() -> None:
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception:
            logging.exception("Bot polling failed, retrying in 2 seconds")
            time.sleep(2)


if __name__ == "__main__":
    run_bot()

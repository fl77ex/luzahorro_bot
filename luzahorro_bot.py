import telebot
import gspread
import os
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import time

# Загрузка настроек из .env
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

bot = telebot.TeleBot(TOKEN)

# Подключение к Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS, SCOPE)
client = gspread.authorize(CREDS)
sheet = client.open("Luz").worksheet("bot")

data = {}

# Функция для увеличения счетчика запусков
def increment_start_count():
    # Проверяем, существует ли файл для хранения счетчика
    if os.path.exists("bot_start_count.txt"):
        with open("bot_start_count.txt", "r") as file:
            count = int(file.read())  # Читаем текущий счетчик
    else:
        count = 0  # Если файла нет, начинаем с 0
    
    count += 1  # Увеличиваем счетчик
    with open("bot_start_count.txt", "w") as file:
        file.write(str(count))  # Записываем новый счетчик в файл

# Загрузка языковых файлов
def load_language(lang):
    with open(f"languages/{lang}.json", "r", encoding="utf-8") as file:
        return json.load(file)

@bot.message_handler(commands=['start'])
def start(message):
    increment_start_count()  # Увеличиваем счетчик запусков
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Valencià", callback_data="lang_valencian"))
    markup.add(InlineKeyboardButton("Español", callback_data="lang_spanish"))
    markup.add(InlineKeyboardButton("Русский", callback_data="lang_russian"))
    bot.send_message(message.chat.id, "Seleccioneu el vostre idioma / Seleccione su idioma / Выберите язык", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
def choose_language(call):
    lang = call.data.split("_")[1]
    data[call.message.chat.id] = {"lang": lang}
    texts = load_language(lang)
    bot.edit_message_text(texts["info"], call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, texts["enter_power"])  # просим ввести мощность
    bot.register_next_step_handler(call.message, process_power)

def process_power(message):
    user_id = message.chat.id
    lang = data[user_id]["lang"]
    texts = load_language(lang)

    try:
        power_str = message.text.replace(",", ".")  # заменяем запятую на точку
        power = float(power_str)
        if power <= 0 or power > 15:
            raise ValueError
        data[user_id]["power"] = power
        bot.send_message(user_id, texts["enter_consumption"])  # просим ввести потребление
        bot.register_next_step_handler(message, process_consumption)
    except ValueError:
        bot.send_message(user_id, texts["invalid_power"])
        bot.register_next_step_handler(message, process_power)

def process_consumption(message):
    user_id = message.chat.id
    lang = data[user_id]["lang"]
    texts = load_language(lang)

    try:
        consumption = int(message.text)
        if consumption <= 0 or consumption > 5000:
            raise ValueError
        data[user_id]["consumption"] = consumption
        calculate_cost_manual(user_id, consumption)  # вызываем расчёт
    except ValueError:
        bot.send_message(user_id, texts["invalid_consumption"])
        bot.register_next_step_handler(message, process_consumption)

def calculate_cost_manual(user_id, consumption):
    power = data[user_id]["power"]
    texts = load_language(data[user_id]["lang"])
    tariffs = get_tariffs()

    results = ""
    tariff_list = []

    for tariff in tariffs:
        name = tariff["Name"]
        link = tariff["Link"]
        punta = float(tariff["Punta"])
        valle = float(tariff["Valle"])
        otros = float(tariff["Otros"])
        contrato = tariff["Contrato"] if tariff["Contrato"] else "-"
        actualizacion = tariff["Actual"]
        imp_electr = float(tariff["Imp electr"]) / 100
        iva = float(tariff["IVA"]) / 100
        power_c = float(tariff["KWh"])

        power_cost = power_c * consumption
        energy_cost = (punta + valle) * float(power) * 30
        tax = (power_cost + energy_cost) * imp_electr
        total = (power_cost + energy_cost + tax + otros) * (1 + iva)

        tariff_list.append({
            "name": name,
            "link": link,
            "total": total,
            "punta": punta,
            "valle": valle,
            "otros": otros,
            "power_c": power_c,
            "imp_electr": imp_electr * 100,
            "iva": iva * 100,
            "contrato": contrato,
            "actualizacion": actualizacion
        })

    tariff_list.sort(key=lambda x: x["total"])

    for tariff in tariff_list:
        results += texts["plan_template"].format(
            name=f"[{tariff['name']}]({tariff['link']})",
            total=tariff["total"], punta=tariff["punta"], valle=tariff["valle"],
            otros=tariff["otros"], power_c=tariff["power_c"],
            imp_electr=tariff["imp_electr"], iva=tariff["iva"],
            contrato=tariff["contrato"], actualizacion=tariff["actualizacion"]
        )

    bot.send_message(user_id, results, parse_mode="Markdown", disable_web_page_preview=True)
    bot.send_message(user_id, texts["calculate_again"])

def get_tariffs():
    records = sheet.get_all_records()
    return records

while True:
    try:
        bot.polling(none_stop=True)
    except:
        time.sleep(2)

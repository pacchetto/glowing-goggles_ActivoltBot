import asyncio
import sqlite3

import requests
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database
import csv
import os
from aiogram.types import FSInputFile

# Завантаження ключів з .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# Стан для покрокового створення запису про аварію (Машина станів - FSM)
class AccidentState(StatesGroup):
    waiting_for_asset_id = State()
    waiting_for_description = State()
    waiting_for_photo = State()


# Головне меню
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📋 Довідник PAS"),
            KeyboardButton(text="⚠️ Нова аварія")
        ],
        [
            KeyboardButton(text="📊 Журнал OZA"),
            KeyboardButton(text="📥 Експорт (CSV)")
        ],
        [
            KeyboardButton(text="🌤 Погода в регіоні")
        ]
    ],
    resize_keyboard=True,
    input_field_placeholder="Оберіть функцію з меню нижче 👇"
)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Авторизація/реєстрація користувача в БД
    database.add_user(message.from_user.id, message.from_user.full_name)
    await message.answer(
        f"Вітаю, {message.from_user.full_name}! Ви авторизовані в системі ТОВ «Активольт».\nОберіть дію:",
        reply_markup=main_kb
    )


@dp.message(F.text == "📋 Довідник PAS")
async def show_assets(message: types.Message):
    assets = database.get_assets()
    text = "<b>Об'єкти системи PAS:</b>\n\n"
    for a in assets:
        text += f"🔹 <b>ID:</b> {a[0]}\n<b>Назва:</b> {a[1]}\n<b>Статус:</b> {a[2]}\n<b>Локація:</b> {a[3]}\n\n"
    await message.answer(text, parse_mode="HTML")


# --- РОБОТА ЗІ СТОРОННІМ API (Погода) ---
@dp.message(F.text == "🌤 Погода в регіоні")
async def get_weather(message: types.Message):
    city = "Ivano-Frankivsk"  # Локація головного офісу
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ua"
    try:
        res = requests.get(url).json()
        temp = res['main']['temp']
        desc = res['weather'][0]['description']
        wind = res['wind']['speed']
        await message.answer(
            f"🌤 <b>Погода в зоні обслуговування ({city}):</b>\nТемпература: {temp}°C, {desc}\nВітер: {wind} м/с",
            parse_mode="HTML")
    except Exception as e:
        await message.answer("Помилка підключення до сервісу погоди.")


# --- ЗАПИС АВАРІЇ (FSM + РОБОТА З ФАЙЛАМИ) ---
@dp.message(F.text == "⚠️ Нова аварія")
async def oza_start(message: types.Message, state: FSMContext):
    # Отримуємо всі об'єкти з бази даних
    assets = database.get_assets()

    # Створюємо клавіатуру з інлайн-кнопками
    builder = InlineKeyboardBuilder()
    for asset in assets:
        asset_id = asset[0]
        asset_name = asset[1]
        # callback_data - це те, що бот отримає "під капотом", коли юзер натисне кнопку
        builder.button(text=asset_name, callback_data=f"asset_{asset_id}")

    builder.adjust(1)  # Робимо так, щоб кожна кнопка була з нового рядка

    await message.answer(
        "Оберіть об'єкт, на якому сталася аварія (або потрібно провести роботи):",
        reply_markup=builder.as_markup()
    )
    await state.set_state(AccidentState.waiting_for_asset_id)


@dp.message(F.text == "📊 Журнал OZA")
async def view_accidents(message: types.Message):
    accidents = database.get_recent_accidents()

    if not accidents:
        await message.answer("У базі даних поки немає зареєстрованих аварій.")
        return

    text = "📂 <b>Останні 10 звернень у системі OZA:</b>\n\n"
    for acc in accidents:
        asset_name = acc[0]
        desc = acc[1]
        date = acc[2]
        text += f"📍 <b>{asset_name}</b>\n📝 {desc}\n📅 <i>{date}</i>\n"
        text += "--------------------------\n"

    await message.answer(text, parse_mode="HTML")


# --- РОБОТА З ФАЙЛАМИ (ЕКСПОРТ ЗВІТУ) ---
@dp.message(F.text == "📥 Експорт (CSV)")
async def export_csv(message: types.Message):
    # Отримуємо дані з БД
    accidents = database.get_recent_accidents()

    if not accidents:
        await message.answer("Немає даних для експорту.")
        return

    # Формуємо ім'я файлу (унікальне для кожного користувача)
    filename = f"report_OZA_{message.from_user.id}.csv"

    # Створення та запис даних у файл CSV (кодування utf-8-sig для підтримки кирилиці в Excel)
    with open(filename, mode='w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerow(['Об\'єкт', 'Опис поломки', 'Дата та час реєстрації'])  # Заголовки колонок
        for acc in accidents:
            writer.writerow([acc[0], acc[1], acc[2]])

    # Відправка готового файлу користувачеві в Telegram
    document = FSInputFile(filename)
    await message.answer_document(document, caption="📊 Звіт успішно згенеровано! Ви можете відкрити його в Excel.")

    # Видалення тимчасового файлу з сервера (щоб не забивати пам'ять)
    os.remove(filename)

@dp.callback_query(AccidentState.waiting_for_asset_id, F.data.startswith("asset_"))
async def process_asset_selection(callback: types.CallbackQuery, state: FSMContext):
    # Витягуємо ID об'єкта з callback_data (наприклад, з "asset_1" дістаємо "1")
    asset_id = int(callback.data.split("_")[1])

    # Зберігаємо ID в пам'ять машини станів (FSM)
    await state.update_data(asset_id=asset_id)

    # Прибираємо кнопки з екрану, щоб чат виглядав охайно
    await callback.message.edit_reply_markup(reply_markup=None)

    await callback.message.answer(f"✅ Об'єкт обрано.\nТепер опишіть суть поломки (текстом):")
    await state.set_state(AccidentState.waiting_for_description)

    # Підтверджуємо Telegram, що ми обробили натискання
    await callback.answer()


@dp.message(AccidentState.waiting_for_description)
async def process_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Надішліть фото з місця аварії (або напишіть 'без фото'):")
    await state.set_state(AccidentState.waiting_for_photo)


@dp.message(AccidentState.waiting_for_photo)
async def process_photo(message: types.Message, state: FSMContext):
    # Перевіряємо, чи користувач надіслав фото
    if message.photo:
        photo_id = message.photo[-1].file_id  # Беремо найкращу якість
    else:
        photo_id = "Немає фотографії"

    data = await state.get_data()

    # Записуємо в БД
    database.add_accident(data['asset_id'], data['description'], photo_id)

    await message.answer("✅ <b>Аварію успішно зафіксовано в системі OZA!</b>\nДані передано диспетчеру.",
                         parse_mode="HTML", reply_markup=main_kb)
    await state.clear()  # Очищаємо стан


async def main():
    database.init_db()  # Ініціалізація БД
    print("Бот ТОВ 'Активольт' запущено!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

def get_recent_accidents():
    conn = sqlite3.connect(database.DB_NAME)
    cursor = conn.cursor()
    # Використовуємо JOIN, щоб отримати назву об'єкта з таблиці assets
    cursor.execute('''
        SELECT a.name, acc.description, acc.created_at 
        FROM accidents acc
        JOIN assets a ON acc.asset_id = a.id
        ORDER BY acc.created_at DESC
        LIMIT 10
    ''')
    data = cursor.fetchall()
    conn.close()
    return data
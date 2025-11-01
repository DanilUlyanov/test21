from datetime import datetime
import logging
import os
import threading

from dotenv import load_dotenv
from flask import Flask
import requests
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


load_dotenv()

# Инициализация Flask
app = Flask(__name__)


@app.route("/")
def home():
    return "Бот запущен и работает!", 200


@app.route("/health")
def health():
    return {"status": "healthy"}, 200


# Загрузка токенов
API_KEY = os.getenv("API_KEY")
TG_KEY = os.getenv("TG_KEY")

if not API_KEY:
    raise ValueError("Не найден API_KEY в переменных окружения (.env)")
if not TG_KEY:
    raise ValueError("Не найден TG_KEY в переменных окружения (.env)")

DEFAULT_CITIES = ["Москва", "Санкт-Петербург", "Сочи", "Игора"]
DEFAULT_CITY = "Санкт-Петербург"

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Отключаем логирование httpx и httpcore (скрываем токены)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx").propagate = False
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpcore").propagate = False


def get_weather(city: str) -> str:
    """Получает погоду для указанного города через OpenWeatherMap API."""
    params = {
        "q": city,
        "appid": API_KEY,
        "units": "metric",
        "lang": "ru",
    }
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather", params=params
        )
        r.raise_for_status()
        data = r.json()
        description = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        humidity = data["main"]["humidity"]
        pressure = data["main"].get("grnd_level", "н/д")
        wind_speed = data["wind"]["speed"]
        sunset_timestamp = data["sys"]["sunset"]
        sunset_time = datetime.fromtimestamp(sunset_timestamp).strftime("%H:%M")
        weather_info = (
            f"🌤 <b>Погода в {city}</b>\n"
            f"Описание: {description}\n"
            f"Температура: {temp} °C\n"
            f"Влажность: {humidity} %\n"
            f"Давление: {pressure} гПа\n"
            f"Скорость ветра: {wind_speed} м/с\n"
            f"Закат: {sunset_time}"
        )
        return weather_info
    except requests.exceptions.HTTPError as e:
        if r.status_code == 404:
            return f"❌ Город '{city}' не найден."
        else:
            logger.error(f"HTTP ошибка при запросе погоды для {city}: {e}")
            return f"❌ Ошибка API: {e}"
    except Exception as e:
        logger.error(f"Неожиданная ошибка при запросе погоды для {city}: {e}")
        return f"❌ Произошла ошибка: {e}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start — показывает клавиатуру с городами"""
    keyboard = [[KeyboardButton(city)] for city in DEFAULT_CITIES]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )
    await update.message.reply_text(
        "Привет! Выберите город из списка или введите свой:",
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "🤖 <b>Помощник погодного бота</b>\n\n"
        "Доступные команды:\n"
        "/start — открыть клавиатуру с городами\n"
        "/help — показать эту справку\n"
        "/weather &lt;город&gt; — погода в указанном городе\n\n"
        "Вы также можете просто написать название города.\n\n"
        "Пример:\n"
        "/weather Москва"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")


async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /weather <город>"""
    if context.args:
        city = " ".join(context.args)
        weather_info = get_weather(city)
        await update.message.reply_text(weather_info, parse_mode="HTML")
    else:
        await update.message.reply_text(
            "❌ Укажите город после команды /weather", parse_mode="HTML"
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений — реагирует на ввод города"""
    city = update.message.text.strip()
    weather_info = get_weather(city)
    await update.message.reply_text(weather_info, parse_mode="HTML")
    context.user_data["last_city"] = city
    logger.info(f"Пользователь {update.effective_user.id} запросил погоду для {city}")


def run_flask():
    """Запускает Flask-сервер в отдельном потоке."""
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Запуск Flask на порту {port}")
    app.run(host="0.0.0.0", port=port)


def main():
    """Запуск бота и Flask-сервера."""
    # Запуск Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Запуск Telegram-бота
    application = Application.builder().token(TG_KEY).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("weather", weather))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Запуск Telegram-бота...")
    application.run_polling()


if __name__ == "__main__":
    main()

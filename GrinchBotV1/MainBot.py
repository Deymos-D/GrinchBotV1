import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.methods import DeleteWebhook
from aiogram.client.default import DefaultBotProperties

import google.generativeai as genai

#Налаштування логування
def setup_logging():
    """Налаштовує логування для запису у файл та виводу в консоль."""
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # створення директорії для логів, у разі її відсутності
    if not os.path.exists('logs'):
        os.makedirs('logs')
        
    # Налаштування для запису у файл (з ротацією)
    # RotatingFileHandler автоматично керуватиме розміром файлу
    log_file = os.path.join('logs', 'bot.log')
    # Створюємо обробник, який записує у файл до 5MB, зберігаючи 3 старих файли
    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)

    # Налаштування для виводу в консоль
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)

    # Отримуємо кореневий логер і додаємо до нього наші обробники
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

# Ініціалізація логування
setup_logging()


# Завантаження конфігурації
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logging.critical("Не вдалося знайти TELEGRAM_TOKEN або GEMINI_API_KEY у змінних середовища.")
    exit("Помилка: Відсутні необхідні токени. Перевірте файл .env або змінні середовища.")

bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Конфігурація Gemini
genai.configure(api_key=GEMINI_API_KEY)
GEMINI_MODEL = genai.GenerativeModel("gemini-1.5-flash-latest")


# Утиліти для читання файлу та звернення до Gemini
def load_reference(file_path: str = "FAQ.txt") -> str:
    """Завантажує текст довідкової інформації з файлу."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл '{file_path}' не знайдено.")
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

async def ask_gemini(question: str, reference: str) -> str:
    """Готує промпт та надсилає його в Gemini, повертає отриманий текст."""
    prompt = (
        "Ти — Асистент кафедри комп’ютерних наук. "
        "Твоє завдання — чітко та лаконічно відповідати на питання студентів та абітурієнтів, "
        "спираючись на надану тобі довідкову інформацію. "
        "У випадку, якщо питання не містить інформації з довідки,  ввічиливо повідомляй про це. "
        "Відпові надавай тільки українською мовою.\n\n"
        "--- Довідкова інформація ---\n"
        f"{reference}\n"
        "--- Кінець довідкової інформації ---\n\n"
        f"Питання користувача: {question}"
    )
    
    result = await GEMINI_MODEL.generate_content_async(prompt)
    return result.text


# Хендлери повідомлень
@dp.message(Command("start"))
async def handle_start(message: types.Message):
    """Обробка команди /start."""
    logging.info(f"Користувач {message.from_user.id} ({message.from_user.full_name}) запустив бота командою /start.")
    await message.answer(
        "Привіт! Я - асистент кафедри комп’ютерних наук.\n\n"
        "Чим можу допомогти? Напишіть своє питання"
    )

@dp.message()
async def handle_text(message: types.Message):
    """Обробник для будь-яких текстових повідомлень."""
    logging.info(f"Отримано повідомлення від {message.from_user.id}: '{message.text}'")
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        reference_text = load_reference()
    except FileNotFoundError as err:
        logging.error(err)
        await message.answer("Файл `FAQ.txt`. Будь ласка, перевірте його наявність.")
        return

    try:
        answer = await ask_gemini(message.text, reference_text)
        await message.answer(answer, parse_mode="Markdown")
        logging.info(f"Надано відповідь для {message.from_user.id}.")
    except Exception as e:
        logging.error(f"Помилка Gemini API {message.from_user.id}: {e}")
        await message.answer("Виникла помилка при обробці вашого запиту. Спробуйте ще раз пізніше.")

# Функція запуску бота
async def main():
    """Функція запуску бота."""
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запускається...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    print("Поточна робоча директорія:", os.getcwd())
    print("Файл FAQ.txt існує:", os.path.isfile("FAQ.txt"))
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Роботу бота зупинено вручну.")
    except Exception as e:
        logging.critical(f"Помилка під час запуску: {e}", exc_info=True)
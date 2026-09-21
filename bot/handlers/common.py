from aiogram import Router, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from bot.keyboards.inline import get_main_menu_keyboard

router = Router(name="common_router")


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    user_name = html.quote(message.from_user.first_name or "Автомобилист")

    text = (
        f"👋 <b>Привет, {user_name}!</b>\n\n"
        "Я твой <b>«Авто-Гараж Ассистент»</b> с искусственным интеллектом.\n\n"
        "🎙 <b>Как со мной работать?</b>\n"
        "Просто отправь мне <b>голосовое</b> или <b>текстовое сообщение</b> своими словами:\n\n"
        "• <i>«Заправил 45 литров на Лукойле на 2500 рублей, пробег 124 500»</i>\n"
        "• <i>«Поменял масло и фильтры, обошлось в 5 800 руб, пробег 125 000»</i>\n"
        "• <i>«Положил динамометрический ключ во второй ящик слева»</i>\n"
        "• <i>«Где лежит домкрат?»</i>\n\n"
        "⚡ Я автоматически распознаю параметры, предложу карточку проверки и бережно сохраню данные в базу."
    )

    await message.answer(text, reply_markup=get_main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help."""
    text = (
        "🛠 <b>Справка по возможностям бота</b>\n\n"
        "<b>1. Учет заправок (FuelLog):</b>\n"
        "Назови литры, сумму, пробег и (опционально) АЗС. Бот подсчитает средний расход и затраты.\n\n"
        "<b>2. Журнал ТО и ремонтов (ServiceLog):</b>\n"
        "Фиксируй замену расходников, ремонты, мойки и пробег для контроля интервалов.\n\n"
        "<b>3. Инвентарь гаража и дачи (ItemLocation):</b>\n"
        "Запоминай местоположение инструментов, сезонных колес и запчастей, чтобы мгновенно находить их.\n\n"
        "<b>Команды:</b>\n"
        "/start — Главное меню\n"
        "/help — Эта справка\n"
        "/menu — Кнопки быстрого доступа"
    )
    await message.answer(text, reply_markup=get_main_menu_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Показывает главное меню."""
    await message.answer("🚘 <b>Панель управления автомобилем и гаражом:</b>", reply_markup=get_main_menu_keyboard())

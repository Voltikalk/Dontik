from aiogram import Router, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from bot.keyboards.inline import get_main_menu_keyboard
from bot.emojis import (
    E_HELLO,
    E_MIC,
    E_LIGHTNING,
    E_WRENCH,
    E_SPEEDOMETER,
    E_DROP,
    E_BOX,
    E_PIN
)

router = Router(name="common_router")


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    user_name = html.quote(message.from_user.first_name or "Автомобилист")

    text = (
        f"{E_HELLO} <b>Привет, {user_name}!</b>\n\n"
        "Я твой <b>«Авто-Гараж Ассистент»</b> с искусственным интеллектом.\n\n"
        f"{E_MIC} <b>Как со мной работать?</b>\n"
        "Просто отправь мне <b>голосовое</b> или <b>текстовое сообщение</b> своими словами:\n\n"
        "• <i>«Заправил 45 литров на Лукойле на 2500 рублей, пробег 124 500»</i>\n"
        "• <i>«Поменял масло и фильтры, обошлось в 5 800 руб, пробег 125 000»</i>\n"
        "• <i>«Положил динамометрический ключ во второй ящик слева»</i>\n"
        "• <i>«Где лежит домкрат?»</i>\n\n"
        f"{E_LIGHTNING} Я автоматически распознаю параметры, предложу карточку проверки и бережно сохраню данные в базу."
    )

    await message.answer(text, reply_markup=get_main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help."""
    text = (
        f"{E_WRENCH} <b>Справка по возможностям бота</b>\n\n"
        f"<b>1. Учет заправок ({E_DROP} FuelLog):</b>\n"
        "Назови литры, сумму, пробег и (опционально) АЗС. Бот подсчитает средний расход и затраты.\n\n"
        f"<b>2. Журнал ТО и ремонтов ({E_WRENCH} ServiceLog):</b>\n"
        "Фиксируй замену расходников, ремонты, мойки и пробег для контроля интервалов.\n\n"
        f"<b>3. Инвентарь гаража и дачи ({E_BOX} ItemLocation):</b>\n"
        "Запоминай местоположение инструментов, сезонных колес и запчастей, чтобы мгновенно находить их.\n\n"
        f"{E_PIN} <b>Команды:</b>\n"
        "/start — Главное меню\n"
        "/help — Эта справка\n"
        "/menu — Кнопки быстрого доступа"
    )
    await message.answer(text, reply_markup=get_main_menu_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Показывает главное меню."""
    await message.answer(f"{E_SPEEDOMETER} <b>Панель управления автомобилем и гаражом:</b>", reply_markup=get_main_menu_keyboard())

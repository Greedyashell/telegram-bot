from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.enums import ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv
import asyncio
import os
import logging
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Файл для хранения конфигурации файлов
CONFIG_FILE = "files_config.json"

# Хранилище ожидающих пользователей
pending_users = {}  # {user_id: {"file_id": file_id, "message_id": message_id}}


# FSM состояния для администратора
class AdminStates(StatesGroup):
    waiting_file_name = State()
    waiting_file_upload = State()
    waiting_file_description = State()
    waiting_file_cover = State()
    waiting_channels = State()
    waiting_repost_required = State()
    
    editing_file_id = State()
    waiting_new_cover = State()
    waiting_edit_channels = State()
    waiting_edit_repost = State()
    waiting_edit_description = State()


def load_files_config():
    """Загрузка конфигурации файлов"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_files_config(config):
    """Сохранение конфигурации файлов"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


async def check_subscription(user_id: int, channels: list) -> tuple:
    """Проверка подписки на каналы"""
    not_subscribed = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                not_subscribed.append(channel)
        except Exception as e:
            logger.error(f"Error checking subscription for user {user_id} in {channel}: {e}")
            not_subscribed.append(channel)
    
    return len(not_subscribed) == 0, not_subscribed


def create_files_keyboard():
    """Создание клавиатуры со списком файлов"""
    config = load_files_config()
    keyboard = []
    
    for file_id, file_data in config.items():
        # Проверяем что у файла есть название
        file_name = file_data.get('name', 'Без названия')
        if file_name:  # Дополнительная проверка
            keyboard.append([InlineKeyboardButton(
                text=file_name, 
                callback_data=f"select_file_{file_id}"
            )])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_admin_keyboard():
    """Создание админ-клавиатуры"""
    keyboard = [
        [InlineKeyboardButton(text="➕ Добавить файл", callback_data="admin_add_file")],
        [InlineKeyboardButton(text="📋 Список файлов", callback_data="admin_list_files")],
        [InlineKeyboardButton(text="🗑 Удалить файл", callback_data="admin_delete_file")],
        [InlineKeyboardButton(text="✏️ Редактировать файл", callback_data="admin_edit_file")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@dp.message(CommandStart())
async def start(message: Message):
    """Обработка команды /start"""
    try:
        config = load_files_config()
        
        if not config:
            await message.answer("❌ В данный момент файлы недоступны. Попробуйте позже.")
            logger.warning("No files in config when user tried /start")
            return
        
        text = "🎵 *ВЫБЕРИТЕ КОЛЛЕКЦИЮ*\n\nВыберите файл, который хотите получить:"
        keyboard = create_files_keyboard()
        
        # Проверяем что клавиатура не пустая
        if not keyboard.inline_keyboard:
            await message.answer("❌ Нет доступных файлов. Попробуйте позже.")
            logger.warning("Empty keyboard created")
            return
        
        await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)
        logger.info(f"Start command from user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже или обратитесь к администратору.")


@dp.callback_query(F.data.startswith("select_file_"))
async def select_file(callback: CallbackQuery):
    """Выбор файла пользователем"""
    file_id = callback.data.replace("select_file_", "")  # Исправлено: берём всё после префикса
    config = load_files_config()
    
    logger.info(f"User {callback.from_user.id} selected file: {file_id}")
    logger.info(f"Available files: {list(config.keys())}")
    
    if file_id not in config:
        await callback.answer("❌ Файл не найден", show_alert=True)
        logger.error(f"File {file_id} not found in config")
        return
    
    file_data = config[file_id]
    channels = file_data.get('channels', [])
    repost_required = file_data.get('repost_required', False)
    user_id = callback.from_user.id
    
    # Если нет никаких условий - сразу отправляем файл
    if not channels and not repost_required:
        try:
            await callback.message.delete()
            await bot.send_document(
                user_id, 
                file_data['file_id'],
                caption=f"✅ *Вот ваш файл!*\n\n📦 {file_data['name']}",
                parse_mode="Markdown"
            )
            logger.info(f"File auto-sent to user {user_id} (no conditions)")
            await callback.answer("✅ Файл отправлен!")
            return
        except Exception as e:
            logger.error(f"Error auto-sending file to {user_id}: {e}")
            await callback.answer("❌ Ошибка отправки файла", show_alert=True)
            return
    
    # Если есть каналы но нет репоста - проверяем подписку и отправляем автоматически
    if channels and not repost_required:
        # Проверяем подписку
        is_subscribed, not_subscribed_channels = await check_subscription(user_id, channels)
        
        if not is_subscribed:
            # Показываем каналы для подписки
            keyboard_buttons = []
            for channel in channels:
                channel_name = channel.lstrip('@')
                keyboard_buttons.append([InlineKeyboardButton(
                    text=f"📢 Подписаться: {channel}", 
                    url=f"https://t.me/{channel_name}"
                )])
            keyboard_buttons.append([InlineKeyboardButton(
                text="✅ Я подписался", 
                callback_data=f"check_sub_{file_id}"
            )])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            
            text = (
                f"📦 *{file_data['name']}*\n\n"
                f"{file_data.get('description', 'Описание отсутствует')}\n\n"
                f"📝 *ЧТО НУЖНО СДЕЛАТЬ:*\n"
                f"1️⃣ Подпишитесь на каналы ({len(channels)} шт.)\n"
                f"2️⃣ Нажмите кнопку '✅ Я подписался'\n\n"
                f"⚡ Файл будет отправлен автоматически после проверки подписки"
            )
            
            # Отправляем обложку если есть
            if file_data.get('cover_file_id'):
                try:
                    await callback.message.delete()
                    await bot.send_photo(
                        user_id,
                        file_data['cover_file_id'],
                        caption=text,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                except:
                    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
            else:
                await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
            
            await callback.answer()
            return
        else:
            # Подписка подтверждена - отправляем файл
            try:
                await callback.message.delete()
                await bot.send_document(
                    user_id, 
                    file_data['file_id'],
                    caption=f"✅ *Вы получили файл!*\n\n📦 {file_data['name']}",
                    parse_mode="Markdown"
                )
                logger.info(f"File auto-sent to user {user_id} after subscription check")
                await callback.answer("✅ Файл отправлен!")
                return
            except Exception as e:
                logger.error(f"Error auto-sending file to {user_id}: {e}")
                await callback.answer("❌ Ошибка отправки файла", show_alert=True)
                return
    
    # Если требуется репост - показываем инструкцию и ждем скриншот
    if repost_required:
        # Создаем кнопки для подписки на каналы
        keyboard_buttons = []
        for channel in channels:
            channel_name = channel.lstrip('@')
            keyboard_buttons.append([InlineKeyboardButton(
                text=f"📢 Подписаться: {channel}", 
                url=f"https://t.me/{channel_name}"
            )])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # Формируем текст с условиями
        conditions = []
        step = 1
        
        if channels:
            conditions.append(f"{step}️⃣ Подпишитесь на каналы ({len(channels)} шт.)")
            step += 1
        
        conditions.append(f"{step}️⃣ Сделайте репост в свой канал")
        step += 1
        conditions.append(f"{step}️⃣ Отправьте скриншот репоста")
        
        text = (
            f"📦 *{file_data['name']}*\n\n"
            f"{file_data.get('description', 'Описание отсутствует')}\n\n"
            f"📝 *ЧТО НУЖНО СДЕЛАТЬ:*\n"
            + "\n".join(conditions) +
            "\n\n⏳ Ожидайте подтверждения от администратора"
        )
        
        # Отправляем обложку если есть
        if file_data.get('cover_file_id'):
            try:
                await callback.message.delete()
                await bot.send_photo(
                    user_id,
                    file_data['cover_file_id'],
                    caption=text,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
            except:
                await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        
        # Сохраняем выбор пользователя
        if user_id not in pending_users:
            pending_users[user_id] = {}
        pending_users[user_id]['selected_file'] = file_id
        
        await callback.answer()


@dp.callback_query(F.data.startswith("check_sub_"))
async def check_subscription_callback(callback: CallbackQuery):
    """Проверка подписки по кнопке"""
    file_id = callback.data.replace("check_sub_", "")  # Исправлено
    config = load_files_config()
    
    if file_id not in config:
        await callback.answer("❌ Файл не найден", show_alert=True)
        return
    
    file_data = config[file_id]
    channels = file_data.get('channels', [])
    user_id = callback.from_user.id
    
    # Проверяем подписку
    is_subscribed, not_subscribed_channels = await check_subscription(user_id, channels)
    
    if not is_subscribed:
        channels_text = "\n".join([f"• {ch}" for ch in not_subscribed_channels])
        await callback.answer(
            f"❌ Вы еще не подписаны на:\n{channels_text}",
            show_alert=True
        )
        return
    
    # Подписка подтверждена - отправляем файл
    try:
        await callback.message.delete()
        await bot.send_document(
            user_id, 
            file_data['file_id'],
            caption=f"✅ *Вы получили файл!*\n\n📦 {file_data['name']}",
            parse_mode="Markdown"
        )
        logger.info(f"File auto-sent to user {user_id} after manual subscription check")
        await callback.answer("✅ Файл отправлен!")
    except Exception as e:
        logger.error(f"Error auto-sending file to {user_id}: {e}")
        await callback.answer("❌ Ошибка отправки файла", show_alert=True)


@dp.message(F.photo, StateFilter(None))
async def handle_screenshot(message: Message, state: FSMContext):
    """Обработка скриншотов от пользователей (только для репоста)"""
    # Этот обработчик срабатывает ТОЛЬКО когда пользователь НЕ в FSM состоянии
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    
    # Проверяем, выбрал ли пользователь файл
    if user_id not in pending_users or 'selected_file' not in pending_users[user_id]:
        await message.answer(
            "❌ Сначала выберите файл командой /start",
            parse_mode="Markdown"
        )
        return
    
    file_id = pending_users[user_id]['selected_file']
    config = load_files_config()
    
    if file_id not in config:
        await message.answer("❌ Выбранный файл больше не доступен. Используйте /start")
        return
    
    file_data = config[file_id]
    channels = file_data.get('channels', [])
    repost_required = file_data.get('repost_required', False)
    
    # Если репост не требуется - игнорируем фото
    if not repost_required:
        await message.answer(
            "ℹ️ Для этого файла не требуется отправка скриншота.\n"
            "Файл должен был быть отправлен автоматически.",
            parse_mode="Markdown"
        )
        return
    
    logger.info(f"Screenshot received from user {user_id} for file {file_id}")
    
    # Проверка подписки
    if channels:
        is_subscribed, not_subscribed_channels = await check_subscription(user_id, channels)
        if not is_subscribed:
            channels_text = "\n".join([f"• {ch}" for ch in not_subscribed_channels])
            await message.answer(
                f"❌ *НЕ ПОДПИСАНЫ*\n\n"
                f"Подпишитесь на эти каналы:\n{channels_text}\n\n"
                f"Затем отправьте скриншот снова.",
                parse_mode="Markdown"
            )
            logger.info(f"User {user_id} not subscribed to: {not_subscribed_channels}")
            return
    
    # Отправляем на проверку админу
    pending_users[user_id]['message_id'] = message.message_id
    pending_users[user_id]['file_id'] = file_id
    
    # Создаем клавиатуру для админа
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{user_id}")
        ]
    ])
    
    caption = (
        f"📸 *Новый запрос на верификацию*\n\n"
        f"📦 Файл: *{file_data['name']}*\n"
        f"👤 User ID: `{user_id}`\n"
        f"🔗 Username: @{username}\n"
        f"👥 Имя: {message.from_user.full_name}\n\n"
        f"Команды: `/approve {user_id}` или `/reject {user_id}`"
    )
    
    await bot.send_photo(
        ADMIN_ID, 
        message.photo[-1].file_id, 
        caption=caption,
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
    await message.answer(
        "⏳ *СКРИНШОТ ПОЛУЧЕН*\n\n"
        "Ваш скриншот отправлен на проверку.\n"
        "Ожидайте подтверждения администратора.",
        parse_mode="Markdown"
    )
    
    logger.info(f"User {user_id} added to pending list for file {file_id}")


# ========== КОМАНДЫ АДМИНИСТРАТОРА ==========

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    """Админ-панель"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У вас нет доступа")
        return
    
    keyboard = create_admin_keyboard()
    await message.answer(
        "👨‍💼 *АДМИН-ПАНЕЛЬ*\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "admin_add_file")
async def admin_add_file_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления файла"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📝 *Добавление нового файла*\n\n"
        "Шаг 1/6: Введите название файла:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_file_name)
    await callback.answer()


@dp.message(AdminStates.waiting_file_name)
async def admin_add_file_name(message: Message, state: FSMContext):
    """Получение названия файла"""
    await state.update_data(name=message.text)
    await message.answer(
        "📤 Шаг 2/6: Загрузите сам файл (документ):",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_file_upload)


@dp.message(AdminStates.waiting_file_upload, F.document)
async def admin_add_file_document(message: Message, state: FSMContext):
    """Получение файла"""
    await state.update_data(
        file_id=message.document.file_id,
        file_name=message.document.file_name
    )
    await message.answer(
        "📝 Шаг 3/6: Введите описание файла:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_file_description)


@dp.message(AdminStates.waiting_file_description)
async def admin_add_file_description(message: Message, state: FSMContext):
    """Получение описания"""
    await state.update_data(description=message.text)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_cover")]
    ])
    
    await message.answer(
        "🖼 Шаг 4/6: Загрузите обложку (фото) или нажмите 'Пропустить':",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await state.set_state(AdminStates.waiting_file_cover)


@dp.message(AdminStates.waiting_file_cover, F.photo)
async def admin_add_file_cover(message: Message, state: FSMContext):
    """Получение обложки"""
    logger.info(f"Cover photo received from admin {message.from_user.id}")
    await state.update_data(cover_file_id=message.photo[-1].file_id)
    logger.info(f"Cover file_id saved: {message.photo[-1].file_id}")
    await ask_channels(message, state)


@dp.callback_query(F.data == "skip_cover")
async def skip_cover(callback: CallbackQuery, state: FSMContext):
    """Пропуск обложки"""
    await state.update_data(cover_file_id=None)
    await callback.message.edit_text(
        "📢 Шаг 5/6: Введите список каналов для подписки через запятую\n"
        "(например: @channel1, @channel2)\n\n"
        "Или отправьте '-' чтобы пропустить:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_channels)
    await callback.answer()


async def ask_channels(message: Message, state: FSMContext):
    """Запрос каналов"""
    await message.answer(
        "📢 Шаг 5/6: Введите список каналов для подписки через запятую\n"
        "(например: @channel1, @channel2)\n\n"
        "Или отправьте '-' чтобы пропустить:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_channels)


@dp.message(AdminStates.waiting_channels)
async def admin_add_channels(message: Message, state: FSMContext):
    """Получение каналов"""
    if message.text.strip() == '-':
        channels = []
    else:
        channels = [ch.strip() for ch in message.text.split(',')]
    
    await state.update_data(channels=channels)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data="repost_yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="repost_no")]
    ])
    
    await message.answer(
        "🔄 Шаг 6/6: Требуется репост записи?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await state.set_state(AdminStates.waiting_repost_required)


@dp.callback_query(AdminStates.waiting_repost_required, F.data.in_(["repost_yes", "repost_no"]))
async def admin_add_repost(callback: CallbackQuery, state: FSMContext):
    """Получение требования репоста"""
    repost_required = callback.data == "repost_yes"
    data = await state.get_data()
    
    # Генерируем уникальный ID для файла
    config = load_files_config()
    file_id = f"file_{len(config) + 1}"
    
    # Сохраняем конфигурацию
    config[file_id] = {
        'name': data['name'],
        'file_id': data['file_id'],
        'file_name': data['file_name'],
        'description': data['description'],
        'cover_file_id': data.get('cover_file_id'),
        'channels': data['channels'],
        'repost_required': repost_required
    }
    
    save_files_config(config)
    
    await callback.message.edit_text(
        f"✅ *Файл успешно добавлен!*\n\n"
        f"📦 Название: {data['name']}\n"
        f"🆔 ID: `{file_id}`\n"
        f"📢 Каналов: {len(data['channels'])}\n"
        f"🔄 Репост: {'Да' if repost_required else 'Нет'}",
        parse_mode="Markdown"
    )
    
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "admin_list_files")
async def admin_list_files(callback: CallbackQuery):
    """Список файлов"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    config = load_files_config()
    
    if not config:
        await callback.message.edit_text("📋 Файлов пока нет")
        await callback.answer()
        return
    
    text = "📋 *СПИСОК ФАЙЛОВ:*\n\n"
    for file_id, data in config.items():
        text += (
            f"🆔 ID: `{file_id}`\n"
            f"📦 Название: {data['name']}\n"
            f"📢 Каналов: {len(data.get('channels', []))}\n"
            f"🔄 Репост: {'Да' if data.get('repost_required') else 'Нет'}\n"
            f"{'─' * 30}\n\n"
        )
    
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "admin_delete_file")
async def admin_delete_file_start(callback: CallbackQuery):
    """Начало удаления файла"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    config = load_files_config()
    
    if not config:
        await callback.answer("Нет файлов для удаления", show_alert=True)
        return
    
    keyboard = []
    for file_id, data in config.items():
        keyboard.append([InlineKeyboardButton(
            text=f"🗑 {data['name']}", 
            callback_data=f"delete_{file_id}"
        )])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")])
    
    await callback.message.edit_text(
        "🗑 *Выберите файл для удаления:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("delete_"))
async def admin_delete_file_confirm(callback: CallbackQuery):
    """Подтверждение удаления"""
    file_id = callback.data.replace("delete_", "")  # Исправлено
    config = load_files_config()
    
    if file_id in config:
        file_name = config[file_id]['name']
        del config[file_id]
        save_files_config(config)
        
        await callback.message.edit_text(
            f"✅ Файл *{file_name}* успешно удалён!",
            parse_mode="Markdown"
        )
    else:
        await callback.answer("Файл не найден", show_alert=True)
    
    await callback.answer()


@dp.callback_query(F.data == "admin_edit_file")
async def admin_edit_file_start(callback: CallbackQuery):
    """Начало редактирования файла"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    config = load_files_config()
    
    if not config:
        await callback.answer("Нет файлов для редактирования", show_alert=True)
        return
    
    keyboard = []
    for file_id, data in config.items():
        keyboard.append([InlineKeyboardButton(
            text=f"✏️ {data['name']}", 
            callback_data=f"edit_{file_id}"
        )])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")])
    
    await callback.message.edit_text(
        "✏️ *Выберите файл для редактирования:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_"))
async def admin_edit_file_menu(callback: CallbackQuery, state: FSMContext):
    """Меню редактирования файла"""
    file_id = callback.data.replace("edit_", "")  # Исправлено
    config = load_files_config()
    
    logger.info(f"Admin editing file: {file_id}")
    logger.info(f"Available files: {list(config.keys())}")
    
    if file_id not in config:
        await callback.answer(f"Файл не найден: {file_id}", show_alert=True)
        logger.error(f"File {file_id} not found in config")
        return
    
    await state.update_data(editing_file_id=file_id)
    logger.info(f"Saved editing_file_id to state: {file_id}")
    
    keyboard = [
        [InlineKeyboardButton(text="🖼 Изменить обложку", callback_data="action_edit_cover")],
        [InlineKeyboardButton(text="📢 Изменить каналы", callback_data="action_edit_channels")],
        [InlineKeyboardButton(text="🔄 Изменить требование репоста", callback_data="action_edit_repost")],
        [InlineKeyboardButton(text="📝 Изменить описание", callback_data="action_edit_description")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")]
    ]
    
    await callback.message.edit_text(
        f"✏️ *Редактирование: {config[file_id]['name']}*\n\n"
        "Выберите что изменить:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@dp.callback_query(F.data == "action_edit_cover")
async def edit_cover_start(callback: CallbackQuery, state: FSMContext):
    """Начало изменения обложки"""
    # Проверяем что editing_file_id сохранён
    data = await state.get_data()
    file_id = data.get('editing_file_id')
    
    logger.info(f"Edit cover requested, editing_file_id from state: {file_id}")
    
    if not file_id:
        await callback.answer("❌ Ошибка: файл не выбран. Попробуйте снова.", show_alert=True)
        logger.error("No editing_file_id in state!")
        return
    
    await callback.message.edit_text(
        "🖼 Загрузите новую обложку (фото):",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_new_cover)
    await callback.answer()


@dp.message(AdminStates.waiting_new_cover, F.photo)
async def edit_cover_save(message: Message, state: FSMContext):
    """Сохранение новой обложки"""
    logger.info(f"New cover photo received from admin {message.from_user.id}")
    data = await state.get_data()
    file_id = data.get('editing_file_id')
    
    logger.info(f"Editing file_id from state: {file_id}")
    
    if not file_id:
        await message.answer("❌ Ошибка: файл не найден. Начните редактирование заново через /admin")
        logger.error("No editing_file_id in state when saving cover!")
        await state.clear()
        return
    
    config = load_files_config()
    if file_id in config:
        config[file_id]['cover_file_id'] = message.photo[-1].file_id
        save_files_config(config)
        logger.info(f"Cover updated for file {file_id}")
        await message.answer(f"✅ Обложка для *{config[file_id]['name']}* обновлена!", parse_mode="Markdown")
    else:
        logger.error(f"File {file_id} not found when updating cover")
        await message.answer(f"❌ Ошибка: файл {file_id} не найден в конфигурации")
    
    await state.clear()


@dp.callback_query(F.data == "action_edit_channels")
async def edit_channels_start(callback: CallbackQuery, state: FSMContext):
    """Начало изменения каналов"""
    # Проверяем что editing_file_id сохранён
    data = await state.get_data()
    file_id = data.get('editing_file_id')
    
    logger.info(f"Edit channels requested, editing_file_id: {file_id}")
    
    if not file_id:
        await callback.answer("❌ Ошибка: файл не выбран. Попробуйте снова.", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📢 Введите новый список каналов через запятую\n"
        "(например: @channel1, @channel2)\n\n"
        "Или отправьте '-' чтобы удалить все:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_edit_channels)
    await callback.answer()


@dp.message(AdminStates.waiting_edit_channels)
async def edit_channels_save(message: Message, state: FSMContext):
    """Сохранение новых каналов"""
    data = await state.get_data()
    file_id = data.get('editing_file_id')
    
    if message.text.strip() == '-':
        channels = []
    else:
        channels = [ch.strip() for ch in message.text.split(',')]
    
    config = load_files_config()
    if file_id in config:
        config[file_id]['channels'] = channels
        save_files_config(config)
        await message.answer(
            f"✅ Каналы для *{config[file_id]['name']}* обновлены!\n"
            f"Всего каналов: {len(channels)}",
            parse_mode="Markdown"
        )
    
    await state.clear()


@dp.callback_query(F.data == "action_edit_repost")
async def edit_repost_start(callback: CallbackQuery, state: FSMContext):
    """Изменение требования репоста"""
    # Проверяем что editing_file_id сохранён
    data = await state.get_data()
    file_id = data.get('editing_file_id')
    
    logger.info(f"Edit repost requested, editing_file_id: {file_id}")
    
    if not file_id:
        await callback.answer("❌ Ошибка: файл не выбран. Попробуйте снова.", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Требуется", callback_data="action_repost_yes")],
        [InlineKeyboardButton(text="❌ Не требуется", callback_data="action_repost_no")]
    ])
    
    await callback.message.edit_text(
        "🔄 Требуется репост?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(F.data.in_(["action_repost_yes", "action_repost_no"]))
async def edit_repost_save(callback: CallbackQuery, state: FSMContext):
    """Сохранение требования репоста"""
    data = await state.get_data()
    file_id = data.get('editing_file_id')
    repost_required = callback.data == "action_repost_yes"
    
    logger.info(f"Saving repost requirement for file {file_id}: {repost_required}")
    
    if not file_id:
        await callback.answer("❌ Ошибка: файл не найден", show_alert=True)
        return
    
    config = load_files_config()
    if file_id in config:
        config[file_id]['repost_required'] = repost_required
        save_files_config(config)
        await callback.message.edit_text(
            f"✅ Требование репоста для *{config[file_id]['name']}* обновлено!\n"
            f"Репост: {'Да' if repost_required else 'Нет'}",
            parse_mode="Markdown"
        )
        logger.info(f"Repost requirement updated for {file_id}")
    else:
        await callback.answer("❌ Файл не найден", show_alert=True)
        logger.error(f"File {file_id} not found when updating repost")
    
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "action_edit_description")
async def edit_description_start(callback: CallbackQuery, state: FSMContext):
    """Начало изменения описания"""
    # Проверяем что editing_file_id сохранён
    data = await state.get_data()
    file_id = data.get('editing_file_id')
    
    logger.info(f"Edit description requested, editing_file_id: {file_id}")
    
    if not file_id:
        await callback.answer("❌ Ошибка: файл не выбран. Попробуйте снова.", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📝 Введите новое описание файла:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_edit_description)
    await callback.answer()


@dp.message(AdminStates.waiting_edit_description)
async def edit_description_save(message: Message, state: FSMContext):
    """Сохранение нового описания"""
    data = await state.get_data()
    file_id = data.get('editing_file_id')
    
    config = load_files_config()
    if file_id in config:
        config[file_id]['description'] = message.text
        save_files_config(config)
        await message.answer(f"✅ Описание для *{config[file_id]['name']}* обновлено!", parse_mode="Markdown")
    
    await state.clear()


@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: CallbackQuery):
    """Возврат в админ-панель"""
    keyboard = create_admin_keyboard()
    await callback.message.edit_text(
        "👨‍💼 *АДМИН-ПАНЕЛЬ*\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


# ========== ОДОБРЕНИЕ/ОТКЛОНЕНИЕ ==========

@dp.message(Command("approve"))
async def approve_user(message: Message):
    """Команда одобрения пользователя"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У вас нет доступа")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("⚠️ Использование: /approve <user_id>")
        return
    
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id должен быть числом")
        return
    
    if user_id not in pending_users or 'file_id' not in pending_users[user_id]:
        await message.answer(f"❌ Пользователь {user_id} не в списке ожидания")
        return
    
    file_id = pending_users[user_id]['file_id']
    config = load_files_config()
    
    if file_id not in config:
        await message.answer(f"❌ Файл не найден")
        return
    
    try:
        file_data = config[file_id]
        file = FSInputFile(file_data['file_name']) if os.path.exists(file_data['file_name']) else file_data['file_id']
        
        await bot.send_document(
            user_id, 
            file_data['file_id'],
            caption=f"✅ *Ваш запрос одобрен!*\n\n📦 {file_data['name']}",
            parse_mode="Markdown"
        )
        
        await message.answer(f"✅ Файл отправлен пользователю {user_id}")
        pending_users.pop(user_id, None)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {str(e)}")
        logger.error(f"Error sending file to {user_id}: {e}")


@dp.message(Command("reject"))
async def reject_user(message: Message):
    """Команда отклонения пользователя"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У вас нет доступа")
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("⚠️ Использование: /reject <user_id> [причина]")
        return
    
    try:
        user_id = int(parts[1])
        reason = parts[2] if len(parts) > 2 else "Ваш запрос отклонён"
    except ValueError:
        await message.answer("❌ user_id должен быть числом")
        return
    
    if user_id not in pending_users:
        await message.answer(f"❌ Пользователь {user_id} не в списке ожидания")
        return
    
    try:
        await bot.send_message(
            user_id,
            f"❌ *Запрос отклонён*\n\n{reason}",
            parse_mode="Markdown"
        )
        await message.answer(f"✅ Пользователь {user_id} уведомлён об отклонении")
        pending_users.pop(user_id, None)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


@dp.message(Command("pending"))
async def list_pending(message: Message):
    """Список ожидающих пользователей"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У вас нет доступа")
        return
    
    if not pending_users:
        await message.answer("📋 Нет ожидающих пользователей")
        return
    
    config = load_files_config()
    text = "📋 *Ожидающие пользователи:*\n\n"
    for user_id, data in pending_users.items():
        file_id = data.get('file_id', 'unknown')
        file_name = config.get(file_id, {}).get('name', 'Неизвестный файл')
        text += f"• User ID: `{user_id}` | Файл: {file_name}\n"
    
    await message.answer(text, parse_mode="Markdown")


@dp.callback_query(F.data.startswith("approve_"))
async def callback_approve(callback: CallbackQuery):
    """Одобрение через кнопку"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[1])
    
    if user_id not in pending_users or 'file_id' not in pending_users[user_id]:
        await callback.answer("Пользователь не в списке ожидания", show_alert=True)
        return
    
    file_id = pending_users[user_id]['file_id']
    config = load_files_config()
    
    if file_id not in config:
        await callback.answer("Файл не найден", show_alert=True)
        return
    
    try:
        file_data = config[file_id]
        
        await bot.send_document(
            user_id, 
            file_data['file_id'],
            caption=f"✅ *Ваш запрос одобрен!*\n\n📦 {file_data['name']}",
            parse_mode="Markdown"
        )
        
        await callback.answer("✅ Файл отправлен")
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ *ОДОБРЕНО*",
            parse_mode="Markdown"
        )
        
        pending_users.pop(user_id, None)
        
    except Exception as e:
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)


@dp.callback_query(F.data.startswith("reject_"))
async def callback_reject(callback: CallbackQuery):
    """Отклонение через кнопку"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[1])
    
    if user_id not in pending_users:
        await callback.answer("Пользователь не в списке ожидания", show_alert=True)
        return
    
    try:
        await bot.send_message(
            user_id,
            "❌ *Запрос отклонён*\n\nУбедитесь, что вы правильно сделали репост.",
            parse_mode="Markdown"
        )
        
        await callback.answer("✅ Пользователь уведомлён")
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ *ОТКЛОНЕНО*",
            parse_mode="Markdown"
        )
        
        pending_users.pop(user_id, None)
        
    except Exception as e:
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)


async def main():
    """Запуск бота"""
    logger.info("Starting bot...")
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
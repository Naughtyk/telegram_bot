import logging
import os
import sqlite3
from datetime import datetime, timedelta
from datetime import date

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, Chat
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import matplotlib.pyplot as plt
import numpy as np
import matplotlib.dates as mdates

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# constants
db_name = 'telegram_bot_timer.db'
CHOOSING, TIMER_OFF, WAIT_FOR_NOTE, DB_INFO, DB_MODIFY, DB_CHOICE, STAT, STAT_CAT = range(8)
keyboard_private_regular = [
    ["Работа", "Учёба", "Чтение", "Прогулка"],
    ["Отдых", "Развлечения", "Спорт", "Еда"],
    ["Записи в базе", "Статистика"],
    ["Завершить работу"]
]
markup_private_regular = ReplyKeyboardMarkup(keyboard_private_regular, one_time_keyboard=True)

keyboard_group_regular = [
    ["Статистика"],
    ["Завершить работу"]
]
markup_group_regular = ReplyKeyboardMarkup(keyboard_group_regular, one_time_keyboard=True)

keyboard_category_stat = [
    ["Все категории"],
    ["Отдых", "Развлечения", "Работа"],
    ["Учёба", "Чтение", "Спорт"],
    ["Еда", "Прогулка"],
    ["Назад"]
]
markup_category_stat = ReplyKeyboardMarkup(keyboard_category_stat, one_time_keyboard=True)

keyboard_stat = [
    ["За день", "За неделю"],
    ["За месяц", "За год"],
    ["За всё время"],
    ["Назад"]
]
markup_stat = ReplyKeyboardMarkup(keyboard_stat, one_time_keyboard=True)

keyboard_db = [
    ["Просмотреть записи"],
    ["Редактировать записи"],
    ["Назад"]
]
markup_db = ReplyKeyboardMarkup(keyboard_db, one_time_keyboard=True)

keyboard_db_info = [
    ["Последняя запись"],
    ["Последние 5 записей"],
    ["Последние 10 записей"],
    ["Все записи"],
    ["Назад"]
]
markup_db_info = ReplyKeyboardMarkup(keyboard_db_info, one_time_keyboard=True)

stop_keyboard = [
    ["Остановить таймер"]
]
stop_markup = ReplyKeyboardMarkup(stop_keyboard, one_time_keyboard=True)


def format_time(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    time_str = "{:02d}:{:02d}:{:02d}".format(int(hours), int(minutes), int(seconds))
    return time_str


# Функция для преобразования времени в формат datetime
def parse_time(time_str):
    return datetime.strptime(time_str, '%H:%M:%S')


# Функция для преобразования времени в формат datetime и учета даты
def parse_datetime(date_str, time_str):
    date = datetime.strptime(date_str, '%Y-%m-%d')
    time = parse_time(time_str)
    return datetime.combine(date, time.time())


async def timer_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == 'Работа':
        mode = 'work'
        reply_text = 'Запущен таймер работы'
    elif text == 'Учёба':
        mode = 'study'
        reply_text = 'Запущен таймер учёбы'
    elif text == 'Развлечения':
        mode = 'fun'
        reply_text = 'Запущен таймер развлечений'
    elif text == 'Чтение':
        mode = 'read'
        reply_text = 'Запущен таймер чтения'
    elif text == 'Спорт':
        mode = 'sport'
        reply_text = 'Запущен таймер спорта'
    elif text == 'Прогулка':
        mode = 'walk'
        reply_text = 'Запущен таймер прогулки'
    elif text == 'Еда':
        mode = 'food'
        reply_text = 'Запущен таймер еды'
    else:
        mode = 'rest'
        reply_text = 'Запущен таймер отдыха'

    # Учитываем, что у нас сервер в Нидерландах (Разница с МСК - 3 часа)
    current_time = datetime.now().replace(microsecond=0) + timedelta(hours=3)
    user_id = update.message.from_user.id
    conn = sqlite3.connect(db_name)
    cur = conn.cursor()
    try:
        cur.execute(f"INSERT INTO current_timers VALUES (?, ?, ?)",
                    (user_id, current_time, mode))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    cur.close()
    conn.close()

    await update.message.reply_text(reply_text, reply_markup=stop_markup)
    return TIMER_OFF


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        f"Работа завершена!",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    note_text = update.message.text
    user_id = update.message.from_user.id
    reply_text = '\nДанные успешно сохранены в базе.'
    if '/skip' not in note_text:
        # Соединяемся с БД
        conn = sqlite3.connect(db_name)
        cur = conn.cursor()

        # Выбираем последний таймер нашего пользователя
        cur.execute(f"SELECT max(timer_id) from data where user_id = ?", (user_id,))
        timer_id = cur.fetchone()[0]
        # timer_id = context.bot_data.get(user_id)

        if '/delete' in note_text:
            # Удаляем запись
            cur.execute(f"DELETE from data where timer_id = ?",
                        (timer_id,))
            reply_text = '\nЗапись успешно удалена из базы.'
        else:
            # Ставим заметку
            cur.execute(f"UPDATE data set note = ? where timer_id = ?",
                        (note_text, timer_id))

        # Выполняем запрос и закрываем соединение
        conn.commit()
        cur.close()
        conn.close()

    await update.message.reply_text(reply_text, reply_markup=markup_private_regular)
    return CHOOSING


async def db(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Выберите: ",
                                    reply_markup=markup_db)
    return DB_CHOICE


async def db_info_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Выберите: ",
                                    reply_markup=markup_db_info)
    return DB_INFO


async def db_modify_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_text = "Запущен редактор строки в базе данных. " \
                 "Введите id таймера, время старта, время финиша, заметку через пробел. \n\n" \
                 "Пример: 22 19:20:00 19:40:00 заметка \n\n" \
                 "В данном случае выбирается таймер с timer_id и меняются параметры записи: время" \
                 "старта, финиша и заметка. Заметку можно не писать.\n" \
                 "Чтобы вернуться обратно, введите 'Назад'"
    await update.message.reply_text(reply_text)
    return DB_MODIFY


async def db_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    user_id = update.message.from_user.id

    # Соединяемся с БД
    conn = sqlite3.connect(db_name)
    cur = conn.cursor()

    if text == 'Последняя запись':
        cur.execute(f"SELECT timer_id, date, mode, start, finish, time, note "
                    f"from data where user_id = ? "
                    f"order by timer_id desc "
                    f"limit 1", (user_id,))
    elif text == 'Последние 5 записей':
        cur.execute(f"SELECT timer_id, date, mode, start, finish, time, note "
                    f"from data where user_id = ? "
                    f"order by timer_id desc "
                    f"limit 5", (user_id,))
    elif text == 'Последние 10 записей':
        cur.execute(f"SELECT timer_id, date, mode, start, finish, time, note "
                    f"from data where user_id = ? "
                    f"order by timer_id desc "
                    f"limit 10", (user_id,))
    else:
        cur.execute(f"SELECT timer_id, date, mode, start, finish, time, note from data where user_id = ?", (user_id,))
    result = cur.fetchall()
    cur.close()
    conn.close()

    if len(result) == 0:
        await update.message.reply_text('У вас нет записей в базе.',
                                        reply_markup=markup_private_regular)
        return CHOOSING

    reply_text = "id таймера; дата; " \
                 "режим; начало таймера; конец таймера; " \
                 "время работы в секундах; заметка\n"
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text=reply_text)
    reply_text = ''
    for idx, row in enumerate(result):
        if idx % 10 == 0 and idx != 0:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text=reply_text)
            reply_text = ''
        reply_text += str(row)
        reply_text += '\n'

    await update.message.reply_text(reply_text, reply_markup=markup_private_regular)
    return CHOOSING


async def db_modify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    text = update.message.text
    if text == 'Назад' or text == 'Домой':
        await update.message.reply_text("Выберите: ",
                                        reply_markup=markup_private_regular)
        return CHOOSING

    text = text.split()
    timer_id, start_time, finish_time = text[0:3]
    if len(text) == 3:
        note = ''
    elif len(text) > 3:
        note = ' '.join(text[3:])
    else:
        await update.message.reply_text("Ошибка с форматом текста")
        return DB_MODIFY

    try:
        start_time = datetime.strptime(start_time, "%H:%M:%S")
        finish_time = datetime.strptime(finish_time, "%H:%M:%S")

        elapsed_time = finish_time - start_time
        elapsed_time_in_sec = int(elapsed_time.total_seconds())

        # Создание объекта datetime с помощью текущей даты и времени из time_struct
        start_time = datetime.strftime(start_time, "%H:%M:%S")
        finish_time = datetime.strftime(finish_time, "%H:%M:%S")
    except Exception as err:
        print(err)
        await update.message.reply_text("Ошибка с форматом времени")
        return DB_MODIFY

    # Соединяемся с БД
    conn = sqlite3.connect(db_name)
    cur = conn.cursor()

    cur.execute(f"SELECT user_id from data where timer_id = ? and user_id = ?", (timer_id, user_id))
    result = cur.fetchone()
    if not result:
        await update.message.reply_text('Вашего таймера с таким id не найдено')
        cur.close()
        conn.close()
        return DB_MODIFY

    cur.execute(f"UPDATE data set start = ?, finish = ?, time = ?,"
                f" note = ? where timer_id = ?", (start_time, finish_time,
                                                  elapsed_time_in_sec, note, timer_id,))
    conn.commit()
    cur.close()
    conn.close()

    await update.message.reply_text("Запись отредактирована",
                                    reply_markup=markup_private_regular)
    return CHOOSING


async def timer_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Узнаём user_id
    user_id = update.message.from_user.id

    try:
        # Соединяемся с БД
        conn = sqlite3.connect(db_name)
        cur = conn.cursor()

        # Узнаём время старта таймера и его мод
        cur.execute(f"SELECT start, mode from current_timers where user_id = ?", (user_id,))

        # Вычисляем время с начала таймера
        start_time, mode = cur.fetchone()
        start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        finish_time = datetime.now().replace(microsecond=0) + timedelta(hours=3)
        elapsed_time = finish_time - start_time
        elapsed_time_in_sec = int(elapsed_time.total_seconds())
        if elapsed_time_in_sec < 0:
            elapsed_time_in_sec += 86400

        # Удаляем таймер из current_timers
        cur.execute(f"DELETE from current_timers where user_id = ?", (user_id,))
        conn.commit()
    except Exception:
        await update.message.reply_text('Произошла непредвиденная ошибка. '
                                        'Попробуйте ещё раз', reply_markup=markup_private_regular)
        return CHOOSING

    """
    if elapsed_time_in_sec < 10:
        reply_text = 'Прошло меньше 10 секунд. Данные в базе не будут сохранены.'
        await update.message.reply_text(reply_text, reply_markup=markup_private_regular)
        return CHOOSING"""
    if elapsed_time_in_sec > 86400:
        reply_text = 'Прошло больше суток. Данные в базе не будут сохранены.'
        await update.message.reply_text(reply_text, reply_markup=markup_private_regular)
        return CHOOSING

    # Выбираем последний таймер и инкрементируем
    cur.execute(f"SELECT max(timer_id) from data")
    timer_id = cur.fetchone()[0] + 1

    cur.execute(f"INSERT INTO data VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (timer_id, user_id, date.today(), mode,
                 start_time.strftime("%H:%M:%S"),
                 finish_time.strftime("%H:%M:%S"), elapsed_time_in_sec, ''))
    conn.commit()
    cur.close()
    conn.close()

    reply_text = f"Таймер остановлен. Прошло {elapsed_time}. "

    reply_text += "Напишите заметку, либо введите /skip. " \
                  "Если хотите удалить запись, введите /delete"
    await update.message.reply_text(reply_text)
    return WAIT_FOR_NOTE


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation, display any stored data and ask user for input."""
    chat_type = update.effective_chat.type
    if chat_type == Chat.PRIVATE:
        await update.message.reply_text("Бот-задрот стартует. Выберите таймер.",
                                        reply_markup=markup_private_regular)
    else:
        # Действия бота в группе
        await update.message.reply_text("Бот-задрот стартует."
                                        " В чате я умею только выводить статистику пользователей.",
                                        reply_markup=markup_group_regular)
    return CHOOSING


async def home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_type = update.effective_chat.type
    if chat_type == Chat.PRIVATE:
        await update.message.reply_text("Выберите: ",
                                        reply_markup=markup_private_regular)
    else:
        # Действия бота в группе
        await update.message.reply_text("Выберите: ",
                                        reply_markup=markup_group_regular)
    return CHOOSING


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    chat_type = update.effective_chat.type
    if chat_type == Chat.PRIVATE:
        # Действия бота в чате с отдельным пользователем
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Это бот-задрот. Я умею "
                                            "запускать таймеры и выводить статистику. \n"
                                            "Чтобы начать нажмите /start")
    elif chat_type == Chat.GROUP or chat_type == Chat.SUPERGROUP:
        # Действия бота в группе
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Это бот-задрот. В чате я умею только "
                                            "выводить статистику пользователей. \n"
                                            "Чтобы начать нажмите /start")
    else:
        # Действия бота в других типах чатов (например, каналы)
        pass


async def stat_cat_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Выберите категорию: ",
                                    reply_markup=markup_category_stat)
    return STAT_CAT


async def stat_time_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    category = update.message.text
    context.user_data['category'] = category

    await update.message.reply_text("Выберите временной период: ",
                                    reply_markup=markup_stat)
    return STAT


async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.message.from_user.id
        category = context.user_data['category']
        time_interval = update.message.text  # за день / за неделю ...

        translator = {'rest': 'Отдых',
                      'fun': 'Развлечения',
                      'work': 'Работа',
                      'study': 'Учёба',
                      'read': 'Чтение',
                      'sport': 'Спорт',
                      'food': 'Еда',
                      'walk': 'Прогулка',
                      'unrecorded': 'Неучтённое время'}

        # Соединяемся с БД
        conn = sqlite3.connect(db_name)
        cur = conn.cursor()

        cnt = int(cur.execute(f"SELECT count(timer_id)"
                              f" from data"
                              f" where user_id = ?", (user_id,)).fetchall()[0][0])
        if cnt == 0:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="У вас нет записей в базе данных")
            return

        # Вычисляем текущую дату и время
        current_time = datetime.now()

        # Вычисляем дату и время с которого собираем статистику
        if 'день' in time_interval:
            time_threshold = current_time - timedelta(days=1)
        elif 'неделю' in time_interval:
            time_threshold = current_time - timedelta(days=7)
        elif 'месяц' in time_interval:
            time_threshold = current_time - timedelta(days=30)
        elif 'год' in time_interval:
            time_threshold = current_time - timedelta(days=365)
        else:
            time_threshold = cur.execute(f"SELECT min(date)"
                                   f" from data"
                                   f" where user_id = ?", (user_id,)).fetchall()[0][0]
            time_threshold = datetime.strptime(time_threshold, "%Y-%m-%d")

        # выбираем минимальный день из БД
        min_date = cur.execute(f"SELECT min(date)"
                               f" from data"
                               f" where user_id = ?", (user_id,)).fetchall()[0][0]
        # переводим его в datetime формат
        min_date = datetime.strptime(min_date, "%Y-%m-%d")

        # Если наш порог окажется дальше, чем минимальная дата, то в качестве порога
        # выбираем минимальную дату
        time_threshold = max(min_date, time_threshold)

        # Форматируем дату и время в строку в нужном формате
        formatted_time_threshold = time_threshold.strftime('%Y-%m-%d %H:%M:%S')

        summary_seconds = (current_time - time_threshold).total_seconds()

        if category == 'Все категории':
            cur.execute(f"SELECT mode, sum(time)"
                        f" from data"
                        f" where user_id = ? AND"
                        f" datetime(date || ' ' || start) >= ? AND "
                        f" datetime(date || ' ' || finish) >= ?"
                        f" group by mode", (user_id, formatted_time_threshold,
                                            formatted_time_threshold))
            result = cur.fetchall()

            unrecorded = summary_seconds - sum([x[1] for x in result])
            result.append(('unrecorded', unrecorded))

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(25, 5))  # Создание двух областей графиков

            # Создание круговой диаграммы
            ax1.pie([x[1] for x in result],
                    labels=[translator[x[0]] for x in result],
                    autopct='%1.1f%%')
            ax1.set_title(f'Статистика')

            # Создание гистограммы
            x = np.arange(len(result))
            bars = ax2.bar(x, [(x[1] / 60) / 60 for x in result])
            ax2.set_xticks(x, [translator[x[0]] for x in result])  # Настройка меток оси x
            ax2.set_ylabel('Время')  # Подпись оси y

            # Добавление надписей над гистами
            for bar, annotation in zip(bars, [format_time(x[1]) for x in result]):
                height = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width() / 2, height, annotation,
                         ha='center', va='bottom')

        else:
            mode = ''
            for k, v in translator.items():
                if v == category:
                    mode = k
                    break
            if mode == '':
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text=f"Произошла ошибка c mode")
                await update.message.reply_text("Выберите категорию: ",
                                                reply_markup=markup_category_stat)
                return STAT_CAT

            # Выполняем SQL-запрос для выборки всех id,
            # у которых дата и время больше time_threshold
            cur.execute(f"SELECT date, start, finish "
                        f"FROM data "
                        f"WHERE mode = ? AND user_id = ? AND "
                        f"datetime(date || ' ' || start) >= ? AND "
                        f"datetime(date || ' ' || finish) >= ?",
                        (mode, user_id, formatted_time_threshold,
                         formatted_time_threshold))

            result = cur.fetchall()
            if not result:
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text=f"За выбранный период не найдено данных")
                await update.message.reply_text("Выберите категорию:",
                                                reply_markup=markup_category_stat)
                return STAT_CAT

            # Создаем фигуру и ось графика
            fig, ax = plt.subplots()

            # Вычисляем разницу между текущим временем и временем порога
            time_difference = current_time - time_threshold

            # Определяем шаг timedelta
            if time_difference <= timedelta(days=1):
                # Установка формата даты на оси X
                # ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))

                num_intervals = 25
                step = timedelta(hours=1)
                # Определяем интервалы для оси X
                time_intervals = [current_time - (i - 1) * step for i in range(num_intervals + 2)]
                # Округляем временные метки до часов
                for i in range(len(time_intervals)):
                    time_intervals[i] = time_intervals[i].replace(minute=0,
                                                                  second=0,
                                                                  microsecond=0)
            elif timedelta(days=30) < time_difference < timedelta(days=90):
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
                num_intervals = time_difference.days // 7
                step = timedelta(days=7)
                # Определяем интервалы для оси X
                time_intervals = [current_time - (i - 1) * step for i in range(num_intervals + 2)]
                for i in range(len(time_intervals)):
                    time_intervals[i] = time_intervals[i].replace(hour=0,
                                                                  minute=0,
                                                                  second=0,
                                                                  microsecond=0)
            elif timedelta(days=90) <= time_difference:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%M'))
                num_intervals = time_difference.days // 30
                step = timedelta(days=30)
                # Определяем интервалы для оси X
                time_intervals = [current_time - (i - 1) * step for i in range(num_intervals + 2)]
                for i in range(len(time_intervals)):
                    time_intervals[i] = time_intervals[i].replace(hour=0,
                                                                  minute=0,
                                                                  second=0,
                                                                  microsecond=0)
            else:
                # Установка формата даты на оси X
                # ax.xaxis.set_major_locator(mdates.HourLocator(interval=24))
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
                num_intervals = time_difference.days
                step = timedelta(days=1)
                # Определяем интервалы для оси X
                time_intervals = [current_time - (i - 1) * step for i in range(num_intervals + 2)]
                for i in range(len(time_intervals)):
                    time_intervals[i] = time_intervals[i].replace(hour=0,
                                                                  minute=0,
                                                                  second=0,
                                                                  microsecond=0)

            # Рисуем вертикальные линии, представляющие интервалы по оси X
            for time in time_intervals:
                plt.axvline(x=time, color='gray', linestyle='--', linewidth=0.5)

            # Построение гистограмм
            s = 0
            for date, start, finish in result:
                start_datetime = parse_datetime(date, start)
                finish_datetime = parse_datetime(date, finish)

                if start > finish:
                    start_datetime -= timedelta(hours=24)

                # Вычисляем длительность каждого интервала
                duration = finish_datetime - start_datetime
                s += duration.total_seconds()

                # Рисуем гистограмму для каждого id
                # ax.bar(duration.total_seconds() / 3600, duration, left=start_datetime)
                ax.bar(start_datetime,
                       duration.total_seconds() / 3600,
                       duration,
                       align='edge',
                       color='b')
                # ax.plot([start_datetime, finish_datetime], [1, 1], color='b', linewidth=10)

            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text=f"Суммарно {time_interval.lower()}, "
                                                f"на категорию \"{category}\" вы "
                                                f"потратили: {format_time(s)}")

            # Добавляем подписи осей и заголовок
            plt.xlabel('Время')
            plt.ylabel('Часы')
            plt.title('Статистика')

        cur.close()
        conn.close()

        # Генерация изображения диаграммы в формате PNG
        plt.savefig('pie_chart.png', format='png')
        plt.close()

        # Отправка изображения пользователю
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=open('pie_chart.png', 'rb'))

        # Удаление файла после отправки
        os.remove('pie_chart.png')

        await update.message.reply_text("Выберите категорию:",
                                        reply_markup=markup_category_stat)
        return STAT_CAT
    except Exception as err:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text=f"Произошла ошибка: {err}")
        await update.message.reply_text("Выберите категорию: ",
                                        reply_markup=markup_category_stat)
    return STAT_CAT


def main() -> None:
    token = '???????????'
    # token = '??????????'  # test bot

    application = Application.builder().token(token).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={CHOOSING: [MessageHandler(
            filters.Regex("^(Работа|Учёба|Развлечения|Еда|"
                          "Отдых|Чтение|Спорт|Прогулка)$"), timer_choice
        ),
            MessageHandler(
                filters.Regex("^Записи в базе$"), db
            ),
            MessageHandler(
                filters.Regex("^Статистика$"), stat_cat_choice
            )
        ],
            STAT: [MessageHandler(filters.Regex("^(За день|"
                                                "За неделю|"
                                                "За месяц|"
                                                "За год|"
                                                "За всё время)$"), stat),
                   MessageHandler(filters.Regex("^Назад$"), home)],
            STAT_CAT: [MessageHandler(filters.Regex("^(Все категории|"
                                                    "Работа|Учёба|Развлечения|Еда|"
                                                    "Отдых|Чтение|Спорт|Прогулка)$"), stat_time_choice),
                       MessageHandler(filters.Regex("^Назад$"), home)],
            DB_CHOICE: [MessageHandler(filters.Regex("^Просмотреть записи$"), db_info_choice),
                        MessageHandler(filters.Regex("^Редактировать записи$"), db_modify_choice),
                        MessageHandler(filters.Regex("^Назад$"), home)],
            DB_INFO: [MessageHandler(filters.Regex(r"(?i)запис"), db_info),
                      MessageHandler(filters.Regex("^Назад$"), home)],
            DB_MODIFY: [MessageHandler(filters.TEXT, db_modify)],
            TIMER_OFF: [MessageHandler(filters.Regex("^Остановить таймер$"), timer_off)],
            WAIT_FOR_NOTE: [MessageHandler(filters.TEXT, note)]},
        fallbacks=[MessageHandler(filters.Regex("^Завершить работу$"), done)],
    )

    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.Regex(r"(?i)stat"), stat))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

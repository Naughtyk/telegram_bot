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

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# constants
db_name = 'data.sqlite'
CHOOSING, TIMER_OFF, WAIT_FOR_NOTE, VIEW_DB = 0, 1, 2, 3
reply_keyboard1 = [
    ["Запустить таймер работы", "Запустить таймер развлечений"],
    ["Запустить таймер учёбы", "Запустить таймер отдыха"],
    ["Просмотреть записи в базе"],
    ["Завершить работу"]
]
markup1 = ReplyKeyboardMarkup(reply_keyboard1, one_time_keyboard=True)
reply_keyboard2 = [
    ["Остановить таймер"]
]
markup2 = ReplyKeyboardMarkup(reply_keyboard2, one_time_keyboard=True)


def format_time(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    time_str = "{:02d}:{:02d}:{:02d}".format(int(hours), int(minutes), int(seconds))
    return time_str


async def regular_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == 'Запустить таймер работы':
        mode = 'work'
        reply_text = 'Запущен таймер работы'
    elif text == 'Запустить таймер учёбы':
        mode = 'study'
        reply_text = 'Запущен таймер учёбы'
    elif text == 'Запустить таймер развлечений':
        mode = 'fun'
        reply_text = 'Запущен таймер развлечений'
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

    await update.message.reply_text(reply_text, reply_markup=markup2)
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
        cur.execute(f"SELECT max(timer_id) from data where user_id = ?", (user_id, ))
        timer_id = cur.fetchone()[0]
        #timer_id = context.bot_data.get(user_id)

        if '/delete' in note_text:
            # Удаляем запись
            cur.execute(f"DELETE from data where timer_id = ?",
                        (timer_id, ))
            reply_text = '\nЗапись успешно удалена из базы.'
        else:
            # Ставим заметку
            cur.execute(f"UPDATE data set note = ? where timer_id = ?",
                        (note_text, timer_id))

        # Выполняем запрос и закрываем соединение
        conn.commit()
        cur.close()
        conn.close()

    await update.message.reply_text(reply_text, reply_markup=markup1)
    return CHOOSING


async def view_db(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id

    # Соединяемся с БД
    conn = sqlite3.connect(db_name)
    cur = conn.cursor()

    cur.execute(f"SELECT date, mode, start, finish, time, note from data where user_id = ?", (user_id, ))
    result = cur.fetchall()
    cur.close()
    conn.close()

    reply_text = "дата;" \
                 " режим; начало таймера; конец таймера;" \
                 " время работы в секундах; заметка\n"
    for row in result:
        reply_text += str(row)
        reply_text += '\n'
    await update.message.reply_text(reply_text, reply_markup=markup1)
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

        # Удаляем таймер из current_timers
        cur.execute(f"DELETE from current_timers where user_id = ?", (user_id,))
        conn.commit()
    except Exception:
        await update.message.reply_text('Произошла непредвиденная ошибка. '
                                        'Попробуйте ещё раз', reply_markup=markup1)
        return CHOOSING

    if elapsed_time_in_sec < 10:
        reply_text = 'Прошло меньше 10 секунд. Данные в базе не будут сохранены.'
        await update.message.reply_text(reply_text, reply_markup=markup1)
        return CHOOSING
    if elapsed_time_in_sec > 86400:
        reply_text = 'Прошло больше суток. Данные в базе не будут сохранены.'
        await update.message.reply_text(reply_text, reply_markup=markup1)
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
    reply_text = "Бот-задрот стартует"
    if chat_type == Chat.PRIVATE:
        await update.message.reply_text(reply_text, reply_markup=markup1)
        return CHOOSING
    else:
        # Действия бота в группе
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="В чате я умею только выводить статистику пользователей. "
                 "Введите /help, чтобы узнать команды")
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
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Чтобы вывести статистику за день, напишите 'day stat'\n"
                                            "Чтобы вывести статистику за неделю, напишите 'week stat'\n"
                                       "Чтобы вывести статистику за месяц, напишите 'month stat'\n"
                                       "Чтобы вывести статистику за год, напишите 'year stat'\n"
                                       "Чтобы вывести статистику за всё время, напишите 'stat'\n")
    elif chat_type == Chat.GROUP or chat_type == Chat.SUPERGROUP:
        # Действия бота в группе
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="Это бот-задрот. В чате я умею только "
                                      "выводить статистику пользователей. \n")
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Чтобы вывести статистику за день, напишите 'day stat'\n"
                                            "Чтобы вывести статистику за неделю, напишите 'week stat'\n"
                                       "Чтобы вывести статистику за месяц, напишите 'month stat'\n"
                                       "Чтобы вывести статистику за год, напишите 'year stat'\n"
                                       "Чтобы вывести статистику за всё время, напишите 'stat'\n")
    else:
        # Действия бота в других типах чатов (например, каналы)
        pass


async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:

        user_id = update.message.from_user.id
        text = update.message.text

        translator = {'rest': 'Отдых/сон',
                      'fun': 'Развлечения',
                      'work': 'Работа',
                      'study': 'Учёба',
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

        if 'day' in text:
            summary_seconds = 86400
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="Вот статистика за прошедшие сутки")
            cur.execute(f"SELECT mode, sum(time)"
                        f" from data"
                        f" where user_id = ?"
                        f" and \"date\" >= date('now', '-1 days') AND \"date\" < date('now')"
                        f" group by mode", (user_id, ))
        elif 'week' in text:
            summary_seconds = 604800
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="Вот статистика за прошедшую неделю")
            cur.execute(f"SELECT mode, sum(time)"
                        f" from data"
                        f" where user_id = ?"
                        f" and \"date\" >= date('now', '-7 days') AND \"date\" < date('now')"
                        f" group by mode", (user_id, ))
        elif 'month' in text:
            summary_seconds = 2592000
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="Вот статистика за прошедший месяц")
            cur.execute(f"SELECT mode, sum(time)"
                        f" from data"
                        f" where user_id = ?"
                        f" and \"date\" >= date('now', '-30 days') AND \"date\" < date('now')"
                        f" group by mode", (user_id, ))
        elif 'year' in text:
            summary_seconds = 31104000
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="Вот статистика за прошедший год")
            cur.execute(f"SELECT mode, sum(time)"
                        f" from data"
                        f" where user_id = ?"
                        f" and \"date\" >= date('now', '-1 year') AND \"date\" < date('now')"
                        f" group by mode", (user_id, ))
        else:
            current_time = datetime.now()
            t = cur.execute(f"SELECT min(date)"
                        f" from data"
                        f" where user_id = ?", (user_id, )).fetchall()[0][0]
            target_date = datetime.strptime(t, "%Y-%m-%d")

            summary_seconds = (current_time - target_date).total_seconds()
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="Вот статистика за всё время")
            cur.execute(f"SELECT mode, sum(time)"
                        f" from data"
                        f" where user_id = ?"
                        f" group by mode", (user_id, ))

        result = cur.fetchall()

        cur.close()
        conn.close()

        unrecorded = summary_seconds - sum([x[1] for x in result])
        result.append(('unrecorded', unrecorded))

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5))  # Создание двух областей графиков

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

        # Генерация изображения диаграммы в формате PNG
        plt.savefig('pie_chart.png', format='png')
        plt.close()

        # Отправка изображения пользователю
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=open('pie_chart.png', 'rb'))

        # Удаление файла после отправки
        os.remove('pie_chart.png')
    except Exception as err:
        print(err)
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Произошла какая-то ошибка")


def main() -> None:

    token = ''

    application = Application.builder().token(token).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={CHOOSING: [MessageHandler(
            filters.Regex("^(Запустить таймер работы|"
                          "Запустить таймер отдыха|"
                          "Запустить таймер учёбы|"
                          "Запустить таймер развлечений)$"), regular_choice
        ),
            MessageHandler(
                filters.Regex("^Просмотреть записи в базе$"), view_db
            )
        ],
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

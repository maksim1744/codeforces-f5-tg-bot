import os
if os.environ.get("TOKEN") is None:
    TOKEN = open("token.txt", "r").readline().strip()
else:
    TOKEN = os.environ["TOKEN"]

from contest import Contest
import submission as sub

from requests import session
import json
import logging
import re
import sys
from time import time

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, PicklePersistence
import telegram

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

def print_submissions(new_submissions, prev_submissions=[], short_print=False):
    msg = ""
    msg += '```\n'
    msg += sub.get_titles(short=short_print)
    for submission in new_submissions:
        msg += sub.to_string(submission, short=short_print)
        if submission not in prev_submissions:
            msg += ' *'
        msg += '\n'
    msg += '```\n'
    return msg

def start(update, context):
    update.message.reply_text('Hi! Use /help to see help')


def help(update, context):
    update.message.reply_text(
        '/add_user [user1] [user2] [...] --- set users to follow\n'
        '/del_user [user1] [user2] [...] --- del users to follow\n'
        '/user --- view current users\n'
        '/contest --- view current contests\n'
        '/start_f5 --- start clicking f5\n'
        '/status --- view current status\n'
        '/stop_f5 --- stop clicking f5\n'
        '/short or /long --- set width of results: long is pretty, but looks bad on mobile devices\n'
        '/show_practice or /hide_practice --- show/hide practice submissions from results\n'
        )


def ask_user(update, context):
    msg = ', '.join(str(user) for user in context.chat_data.get('user', []))
    update.message.reply_text('Current users: ' + msg)

def add_user(update, context):
    context.chat_data.setdefault('user', set())
    for user in context.args:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', user):
            update.message.reply_text('Don\'t user strange symbols')
            return
        user = user.lower()
        context.chat_data['user'].add(user)
    ask_user(update, context)

def del_user(update, context):
    if context.chat_data.get('user') is None:
        update.message.reply_text('Add users first')
        return
    for user in context.args:
        if user in context.chat_data['user']:
            context.chat_data['user'].remove(user)
        for contest in context.chat_data.get("data", dict()):
            if user in context.chat_data['data'][contest]:
                context.chat_data['data'][contest].pop(user)
    ask_user(update, context)


def ask_contest(update, context):
    msg = ', '.join(str(contest) for contest in context.bot_data.get('contest', dict()).keys())
    update.message.reply_text('Current contests: ' + msg)

def add_contest(update, context):
    if update.message.from_user.username != 'maksim1744':
        update.message.reply_text('This option is not available for you')
        return

    context.bot_data.setdefault('contest', dict())

    for contest in context.args:
        if not re.fullmatch(r'[0-9]+', contest):
            update.message.reply_text('Contest must be an integer')
            break
        if contest in context.bot_data['contest']:
            continue
        context.bot_data['contest'][contest] = Contest(contest)
    ask_contest(update, context)

def del_contest(update, context):
    if update.message.from_user.username != 'maksim1744':
        update.message.reply_text('This option is not available for you')
        return

    if context.bot_data.get('contest') is None:
        update.message.reply_text('Add contests first')
        return
    for contest in context.args:
        if contest in context.bot_data['contest']:
            if context.bot_data['contest'][contest].isAlive():
                context.bot_data['contest'][contest].stop()
            context.bot_data['contest'].pop(contest)
    ask_contest(update, context)


def error(update, context):
    logger.warning('Update "%s" caused error "%s"', update, context.error)
    users = []
    if context.chat_data is not None:
        users = [user for user in context.chat_data.get('user', set())]
    contests = []
    if context.bot_data is not None:
        contests = [contest for contest in context.bot_data.get('contest', set())]
    logger.warning('contests: ({}), users: ({})'.format(
        ', '.join(contests),
        ', '.join(users)))


def stop_f5_job(chat_id, context):
    if context.chat_data.get("f5_job") is None:
        context.bot.send_message(chat_id, text='Nothing to stop')
        return;
    context.chat_data.get("f5_job").schedule_removal()
    context.chat_data.pop("f5_job")
    context.bot.send_message(chat_id, text='Stopped job')

def check_updates(context):
    job = context.job
    context = job.context[1]
    chat_id = job.context[0]

    if context.chat_data["f5_job_start_time"] + 86400 < time() or context.bot_data.get("contest", dict()) == dict() or \
        context.chat_data.get("user", set()) == set():
        stop_f5_job(chat_id, context)

    context.chat_data.setdefault("data", dict())

    msg = ""

    short_print = context.chat_data.get("short_print", False)

    for contest in context.bot_data['contest'].values():
        context.chat_data["data"].setdefault(contest.ID, dict())
        for user in context.chat_data["user"]:
            prev_submissions = context.chat_data["data"][contest.ID].get(user, list())[:]
            new_submissions = contest.get_submissions(user)
            if prev_submissions == new_submissions:
                continue
            msg += "user {}, contest {}\n".format(user, contest.ID)
            msg += print_submissions(new_submissions, prev_submissions, short_print)
            msg += "\n"
            context.chat_data["data"][contest.ID][user] = new_submissions
    if msg != "":
        context.bot.send_message(chat_id, text=msg, parse_mode=telegram.ParseMode.MARKDOWN_V2)


def get_status(update, context):
    if context.chat_data.get("f5_job") is None:
        update.message.reply_text('Start job with /start_f5')
        return

    msg = ""

    short_print = context.chat_data.get("short_print", False)

    for contest in context.bot_data['contest'].values():
        context.chat_data["data"].setdefault(contest.ID, dict())
        for user in context.chat_data["user"]:
            submissions = context.chat_data["data"][contest.ID].get(user, list())[:]
            msg += "user {}, contest {}\n".format(user, contest.ID)
            msg += print_submissions(submissions, submissions, short_print)
            msg += "\n"

    if msg == "":
        msg = "No submissions found"
    context.bot.send_message(update.message.chat_id, text=msg, parse_mode=telegram.ParseMode.MARKDOWN_V2)


def start_f5(update, context):
    if context.chat_data.get("f5_job") is not None:
        update.message.reply_text('Stop previous job with /stop_f5')
        return

    if context.chat_data.get('user', set()) == set():
        update.message.reply_text('Need user, for example "/add_user User"')
        return
    if context.bot_data.get('contest', set()) == set():
        update.message.reply_text('No contests now, come back later')
        return

    context.chat_data['data'] = dict()
    context.chat_data['f5_job_start_time'] = time()
    context.chat_data["f5_job"] = context.job_queue.run_repeating(check_updates, interval=0.5, first=0,
        context=[update.message.chat_id, context])
    update.message.reply_text('Started job with users ({}), contests ({})'.format(
        ', '.join(context.chat_data.get('user')),
        ', '.join(context.bot_data.get('contest'))))

def stop_f5(update, context):
    stop_f5_job(update.message.chat_id, context)


def set_short(update, context):
    context.chat_data["short_print"] = True
def set_long(update, context):
    context.chat_data["short_print"] = False

def show_practice(update, context):
    context.chat_data["only_contestant"] = False
def hide_practice(update, context):
    context.chat_data["only_contestant"] = True


def main():
    # my_persistence = PicklePersistence(filename='persistent_data.txt') , persistence=my_persistence
    updater = Updater(TOKEN, use_context=True)

    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))

    dp.add_handler(CommandHandler("user", ask_user, pass_chat_data=True, pass_args=True))
    dp.add_handler(CommandHandler("add_user", add_user, pass_chat_data=True, pass_args=True))
    dp.add_handler(CommandHandler("del_user", del_user, pass_chat_data=True, pass_args=True))

    dp.add_handler(CommandHandler("contest", ask_contest, pass_chat_data=True, pass_args=True))
    dp.add_handler(CommandHandler("add_contest", add_contest, pass_chat_data=True, pass_args=True))
    dp.add_handler(CommandHandler("del_contest", del_contest, pass_chat_data=True, pass_args=True))

    dp.add_handler(CommandHandler("status", get_status, pass_chat_data=True))
    dp.add_handler(CommandHandler("start_f5", start_f5, pass_chat_data=True, pass_job_queue=True, pass_args=True))
    dp.add_handler(CommandHandler("stop_f5", stop_f5, pass_chat_data=True, pass_job_queue=True))

    dp.add_handler(CommandHandler("short", set_short, pass_chat_data=True))
    dp.add_handler(CommandHandler("long", set_long, pass_chat_data=True))

    dp.add_handler(CommandHandler("show_practice", show_practice, pass_chat_data=True))
    dp.add_handler(CommandHandler("hide_practice", hide_practice, pass_chat_data=True))

    dp.add_error_handler(error)

    updater.start_polling()

    updater.idle()


if __name__ == '__main__':
    main()

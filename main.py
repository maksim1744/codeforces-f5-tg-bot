#!/usr/bin/env python
# -*- coding: utf-8 -*-
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Dispatcher and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""

import os
TOKEN = os.environ["TOKEN"]

from requests import session
import json
import logging
import re
from time import time

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import telegram

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

def get_submissions(contestId, user, only_contestant=False):
    data = session().get(
        "https://codeforces.com/api/contest.status?handle={}&contestId={}&from=1&count=1000".format(user, contestId))
    if not data.ok:
        return None
    data = json.loads(data.text)
    if data["status"] != "OK" or data.get("result") is None:
        return None
    result = []
    for item in data["result"]:
        if item.get("contestId") is None or item.get("author") is None or item.get("problem") is None:
            continue
        if only_contestant and item.get("author").get("participantType", "?") != "CONTESTANT":
            continue

        verdict = item.get("verdict", "?")
        testset = item.get("testset")
        if testset == "PRETESTS" and verdict != "OK":
            continue

        if verdict != '?':
            if verdict.count('_') >= 1:
                verdict = ''.join([s[0] for s in verdict.split('_')])
            else:
                verdict = verdict[:8]

        passedTestCount = int(item.get("passedTestCount", 0))
        problemIndex = item.get("problem").get("index", "?")

        result.append([problemIndex, testset, verdict, passedTestCount])
    return result[::-1]

def print_submissions(submissions, prev=[], short=False):
    if submissions is None:
        return ""
    headings = ["problem", "testset", "verdict", "passed tests"]
    fmt = "|{: ^9}|{: ^12}|{: ^10}|{: ^14}|"
    if short:
        headings = ["№", "testset", "res", "tests"]
        fmt = "|{: ^3}|{: ^10}|{: ^3}|{: ^5}|"
    result  = (fmt + "\n").format(*headings)
    result += (fmt.replace(' ', '-') + "\n").format("", "", "", "")
    # result += "|" + "-" * 3 + "|" + "-" * 12 + "|" + "-" * 10 + "|" + "-" * 7 + "|\n"
    for i, submission in enumerate(submissions):
        if short:
            if submission[2] == "TESTING":
                submission[2] = "..."
            else:
                submission[2] = submission[2][:3]
        result += fmt.format(*submission)
        if i >= len(prev) or (i < len(prev) and submissions[i] != prev[i]):
            result += ' *\n'
        else:
            result += '\n'
    return '```\n' + result.replace('|', '\\|').replace('-', '\\-').replace('*', '\\*').replace('_', '\\_') + '```'

# Define a few command handlers. These usually take the two arguments update and
# context. Error handlers also receive the raised TelegramError object in error.
def start(update, context):
    """Send a message when the command /start is issued."""
    update.message.reply_text('Hi! Use /help to see help')


def help(update, context):
    """Send a message when the command /help is issued."""
    update.message.reply_text(
        '/user User --- set user to follow\n'
        '/contest Context --- set context to follow\n'
        '/start_f5 [contest] [user] --- start clicking f5, contest and user are optional\n'
        '/status --- view current status\n'
        '/stop_f5 --- stop clicking f5\n'
        '/short or /long --- set width of results: long is pretty, but looks bad on mobile devices\n'
        '/show_practice or /hide_practice --- show/hide practice submissions from results\n'
        )

def ask_user(update, context):
    if len(context.args) < 1:
        if context.chat_data.get('user') is None:
            update.message.reply_text('Need user, for example "/user User"')
        else:
            update.message.reply_text('Current user: {}'.format(context.chat_data['user']))
    else:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', context.args[0]):
            update.message.reply_text('Нашелся хакер... Я регулярку поставил')
            return
        context.chat_data['user'] = context.args[0]
        update.message.reply_text('Current user: {}'.format(context.chat_data['user']))

def ask_contest(update, context):
    if len(context.args) < 1:
        if context.chat_data.get('contest') is None:
            update.message.reply_text('Need contest, for example "/contest Contest"')
        else:
            update.message.reply_text('Current contest: {}'.format(context.chat_data['contest']))
    else:
        if not re.fullmatch(r'[0-9]+', context.args[0]):
            update.message.reply_text('Contest must be an integer')
            return
        context.chat_data['contest'] = context.args[0]
        update.message.reply_text('Current contest: {}'.format(context.chat_data['contest']))

def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)



def check_updates(context):
    if context.job.context[1].chat_data["f5_job_start_time"] + 86400 < time():
        context.job.context[1].chat_data.get("f5_job").schedule_removal()
        context.job.context[1].chat_data.pop("f5_job")
        context.bot.send_message(context.job.context[0], text='Stopped job with user {}, contest {}'.format(
            context.job.context[1].chat_data.get('user'),
            context.job.context[1].chat_data.get('contest')))
        return
    new_submissions = get_submissions(
        context.job.context[1].chat_data["contest"],
        context.job.context[1].chat_data["user"],
        context.job.context[1].chat_data.get("only_contestant", False))
    if new_submissions is None:
        return
    if new_submissions == context.job.context[1].chat_data["submissions"]:
        return
    info = print_submissions(new_submissions,
        context.job.context[1].chat_data["submissions"],
        context.job.context[1].chat_data.get("short_print", False))
    context.bot.send_message(context.job.context[0], text=info, parse_mode=telegram.ParseMode.MARKDOWN_V2)
    context.job.context[1].chat_data["submissions"] = new_submissions[:]


def get_status(update, context):
    if context.chat_data.get("f5_job") is None:
        update.message.reply_text('Start job with /start_f5')
        return
    info = print_submissions(context.chat_data['submissions'],
        context.chat_data["submissions"],
        context.chat_data.get("short_print", False))
    context.bot.send_message(update.message.chat_id, text=info, parse_mode=telegram.ParseMode.MARKDOWN_V2)


def start_f5(update, context):
    if context.chat_data.get("f5_job") is not None:
        update.message.reply_text('Stop previous job with /stop_f5')
        return

    if len(context.args) >= 1:
        if not re.fullmatch(r'[0-9]+', context.args[0]):
            update.message.reply_text('Contest must be an integer')
            return
        context.chat_data['contest'] = context.args[0]
        update.message.reply_text('Current contest: {}'.format(context.chat_data['contest']))
    if len(context.args) >= 2:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', context.args[1]):
            update.message.reply_text('Нашелся хакер... Я регулярку поставил')
            return
        context.chat_data['user'] = context.args[1]
        update.message.reply_text('Current user: {}'.format(context.chat_data['user']))

    if context.chat_data.get('user') is None:
        update.message.reply_text('Need user, for example "/user User"')
        return
    if context.chat_data.get('contest') is None:
        update.message.reply_text('Need contest, for example "/contest Contest"')
        return

    context.chat_data['submissions'] = []
    context.chat_data['f5_job_start_time'] = time()
    context.chat_data["f5_job"] = context.job_queue.run_repeating(check_updates, interval=1, first=0,
        context=[update.message.chat_id, context])
    update.message.reply_text('Started job with user {}, contest {}'.format(
        context.chat_data.get('user'),
        context.chat_data.get('contest')))

def stop_f5(update, context):
    if context.chat_data.get("f5_job") is None:
        update.message.reply_text('Nothing to stop')
    else:
        context.chat_data.get("f5_job").schedule_removal()
        context.chat_data.pop("f5_job")
        update.message.reply_text('Stopped job with user {}, contest {}'.format(
            context.chat_data.get('user'),
            context.chat_data.get('contest')))


def set_short(update, context):
    context.chat_data["short_print"] = True
def set_long(update, context):
    context.chat_data["short_print"] = False

def show_practice(update, context):
    context.chat_data["only_contestant"] = False
def hide_practice(update, context):
    context.chat_data["only_contestant"] = True


def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(CommandHandler("user", ask_user, pass_chat_data=True, pass_args=True))
    dp.add_handler(CommandHandler("contest", ask_contest, pass_chat_data=True, pass_args=True))
    dp.add_handler(CommandHandler("status", get_status, pass_chat_data=True))
    dp.add_handler(CommandHandler("start_f5", start_f5, pass_chat_data=True, pass_job_queue=True, pass_args=True))
    dp.add_handler(CommandHandler("stop_f5", stop_f5, pass_chat_data=True, pass_job_queue=True))
    dp.add_handler(CommandHandler("short", set_short, pass_chat_data=True))
    dp.add_handler(CommandHandler("long", set_long, pass_chat_data=True))
    dp.add_handler(CommandHandler("show_practice", show_practice, pass_chat_data=True))
    dp.add_handler(CommandHandler("hide_practice", hide_practice, pass_chat_data=True))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()

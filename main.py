import os
TOKEN = os.environ.get("TOKEN", open("token.txt", "r").readline().strip())

from requests import session
import json
import logging
import re
from time import time

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, PicklePersistence
import telegram

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

def ask_status(contest, from_=1, count=1000, only_contestant=False):
    data = session().get("https://codeforces.com/api/contest.status?contestId={}&from={}&count={}".format(
        contest, from_, count))
    if not data.ok:
        return None
    data = json.loads(data.text)
    if data["status"] != "OK" or data.get("result") is None:
        return None
    result = dict()
    for item in data["result"]:
        if item.get("contestId") is None or item.get("author") is None or item.get("problem") is None:
            continue
        if only_contestant and item.get("author").get("participantType", "?") != "CONTESTANT":
            continue

        author = item.get("author").get("members")[0]["handle"].lower()
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

        submission_id = item.get("id", 0)

        if result.get(author) is None:
            result[author] = []
        result[author].append([submission_id, problemIndex, testset, verdict, passedTestCount])
    return result


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
    for user in context.args:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', user):
            update.message.reply_text('Don\'t user strange symbols')
            return
        user = user.lower()
        if context.chat_data.get('user') is None:
            context.chat_data['user'] = set()
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
    msg = ', '.join(str(contest) for contest in context.bot_data.get('contest', []))
    update.message.reply_text('Current contests: ' + msg)

def add_contest(update, context):
    if update.message.from_user.username != 'maksim1744':
        update.message.reply_text('This option is not available for you')
        return

    for contest in context.args:
        if not re.fullmatch(r'[0-9]+', contest):
            update.message.reply_text('Contest must be an integer')
            break
        if context.bot_data.get('contest') is None:
            context.bot_data['contest'] = set()
        context.bot_data['contest'].add(contest)
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
            context.bot_data['contest'].remove(contest)
        if contest in context.bot_data.get('last_update', dict()):
            context.bot_data['last_update'].pop(contest)
        if contest in context.bot_data.get('data', dict()):
            context.bot_data['data'].pop(contest)
    ask_contest(update, context)


def error(update, context):
    logger.warning('Update "%s" caused error "%s"', update, context.error)



def stop_f5_job(chat_id, context):
    if context.chat_data.get("f5_job") is None:
        context.bot.send_message(chat_id, text='Nothing to stop')
        return;
    context.chat_data.get("f5_job").schedule_removal()
    context.chat_data.pop("f5_job")
    context.bot.send_message(chat_id, text='Stopped job')
    context.chat_data.get("data", dict()).clear()

def check_updates(context):
    job = context.job
    context = job.context[1]
    chat_id = job.context[0]

    if context.chat_data["f5_job_start_time"] + 86400 < time() or context.bot_data.get("contest", set()) == set() or \
        context.chat_data.get("user", set()) == set():
        stop_f5_job(chat_id, context)

    context.bot_data.setdefault("last_update", dict())
    context.bot_data.setdefault("data", dict())
    context.chat_data.setdefault("data", dict())

    msg = ""

    for contest in context.bot_data['contest']:
        context.bot_data["data"].setdefault(contest, dict())
        if context.bot_data["last_update"].get(contest, 0) + 1 < time():
            context.bot_data["data"][contest] = ask_status(contest,
                    only_contestant=context.chat_data.get("only_contestant", False))
            context.bot_data["last_update"][contest] = time()
        context.chat_data["data"].setdefault(contest, dict())
        for user in context.chat_data["user"]:
            context.chat_data["data"][contest].setdefault(user, dict())
            user_changed = False
            prev_submissions = []
            try:
                prev_submissions = [context.chat_data["data"][contest][user][key] for key in \
                             sorted(context.chat_data["data"][contest][user].keys())]
            except:
                print(context.chat_data["data"], flush=True)
            for submission in context.bot_data["data"][contest].get(user, []):
                if context.chat_data["data"][contest][user].get(submission[0], []) != submission[1:]:
                    context.chat_data["data"][contest][user][submission[0]] = submission[1:]
                    user_changed = True
            if user_changed:
                if msg != "":
                    msg += "\n"
                msg += "Contest {}, user {}\n".format(contest, user)
                cur_submissions = [context.chat_data["data"][contest][user][key] for key in \
                            sorted(context.chat_data["data"][contest][user].keys())]
                msg += print_submissions(
                    cur_submissions,
                    prev_submissions,
                    context.chat_data.get("short_print", False))
    if msg != "":
        context.bot.send_message(chat_id, text=msg, parse_mode=telegram.ParseMode.MARKDOWN_V2)


def get_status(update, context):
    if context.chat_data.get("f5_job") is None:
        update.message.reply_text('Start job with /start_f5')
        return
    msg = ''
    for contest in context.bot_data.get("contest", set()):
        for user in context.chat_data.get("user", set()):
            cur_submissions = [context.chat_data["data"][contest][user][key] for key in \
                        sorted(context.chat_data["data"][contest].get(user, dict()).keys())]
            if len(cur_submissions) > 0:
                if msg != "":
                    msg += "\n"
                msg += "Contest {}, user {}\n".format(contest, user)
                msg += print_submissions(
                    cur_submissions,
                    cur_submissions,
                    context.chat_data.get("short_print", False))
    if msg != "":
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

    context.chat_data['submissions'] = []
    context.chat_data['f5_job_start_time'] = time()
    context.chat_data["f5_job"] = context.job_queue.run_repeating(check_updates, interval=1, first=0,
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

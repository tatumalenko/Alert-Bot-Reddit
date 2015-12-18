"""
==========================================
Author:         Tyler Brockett
Description:    Reddit Bot - buildapcsales
Date:           11/13/2015
==========================================
"""

import os
import time
import praw
import sqlite3
import traceback
from sys import stdout

from helpers import color, times, database, inbox, files, output
from private import accountinfo

SLEEP_SECONDS = 15
NUM_POSTS_TO_CRAWL = 20
bot = accountinfo.username

connection = None
reddit = None
start_time = None


def run_bot():
    global start_time
    output.about_message()
    while True:
        read_inbox()
        crawl_subreddit('buildapcsales')
        color.print_color('yellow', times.get_time_passed(start_time))
        sleep(SLEEP_SECONDS)


def crawl_subreddit(subreddit):
    global reddit
    submissions = []
    try:
        submissions = reddit.get_subreddit(subreddit).get_new(limit=NUM_POSTS_TO_CRAWL)
    except:
        output.get_submissions_exception()
        reddit.send_message(accountinfo.developerusername, "Bot Exception - Crawl Subreddit", traceback.format_exc())
    for submission in submissions:
        # Make sure sale is not expired!
        if not submission.over_18:
            check_for_subscription(submission)


def handle_item_match(username, item, message_id, title, permalink, url):
    global connection, reddit
    try:
        message = reddit.get_message(message_id)
        connection.cursor().execute(database.INSERT_ROW_MATCHES,
                                    (username, item, permalink, times.get_current_timestamp()))
        message.reply(inbox.compose_match_message(username, item, title, permalink, url))
        connection.commit()
        output.match(username, item, message_id, title, permalink, url)
    except:
        connection.rollback()
        output.match_exception(username, item, message_id, title, permalink, url)
        reddit.send_message(accountinfo.developerusername, "Bot Exception - Handle Item Match", traceback.format_exc())
    sleep(2)


def check_for_subscription(submission):
    global connection

    title = submission.title.lower()
    text = submission.selftext.lower()
    permalink = submission.permalink
    url = submission.url

    for item in connection.cursor().execute(database.SELECT_DISTINCT_ITEMS).fetchall():
        if item[0] in title or item[0] in text:
            matches = connection.cursor().execute(database.GET_SUBSCRIBED_USERS_WITHOUT_LINK,
                                                  (item[0], permalink)).fetchall()
            for match in matches:
                handle_item_match(match[database.COL_SUB_USERNAME],
                                  match[database.COL_SUB_ITEM],
                                  match[database.COL_SUB_MESSAGE_ID],
                                  title,
                                  permalink,
                                  url)


def read_inbox():
    global connection, reddit
    i = 0

    unread_messages = []
    try:
        unread_messages = reddit.get_unread(limit=None)
    except:
        output.read_inbox_exception()
        reddit.send_message(accountinfo.developerusername, "Bot Exception - Read Inbox", traceback.format_exc())

    for unread_message in unread_messages:
        i += 1
        username, message_id, subject, body = \
            (str(unread_message.author).lower(),
             unread_message.id,
             inbox.format_subject(unread_message.subject.lower()),
             unread_message.body.lower())

        if ('unsubscribe' in body and 'all' in body) \
                or ('unsubscribe' in subject and 'all' in subject):
            try:
                cursor = connection.cursor()
                cursor.execute(database.REMOVE_ALL_SUBSCRIPTIONS_BY_USERNAME, (username,))
                cursor.execute(database.REMOVE_ALL_MATCHES_BY_USERNAME, (username,))
                unread_message.reply(inbox.compose_unsubscribe_all_message(username))
                unread_message.mark_as_read()
                connection.commit()
                output.unsubscribe_all(username)
            except:
                connection.rollback()
                output.unsubscribe_all_exception(username)
                reddit.send_message(accountinfo.developerusername, "Bot Exception - Unsubscribe All", traceback.format_exc())

        elif body == 'unsubscribe' and subject.replace(' ', '') != '':
            try:
                cursor = connection.cursor()
                cursor.execute(database.REMOVE_ROW_SUBSCRIPTIONS, (username, subject))
                cursor.execute(database.REMOVE_MATCHES_BY_USERNAME_AND_SUBJECT, (username, subject))
                unread_message.reply(inbox.compose_unsubscribe_message(username, subject))
                unread_message.mark_as_read()
                connection.commit()
                output.unsubscribe(username, subject)
            except:
                connection.rollback()
                output.unsubscribe_exception(username, subject)
                reddit.send_message(accountinfo.developerusername, "Bot Exception - Unsubscribe", traceback.format_exc())

        # Item must be longer than 2 non-space characters.
        elif body == 'subscribe' and len(inbox.format_subject(subject).replace(' ', '')) > 2:
            subscription = (username, message_id, subject, times.get_current_timestamp())
            try:
                cursor = connection.cursor()
                cursor.execute(database.INSERT_ROW_SUBMISSIONS, subscription)
                unread_message.reply(inbox.compose_subscribe_message(username, subject))
                unread_message.mark_as_read()
                connection.commit()
                output.subscribe(username, subject)
            except:
                connection.rollback()
                output.subscribe_exception(username, subject)
                reddit.send_message(accountinfo.developerusername, "Bot Exception - Subscribe", traceback.format_exc())

        elif subject == 'information' or subject == 'help':
            try:
                cursor = connection.cursor()
                cursor.execute(database.GET_SUBSCRIPTIONS_BY_USERNAME, (username,))
                unread_message.reply(inbox.compose_information_message(username, cursor.fetchall()))
                unread_message.mark_as_read()
                output.information(username)
            except:
                output.information_exception(username)
                reddit.send_message(accountinfo.developerusername, "Bot Exception - Information", traceback.format_exc())

        elif subject == 'feedback':
            try:
                reddit.send_message(accountinfo.developerusername, "Feedback for sales__bot",
                                    inbox.compose_feedback_forward(username, body))
                unread_message.reply(inbox.compose_feedback_message(username))
                unread_message.mark_as_read()
                output.feedback(username, body)
            except:
                output.feedback_exception(username, body)
                reddit.send_message(accountinfo.developerusername, "Bot Exception - Feedback", traceback.format_exc())
        else:
            try:
                unread_message.reply(inbox.compose_default_message(username, subject, body))
                unread_message.mark_as_read()
                output.default(username, subject, body)
            except:
                output.default_exception(username, subject, body)
                reddit.send_message(accountinfo.developerusername, "Bot Exception - Default", traceback.format_exc())
        sleep(2)
    color.print_color('cyan', str(i) + ' UNREAD MESSAGES')


def open_database():
    global connection
    connection = sqlite3.connect(os.path.dirname(os.path.abspath(__file__)) + database.DATABASE_LOCATION)
    cursor = connection.cursor()
    cursor.execute(database.CREATE_TABLE_SUBSCRIPTIONS)
    cursor.execute(database.CREATE_TABLE_MATCHES)
    cursor.execute(database.CREATE_TABLE_ALERTS)


def connect_to_reddit():
    global reddit
    # Connecting to Reddit
    user_agent = 'SALES__B0T - A Sales Notifier R0B0T'
    reddit = praw.Reddit(user_agent=user_agent)
    # TODO Use OAuth instead of this login method
    reddit.login(accountinfo.username, accountinfo.password, disable_warning=True)


def sleep(seconds):
    print 'Sleeping',
    for i in range(seconds):
        stdout.write(".")
        stdout.flush()
        time.sleep(1)
    print ''


def initialize():
    global start_time
    start_time = times.get_current_timestamp()
    # Setup process_id.pid
    files.write_to_file(files.PROCESS_ID, str(os.getpid()))
    connect_to_reddit()
    open_database()


def handle_crash(stacktrace):
    global connection, reddit
    reddit.send_message(accountinfo.developerusername, "Bot Crashed", stacktrace)
    files.erase_contents(files.PROCESS_ID)
    files.write_to_file(files.STACKTRACE, stacktrace)
    connection.close()
    exit()


__author__ = 'tyler'
if __name__ == "__main__":
    try:
        initialize()
        run_bot()
    except KeyboardInterrupt:
        color.print_color('red', 'Interrupted')
        exit()
    except:
        handle_crash(traceback.format_exc())

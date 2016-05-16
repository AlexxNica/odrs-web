#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2016 Richard Hughes <richard@hughsie.com>
# Licensed under the GNU General Public License Version 3

import MySQLdb as mdb
import cgi
import datetime

class CursorError(Exception):
    def __init__(self, cur, e):
        self.value = cgi.escape(cur._last_executed) + '&#10145; ' + cgi.escape(str(e))
    def __str__(self):
        return repr(self.value)

def _combine_karma(karma_up, karma_down):
    """ This is required because society is broken """
    return (karma_up * 5) - karma_down

def _create_review_item(e):
    """ Parse a review """
    item = {}
    item['review_id'] = int(e[0])
    item['date_created'] = int(e[1].strftime("%s"))
    item['app_id'] = e[2]
    item['locale'] = e[3]
    item['summary'] = e[4]
    item['description'] = e[5]
    item['version'] = e[6]
    item['distro'] = e[7]
    item['karma'] = _combine_karma(int(e[8]), int(e[9]))
    item['user_hash'] = e[10]
    item['user_display'] = e[11]
    item['rating'] = int(e[12])
    if e[13]:
        item['date_deleted'] = int(e[13].strftime("%s"))
    return item

def _create_event_item(e):
    """ Parse an event """
    item = {}
    item['eventlog_id'] = int(e[0])
    item['date_created'] = int(e[1].strftime("%s"))
    item['user_addr'] = e[2]
    item['user_hash'] = e[3]
    item['message'] = e[4]
    item['app_id'] = e[5]
    item['important'] = int(e[6])
    return item

def _create_user_item(e):
    """ Parse a user """
    item = {}
    item['user_id'] = int(e[0])
    item['date_created'] = int(e[1].strftime("%s"))
    item['date_request'] = int(e[2].strftime("%s"))
    item['user_hash'] = e[3]
    item['karma'] = int(e[4])
    item['is_banned'] = int(e[5])
    return item

class ReviewsDatabase(object):

    def __init__(self, environ):
        """ Constructor for object """
        assert environ
        self._db = None
        try:
            if 'OPENSHIFT_MYSQL_DB_HOST' in environ:
                self._db = mdb.connect(environ['OPENSHIFT_MYSQL_DB_HOST'],
                                       environ['OPENSHIFT_MYSQL_DB_USERNAME'],
                                       environ['OPENSHIFT_MYSQL_DB_PASSWORD'],
                                       'secure',
                                       int(environ['OPENSHIFT_MYSQL_DB_PORT']),
                                       use_unicode=True, charset='utf8')
            else:
                self._db = mdb.connect('localhost', 'test', 'test', 'secure',
                                       use_unicode=True, charset='utf8')
            self._db.autocommit(True)
        except mdb.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
        assert self._db

    def __del__(self):
        """ Clean up the database """
        if self._db:
            self._db.close()

    def review_add(self, item, user_addr):
        """ Add a review to the database """
        try:
            cur = self._db.cursor()
            cur.execute("INSERT INTO reviews (app_id, locale, summary, "
                        "description, user_hash, user_display, version, "
                        "distro, rating, user_addr) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);",
                        (item['app_id'],
                         item['locale'],
                         item['summary'],
                         item['description'],
                         item['user_hash'],
                         item['user_display'],
                         item['version'],
                         item['distro'],
                         item['rating'],
                         user_addr,))
        except mdb.Error, e:
            raise CursorError(cur, e)

    def review_remove(self, review_id, user_hash):
        """ Marks a review as removed """
        try:
            cur = self._db.cursor()
            cur.execute("UPDATE reviews SET date_deleted = CURRENT_TIMESTAMP "
                        "WHERE user_hash = %s AND review_id = %s;",
                        (user_hash, review_id,))
        except mdb.Error, e:
            raise CursorError(cur, e)
        return True

    def review_get_for_app_id(self, app_id):
        """ Returns all the reviews for an application (for client-side) """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT review_id, date_created, app_id, locale, summary, "
                        "description, version, distro, karma_up, karma_down, "
                        "user_hash, user_display, rating, date_deleted "
                        "FROM reviews WHERE app_id=%s AND reported=0 AND "
                        "date_deleted=0 ORDER BY date_created DESC;",
                        (app_id,))
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return []
        items = []
        for e in res:
            items.append(_create_review_item(e))
        return items

    def review_exists(self, app_id, user_hash):
        """ Checks to see if a review exists for the application+user """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT review_id FROM reviews WHERE app_id=%s "
                        "AND user_hash=%s AND date_deleted=0;",
                        (app_id, user_hash,))
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchone()
        if res is not None:
            return True
        return False

    def vote_exists(self, review_id, user_hash):
        """ Checks to see if a vote exists for the review+user """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT date_created "
                        "FROM votes WHERE review_id=%s AND user_hash=%s;",
                        (review_id, user_hash,))
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchone()
        if res is not None:
            return True
        return False

    def vote_add(self, review_id, val, user_hash):
        """ Votes on a specific review and add to the votes database """
        try:
            cur = self._db.cursor()
            if val == -5:
                cur.execute("UPDATE reviews SET reported = reported + 1 "
                            "WHERE review_id = %s;", (review_id,))
            elif val == 1:
                cur.execute("UPDATE reviews SET karma_up = karma_up + 1 "
                            "WHERE review_id = %s;", (review_id,))
            elif val == -1:
                cur.execute("UPDATE reviews SET karma_down = karma_down + 1 "
                            "WHERE review_id = %s;", (review_id,))
            cur.execute("INSERT INTO votes (user_hash, review_id, val) "
                        "VALUES (%s, %s, %s);",
                        (user_hash, review_id, val,))
        except mdb.Error, e:
            raise CursorError(cur, e)

    def review_get_all(self):
        """ Gets all non-removed reviews from the server for all applications """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT review_id, date_created, app_id, locale, summary, "
                        "description, version, distro, karma_up, karma_down, "
                        "user_hash, user_display, rating, date_deleted FROM reviews "
                        "WHERE reported=0 "
                        "ORDER BY date_created DESC;")
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return []
        items = []
        for e in res:
            items.append(_create_review_item(e))
        return items

    def event_warn(self,
                   user_addr=None,
                   user_hash=None,
                   app_id=None,
                   message=None,
                   important=True):
        """ Adds a warning to the event log """
        try:
            cur = self._db.cursor()
            cur.execute("INSERT INTO eventlog2 (user_addr, user_hash, app_id, "
                        "message, important) "
                        "VALUES (%s, %s, %s, %s, %s);",
                        (user_addr, user_hash, app_id, message, important,))
        except mdb.Error, e:
            raise CursorError(cur, e)

    def event_info(self, user_addr=None, user_hash=None, app_id=None, message=None):
        """ Adds an info item to the event log """
        self.event_warn(user_addr, user_hash, app_id, message, False)

    def event_get_all(self):
        """ Returns all events from the event log """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT eventlog_id, date_created, user_addr, user_hash, "
                        "message, app_id, important "
                        "FROM eventlog2 ORDER BY eventlog_id DESC;")
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return []
        items = []
        for e in res:
            items.append(_create_event_item(e))
        return items

    def user_add(self, user_hash):
        """ Add a user to the database """
        try:
            cur = self._db.cursor()
            cur.execute("INSERT INTO users2 (user_hash) VALUES (%s);",
                        (user_hash,))
            cur.execute("UPDATE users2 SET date_request = CURRENT_TIMESTAMP "
                        "WHERE user_hash = %s;", (user_hash,))
        except mdb.Error, e:
            raise CursorError(cur, e)

    def user_get_all(self):
        """ Get all the users on the system """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT user_id, date_created, date_request, "
                        "user_hash, karma, is_banned "
                        "FROM users2 ORDER BY user_id DESC;")
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        if not res:
            return []
        items = []
        for e in res:
            items.append(_create_user_item(e))
        return items

    def user_get_by_id(self, user_hash):
        """ Get information about a specific user """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT user_id, date_created, date_request, "
                        "user_hash, karma, is_banned "
                        "FROM users2 WHERE user_hash=%s ORDER BY user_id DESC;",
                        (user_hash,))
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchone()
        if not res:
            return None
        return _create_user_item(res)

    def user_update_request(self, user_hash):
        """ Update the request time for a specific user ID """

        # if not existing, create it
        user = self.user_get_by_id(user_hash)
        if not user:
            self.user_add(user_hash)
            return

        # update the timestamp
        try:
            cur = self._db.cursor()
            cur.execute("UPDATE users2 SET date_request = CURRENT_TIMESTAMP "
                        "WHERE user_hash = %s;", (user_hash,))
        except mdb.Error, e:
            raise CursorError(cur, e)

    def user_update_karma(self, user_hash, val):
        """ Update the request time for a specific user ID """

        # if not existing, create it
        user = self.user_get_by_id(user_hash)
        if not user:
            self.user_add(user_hash)
            return

        # update the karma value
        try:
            cur = self._db.cursor()
            cur.execute("UPDATE users2 SET karma = karma + %s "
                        "WHERE user_hash = %s;", (user_hash, val,))
        except mdb.Error, e:
            raise CursorError(cur, e)

    def reviews_get_rating_for_app_id(self, app_id):
        """ Gets the ratings information for the application """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT COUNT(*) total,"
                        "       SUM(rating = 0) star0,"
                        "       SUM(rating = 20) star1,"
                        "       SUM(rating = 40) star2,"
                        "       SUM(rating = 60) star3,"
                        "       SUM(rating = 80) star4,"
                        "       SUM(rating = 100) star5 "
                        "FROM reviews WHERE app_id = %s "
                        "AND date_deleted=0;", (app_id,))
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchone()
        if not res:
            return []
        item = {}
        item['total'] = int(res[0])
        for i in range(6):
            if res[i + 1]:
                item['star%i' % i] = int(res[i + 1])
            else:
                item['star%i' % i] = 0
        return item

    def get_stats_fetch(self):
        """ Returns interesting statistics for the webapp """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT DISTINCT app_id, COUNT(app_id) as total "
                        "FROM eventlog2 WHERE app_id IS NOT NULL "
                        "AND message='fetching review' GROUP BY app_id "
                        "ORDER BY total DESC LIMIT 20;")
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        data = []
        for en in res:
            data.append((en[0], en[1]))
        return data

    def get_stats(self):
        """ Returns interesting statistics for the webapp """
        item = {}

        # get the total number of reviews
        try:
            cur = self._db.cursor()
            cur.execute("SELECT COUNT(*) FROM reviews;")
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        item['NumberReviews'] = int(res[0][0])

        # unique reviewers
        try:
            cur.execute("SELECT COUNT(DISTINCT(user_hash)) FROM reviews;")
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        item['NumberUniqueReviewers'] = int(res[0][0])

        # total votes
        try:
            cur.execute("SELECT COUNT(*) FROM votes WHERE val = 1;")
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        item['NumberVotesUp'] = int(res[0][0])
        try:
            cur.execute("SELECT COUNT(*) FROM votes WHERE val = -1;")
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        item['NumberVotesDown'] = int(res[0][0])

        # unique voters
        try:
            cur.execute("SELECT COUNT(DISTINCT(user_hash)) FROM votes;")
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        item['NumberUniqueVoters'] = int(res[0][0])

        # unique distros
        try:
            cur.execute("SELECT COUNT(DISTINCT(distro)) FROM reviews;")
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        item['NumberUniqueDistros'] = int(res[0][0])

        # unique distros
        try:
            cur.execute("SELECT COUNT(*) FROM reviews WHERE reported > 0;")
        except mdb.Error, e:
            raise CursorError(cur, e)
        res = cur.fetchall()
        item['NumberReviewsReported'] = int(res[0][0])

        # done
        return item

    def get_stats_by_interval(self, size, interval, msg, distinct=False):
        """ Gets stats data """
        data = []
        now = datetime.date.today()

        # yes, there's probably a way to do this in one query
        for i in range(size):
            start = now - datetime.timedelta((i * interval) + interval - 1)
            end = now - datetime.timedelta((i * interval) - 1)
            try:
                cur = self._db.cursor()
                if distinct:
                    cur.execute("SELECT COUNT(DISTINCT(user_hash)) FROM eventlog2 "
                                "WHERE message = %s AND date_created >= %s "
                                "AND date_created <  %s", (msg, start, end,))
                else:
                    cur.execute("SELECT COUNT(*) FROM eventlog2 "
                                "WHERE message = %s AND date_created >= %s "
                                "AND date_created <  %s", (msg, start, end,))
            except mdb.Error, e:
                raise CursorError(cur, e)
            data.append(int(cur.fetchone()[0]))
        return data

    def get_stats_by_month(self, msg, distinct=False):
        data = []
        now = datetime.date.today()
        for i in range(0, 12):
            month_num = now.month - i
            if month_num < 1:
                month_num = 12 - month_num
            try:
                cur = self._db.cursor()
                if distinct:
                    cur.execute("SELECT COUNT(DISTINCT(user_hash)) FROM eventlog2 "
                                "WHERE message = %s AND MONTH(date_created) = %s;",
                                (msg, month_num,))
                else:
                    cur.execute("SELECT COUNT(*) FROM eventlog2 "
                                "WHERE message = %s AND MONTH(date_created) = %s;",
                                (msg, month_num,))
            except mdb.Error, e:
                raise CursorError(cur, e)
            data.append(int(cur.fetchone()[0]))
        return data

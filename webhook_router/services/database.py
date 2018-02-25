import asyncio
import logging
import sqlite3
import time
from asyncio import Future
from functools import wraps
from queue import Queue
from threading import Thread
from types import MethodType


def queued_call(fn):
    @wraps(fn)
    def decorated(self, *a, **kw):
        # noinspection PyArgumentList
        bound_method = MethodType(fn, self)
        return self.call(bound_method, *a, **kw)
    return decorated


class DatabaseWorker(Thread):
    def __init__(self, filename):
        super().__init__(name='DatabaseThread', daemon=True)
        self.connection = None
        self.work_queue = Queue()
        self.filename = filename
        self.logger = logging.getLogger(__name__)
        self.loop = asyncio.get_event_loop()

    def connect(self):
        self.logger.info('Connecting to database: %r', self.filename)
        self.connection = sqlite3.connect(
            self.filename, detect_types=sqlite3.PARSE_DECLTYPES)
        self.connection.set_trace_callback(self.logger.getChild("sql").debug)
        self.connection.row_factory = sqlite3.Row
        self.connection.isolation_level = None
        #self.connection.execute("PRAGMA journal_mode = WAL")
        #self.connection.isolation_level = ''
        #self.connection.execute("PRAGMA journal_mode = MEMORY")
        # con.execute("PRAGMA foreign_keys = ON")

    def call(self, fn, *args, **kwargs):
        future = Future()
        work_item = (future, fn, args, kwargs)
        self.work_queue.put(work_item)
        self.logger.debug("Pending storage calls: %s", self.work_queue.qsize())
        return future

    def run(self):
        self.logger.info("Starting Database Worker")
        self.connect()
        self.create_schema()

        while True:
            future, fn, args, kwargs = self.work_queue.get(block=True)
            before = time.time()
            try:
                result = fn(*args, **kwargs)
            except BaseException as e:
                self.loop.call_soon_threadsafe(future.set_exception, e)
            else:
                self.loop.call_soon_threadsafe(future.set_result, result)
            self.logger.debug("Database operation took %.2f ms",
                              (time.time() - before) * 1000)

    def create_schema(self):
        conn = self.connection
        conn.execute("CREATE TABLE IF NOT EXISTS Messages("
                     "id INTEGER PRIMARY KEY, "
                     "time REAL NOT NULL, "
                     "channel TEXT NOT NULL, "
                     "content TEXT NOT NULL, "
                     "meta TEXT NOT NULL)")

    @queued_call
    def insert_message(self, timestamp, channel, content, meta):
        conn = self.connection
        sql = ("INSERT INTO Messages (time, channel, content, meta) "
               "VALUES (:time, :channel, :content, :meta)")
        cur = conn.execute(sql, {'time': timestamp, 'channel': channel,
                                 'content': content, 'meta': meta})
        return cur.lastrowid if cur.rowcount > 0 else None

    @queued_call
    def get_messages(self, channel, limit):
        conn = self.connection
        sql = ("SELECT id, time, channel, content, meta "
               "FROM Messages "
               "WHERE channel=:channel "
               "ORDER BY id DESC "
               "LIMIT :limit")
        cur = conn.execute(sql, {'channel': channel, 'limit': limit})
        return cur.fetchall()

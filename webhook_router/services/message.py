import datetime
import json
import logging
import time
from collections import defaultdict

from webhook_router.utils import json_dumps

logger = logging.getLogger(__name__)


class MessageService:

    def __init__(self, database, publish=None, handlers=None):
        self.database = database
        self.publish = publish
        self.handlers = handlers or {}

    async def handle_message(self, channel, content, meta):
        now = time.time()

        future = self.database.insert_message(
            now, channel, content=json_dumps(content), meta=json_dumps(meta))
        future.add_done_callback(lambda f: f.result())

        #now_dt = datetime.datetime.utcfromtimestamp(now)
        if self.publish:
            self.publish(channel=channel, content=content, time=now,
                         meta=meta)

        if channel not in self.handlers:
            return None
        async_handler = self.handlers[channel]
        return_value = await async_handler(content, channel=channel,
                                           time=now, meta=meta)
        return return_value

    async def get_messages(self, channel, limit):
        messages = await self.database.get_messages(channel, limit=limit)
        return [{'id': m['id'],
                 'time': datetime.datetime.utcfromtimestamp(m['time']),
                 'channel': m['channel'],
                 'content': json.loads(m['content']),
                 'meta': json.loads(m['meta'])} for m in messages]

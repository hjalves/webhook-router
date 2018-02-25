import datetime
import json
import time
import logging
from asyncio import ensure_future, gather
from collections import defaultdict

from aiohttp import WSMsgType
from aiohttp.web_ws import WebSocketResponse

from webhook_router.utils import json_dumps

logger = logging.getLogger(__name__)


class WebsocketSubscriber:

    def __init__(self, request):
        self.request = request
        self.remote = request.remote
        self.peername = request.transport.get_extra_info('peername')
        self.response = WebSocketResponse()

    def __repr__(self):
        return f"<WebsocketSubscriber {self.remote}: {self.peername}>"

    async def prepare(self):
        result = await self.response.prepare(self.request)
        logger.debug("Websocket prepared, result: %s", result)
        return result

    async def send_message(self, message):
        await self.response.send_str(message)

    async def until_closed(self):
        async for msg in self.response:
            logger.warning("ws message: %s", msg)
            if msg.type == WSMsgType.ERROR:
                logger.error('ws connection closed with exception %s',
                             self.response.exception())
                break
        logger.debug("Websocket closed: %r", self)


class MessageService:

    def __init__(self, database):
        self.channels = defaultdict(set)
        self.database = database

    def subscribe(self, channel, subscriber):
        logger.debug("subscribe: %r, %r", channel, subscriber)
        self.channels[channel].add(subscriber)

    def unsubscribe(self, channel, subscriber):
        logger.debug("unsubscribe: %r, %r", channel, subscriber)
        self.channels[channel].remove(subscriber)

    async def _async_publish(self, channel, message):
        coros = [sub.send_message(message) for sub in self.channels[channel]]
        return await gather(*coros, return_exceptions=True)

    def publish(self, channel, message):
        if channel not in self.channels or not self.channels[channel]:
            return

        def publish_callback(future):
            result = future.result()
            failed = len([x for x in result if isinstance(x, Exception)])
            success = len(result) - failed
            logger.debug("Published for %s, failed %s: %s", success, failed,
                         result)

        task = ensure_future(self._async_publish(channel, message))
        task.add_done_callback(publish_callback)

    async def new_message(self, channel, content, meta):
        now = time.time()
        msg_id = await self.database.insert_message(
            now, channel, content=json_dumps(content), meta=json_dumps(meta))
        message = {'id': msg_id,
                   'time': datetime.datetime.fromtimestamp(now),
                   'channel': channel,
                   'content': content,
                   'meta': meta}
        self.publish(channel, json_dumps(message))
        return message

    async def get_messages(self, channel, limit):
        messages = await self.database.get_messages(channel, limit=limit)
        return [{'id': m['id'],
                 'time': datetime.datetime.fromtimestamp(m['time']),
                 'channel': m['channel'],
                 'content': json.loads(m['content']),
                 'meta': json.loads(m['meta'])} for m in messages]

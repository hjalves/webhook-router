import datetime
import json
import time

from webhook_router.services.message import WebsocketSubscriber
from webhook_router.utils import jsonify, jsonbody


async def webhook_receiver(request):
    messages = request.app['messages']
    channel = request.match_info['channel']
    content = await jsonbody(request)
    meta = {'headers': dict(request.headers),
            'address': request.remote}
    message = await messages.new_message(channel, content, meta)
    return jsonify(message)


async def get_messages(request):
    channel = request.match_info['channel']
    messages = request.app['messages']
    msgs = await messages.get_messages(channel, limit=20)
    return jsonify(messages=msgs)


async def websocket_handler(request):
    messages = request.app['messages']
    channel = request.match_info['channel']
    ws = WebsocketSubscriber(request)
    await ws.prepare()
    messages.subscribe(channel, ws)
    await ws.until_closed()
    messages.unsubscribe(channel, ws)
    return ws.response

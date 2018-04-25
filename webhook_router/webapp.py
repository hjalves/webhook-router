import asyncio
import logging
import logging.config
import time
from asyncio import ensure_future
from pathlib import Path

from aiohttp import web
from aiohttp_remotes import XForwardedRelaxed

from webhook_router.utils import jsonify, jsonbody, json_error, \
    format_exception

logger = logging.getLogger(__name__)


async def webhook_handler(request):
    try:
        messages = request.app['messages']
        channel = request.match_info['channel']
        content = await jsonbody(request)
        meta = {'headers': dict(request.headers),
                'address': request.remote}
        result = await messages.handle_message(channel, content, meta)
        if result is None:
            return web.Response(status=204)
        return jsonify(result)
    except Exception as e:
        logger.debug("Error handling request: %s\nHeaders: %s",
                     e, request.headers)
        raise

async def get_messages(request):
    channel = request.match_info['channel']
    messages = request.app['messages']
    msgs = await messages.get_messages(channel, limit=20)
    return jsonify(messages=msgs)


def create_webapp(config, messages_service):
    webapp = web.Application(
        middlewares=[timer_middleware, error_middleware],
        debug=config['debug_mode'],
        logger=logger
    )
    x_forwarded = XForwardedRelaxed(num=0)  # num=0 is a hack to get the first
    ensure_future(x_forwarded.setup(webapp))

    prefix = config['prefix']
    webapp.router.add_get(prefix + '/{channel}', get_messages)
    webapp.router.add_post(prefix + '/{channel}', webhook_handler)

    webapp['messages'] = messages_service
    return webapp


async def start_webapp(webapp, config):
    logger.warning("CONFIG: %s", config)
    runner = web.AppRunner(webapp)
    await runner.setup()
    if 'http_host' in config or 'http_port' in config:
        tcp_site = web.TCPSite(runner, config.get('http_host'),
                               config.get('http_port'))
        logger.info("Will start http on: %s", tcp_site.name)
        await tcp_site.start()
    if 'unix_socket' in config:
        unix_socket = Path(config['unix_socket']).absolute()
        unix_site = web.UnixSite(runner, unix_socket)
        logger.info("Will start unix on: %s", unix_site.name)
        await unix_site.start()
        unix_socket.chmod(0o777)
    return runner


@web.middleware
async def timer_middleware(request, handler):
    now = time.time()
    response = await handler(request)
    elapsed = (time.time() - now) * 1000
    timer_logger = logger.getChild('timer')
    if response is not None and not response.prepared:
        response.headers['X-Elapsed'] = "%.3f ms" % elapsed

    response_class_name = (response.__class__.__name__
                           if response is not None else response)
    timer_logger.log(logging.DEBUG if elapsed <= 100 else logging.WARNING,
                     f"%s | %s %s: %.3f ms", response_class_name,
                     request.method, request.rel_url, elapsed)
    return response


@web.middleware
async def error_middleware(request, handler):
    try:
        response = await handler(request)
        if response is not None and response.status >= 400:
            return json_error(response.reason, response.status)
        return response
    except web.HTTPException as ex:
        if ex.status >= 400:
            return json_error(ex.reason, ex.status)
        raise
    except asyncio.CancelledError:
        raise
    except Exception as e:
        request.app.logger.exception(
            "Exception while handling request %s %s:", request.method,
            request.rel_url)
        return json_error(format_exception(e), 500)

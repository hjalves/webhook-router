import asyncio
import argparse
import logging
import logging.config
from asyncio import ensure_future
from pathlib import Path
import time

from aiohttp import web
from aiohttp_remotes import XForwardedRelaxed
import toml

from webhook_router import views
from webhook_router.services.database import DatabaseWorker
from webhook_router.services.message import MessageService
from webhook_router.utils import json_error, format_exception

logger = logging.getLogger(__name__)
here_path = Path(__file__).parent


def main(args=None):
    parser = argparse.ArgumentParser(description='webhook-router')
    parser.add_argument('-c', '--config', required=True,
                        type=argparse.FileType('r'),
                        help='Configuration file')
    args = parser.parse_args(args)
    return app(config_file=args.config)


def app(config_file):
    config = load_config(config_file)

    logging.config.dictConfig(config['logging'])
    logging.captureWarnings(True)
    logger.info('Logging configured!')

    database = DatabaseWorker(filename='db.sqlite')
    database.start()
    messages = MessageService(database)

    application = web.Application(
        middlewares=[timer_middleware, error_middleware],
        debug=config['debug_mode'],
        logger=logger
    )

    x_forwarded = XForwardedRelaxed()
    ensure_future(x_forwarded.setup(application))

    application.router.add_get('/c/{channel}', views.get_messages)
    application.router.add_post('/c/{channel}', views.webhook_receiver)
    application.router.add_post('/ws/{channel}', views.websocket_handler)
    
    application.router.add_get('/{channel}', views.get_messages)
    application.router.add_post('/{channel}', views.webhook_receiver)
    application.router.add_get('/{channel}/ws', views.websocket_handler)

    application['database'] = database
    application['messages'] = messages

    web.run_app(application, host=config['http_host'],
                port=config['http_port'])


def load_config(file):
    if isinstance(file, (str, Path)):
        file = open(file)
    with file:
        config = toml.load(file)
    return config


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
        logger.exception("Exception while handling request %s:",
                         request.rel_url)
        return json_error(format_exception(e), 500)

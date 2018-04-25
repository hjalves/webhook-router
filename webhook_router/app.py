import argparse
import asyncio
import logging
import logging.config
from functools import partial
from pathlib import Path

from autobahn.asyncio.component import Component
import toml
from txaio.aio import _TxaioLogWrapper

from webhook_router.services.database import DatabaseWorker
from webhook_router.services.message import MessageService
from webhook_router.webapp import start_webapp, create_webapp

logger = logging.getLogger(__name__)
here_path = Path(__file__).parent


def main(args=None):
    parser = argparse.ArgumentParser(description='webhook-router')
    parser.add_argument('-c', '--config', required=True,
                        type=argparse.FileType('r'),
                        help='Configuration file')
    args = parser.parse_args(args)
    return App(config_file=args.config).run()


class App:
    def __init__(self, config_file):
        self.config_file = config_file
        self.config = self.load_config(self.config_file)
        self.database = DatabaseWorker(filename='db.sqlite')
        self.messages = MessageService(self.database)
        self.webapp = create_webapp(self.config['web'], self.messages)
        # WAMP
        self.channel_handlers = {}
        wamp_config = self.config['wamp']
        self.wamp_session = None
        self.wamp_comp = Component(
            transports=wamp_config['router'],
            realm=wamp_config['realm']
        )
        #self.wamp_comp.log = _TxaioLogWrapper(logger.getChild('wamp'))
        self.wamp_comp.on('join', self.initialize_wamp)
        self.wamp_comp.on('leave', self.uninitialize_wamp)

    @staticmethod
    def load_config(file):
        if isinstance(file, (str, Path)):
            file = open(file)
        with file:
            config = toml.load(file)
        return config

    def run(self):
        config = self.config
        logging.config.dictConfig(config['logging'])
        logging.captureWarnings(True)
        logger.info('Logging configured!')

        # Start database worker thread
        self.database.start()

        loop = asyncio.get_event_loop()
        try:
            return loop.run_until_complete(self.main_loop())
        except KeyboardInterrupt:
            logger.warning("KeyboardInterrupt")
            return 130
        finally:
            logger.info("Cleaning up")
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    async def main_loop(self):
        channels = await self.database.get_channels()
        self.channel_handlers = {c['channel']: c['handler'] for c in channels}
        logger.info("Channel Handlers: %s", self.channel_handlers)

        runner = await start_webapp(self.webapp, self.config['web'])
        await self.wamp_comp.start()

        # running = True
        #while running:
        #    logger.info("Running in main loop")
        #    await asyncio.sleep(60)

        await runner.cleanup()

    async def initialize_wamp(self, session, details):
        logger.info("Connected to WAMP router: %s", details)
        self.wamp_session = session
        # Setup messages
        self.messages.publish = self.publish_wamp
        self.messages.handlers = {
            name: partial(self.wamp_session.call, handler)
            for name, handler in self.channel_handlers.items()
        }
        self.messages.handlers['echo'] = self.echo

    async def uninitialize_wamp(self, session, reason):
        logger.info("%s %s", session, reason)
        logger.info("Lost WAMP connection")
        self.wamp_session = None
        self.messages.publish = None
        self.messages.handlers = {}

    async def echo(self, content, channel, time, meta):
        return dict(content=content, channel=channel, time=time, meta=meta)

    def publish_wamp(self, channel, content, meta, time):
        self.wamp_session.publish(f'webhooks.{channel}', content,
                                  channel=channel, meta=meta, time=time)

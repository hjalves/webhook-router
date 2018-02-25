import datetime
import json
from json import JSONDecodeError
from traceback import format_exception_only

from aiohttp import web


def format_exception(ex):
    return format_exception_only(ex.__class__, ex)[-1].strip()


async def jsonbody(request):
    if not request.content_type == 'application/json':
        raise web.HTTPBadRequest(reason='Only JSON is supported')
    try:
        return await request.json()
    except ValueError as e:
        raise web.HTTPBadRequest(reason=format_exception(e))


def json_dumps(obj):
    def default(o):
        if isinstance(o, (datetime.datetime, datetime.date)):
            return o.isoformat()
        raise TypeError('%r is not JSON serializable' % obj)
    return json.dumps(obj, default=default)


def jsonify(*a, status=200, reason=None, headers=None, content_type=None,
            dumps=json_dumps, **kw):
    content_type = content_type or 'application/json'
    text = dumps(dict(*a, **kw))
    return web.Response(text=text, status=status, reason=reason,
                        headers=headers, content_type=content_type)


def json_error(error, status):
    message = {'error': error, 'status': status}
    return web.json_response(message, status=status)

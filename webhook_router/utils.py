import datetime
import json
from traceback import format_exception_only

from aiohttp import web

JSON_TYPE = 'application/json'
FORM_TYPE = 'application/x-www-form-urlencoded'


def format_exception(ex):
    return format_exception_only(ex.__class__, ex)[-1].strip()


async def http_body(request):
    if request.content_type in (JSON_TYPE, FORM_TYPE):
        try:
            if request.content_type == JSON_TYPE:
                return await request.json()
            else:
                return dict(await request.post())
        except Exception as e:
            raise web.HTTPBadRequest(reason=format_exception(e))
    else:
        raise web.HTTPBadRequest(
            reason=f"Content-Type must be '{JSON_TYPE}' or '{FORM_TYPE}'")


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

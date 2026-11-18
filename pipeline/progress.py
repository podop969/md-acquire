"""Job-local progress events, shared with async download tasks."""
from contextlib import contextmanager
from contextvars import ContextVar
import re

_sink = ContextVar('download_progress_sink', default=None)


@contextmanager
def listen(callback):
    token = _sink.set(callback)
    try:
        yield
    finally:
        _sink.reset(token)


def emit(stage, message, **fields):
    callback = _sink.get()
    if callback is not None:
        event = dict(stage=stage, message=message, received=None, total=None)
        event.update(fields)
        callback(event)


def failure_reason(exc):
    """Keep diagnostics readable without exposing signed URLs in the status card."""
    import requests
    if isinstance(exc, requests.exceptions.SSLError):
        return 'The server’s certificate could not be verified. Try another source.'
    if isinstance(exc, requests.Timeout):
        return 'The server timed out. Retry later or try another source.'
    if isinstance(exc, requests.ConnectionError):
        return 'Could not connect to the server. Check your connection and retry.'
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        return {401: 'The file server requires authorization; this copy is not publicly accessible.',
                403: 'The file server refused access; verification or borrowing may be required.',
                404: 'The file link no longer exists.',
                429: 'The source is rate-limiting requests. Wait before retrying.'}.get(
                    code, f'The file server returned HTTP {code}. Try another source.')
    return re.sub(r'https?://\S+', '[source URL]', str(exc))[:700] or type(exc).__name__

import asyncio
import threading
import time

import pytest
import requests

from pipeline.progress import emit, listen, failure_reason
from pipeline.webui import Job
from pipeline.download import download
from pipeline.models import Candidate
from tests.conftest import FakeResponse


def test_listener_follows_async_tasks_but_not_other_threads():
    events = []
    async def work():
        emit('waiting', 'Verify')
    with listen(events.append):
        asyncio.run(work())
        thread = threading.Thread(target=lambda: emit('failed', 'Unrelated search'))
        thread.start()
        thread.join()
    emit('failed', 'Outside job')
    assert [e['message'] for e in events] == ['Verify']


def test_job_reports_live_status_and_keeps_finished_results():
    job = Job()
    ready, release = threading.Event(), threading.Event()
    def work():
        emit('waiting', 'Verify in browser', key='book', title='Book')
        ready.set()
        assert release.wait(3)
        emit('saved', 'Saved book.epub', result='ok')
        return 0
    assert job.start('fetch', work)
    try:
        assert ready.wait(3)
        assert job.status()['progress']['stage'] == 'waiting'
        assert not job.start('another', lambda: 0)
    finally:
        release.set()
    deadline = time.monotonic() + 3
    while job.status()['running'] and time.monotonic() < deadline:
        time.sleep(.01)
    status = job.status()
    assert not status['running']
    assert status['results'][0]['result'] == 'ok'
    assert status['progress']['stage'] == 'saved'
    assert job.status()['elapsed'] == status['elapsed']


@pytest.mark.parametrize('length', [True, False])
def test_stream_reports_measured_bytes_then_validation(tmp_path, make_spec, fake_client, length):
    data = b'%PDF-' + b'x' * 70000
    headers = {'content-length': str(len(data))} if length else {}
    client = fake_client({'file': FakeResponse(content=data, headers=headers)})
    events = []
    with listen(events.append):
        path, _ = download(client, Candidate(source='test', url='https://file', fmt='pdf'), make_spec(), tmp_path)
    assert path.read_bytes() == data
    assert events[-1]['stage'] == 'validating'
    assert events[-2]['received'] == len(data)
    assert events[-2]['total'] == (len(data) if length else None)


def test_http_failure_is_readable_and_does_not_expose_signed_url():
    response = requests.Response()
    response.status_code = 401
    error = requests.HTTPError('https://file?secret=token', response=response)
    assert 'authorization' in failure_reason(error)
    assert 'secret' not in failure_reason(error)

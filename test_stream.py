import json
import unittest
from unittest.mock import patch
import requests
import app as module

class Upstream:
    ok = True
    status_code = 200
    closed = False
    def __init__(self, results=None, failure=None):
        self.results = results or []
        self.failure = failure
    def iter_lines(self, **kwargs):
        for result in self.results:
            yield 'data: ' + json.dumps(result)
            yield ''
        if self.failure:
            raise self.failure
    def close(self):
        self.closed = True

def candidate(text=None, finish=None):
    c = {'content': {'parts': [{'text': text}] if text else []}}
    if finish: c['finishReason'] = finish
    return {'candidates': [c]}

class StreamTests(unittest.TestCase):
    def setUp(self):
        self.client = module.app.test_client()
        self.key = patch.object(module, 'GEMINI_API_KEY', 'test-secret')
        self.key.start()
    def tearDown(self): self.key.stop()
    def test_validation(self):
        for body in [None, [], {}, {'prompt': 12}, {'prompt': ' '}, {'prompt': 'a'*12001}]:
            self.assertEqual(self.client.post('/generate/stream', json=body).status_code, 400)
    def test_key_missing(self):
        with patch.object(module, 'GEMINI_API_KEY', None):
            self.assertEqual(self.client.post('/generate/stream', json={'prompt':'Once'}).status_code, 503)
    def test_incremental_success(self):
        upstream = Upstream([candidate('Hello '), candidate('🌙 world', 'STOP')])
        with patch.object(module.requests, 'post', return_value=upstream) as post:
            r=self.client.post('/generate/stream', json={'prompt':'Once'}, buffered=False)
            frames=iter(r.response)
            self.assertIn(b'event: start', next(frames))
            self.assertIn(b'Hello ', next(frames))
            self.assertFalse(upstream.closed)
            rest=b''.join(frames).decode()
            self.assertIn('🌙 world',rest)
            self.assertIn('event: done',rest)
            self.assertTrue(upstream.closed)
            self.assertTrue(post.call_args.kwargs['stream'])
            self.assertIn('streamGenerateContent?alt=sse',post.call_args.args[0])
            self.assertNotIn('test-secret',rest)
    def test_timeout_before_headers(self):
        with patch.object(module.requests, 'post', side_effect=requests.Timeout):
            self.assertEqual(self.client.post('/generate/stream',json={'prompt':'Once'}).status_code,504)
    def test_provider_http_error(self):
        upstream=Upstream();upstream.ok=False;upstream.status_code=429
        with patch.object(module.requests, 'post', return_value=upstream):
            r=self.client.post('/generate/stream',json={'prompt':'Once'})
            self.assertEqual(r.status_code,503)
            self.assertTrue(upstream.closed)
    def test_mid_stream_error_preserves_partial(self):
        upstream=Upstream([candidate('Partial')],requests.ConnectionError('secret'))
        with patch.object(module.requests, 'post',return_value=upstream):
            text=self.client.post('/generate/stream',json={'prompt':'Once'}).data.decode()
            self.assertIn('Partial',text);self.assertIn('event: error',text)
            self.assertNotIn('secret',text);self.assertNotIn('event: done',text)
            self.assertTrue(upstream.closed)
    def test_empty_blocked_incomplete(self):
        for results in [[],[{'promptFeedback':{'blockReason':'SAFETY'}}],[candidate('partial')],[candidate('unsafe','SAFETY')]]:
            with patch.object(module.requests,'post',return_value=Upstream(results)):
                text=self.client.post('/generate/stream',json={'prompt':'Once'}).data.decode()
                self.assertIn('event: error',text);self.assertNotIn('event: done',text)
    def test_length_limit(self):
        with patch.object(module.requests,'post',return_value=Upstream([candidate('story','MAX_TOKENS')])):
            text=self.client.post('/generate/stream',json={'prompt':'Once'}).data.decode()
            self.assertIn('"truncated": true',text)
    def test_disconnect_closes_upstream(self):
        upstream=Upstream([candidate('first'),candidate('second','STOP')])
        with patch.object(module.requests,'post',return_value=upstream):
            r=self.client.post('/generate/stream',json={'prompt':'Once'},buffered=False)
            next(iter(r.response));r.close()
            self.assertTrue(upstream.closed)
    def test_cors(self):
        r=self.client.options('/generate/stream',headers={'Origin':'https://ishita-singh-12.github.io','Access-Control-Request-Method':'POST'})
        self.assertEqual(r.headers['Access-Control-Allow-Origin'],'https://ishita-singh-12.github.io')

if __name__ == '__main__': unittest.main()

# StoryWeaver backend

Flask story continuation API using a server-side Gemini key.

## Run

Install `requirements.txt`, set `GEMINI_API_KEY`, then run `gunicorn --threads 4 --timeout 120 app:app`. `GEMINI_MODEL` defaults to `gemini-3.1-flash-lite`.

## Streaming

`POST /generate/stream` accepts `{"prompt":"Your story beginning"}` and returns server-sent events. `start` begins the response, `delta` carries new text, `done` confirms completion, and `error` reports an interrupted or blocked response. A `done` event with `truncated: true` means the output token limit was reached. Gemini sends text in chunks, which may contain several tokens. The server forwards chunks as they arrive, without simulating typing or storing stories.

The original `POST /generate` JSON endpoint remains available. Keys stay in environment variables, never in the frontend. Streaming requests use a 10-second connect timeout and a 30-second idle-read timeout. Client disconnection closes the upstream response when detected; cancellation does not guarantee the provider stops billing immediately.

Use a threaded worker and a timeout long enough for generation. Responses disable proxy buffering where supported. CORS permits the existing GitHub Pages origin.

## Tests

`python -m unittest -v` tests validation, incremental events, Unicode, provider errors, timeouts, blocked/empty output, completion, cancellation cleanup, and CORS without making paid API calls.

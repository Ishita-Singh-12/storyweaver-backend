from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import json
import os
import requests

app = Flask(__name__)
CORS(app, origins=["https://ishita-singh-12.github.io"])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


@app.route("/")
def home():
    return "Story Generator backend is running."


@app.route("/generate", methods=["POST"])
def generate_story():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object with a prompt is required"}), 400
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "Prompt is required"}), 400
    if not GEMINI_API_KEY:
        return jsonify({"error": "Story generation is not configured"}), 503

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    body = {
        "systemInstruction": {
            "parts": [{"text": "Continue the user's story. Keep its tone and characters, and return only the story continuation, without introductory commentary."}]
        },
        "contents": [{"parts": [{"text": prompt.strip()}]}],
        "generationConfig": {"maxOutputTokens": 1024},
    }
    try:
        response = requests.post(url, headers=headers, json=body, timeout=20)
    except requests.Timeout:
        return jsonify({"error": "Story generation timed out. Please try again."}), 504
    except requests.RequestException:
        app.logger.warning("Gemini connection failed")
        return jsonify({"error": "Could not reach the story generator. Please try again."}), 502
    if not response.ok:
        app.logger.warning("Gemini returned status %s", response.status_code)
        return jsonify({"error": "Story generation is temporarily unavailable. Please try again."}), 503
    try:
        result = response.json()
        parts = result["candidates"][0]["content"]["parts"]
        story = "\n".join(part["text"] for part in parts if part.get("text") and not part.get("thought")).strip()
        if not story:
            raise ValueError("Empty story")
    except (ValueError, KeyError, IndexError, TypeError):
        return jsonify({"error": "No story was returned. Please try a different prompt."}), 502
    return jsonify({"story": story})


def sse_event(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def provider_events(response):
    """Decode SSE frames, not TCP chunks. Gemini may split one frame across lines."""
    data_lines = []
    for line in response.iter_lines(chunk_size=1, decode_unicode=True):
        if not line:
            if data_lines:
                yield json.loads("\n".join(data_lines))
                data_lines = []
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        yield json.loads("\n".join(data_lines))


@app.route("/generate/stream", methods=["POST"])
def stream_story():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object with a prompt is required"}), 400
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "Prompt is required"}), 400
    if len(prompt) > 12000:
        return jsonify({"error": "Please keep your beginning under 12,000 characters."}), 400
    if not GEMINI_API_KEY:
        return jsonify({"error": "Story generation is not configured"}), 503
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:streamGenerateContent?alt=sse"
    body = {
        "systemInstruction": {"parts": [{"text": "Continue the user's story. Keep its tone and characters, and return only the story continuation, without introductory commentary."}]},
        "contents": [{"parts": [{"text": prompt.strip()}]}],
        "generationConfig": {"maxOutputTokens": 1024},
    }
    try:
        upstream = requests.post(url, headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}, json=body, stream=True, timeout=(10, 30))
    except requests.Timeout:
        return jsonify({"error": "Story generation timed out. Please try again."}), 504
    except requests.RequestException:
        return jsonify({"error": "Could not reach the story generator. Please try again."}), 502
    if not upstream.ok:
        app.logger.warning("Gemini streaming returned status %s", upstream.status_code)
        upstream.close()
        return jsonify({"error": "Story generation is temporarily unavailable. Please try again."}), 503
    upstream.encoding = "utf-8"

    @stream_with_context
    def events():
        has_text = False
        finish_reason = None
        try:
            yield sse_event("start", {})
            for result in provider_events(upstream):
                if result.get("error"):
                    raise ValueError("Provider stream error")
                candidates = result.get("candidates", [])
                if not candidates:
                    if result.get("promptFeedback", {}).get("blockReason"):
                        raise ValueError("Prompt blocked")
                    continue
                candidate = candidates[0]
                finish_reason = candidate.get("finishReason", finish_reason)
                for part in candidate.get("content", {}).get("parts", []):
                    text = part.get("text")
                    if text and not part.get("thought"):
                        has_text = True
                        yield sse_event("delta", {"text": text})
            if finish_reason not in ("STOP", "MAX_TOKENS"):
                raise ValueError("Incomplete or blocked stream")
            if not has_text:
                raise ValueError("Empty story")
            yield sse_event("done", {"truncated": finish_reason == "MAX_TOKENS"})
        except (requests.RequestException, ValueError, KeyError, TypeError):
            # Never forward provider errors: they can contain sensitive request details.
            yield sse_event("error", {"error": "The story stream stopped early. Please try again."})
        finally:
            upstream.close()

    return Response(events(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
    })

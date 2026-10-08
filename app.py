from flask import Flask, request, jsonify
from flask_cors import CORS
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

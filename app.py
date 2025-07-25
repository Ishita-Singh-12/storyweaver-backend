from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests

app = Flask(__name__)
CORS(app, origins = [
    "https://ishita-singh-12.github.io/storyweaver_frontend/"
])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

@app.route('/')
def home():
    return "Story Generator backend is running."

@app.route("/generate", methods=["GET", "POST"])
def generate_story():
    data = request.get_json()
    prompt = data.get("prompt")

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    url = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}
    body = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }

    response = requests.post(url, headers=headers, params=params, json=body)
    result = response.json()

    try:
        story = result["candidates"][0]["content"]["parts"][0]["text"]
        return jsonify({"story": story})
    except Exception:
        return jsonify({"error": "Failed to generate story", "raw": Exception}), 500

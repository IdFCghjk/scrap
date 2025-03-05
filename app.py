from flask import Flask, render_template, request, jsonify
import os
import cv2
import pytesseract
import requests
import re
import yt_dlp
import concurrent.futures

app = Flask(__name__)

def get_video_info(video_url):
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(video_url, download=False)
        return {"title": info.get("title", "Unknown"), "uploader": info.get("uploader", "Unknown")}

def download_video(video_url, output_path="video.mp4"):
    ydl_opts = {'format': 'worstvideo+bestaudio/best', 'outtmpl': output_path, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])
    return output_path

def extract_frames(video_path, interval=30):
    cap = cv2.VideoCapture(video_path)
    frames = []
    frame_count = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % interval == 0:
            frames.append(frame)
        frame_count += 1
    cap.release()
    return frames

def extract_text(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    text = pytesseract.image_to_string(gray).strip()
    return text if len(text) > 5 else None

def find_location(place):
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={place}&format=json"
        response = requests.get(url, headers={"User-Agent": "LocationFinder"})
        data = response.json()
        if data:
            return {"name": place, "address": data[0]["display_name"]}
    except:
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_video():
    data = request.get_json()
    video_url = data.get("video_url")
    if not video_url:
        return jsonify({"success": False, "error": "Invalid URL"}), 400

    video_info = get_video_info(video_url)
    video_path = download_video(video_url)

    frames = extract_frames(video_path)
    found_texts = set()

    for frame in frames:
        text = extract_text(frame)
        if text:
            found_texts.add(text)

    places = set(re.findall(r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)*", " ".join(found_texts)))

    with concurrent.futures.ThreadPoolExecutor() as executor:
        locations = list(filter(None, executor.map(find_location, places)))

    os.remove(video_path)

    return jsonify({
        "success": True,
        "title": video_info["title"],
        "uploader": video_info["uploader"],
        "locations": locations
    })

if __name__ == "__main__":
    app.run(debug=True)

import cv2
import pytesseract
import requests
import re
import os
import yt_dlp
import concurrent.futures
from flask import Flask, render_template, request, jsonify

# Configure Tesseract path (uncomment for your system)
# pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

app = Flask(__name__)

def get_video_info(video_url):
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return {
                "title": info.get("title", "Untitled TikTok"),
                "author": info.get("uploader", "Unknown Creator"),
                "duration": info.get("duration", 0)
            }
    except Exception as e:
        raise RuntimeError(f"Could not fetch video info: {str(e)}")

def download_video(video_url):
    try:
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio/best',
            'outtmpl': 'temp_video',
            'quiet': True,
            'retries': 3
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url)
            filename = ydl.prepare_filename(info)
            ydl.process_info(info)
        return filename
    except Exception as e:
        raise RuntimeError(f"Video download failed: {str(e)}")

def extract_frames(video_path):
    try:
        cap = cv2.VideoCapture(video_path)
        frames = []
        frame_interval = 15  # More frequent sampling for short videos
        max_frames = 50
        
        for _ in range(max_frames):
            ret, frame = cap.read()
            if not ret: break
            if _ % frame_interval == 0:
                frames.append(frame)
        cap.release()
        return frames
    except Exception as e:
        raise RuntimeError(f"Frame extraction failed: {str(e)}")

def extract_text(image):
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 3)
        text = pytesseract.image_to_string(gray, config='--psm 6 --oem 3').strip()
        return text if len(text) > 2 else None
    except Exception as e:
        print(f"OCR Error: {str(e)}")
        return None

def find_location(place):
    try:
        if not place or len(place) < 4: return None
            
        headers = {"User-Agent": "TikTokLocationFinder/1.0"}
        response = requests.get(
            f"https://nominatim.openstreetmap.org/search?q={place}&format=json",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            return data[0] if data else None
        return None
    except Exception as e:
        print(f"Geocoding error: {str(e)}")
        return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'success': False, 'error': 'Missing TikTok URL'})
            
        video_url = data['url']
        if not any(domain in video_url for domain in ['tiktok.com', 'vm.tiktok']):
            return jsonify({'success': False, 'error': 'Invalid TikTok URL'})

        video_info = get_video_info(video_url)
        video_path = download_video(video_url)
        frames = extract_frames(video_path)
        
        texts = set()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(extract_text, frames)
            for text in results:
                if text: texts.add(text)

        places = set()
        for text in texts:
            matches = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
            places.update(matches)

        locations = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(find_location, place) for place in places]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result: 
                    locations.append({
                        'name': result['display_name'].split(',')[0],
                        'address': result['display_name'],
                        'lat': result['lat'],
                        'lon': result['lon']
                    })

        return jsonify({
            'success': True,
            'video_info': video_info,
            'locations': locations
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
    finally:
        if 'video_path' in locals() and os.path.exists(video_path):
            os.remove(video_path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
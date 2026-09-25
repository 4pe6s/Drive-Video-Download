import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import requests
from flask import Flask, Response, jsonify, render_template, request

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
jobs = {}
lock = threading.Lock()


def emit(job, message, progress=None, done=False, error=False):
    event = {'message': message, 'progress': progress, 'done': done, 'error': error}
    job['events'].put(event)


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('أدخل رابط HTTP/HTTPS مباشرًا وصحيحًا.')
    # Only download from hosts explicitly permitted by the operator.
    allowed = {h.strip().lower() for h in os.environ.get('ALLOWED_MEDIA_HOSTS', '').split(',') if h.strip()}
    if not allowed or parsed.hostname.lower() not in allowed:
        raise ValueError('المضيف غير مسموح. أضف نطاق مصدر الوسائط المصرح به إلى ALLOWED_MEDIA_HOSTS.')
    return url


def download(url, path, job, start, end, label):
    emit(job, f'بدء تنزيل {label}...')
    # No browser cookies, authorization headers, or session-token extraction.
    with requests.get(url, stream=True, timeout=(15, 45), allow_redirects=False,
                      headers={'Accept-Encoding': 'identity'}) as response:
        if response.is_redirect:
            raise ValueError('الرابط يعيد توجيهًا؛ استخدم رابط الوسائط المباشر المصرح به.')
        response.raise_for_status()
        if response.status_code != 200 or response.headers.get('Content-Range'):
            raise ValueError('المصدر لم يقدم ملفًا كاملًا (HTTP 200).')
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' in content_type or 'application/json' in content_type:
            raise ValueError('الرابط أعاد صفحة أو بيانات JSON بدل ملف وسائط.')
        total = int(response.headers.get('Content-Length', '0') or 0)
        received = 0
        with open(path, 'wb') as output:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if chunk:
                    output.write(chunk)
                    received += len(chunk)
                    if total:
                        emit(job, f'{label}: {received / 1048576:.1f} / {total / 1048576:.1f} MB',
                             start + (end - start) * min(received / total, 1))
        if not received or (total and received != total):
            raise ValueError(f'تنزيل {label} غير مكتمل.')
        emit(job, f'اكتمل تنزيل {label} ({received / 1048576:.1f} MB)', end)


def worker(job, data):
    try:
        video_url = validate_url(data['video_url'].strip())
        audio_url = validate_url(data['audio_url'].strip())
        directory = Path(data['output_dir'].strip()).expanduser().resolve()
        if not directory.is_dir():
            raise ValueError('مجلد الإخراج غير موجود على الجهاز الذي يشغّل Flask.')
        name = data['filename'].strip()
        if not name or not re.fullmatch(r'[^<>:"/\\|?*\x00-\x1f.][^<>:"/\\|?*\x00-\x1f]*', name) or name.endswith((' ', '.')):
            raise ValueError('اسم الملف غير صالح.')
        if name.lower().endswith('.mp4'):
            name = name[:-4]
        output = directory / f'{name}.mp4'
        if output.exists():
            raise ValueError('يوجد ملف بنفس الاسم؛ اختر اسمًا آخر.')
        if not shutil.which('ffmpeg'):
            raise ValueError('FFmpeg غير موجود في PATH.')
        with tempfile.TemporaryDirectory(prefix='drive_media_') as temp:
            video = Path(temp) / 'video.bin'
            audio = Path(temp) / 'audio.bin'
            partial = Path(temp) / 'merged.mp4'
            download(video_url, video, job, 0, 40, 'الفيديو')
            download(audio_url, audio, job, 40, 80, 'الصوت')
            emit(job, 'جاري دمج المسارين بواسطة FFmpeg...', 85)
            cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                   '-i', str(video), '-i', str(audio), '-map', '0:v:0', '-map', '1:a:0',
                   '-c:v', 'copy', '-c:a', 'aac', '-movflags', '+faststart', str(partial)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
            if result.returncode or not partial.is_file() or not partial.stat().st_size:
                raise ValueError('فشل الدمج: ' + result.stderr[-1000:])
            # Exclusive creation prevents accidental overwrite of an existing output.
            with open(output, 'xb') as dest, open(partial, 'rb') as source:
                shutil.copyfileobj(source, dest)
            emit(job, f'تم الحفظ: {output}', 100, done=True)
    except Exception as exc:
        emit(job, str(exc), done=True, error=True)
    finally:
        job['finished'] = True


@app.get('/')
def index():
    return render_template('index.html')


@app.post('/api/jobs')
def create_job():
    data = request.get_json(silent=True) or {}
    required = ('video_url', 'audio_url', 'output_dir', 'filename')
    if any(not isinstance(data.get(k), str) or not data[k].strip() for k in required):
        return jsonify(error='جميع الحقول مطلوبة.'), 400
    job_id = uuid.uuid4().hex
    job = {'events': queue.Queue(), 'finished': False}
    with lock:
        jobs[job_id] = job
    threading.Thread(target=worker, args=(job, data), daemon=True).start()
    return jsonify(job_id=job_id), 202


@app.get('/api/jobs/<job_id>/events')
def events(job_id):
    with lock:
        job = jobs.get(job_id)
    if job is None:
        return jsonify(error='المهمة غير موجودة.'), 404

    def stream():
        while True:
            try:
                event = job['events'].get(timeout=15)
            except queue.Empty:
                if job['finished']:
                    break
                yield ': heartbeat\n\n'
                continue
            yield 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
            if event['done']:
                break
        with lock:
            jobs.pop(job_id, None)

    return Response(stream(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)

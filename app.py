import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import requests
import streamlit as st

st.set_page_config(page_title='دمج مسارات الفيديو والصوت', page_icon='🎬', layout='centered')
st.title('🎬 تنزيل ودمج الوسائط')
st.caption('لروابط الوسائط المباشرة المصرح بتنزيلها فقط. لا يستخرج التطبيق روابط Google Drive المقيدة أو يتجاوز إعدادات المشاركة.')

MAX_BYTES = 750 * 1024 * 1024


def validate_url(value):
    parsed = urlsplit(value)
    hosts = {x.strip().lower() for x in os.getenv('ALLOWED_MEDIA_HOSTS', '').split(',') if x.strip()}
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('أدخل رابط HTTPS مباشرًا وصحيحًا.')
    if not hosts or parsed.hostname.lower() not in hosts:
        raise ValueError('نطاق المصدر غير مسموح. اضبط ALLOWED_MEDIA_HOSTS في إعدادات Streamlit Secrets.')
    return value


def download(url, path, label, progress, log, start, end):
    log.info(f'جاري تنزيل {label}...')
    with requests.get(url, stream=True, timeout=(15, 60), allow_redirects=False,
                      headers={'Accept-Encoding': 'identity'}) as response:
        if response.status_code != 200 or response.headers.get('Content-Range'):
            raise ValueError(f'{label}: المصدر لم يقدم ملفًا كاملًا (HTTP 200).')
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' in content_type or 'application/json' in content_type:
            raise ValueError(f'{label}: الرابط أعاد صفحة ويب بدل الوسائط.')
        total = int(response.headers.get('Content-Length', '0') or 0)
        if total > MAX_BYTES:
            raise ValueError('حجم الملف أكبر من الحد المسموح في هذه النسخة (750 MB لكل مسار).')
        count = 0
        with open(path, 'wb') as target:
            for chunk in response.iter_content(chunk_size=512 * 1024):
                if chunk:
                    count += len(chunk)
                    if count > MAX_BYTES:
                        raise ValueError('تم تجاوز الحد المسموح للحجم (750 MB لكل مسار).')
                    target.write(chunk)
                    if total:
                        progress.progress(min(end, start + int((end - start) * count / total)), text=f'{label}: {count / 1048576:.1f} MB')
        if count == 0 or (total and count != total):
            raise ValueError(f'{label}: الملف فارغ أو غير مكتمل.')
    progress.progress(end, text=f'اكتمل تنزيل {label}')


with st.form('media'):
    video_url = st.text_input('رابط الفيديو المباشر', placeholder='https://media.example.com/video.mp4')
    audio_url = st.text_input('رابط الصوت المباشر', placeholder='https://media.example.com/audio.m4a')
    filename = st.text_input('اسم الملف النهائي', value='my_video')
    submitted = st.form_submit_button('بدء التنزيل والدمج', type='primary', use_container_width=True)

st.info('في Streamlit Cloud، الحفظ يكون مؤقتًا على الخادم؛ بعد اكتمال المعالجة استخدم زر تحميل الملف إلى جهازك. لا يمكن كتابة ملف مباشرة داخل مجلد ويندوز لديك.')

if submitted:
    progress = st.progress(0, text='جاري التحقق...')
    log = st.empty()
    try:
        video_url = validate_url(video_url.strip())
        audio_url = validate_url(audio_url.strip())
        name = filename.strip()
        if name.lower().endswith('.mp4'):
            name = name[:-4]
        if not name or not re.fullmatch(r'[^<>:"/\\|?*\x00-\x1f.][^<>:"/\\|?*\x00-\x1f]*', name) or name.endswith((' ', '.')):
            raise ValueError('اسم الملف غير صالح.')
        if not shutil.which('ffmpeg'):
            raise ValueError('FFmpeg غير مثبت. أضف ffmpeg إلى packages.txt ثم أعد نشر التطبيق.')
        with tempfile.TemporaryDirectory(prefix='media_') as folder:
            folder = Path(folder)
            video, audio, output = folder / 'video.bin', folder / 'audio.bin', folder / 'output.mp4'
            download(video_url, video, 'الفيديو', progress, log, 0, 40)
            download(audio_url, audio, 'الصوت', progress, log, 40, 80)
            progress.progress(85, text='جاري الدمج باستخدام FFmpeg...')
            result = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                                     '-i', str(video), '-i', str(audio), '-map', '0:v:0', '-map', '1:a:0',
                                     '-c:v', 'copy', '-c:a', 'aac', '-movflags', '+faststart', str(output)],
                                    capture_output=True, text=True, timeout=3600)
            if result.returncode != 0 or not output.exists() or not output.stat().st_size:
                raise ValueError('فشل الدمج: ' + result.stderr[-700:])
            if output.stat().st_size > MAX_BYTES:
                raise ValueError('الملف النهائي كبير جدًا للتقديم عبر هذه الاستضافة.')
            progress.progress(100, text='اكتمل الدمج')
            log.success('تم الدمج بنجاح. حمّل الملف الآن قبل إغلاق الصفحة.')
            st.download_button('⬇️ تحميل الفيديو النهائي', data=output.read_bytes(),
                               file_name=f'{name}.mp4', mime='video/mp4', use_container_width=True)
    except (ValueError, requests.RequestException, subprocess.TimeoutExpired, OSError) as exc:
        log.error(str(exc))

with st.expander('طريقة الاستخدام والقيود'):
    st.write('أدخل روابط HTTPS مباشرة لملفات وسائط يتيح لك مصدرها تنزيلها. التطبيق لا يزيل قيود Google Drive، ولا يستخدم ملفات تعريف الارتباط أو جلسة المتصفح. الروابط المنتهية أو التي تعيد مقاطع جزئية لن تعمل. قد تتوقف الملفات الكبيرة بسبب حدود موارد Streamlit Cloud.')

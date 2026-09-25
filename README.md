# Local Media Download & Merge

This application downloads **authorized direct media URLs** and merges separate video/audio tracks. It does not bypass Google Drive view-only restrictions, extract session credentials, or alter signed/ranged stream URLs.

## Windows setup
1. Install Python 3.11+ and select **Add Python to PATH**.
2. Install FFmpeg from https://ffmpeg.org/download.html (Windows build). Extract to e.g. `C:\ffmpeg`; ensure `C:\ffmpeg\bin\ffmpeg.exe` exists.
3. Open **Edit the system environment variables → Environment Variables → Path → Edit → New**, add `C:\ffmpeg\bin`, then reopen Command Prompt. Check `ffmpeg -version`.
4. In Command Prompt, navigate to the extracted project folder and allowlist the exact authorized media host(s), e.g. `set ALLOWED_MEDIA_HOSTS=media.example.com` (multiple hosts separated by commas). This setting applies to the current Command Prompt window.
5. Run `run.bat` in the same Command Prompt. Visit http://127.0.0.1:5000 if the browser does not open automatically.
6. Enter direct video/audio URLs from the allowed host(s), an **existing** output folder on the same computer, and a filename.

The application deliberately does not remove `range`, `ump`, or signed URL parameters; doing so can corrupt downloads or invalidate authorization. HTTP 206 responses are rejected rather than being represented as complete media. The video is stream-copied and audio is encoded as AAC for MP4 compatibility. Tailwind CDN requires an internet connection for styling; the Flask server itself is local.

Security: Keep the service bound to 127.0.0.1; use only trusted hosts and authorized files. This lightweight single-user application does not provide authentication or production-grade job management.

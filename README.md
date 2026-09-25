# Streamlit deployment
Upload app.py, requirements.txt, packages.txt, and .streamlit/config.toml to the root of your GitHub repository. In Streamlit Community Cloud choose the repository, branch main, and main file app.py. Set ALLOWED_MEDIA_HOSTS in the app's Advanced settings > Secrets, for example:

ALLOWED_MEDIA_HOSTS = "media.example.com"

Replace the example with the exact domain of your authorized direct media source. This application does not bypass Google Drive download restrictions. On Streamlit Cloud the output is downloaded through the browser, not saved to your local Windows path. Large media may exceed free hosting limits.

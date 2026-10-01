FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements-docker-lock.txt ./
RUN pip install --no-cache-dir -r requirements-docker-lock.txt
COPY gateway.py web_ui.py web_files.py usb_remote.py web.html ./
USER 10001:10001
ENTRYPOINT ["python", "gateway.py"]

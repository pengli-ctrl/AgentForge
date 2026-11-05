FROM python:3.10-slim
RUN pip install fastapi uvicorn
COPY app.py /app.py
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8010"]

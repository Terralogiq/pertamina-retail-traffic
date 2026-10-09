FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# ENTRYPOINT + CMD (not CMD alone): a Cloud Run `args` override replaces CMD only, so the Scheduler can send
# ["--mode", "sample"] without replacing the program.
ENTRYPOINT ["python", "main.py"]
CMD ["--mode", "newest"]

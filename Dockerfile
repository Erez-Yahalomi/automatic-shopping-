FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python", "weight_event_detector_annotated.py", "/app/data/50_gr.csv", "/app/data/500_gr.csv", "/app/data/1000_gr.csv", "--plot", "--output-directory", "/app/results"]

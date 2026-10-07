FROM python:3.13-slim

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

COPY llm_label.py /llm_label.py
COPY event_log.py /event_log.py
COPY predict.py /predict.py
RUN chmod +x /predict.py

ENTRYPOINT ["/predict.py"]

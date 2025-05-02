# Use a lightweight Python image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy your code
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install gunicorn too if not in your requirements.txt
RUN pip install gunicorn

ENV PORT=5000

CMD ["sh", "-c", "gunicorn -w 2 -k gevent -b 0.0.0.0:${PORT} app:app"]

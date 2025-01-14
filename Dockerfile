# Basbild
FROM python:3.9-slim

# Arbetskatalog
WORKDIR /app

# Kopiera nödvändiga filer
COPY requirements.txt requirements.txt
COPY . .

# Installera beroenden
RUN pip install --no-cache-dir -r requirements.txt

# Exponera porten Flask kör på
EXPOSE 5000

# Startkommandot
CMD ["python", "app.py"]

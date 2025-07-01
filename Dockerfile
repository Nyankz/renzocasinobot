# 1. Python базалық образын қолданамыз
FROM python:3.10-slim

# 2. Жұмыс директория орнатамыз
WORKDIR /app

# 3. Жобаны контейнерге көшіреміз
COPY . .

# 4. Кітапханаларды орнатамыз
RUN pip install --no-cache-dir -r requirements.txt

# 5. Ботты іске қосамыз
CMD ["python", "main.py"]

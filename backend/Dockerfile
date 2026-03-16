# 1. Use the version that matches your local environment
FROM python:3.14-slim

# 2. Set the working directory in the container
WORKDIR /app

# 3. Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 4. Install system dependencies
# gcc and libpq-dev are CRITICAL here because binary wheels for
# libraries like psycopg2 might not be available for 3.14 yet.
# These tools allow Docker to build them from source automatically.
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of the application code
COPY . .

# 7. Expose port 5000 for Flask
EXPOSE 5000

# 8. Run migrations and then start the server
CMD ["sh", "-c", "flask db upgrade && python wsgi.py"]
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for matplotlib and other packages
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY .env.example .

# Create directories for data persistence
RUN mkdir -p /app/data /app/charts

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Run bot with commands enabled
CMD ["python", "-m", "src.main", "--commands", "--interval", "15"]

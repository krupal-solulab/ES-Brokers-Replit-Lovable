# Use official Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Install system dependencies (build-essential may be required for some Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt to leverage Docker cache
COPY requirements.txt ./

# Install standard dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Install the package itself (resolves pyproject.toml dependencies like pypdf, python-docx, openpyxl)
RUN pip install --no-cache-dir .

# Expose port 4000
EXPOSE 4000

# Start the FastAPI application directly
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "4000", "--app-dir", "src"]

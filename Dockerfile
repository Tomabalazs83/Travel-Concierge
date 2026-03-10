# Use a slim Python 3.11 base image (lightweight, good for Railway)
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements first (better caching during builds)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Expose port (optional - Railway doesn't require it, but good practice)
EXPOSE 8000

# Run the bot
CMD ["python", "app.py"]

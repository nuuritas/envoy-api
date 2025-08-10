# Use an official lightweight Python image.
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Prevent python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE 1
# Ensure python output is sent straight to the terminal without buffering
ENV PYTHONUNBUFFERED 1

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container
COPY . .

# Expose the port the app runs on
EXPOSE 8080

# Command to run the application using uvicorn
# Gunicorn is often used as a process manager in production, but for Cloud Run's
# single-process model, Uvicorn is sufficient and simpler.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
# Start with Python 3.9 as our base image
# This provides us with a pre-configured Python environment
# We're using the slim variant to keep the image size small
FROM python:3.9-slim

# Set working directory in the container
# This is where our application code will live inside the container
# It's a best practice to use a dedicated directory rather than the root
WORKDIR /app

# Copy just the CSV file first, which changes less frequently
# This improves build caching - if the CSV doesn't change, this layer will be reused
COPY employee_data.csv .

# Copy our Python script to the working directory
# This is our application code that will be executed
COPY csv_tool.py .

# Set the default command to run when the container starts
# Using array syntax allows proper handling of arguments and quotes
# The Python interpreter will run our csv_tool.py script
CMD ["python", "csv_tool.py"]

# Note: We don't need to install dependencies because our script only uses Python's standard library
# (csv and statistics modules are built into Python)
# If we needed additional packages, we would add:
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt 
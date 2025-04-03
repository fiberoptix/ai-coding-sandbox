#!/bin/bash

# Start PostgreSQL
docker-entrypoint.sh postgres &

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to start up..."
until pg_isready -U postgres -h localhost; do
  echo "Waiting for PostgreSQL to become available..."
  sleep 2
done

echo "PostgreSQL is up and running."
echo "Starting web service..."

# Fix database connection in web service
sed -i 's/"host": "localhost"/"host": "127.0.0.1"/g' /app/web_service.py

# Start the web service
cd /app
python3 web_service.py 
#!/bin/bash

# Build the Docker image
echo "Building PostgreSQL Docker image..."
docker build -t spending-db .

# Run the container
echo "Starting PostgreSQL container..."
docker run --name spending-postgres -p 5432:5432 -d spending-db

# Wait for PostgreSQL to start
echo "Waiting for PostgreSQL to initialize..."
sleep 5

# Connect to PostgreSQL with interactive terminal
echo "Connecting to PostgreSQL..."
docker exec -it spending-postgres psql -U postgres -d spending_db

# Note: When you're done, you can stop and remove the container with:
# docker stop spending-postgres
# docker rm spending-postgres 
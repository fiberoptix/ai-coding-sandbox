#!/bin/bash

# Function to check if container exists
container_exists() {
  docker ps -a --format '{{.Names}}' | grep -q "^spending-postgres$"
}

# Function to check if container is running
container_running() {
  docker ps --format '{{.Names}}' | grep -q "^spending-postgres$"
}

# Check if the container already exists
if container_exists; then
  echo "Container spending-postgres already exists."
  
  # Check if it's running
  if container_running; then
    echo "Container is already running."
  else
    echo "Starting existing container..."
    docker start spending-postgres
  fi
else
  # Build the Docker image
  echo "Building PostgreSQL Docker image..."
  docker build -t spending-db .

  # Run the container
  echo "Starting PostgreSQL container..."
  docker run --name spending-postgres -p 5432:5432 -d spending-db
  
  echo "Waiting for PostgreSQL to initialize..."
  sleep 10  # Give more time for initialization
fi

# Connect to PostgreSQL with interactive terminal
echo "Connecting to PostgreSQL..."
echo "You should now be in the PostgreSQL client. Type your SQL commands directly."
echo "For example: SELECT * FROM transactions LIMIT 10;"
echo "To exit the PostgreSQL client, type: \q"
echo "-----------------------------------------------------------------"

# Use exec to replace the current process with the psql client
# This ensures the user stays in the psql client
exec docker exec -it spending-postgres psql -U postgres -d spending_db

# Note: When you're done, you can stop and remove the container with:
# docker stop spending-postgres
# docker rm spending-postgres 
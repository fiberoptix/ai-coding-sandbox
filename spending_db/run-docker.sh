#!/bin/bash

# This script manages the Docker container for the Transaction Tagger application

# Function to display help
show_help() {
    echo "Usage: ./run-docker.sh [command]"
    echo ""
    echo "Commands:"
    echo "  build       - Build the Docker image"
    echo "  start       - Start the Docker container"
    echo "  stop        - Stop the Docker container"
    echo "  restart     - Restart the Docker container"
    echo "  flush       - Clear the database and restart container (fresh import)"
    echo "  logs        - Show logs from the container"
    echo "  shell       - Open a shell inside the container"
    echo "  help        - Show this help message"
    echo ""
}

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose is not installed."
    echo "Please install Docker and docker-compose first."
    exit 1
fi

# Handle commands
case "$1" in
    build)
        echo "Building Docker image..."
        docker-compose build
        ;;
    start)
        echo "Starting Docker container..."
        docker-compose up -d
        echo "Application is starting at http://localhost:5001"
        ;;
    stop)
        echo "Stopping Docker container..."
        docker-compose down
        ;;
    restart)
        echo "Restarting Docker container..."
        docker-compose down
        docker-compose up -d
        echo "Application is restarting at http://localhost:5001"
        ;;
    flush)
        echo "Clearing database and restarting container..."
        echo "Stopping containers..."
        docker-compose down
        
        echo "Removing PostgreSQL data volume..."
        # Find the volume name for the PostgreSQL data
        POSTGRES_VOLUME=$(docker volume ls -q | grep spending_db_postgres_data | head -1)
        if [ -n "$POSTGRES_VOLUME" ]; then
            echo "Found PostgreSQL volume: $POSTGRES_VOLUME"
            docker volume rm $POSTGRES_VOLUME
        else
            echo "PostgreSQL volume not found. Creating fresh database."
        fi
        
        echo "Starting containers with fresh database..."
        docker-compose up -d
        echo "Application is starting with a fresh database at http://localhost:5001"
        echo "This will import transactions.csv from scratch."
        ;;
    logs)
        echo "Showing container logs..."
        docker-compose logs -f
        ;;
    shell)
        echo "Opening shell in container..."
        docker-compose exec transaction-tagger bash
        ;;
    help|*)
        show_help
        ;;
esac 
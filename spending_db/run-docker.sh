#!/bin/bash

# This script manages the Docker container for the Transaction Tagger application

# Function to increment build count
increment_build_count() {
    BUILD_INFO_DIR=".build_info"
    BUILD_COUNT_FILE="${BUILD_INFO_DIR}/build_count.txt"
    
    # Create directory if it doesn't exist
    mkdir -p "${BUILD_INFO_DIR}"
    
    # Initialize build count if file doesn't exist
    if [ ! -f "${BUILD_COUNT_FILE}" ]; then
        echo "1" > "${BUILD_COUNT_FILE}"
        export BUILD_NUMBER=1
        echo "Build count initialized to 1"
        return
    fi
    
    # Read current build count
    CURRENT_COUNT=$(cat "${BUILD_COUNT_FILE}")
    
    # Increment build count
    NEW_COUNT=$((CURRENT_COUNT + 1))
    
    # Save new build count
    echo "${NEW_COUNT}" > "${BUILD_COUNT_FILE}"
    export BUILD_NUMBER=$NEW_COUNT
    echo "Build count incremented to ${NEW_COUNT}"
}

# Function to display help
show_help() {
    echo "Usage: ./run-docker.sh [command]"
    echo ""
    echo "Commands:"
    echo "  build       - Build the Docker image"
    echo "  bb          - Stop, Build, and Start the Docker container"
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
        increment_build_count
        BUILD_NUMBER=$BUILD_NUMBER docker-compose build
        ;;
    bb)
        echo "Stopping, Building, and Starting Docker image..."
        docker-compose down
        increment_build_count
        BUILD_NUMBER=$BUILD_NUMBER docker-compose build
        BUILD_NUMBER=$BUILD_NUMBER docker-compose up -d
        echo "Application is starting at http://localhost:5001"
        ;;
    start)
        echo "Starting Docker container..."
        # Get current build number if exists
        if [ -f ".build_info/build_count.txt" ]; then
            export BUILD_NUMBER=$(cat ".build_info/build_count.txt")
        else
            export BUILD_NUMBER=1
        fi
        BUILD_NUMBER=$BUILD_NUMBER docker-compose up -d
        echo "Application is starting at http://localhost:5001"
        ;;
    stop)
        echo "Stopping Docker container..."
        docker-compose down
        ;;
    restart)
        echo "Restarting Docker container..."
        docker-compose down
        # Get current build number if exists
        if [ -f ".build_info/build_count.txt" ]; then
            export BUILD_NUMBER=$(cat ".build_info/build_count.txt")
        else
            export BUILD_NUMBER=1
        fi
        BUILD_NUMBER=$BUILD_NUMBER docker-compose up -d
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
        increment_build_count
        BUILD_NUMBER=$BUILD_NUMBER docker-compose up -d
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
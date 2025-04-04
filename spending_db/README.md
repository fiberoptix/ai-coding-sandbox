# Transaction Tagger

A web application for tagging financial transactions based on their descriptions.

## Project Overview

This application provides a web interface for:
- Viewing transactions from a PostgreSQL database
- Tagging transactions by their descriptions
- Filtering transactions (all, tagged, untagged)
- Searching for specific transactions
- Applying tags to multiple transactions at once

## Key Files

- `full-app.py` - The main Flask web application
- `migrate_tags.py` - Script for migrating the transaction_tags table structure
- `transactions.csv` - Source data for transactions
- `init.sql` - SQL initialization script for the database
- `Dockerfile` - Docker configuration for the application
- `docker-compose.yml` - Docker Compose configuration
- `run-docker.sh` - Script for managing Docker container

## Running with Docker

This application is designed to run in a Docker container, which includes both PostgreSQL and the Flask web application.

### Prerequisites

- Docker and docker-compose installed on your system

### Getting Started

1. Build the Docker image:
   ```
   ./run-docker.sh build
   ```

2. Start the Docker container:
   ```
   ./run-docker.sh start
   ```

3. Access the web application at http://localhost:5001

### Docker Commands

- `./run-docker.sh build` - Build the Docker image
- `./run-docker.sh start` - Start the Docker container
- `./run-docker.sh stop` - Stop the Docker container
- `./run-docker.sh restart` - Restart the Docker container
- `./run-docker.sh logs` - Show logs from the container
- `./run-docker.sh shell` - Open a shell inside the container

## Usage

- Use the search box to search for specific transaction descriptions
- Use the filter dropdown to view all, tagged, or untagged transactions
- Enter a tag for each transaction
- Use "Tag All" feature to tag multiple matching transactions at once

## Data Persistence

The application uses a Docker volume (`postgres_data`) to ensure your tagged data persists between container restarts.

## Features

- View all unique transactions grouped by description
- Add tags to categorize transactions
- Search functionality to filter transactions
- Statistics showing progress of tagging

## Setup Options

### Option 1: Run with Docker Compose (Recommended)

1. Make sure Docker and Docker Compose are installed
2. Build the images:
   ```
   cd spending_db
   docker-compose build
   ```
3. Start the services:
   ```
   docker-compose up -d
   ```
4. Navigate to http://localhost:5001 in your browser
5. To restart just the web service after code changes:
   ```
   docker-compose restart webservice
   ```
   Or to rebuild and restart:
   ```
   docker-compose build webservice
   docker-compose up -d --no-deps webservice
   ```

### Option 2: Run with a Python virtual environment

1. Make sure you have a running PostgreSQL instance with the database set up
2. Run the web service using the script:
   ```
   cd spending_db
   chmod +x run-web.sh
   ./run-web.sh
   ```
3. Navigate to http://localhost:5000 in your browser

## Management Script

For convenience, you can use the management script:

```
./manage-services.sh start      # Start all services
./manage-services.sh stop       # Stop all services
./manage-services.sh restart-web # Restart only the web service
./manage-services.sh logs       # View logs
./manage-services.sh status     # Check status
./manage-services.sh rebuild-web # Rebuild and restart web service
```

## Database Schema

The main tables are:

- `transactions`: Contains all financial transactions
- `transaction_tags`: Contains the user-defined tags for transactions

## Web Interface Usage

1. Browse the list of transactions
2. Use the search box to filter transactions
3. Enter a tag for each transaction
4. Click the "Save" button to save the tag
5. The statistics at the bottom show your progress 
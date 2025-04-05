#!/bin/bash
# Financial Analyst - Remote Deployment Script
# This script deploys the application to a remote Linux server

# Load configuration from config.env file
CONFIG_FILE="$(dirname "$0")/config.env"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
else
    echo "Error: Configuration file not found at $CONFIG_FILE"
    exit 1
fi

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to display steps
print_step() {
    echo -e "${YELLOW}[STEP]${NC} $1"
}

# Function to display success
print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Function to display errors
print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to display info
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Check if SSH key exists
if [ ! -f "$SSH_KEY_PATH" ]; then
    print_error "SSH key not found at $SSH_KEY_PATH"
    exit 1
fi

# Start deployment
print_step "Starting deployment to $REMOTE_HOST..."

# 1. Create a temporary directory for files to transfer
print_step "Preparing files for deployment..."
TEMP_DIR=$(mktemp -d)
mkdir -p "$TEMP_DIR/financial_analyst"

# 2. Copy necessary files to temp directory
cp -r ../full-app.py ../requirements.txt ../init.sql ../Dockerfile ../docker-compose.yml ../templates "$TEMP_DIR/financial_analyst/"
cp ../run-docker.sh "$TEMP_DIR/financial_analyst/"
mkdir -p "$TEMP_DIR/financial_analyst/.build_info"
cp -r ../.build_info/build_count.txt "$TEMP_DIR/financial_analyst/.build_info/"

print_success "Files prepared for deployment"

# 3. Create remote directories if they don't exist
print_step "Setting up remote directories..."
ssh -i "$SSH_KEY_PATH" -p "$REMOTE_PORT" "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_DIR/templates && mkdir -p $REMOTE_DIR/.build_info"

if [ $? -ne 0 ]; then
    print_error "Failed to create remote directories. Check your SSH connection and permissions."
    rm -rf "$TEMP_DIR"
    exit 1
fi

# 4. Transfer files to remote server
print_step "Transferring files to remote server..."
scp -i "$SSH_KEY_PATH" -P "$REMOTE_PORT" -r "$TEMP_DIR/financial_analyst/"* "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/"
scp -i "$SSH_KEY_PATH" -P "$REMOTE_PORT" -r "$TEMP_DIR/financial_analyst/.build_info/build_count.txt" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/.build_info/"

if [ $? -ne 0 ]; then
    print_error "Failed to transfer files. Check your SSH connection and permissions."
    rm -rf "$TEMP_DIR"
    exit 1
fi

print_success "Files transferred to remote server"

# 5. Clean up temporary directory
rm -rf "$TEMP_DIR"

# 6. Make run-docker.sh executable on remote server
print_step "Setting permissions on remote server..."
ssh -i "$SSH_KEY_PATH" -p "$REMOTE_PORT" "$REMOTE_USER@$REMOTE_HOST" "chmod +x $REMOTE_DIR/run-docker.sh"

if [ $? -ne 0 ]; then
    print_error "Failed to set permissions. Check your SSH connection and permissions."
    exit 1
fi

# 7. Stop, rebuild and start the application on the remote server
print_step "Rebuilding and starting the application on remote server..."
ssh -i "$SSH_KEY_PATH" -p "$REMOTE_PORT" "$REMOTE_USER@$REMOTE_HOST" "cd $REMOTE_DIR && ./run-docker.sh bb"

if [ $? -ne 0 ]; then
    print_error "Failed to rebuild and start the application. Check the remote server logs."
    exit 1
fi

print_success "Application deployed and started on remote server!"
print_info "You can access the application at: http://$REMOTE_HOST:$APP_PORT"

exit 0 
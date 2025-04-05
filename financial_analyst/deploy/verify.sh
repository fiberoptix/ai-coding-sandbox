#!/bin/bash
# Financial Analyst - Remote Deployment Verification Script
# This script verifies that the application is running correctly on the remote server

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

echo -e "${BLUE}[INFO]${NC} Verifying deployment on $REMOTE_HOST..."

# Check if the application is running
echo -e "${YELLOW}[CHECK]${NC} Testing if application is accessible..."
ssh -i "$SSH_KEY_PATH" -p "$REMOTE_PORT" "$REMOTE_USER@$REMOTE_HOST" "curl -s -o /dev/null -w '%{http_code}' http://localhost:$APP_PORT/" > /tmp/status_code.txt
STATUS_CODE=$(cat /tmp/status_code.txt)

if [ "$STATUS_CODE" = "200" ] || [ "$STATUS_CODE" = "302" ]; then
    echo -e "${GREEN}[SUCCESS]${NC} Application is accessible (Status code: $STATUS_CODE)"
else
    echo -e "${RED}[ERROR]${NC} Application is not accessible (Status code: $STATUS_CODE)"
    exit 1
fi

# Get build number
echo -e "${YELLOW}[CHECK]${NC} Getting build number..."
BUILD_NUMBER=$(ssh -i "$SSH_KEY_PATH" -p "$REMOTE_PORT" "$REMOTE_USER@$REMOTE_HOST" "cat $REMOTE_DIR/.build_info/build_count.txt 2>/dev/null || echo 'unknown'")
echo -e "${GREEN}[INFO]${NC} Build number: $BUILD_NUMBER"

# Run basic QA checks
echo -e "${YELLOW}[CHECK]${NC} Running basic QA checks..."

# Check all major pages
for PAGE in "/" "/data_import_tagging" "/monthly_summary" "/transaction_summary" "/historical_analysis" "/budgets"; do
    STATUS=$(ssh -i "$SSH_KEY_PATH" -p "$REMOTE_PORT" "$REMOTE_USER@$REMOTE_HOST" "curl -s -o /dev/null -w '%{http_code}' http://localhost:$APP_PORT$PAGE")
    if [ "$STATUS" = "200" ] || [ "$STATUS" = "302" ]; then
        echo -e "${GREEN}[SUCCESS]${NC} Page $PAGE is accessible"
    else
        echo -e "${RED}[ERROR]${NC} Page $PAGE returned status $STATUS"
    fi
done

# Check Docker container status
echo -e "${YELLOW}[CHECK]${NC} Checking Docker container status..."
CONTAINER_STATUS=$(ssh -i "$SSH_KEY_PATH" -p "$REMOTE_PORT" "$REMOTE_USER@$REMOTE_HOST" "docker ps -f name=financial_analyst --format '{{.Status}}'")

if [ -n "$CONTAINER_STATUS" ]; then
    echo -e "${GREEN}[SUCCESS]${NC} Docker container is running: $CONTAINER_STATUS"
else
    echo -e "${RED}[ERROR]${NC} Docker container is not running"
fi

echo -e "${BLUE}[INFO]${NC} Verification complete!"
echo -e "${BLUE}[INFO]${NC} Application URL: http://$REMOTE_HOST:$APP_PORT"
exit 0 
# Remote Deployment Scripts

This directory contains scripts to help you deploy the Financial Analyst application to a remote Linux server.

## Files

- `config.env` - Configuration settings for your remote server
- `deploy.sh` - Main deployment script
- `verify.sh` - Script to verify the deployment is working correctly

## Setup Instructions

1. Edit the `config.env` file with your server information:
   ```
   REMOTE_USER="your_username"     # Your SSH username
   REMOTE_HOST="your_server_ip"    # IP address or hostname
   REMOTE_PORT="22"                # SSH port (usually 22)
   REMOTE_DIR="/path/on/server"    # Where to deploy the application
   SSH_KEY_PATH="$HOME/.ssh/id_rsa" # Path to your SSH key
   APP_PORT="5002"                 # Port the application uses
   ```

2. Make the scripts executable:
   ```bash
   chmod +x deploy.sh verify.sh
   ```

## Usage

### Deploying to the Remote Server

To deploy the application to your remote server:

```bash
./deploy.sh
```

This will:
1. Package up the necessary files
2. Copy them to your remote server
3. Stop any running containers
4. Build a new Docker image
5. Start the application

### Verifying the Deployment

After deploying, you can verify that everything is working correctly:

```bash
./verify.sh
```

This will:
1. Check if the application is accessible
2. Verify the build number
3. Test all major pages
4. Check the Docker container status

## Requirements

- SSH access to your remote server
- SSH key authentication set up (recommended)
- Docker and Docker Compose installed on the remote server
- `curl` installed on both local and remote machines

## Troubleshooting

If you encounter issues:

1. Check your SSH connection manually:
   ```bash
   ssh -i $SSH_KEY_PATH -p $REMOTE_PORT $REMOTE_USER@$REMOTE_HOST
   ```

2. Verify Docker is running on the remote server:
   ```bash
   docker ps
   ```

3. Check the application logs:
   ```bash
   docker logs financial_analyst
   ``` 
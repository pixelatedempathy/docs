# NeMo Data Designer Remote Server Deployment

This guide covers deploying NeMo Data Designer on a remote server for use with
the Pixelated Empathy platform.

## Prerequisites

### On Your Local Machine

- SSH access to the remote server
- SSH key configured (or password authentication enabled)
- `.env` file with `NVIDIA_API_KEY` set

### On Remote Server (212.2.244.60)

- Docker installed
- Docker Compose installed
- At least 8GB RAM
- At least 20GB free disk space
- Internet connectivity for downloading images

## Quick Deployment

### Option 1: Automated Deployment Script

Run the deployment script from your local machine:

```bash text
./scripts/deploy/deploy-nemo-data-designer-remote.sh

```

The script will:

1. Test SSH connection to the remote server
1. Verify Docker and Docker Compose are installed
1. Copy deployment scripts to the remote server
1. Download and set up NeMo Microservices
1. Start the Data Designer service

### Option 2: Manual Deployment

1. **SSH into the remote server:**

```bash text

   ssh vivi@212.2.244.60

   ```

1. **Install Docker (if not installed):**

   ```bash

   curl -fsSL <https://get.docker.com> -o get-docker.sh
   sh get-docker.sh

   ```

1. **Install Docker Compose (if not installed):**

   ```bash

   # For Docker Compose V2 (recommended)
   sudo apt-get update
   sudo apt-get install docker-compose-plugin

   # Or for Docker Compose V1
   sudo curl -L "<https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname> -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose

``` text


1. **Download NeMo Microservices Quickstart:**


   ```bash

   mkdir -p ~/nemo-microservices
   cd ~/nemo-microservices

   # Download from NGC (requires NGC account)
   # Visit: <https://catalog.ngc.nvidia.com/orgs/nvidia/teams/nemo/resources/nemo-microservices-quickstart>
   # Or use the deployment script which handles this automatically

``` text


1. **Set environment variables:**


   ```bash

   export NEMO_MICROSERVICES_IMAGE_REGISTRY="nvcr.io/nvidia/nemo-microservices"
   export NEMO_MICROSERVICES_IMAGE_TAG="25.10"
   export NIM_API_KEY="your-nvidia-api-key-here"

``` text


1. **Authenticate with NGC:**


   ```bash

   echo $NIM_API_KEY | docker login nvcr.io -u '$oauthtoken' --password-stdin

``` text


1. **Start the service:**


   ```bash

   cd nemo-microservices-quickstart_v25.10
   docker compose --profile data-designer up -d

   ```

## Configuration

### Update Local .env File

After deployment, update your local `.env` file:

```env text

NEMO_DATA_DESIGNER_BASE_URL=<http://212.2.244.60:8080>

```

### Firewall Configuration

Ensure the port is open on the remote server:

```bash

## For UFW (Ubuntu)
sudo ufw allow 8080/tcp

## For firewalld (CentOS/RHEL)
sudo firewall-cmd --add-port=8080/tcp --permanent
sudo firewall-cmd --reload

```

## Verification

### Check Service Status

```bash

ssh vivi@212.2.244.60 'cd ~/nemo-microservices/nemo-microservices-quickstart_* && docker compose ps'

```

### Test Health Endpoint

```bash

curl <http://212.2.244.60:8080/health>

```

### View Logs

```bash

ssh vivi@212.2.244.60 'cd ~/nemo-microservices/nemo-microservices-quickstart_* && docker compose logs -f'

```

## Management Commands

### Start Service

```bash

ssh vivi@212.2.244.60 'cd ~/nemo-microservices/nemo-microservices-quickstart_* && docker compose --profile data-designer
up -d'

```

### Stop Service

```bash

ssh vivi@212.2.244.60 'cd ~/nemo-microservices/nemo-microservices-quickstart_* && docker compose --profile data-designer
down'

```

### Restart Service

```bash

ssh vivi@212.2.244.60 'cd ~/nemo-microservices/nemo-microservices-quickstart_* && docker compose --profile data-designer
restart'

```

### View Logs (2)

```bash

ssh vivi@212.2.244.60 'cd ~/nemo-microservices/nemo-microservices-quickstart_* && docker compose logs -f'

```

### Update Service

```bash

ssh vivi@212.2.244.60 'cd ~/nemo-microservices/nemo-microservices-quickstart_* && docker compose --profile data-designer
pull && docker compose --profile data-designer up -d'

```

## Troubleshooting

### Service Not Starting

1. **Check Docker logs:**

   ```bash

   ssh vivi@212.2.244.60 'cd ~/nemo-microservices/nemo-microservices-quickstart_* && docker compose logs'

``` text


1. **Check system resources:**


```bash text

   ssh vivi@212.2.244.60 'free -h && df -h'

   ```

1. **Verify Docker is running:**

```bash text

   ssh vivi@212.2.244.60 'sudo systemctl status docker'

   ```

### Cannot Connect to Service

1. **Check if port is listening:**

```bash text

   ssh vivi@212.2.244.60 'netstat -tlnp | grep 8080'

``` text


1. **Check firewall rules:**


```bash text

   ssh vivi@212.2.244.60 'sudo ufw status'

   ```

1. **Test from server itself:**

   ```bash

   ssh vivi@212.2.244.60 'curl <http://localhost:8080/health'>

   ```

### Authentication Errors

1. **Verify API key is correct:**

```bash text

   ssh vivi@212.2.244.60 'echo $NIM_API_KEY'

``` text


1. **Re-authenticate with NGC:**


   ```bash

   ssh vivi@212.2.244.60 'echo $NIM_API_KEY | docker login nvcr.io -u '\''$oauthtoken'\'' --password-stdin'

   ```

### Image Pull Errors

If you get errors pulling images:

1. **Check NGC authentication:**

   ```bash

   ssh vivi@212.2.244.60 'docker login nvcr.io'

   ```

1. **Verify API key has access:**
   - Visit <https://catalog.ngc.nvidia.com>
   - Ensure your API key has access to NeMo Microservices

## Security Considerations

1. **Use SSH keys instead of passwords**
1. **Restrict firewall access** to only necessary IPs
1. **Use HTTPS** if exposing publicly (set up reverse proxy)
1. **Keep API keys secure** - never commit them to git
1. **Regular updates** - keep Docker images updated

## Next Steps

After successful deployment:

1. Update your local `.env` file with the remote URL
1. Test the connection:

   ```bash

   uv run python ai/data_designer/test_setup.py

``` text


1. Run example scripts:


   ```bash

   uv run python ai/data_designer/examples.py

   ```

## Resources

- [Official NeMo Data Designer Documentation](https://docs.nvidia.com/nemo/microservices/latest/design-synthetic-data-from-scratch-or-seeds/index.html)
- [Deployment Guide](https://docs.nvidia.com/nemo/microservices/latest/set-up/deploy-as-microservices/data-designer/parent-chart.html)
- [NGC Catalog](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/nemo/resources/nemo-microservices-quickstart)

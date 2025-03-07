# KleinanzeigenScraper: Nginx Integration Guide

## Current Architecture

The current architecture consists of:

1. **Node.js Server (server.js)**:
   - Serves a web interface on port 3030
   - Provides API endpoints for viewing listings
   - Triggers Python scraping scripts via `child_process.spawn()`
   - Runs scheduled scraping jobs

2. **Python Scripts (main.py, scraper.py)**:
   - Handle the actual scraping and processing
   - Store results in JSON files in the data directory

3. **Systemd Service**:
   - Runs the Node.js server as a background service

## Recommended Architecture with Nginx

### Option 1: Reverse Proxy (Simplest Approach)

This approach keeps your current application structure but puts Nginx in front of it.

```
Client → Nginx → Node.js Server → Python Scripts
```

#### Steps:

1. **Keep your current Node.js server running on port 3030**

2. **Create an Nginx site configuration**:

```nginx
server {
    listen 80;
    server_name kleinanzeigen.yourdomain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name kleinanzeigen.yourdomain.com;

    # SSL configuration
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Proxy all requests to the Node.js server
    location / {
        proxy_pass http://localhost:3030;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

3. **Restart Nginx**:
```bash
sudo systemctl restart nginx
```

### Option 2: Separate Frontend and API (More Scalable)

This approach separates the frontend (static files) from the backend (API).

```
Client → Nginx → Static Files (Frontend)
       ↘ Node.js API Server → Python Scripts
```

#### Steps:

1. **Modify your Node.js server to be API-only**:
   - Remove the static file serving
   - Keep only the API endpoints and Python script execution

2. **Extract the frontend to static files**:
   - Create a `public` directory in your Nginx webroot
   - Move HTML, CSS, and client-side JS there

3. **Create an Nginx site configuration**:

```nginx
server {
    listen 80;
    server_name kleinanzeigen.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name kleinanzeigen.yourdomain.com;

    # SSL configuration
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Serve static frontend files
    root /home/flo/docker-projects/nginx/webroot/kleinanzeigen;
    index index.html;

    # API requests - proxy to Node.js
    location /api/ {
        proxy_pass http://localhost:3030;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Serve static files directly
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

4. **Update your frontend code to use the API endpoints**:
   - Change API URLs from relative paths to `/api/`

## Implementation Plan

### 1. For Option 1 (Reverse Proxy - Simplest)

1. **Create Nginx configuration**:
   ```bash
   sudo nano /home/flo/docker-projects/nginx/sites-available/kleinanzeigen.conf
   ```
   
   Add the configuration from Option 1 above.

2. **Enable the site**:
   ```bash
   cd /home/flo/docker-projects/nginx/sites-enabled
   ln -s ../sites-available/kleinanzeigen.conf .
   ```

3. **Restart Nginx**:
   ```bash
   cd /home/flo/docker-projects/nginx
   docker-compose restart
   ```

### 2. For Option 2 (Separate Frontend and API - More Scalable)

1. **Create a directory for the frontend**:
   ```bash
   mkdir -p /home/flo/docker-projects/nginx/webroot/kleinanzeigen
   ```

2. **Extract the frontend**:
   - Copy the HTML, CSS, and client-side JS from your current application
   - Update API URLs to use `/api/` prefix

3. **Modify server.js to be API-only**:
   - Remove static file serving
   - Add API prefix to routes
   - Keep Python script execution

4. **Create Nginx configuration**:
   ```bash
   sudo nano /home/flo/docker-projects/nginx/sites-available/kleinanzeigen.conf
   ```
   
   Add the configuration from Option 2 above.

5. **Enable the site and restart Nginx** (same as Option 1)

## Security Considerations

1. **API Security**:
   - Consider adding authentication to your API endpoints
   - Use HTTPS for all connections

2. **Python Script Execution**:
   - Ensure the Python scripts run with appropriate permissions
   - Validate any user input before passing to Python scripts

3. **Rate Limiting**:
   - Add rate limiting to prevent abuse:
   ```nginx
   # Add to your Nginx configuration
   limit_req_zone $binary_remote_addr zone=api:10m rate=5r/s;
   
   location /api/ {
       limit_req zone=api burst=10 nodelay;
       # ... rest of proxy configuration
   }
   ```

## Monitoring and Maintenance

1. **Logging**:
   - Configure Nginx to log access and errors
   - Ensure Node.js and Python logs are captured

2. **Backup**:
   - Regularly backup your data directory
   - Consider using a version control system for your code

3. **Updates**:
   - Keep Node.js, Python, and their dependencies updated
   - Regularly update Nginx and your SSL certificates 
#!/bin/bash

# Setup script for nginx configuration for productivity.oneemcure.ai
# Run this script on your EC2 instance

echo "Setting up nginx for productivity.oneemcure.ai..."

# Update system packages
sudo apt update

# Install nginx if not already installed
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx..."
    sudo apt install nginx -y
fi

# Create the nginx configuration file
echo "Creating nginx configuration..."
sudo tee /etc/nginx/sites-available/productivity.oneemcure.ai > /dev/null << 'EOF'
server {
    listen 80;
    server_name productivity.oneemcure.ai;

    # Log files
    access_log /var/log/nginx/productivity.oneemcure.ai.access.log;
    error_log /var/log/nginx/productivity.oneemcure.ai.error.log;

    # Main application proxy
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Handle WebSocket connections if needed
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeout settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }

    # Handle static files directly for better performance
    location /static/ {
        alias /home/ubuntu/OneEmcureProductivityApp/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        
        # Enable gzip for static files
        gzip on;
        gzip_vary on;
        gzip_min_length 1024;
        gzip_types
            text/plain
            text/css
            text/xml
            text/javascript
            application/javascript
            application/xml+rss
            application/json;
    }

    # Handle uploads directory
    location /uploads/ {
        alias /home/ubuntu/OneEmcureProductivityApp/uploads/;
        expires 1h;
        add_header Cache-Control "public";
    }

    # Handle flowcharts directory
    location /flowcharts/ {
        alias /home/ubuntu/OneEmcureProductivityApp/flowcharts/;
        expires 1h;
        add_header Cache-Control "public";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;

    # Client max body size for file uploads
    client_max_body_size 100M;

    # Enable gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied expired no-cache no-store private must-revalidate auth;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/javascript
        application/xml+rss
        application/json
        application/pdf
        image/svg+xml;
}
EOF

# Enable the site
echo "Enabling the site..."
sudo ln -sf /etc/nginx/sites-available/productivity.oneemcure.ai /etc/nginx/sites-enabled/

# Remove default nginx site if it exists
if [ -f /etc/nginx/sites-enabled/default ]; then
    echo "Removing default nginx site..."
    sudo rm /etc/nginx/sites-enabled/default
fi

# Test nginx configuration
echo "Testing nginx configuration..."
sudo nginx -t

if [ $? -eq 0 ]; then
    echo "Nginx configuration is valid. Restarting nginx..."
    sudo systemctl restart nginx
    sudo systemctl enable nginx
    
    echo "Nginx setup complete!"
    echo "Your Flask app should now be accessible at http://productivity.oneemcure.ai"
    echo ""
    echo "Make sure your Flask app is running on port 5000:"
    echo "cd /home/ubuntu/OneEmcureProductivityApp"
    echo "python3 app.py"
    echo ""
    echo "To check nginx status: sudo systemctl status nginx"
    echo "To check nginx logs: sudo tail -f /var/log/nginx/productivity.oneemcure.ai.error.log"
else
    echo "Nginx configuration test failed. Please check the configuration."
    exit 1
fi



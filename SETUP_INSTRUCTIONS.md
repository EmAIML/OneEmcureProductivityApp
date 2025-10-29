# Domain Setup Instructions for Flask App

## Current Issue
Your domain is showing the default Nginx welcome page instead of your Flask application running on port 5000.

## Solution Steps

### 1. Replace the default Nginx configuration

**On your EC2 instance, run these commands:**

```bash
# Backup the current default configuration
sudo cp /etc/nginx/sites-available/default /etc/nginx/sites-available/default.backup

# Replace with your domain configuration
sudo nano /etc/nginx/sites-available/default
```

**Replace the entire content with the configuration from `nginx_config_current.conf`:**

```nginx
server {
    listen 80;
    server_name productivity.oneemcure.ai www.productivity.oneemcure.ai;
    
    # Proxy settings
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeout settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # File upload size limit
    client_max_body_size 100M;
    
    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml+rss
        application/atom+xml
        image/svg+xml;
}
```

### 2. Test and reload Nginx

```bash
# Test the configuration
sudo nginx -t

# If test passes, reload Nginx
sudo systemctl reload nginx

# Check Nginx status
sudo systemctl status nginx
```

### 3. Ensure your Flask app is running

```bash
# Make sure your Flask app is running on port 5000
cd /path/to/your/app
python3 app.py
```

### 4. Test your domain

Visit `http://productivity.oneemcure.ai` - it should now show your Flask application instead of the Nginx welcome page.

## Optional: Set up HTTPS with Let's Encrypt

Once the HTTP version is working, you can set up HTTPS. See the detailed instructions in `SSL_UPGRADE_INSTRUCTIONS.md` file.

**Quick SSL setup:**
```bash
# Install Certbot
sudo apt update
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d productivity.oneemcure.ai -d www.productivity.oneemcure.ai

# Test auto-renewal
sudo certbot renew --dry-run
```

**Note:** The SSL-ready configuration is already prepared in `nginx_config.conf` for when you're ready to upgrade.

## Troubleshooting

1. **If you get "502 Bad Gateway":**
   - Check if your Flask app is running: `ps aux | grep python`
   - Check if port 5000 is listening: `netstat -tlnp | grep 5000`

2. **If domain still shows Nginx welcome:**
   - Check Nginx configuration: `sudo nginx -t`
   - Check which sites are enabled: `ls -la /etc/nginx/sites-enabled/`
   - Make sure your domain configuration is active

3. **If you get permission errors:**
   - Make sure your Flask app is running as a user that can bind to port 5000
   - Check firewall settings: `sudo ufw status`

## Security Considerations

- The current setup uses HTTP only. For production, set up HTTPS.
- Consider running your Flask app as a service using systemd.
- Set up proper logging and monitoring.

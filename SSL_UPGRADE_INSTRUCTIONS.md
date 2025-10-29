# SSL Certificate Upgrade Instructions

## Current Setup
Your domain `productivity.oneemcure.ai` is currently configured for HTTP only. When you're ready to add SSL, follow these steps:

## Step 1: Get SSL Certificate with Let's Encrypt

```bash
# Install Certbot
sudo apt update
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate for your domain
sudo certbot --nginx -d productivity.oneemcure.ai -d www.productivity.oneemcure.ai

# Test auto-renewal
sudo certbot renew --dry-run
```

## Step 2: Verify SSL Configuration

After running the certbot command, it will automatically update your Nginx configuration. You can verify it by:

```bash
# Test Nginx configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx

# Check SSL certificate
sudo certbot certificates
```

## Step 3: Test HTTPS Access

Visit `https://productivity.oneemcure.ai` to ensure SSL is working properly.

## Manual SSL Configuration (if needed)

If you prefer to manually configure SSL, replace your current Nginx configuration with the content from `nginx_config.conf` (which includes SSL settings).

## Automatic Renewal Setup

Let's Encrypt certificates expire every 90 days. Set up automatic renewal:

```bash
# Add to crontab for automatic renewal
sudo crontab -e

# Add this line to run renewal check twice daily
0 12 * * * /usr/bin/certbot renew --quiet
```

## Troubleshooting SSL Issues

1. **Certificate not working:**
   - Check if port 443 is open: `sudo ufw status`
   - Verify DNS is pointing to your server: `nslookup productivity.oneemcure.ai`

2. **Mixed content warnings:**
   - Ensure your Flask app uses HTTPS URLs in templates
   - Update any hardcoded HTTP links

3. **Certificate renewal fails:**
   - Check certbot logs: `sudo journalctl -u certbot`
   - Ensure Nginx is running: `sudo systemctl status nginx`

## Security Headers (Already Included)

The SSL configuration includes these security headers:
- `Strict-Transport-Security` - Forces HTTPS
- `X-Frame-Options` - Prevents clickjacking
- `X-Content-Type-Options` - Prevents MIME sniffing
- `X-XSS-Protection` - XSS protection

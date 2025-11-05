# Deployment Guide for OneEmcure Productivity App

## Overview
This guide will help you deploy your Flask application with nginx on your EC2 instance so it's accessible via your domain `productivity.oneemcure.ai`.

## Prerequisites
- EC2 instance running Ubuntu
- Domain `productivity.oneemcure.ai` pointing to your EC2 public IP
- Flask application files in `/home/ubuntu/OneEmcureProductivityApp/`

## Step 1: Upload Files to EC2
Upload these files to your EC2 instance:
- `productivity.oneemcure.ai.conf` (nginx configuration)
- `setup_nginx.sh` (setup script)
- `productivity-app.service` (systemd service file)

## Step 2: Run the Setup Script
```bash
# Make the script executable
chmod +x setup_nginx.sh

# Run the setup script
./setup_nginx.sh
```

## Step 3: Set Up Flask App as a Service
```bash
# Copy the service file to systemd directory
sudo cp productivity-app.service /etc/systemd/system/

# Reload systemd and enable the service
sudo systemctl daemon-reload
sudo systemctl enable productivity-app.service
sudo systemctl start productivity-app.service

# Check if the service is running
sudo systemctl status productivity-app.service
```

## Step 4: Verify Everything is Working
1. Check nginx status: `sudo systemctl status nginx`
2. Check Flask app status: `sudo systemctl status productivity-app.service`
3. Test nginx configuration: `sudo nginx -t`
4. Visit your domain: `http://productivity.oneemcure.ai`

## Troubleshooting

### If nginx shows "Welcome to nginx" instead of your app:
1. Check if your Flask app is running: `sudo systemctl status productivity-app.service`
2. Check nginx configuration: `sudo nginx -t`
3. Check nginx logs: `sudo tail -f /var/log/nginx/productivity.oneemcure.ai.error.log`
4. Restart nginx: `sudo systemctl restart nginx`

### If Flask app is not starting:
1. Check the service logs: `sudo journalctl -u productivity-app.service -f`
2. Make sure all dependencies are installed in your virtual environment
3. Check if port 5000 is available: `sudo netstat -tlnp | grep :5000`

### If domain is not resolving:
1. Verify DNS settings in GoDaddy
2. Check if A record points to correct IP
3. Wait for DNS propagation (up to 24 hours, but usually within 1 hour)
4. Test with: `nslookup productivity.oneemcure.ai`

## File Structure After Setup
```
/home/ubuntu/OneEmcureProductivityApp/
├── app.py
├── modules/
├── templates/
├── static/
├── uploads/
├── flowcharts/
└── venv/ (if using virtual environment)

/etc/nginx/sites-available/productivity.oneemcure.ai
/etc/nginx/sites-enabled/productivity.oneemcure.ai -> /etc/nginx/sites-available/productivity.oneemcure.ai
/etc/systemd/system/productivity-app.service
```

## Security Considerations
- Consider setting up SSL/TLS with Let's Encrypt for HTTPS
- Configure firewall rules to only allow necessary ports
- Regularly update your system packages
- Monitor logs for any suspicious activity

## Monitoring
- Nginx access logs: `/var/log/nginx/productivity.oneemcure.ai.access.log`
- Nginx error logs: `/var/log/nginx/productivity.oneemcure.ai.error.log`
- Flask app logs: `sudo journalctl -u productivity-app.service -f`



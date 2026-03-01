# SSL Certificates

## Development

For development, SSL is not required. The HTTP server will work fine.

## Production

For production, you need SSL certificates. Here are your options:

### Option 1: Let's Encrypt (Recommended - FREE)

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Certificates will be saved to:
# /etc/letsencrypt/live/your-domain.com/fullchain.pem
# /etc/letsencrypt/live/your-domain.com/privkey.pem

# Copy to project
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ./nginx/ssl/cert.pem
cp /etc/letsencrypt/live/your-domain.com/privkey.pem ./nginx/ssl/key.pem

# Auto-renewal (certbot does this automatically)
sudo certbot renew --dry-run
```

### Option 2: Self-Signed (Development/Testing Only)

```bash
# Generate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ./nginx/ssl/key.pem \
  -out ./nginx/ssl/cert.pem \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
```

⚠️ **Warning**: Self-signed certificates will show security warnings in browsers.

### Option 3: Commercial Certificate

Purchase from providers like:
- Namecheap
- GoDaddy
- DigiCert
- Comodo

Then place files here:
- `./nginx/ssl/cert.pem` - Certificate
- `./nginx/ssl/key.pem` - Private key

## Enable HTTPS

1. Uncomment HTTPS server block in `nginx.conf`
2. Update `server_name` with your domain
3. Ensure certificates are in place
4. Restart nginx: `docker-compose restart nginx`

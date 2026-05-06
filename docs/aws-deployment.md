# Interview Lens — AWS Deployment Guide

### Stack: Django + Gunicorn + Celery + Redis + PostgreSQL (RDS) + Nginx + Auth0

> This guide covers self-hosted deployment on AWS EC2. For the managed Render deployment see the main [README](../README.md).

---

## Navigation Overview

| Phase | What You'll Do |
|-------|---------------|
| **Phase 1** | AWS account setup + billing protection |
| **Phase 2** | Launch & configure EC2 |
| **Phase 3** | Launch RDS PostgreSQL |
| **Phase 4** | Configure security groups (firewall rules) |
| **Phase 5** | SSH into EC2 — install everything |
| **Phase 6** | Deploy your Django backend |
| **Phase 7** | Set up systemd services (Gunicorn + Celery) |
| **Phase 8** | Configure Nginx + HTTPS |
| **Phase 9** | Point your domain (Route53 + ACM) |
| **Phase 10** | Connect Vercel frontend to your API |
| **Phase 11** | Test everything end-to-end |

---

## Phase 1 — AWS Account Setup & Billing Protection

> Do this FIRST before touching anything else. AWS charges real money if you're not careful.

### 1.1 — Create your AWS account
Go to https://aws.amazon.com → click "Create an AWS Account" → use a new email, add a credit card (required even for free tier), choose the **Free** support plan.

### 1.2 — Set up billing alerts (CRITICAL — do this now)

1. In AWS Console, click your name (top right) → **Billing and Cost Management**
2. Left sidebar → **Budgets** → **Create budget**
3. Choose **Monthly cost budget** → set amount to **$5**
4. Add your email for alerts at **80%** and **100%**
5. Click Create

Then enable **Free Tier alerts**:
1. Left sidebar → **Billing preferences**
2. Check ✅ **Receive Free Tier Usage Alerts**
3. Enter your email → Save

### 1.3 — Choose your region
In the top-right dropdown, select **us-east-1 (N. Virginia)** — it has the most free tier coverage and cheapest prices. Stick to this region for everything.

---

## Phase 2 — Launch Your EC2 Instance

> EC2 is the virtual server that will run Django, Celery, and Redis all together.

### 2.1 — Open EC2
AWS Console → search "EC2" → click **EC2** → click **Launch Instance** (orange button)

### 2.2 — Configure the instance

**Name:** `interview-lens-server`

**AMI (operating system):**
- Click **Ubuntu**
- Select **Ubuntu Server 22.04 LTS**
- Make sure it says "Free tier eligible" ✅

**Instance type:**
- Select **t2.micro**
- Check it says "Free tier eligible" ✅

**Key pair (for SSH access):**
- Click **Create new key pair**
- Name it: `interview-lens-key`
- Type: **RSA**
- Format: **.pem**
- Click **Create key pair** — it downloads a `.pem` file to your computer
- **SAVE THIS FILE SAFELY — you cannot download it again**

### 2.3 — Network settings
Click **Edit** on the Network settings section:

- VPC: leave as default
- Subnet: leave as default
- Auto-assign public IP: **Enable**
- Firewall: **Create security group**
- Name it: `interview-lens-ec2-sg`
- **Add these rules:**

| Type | Protocol | Port | Source | Why |
|------|----------|------|--------|-----|
| SSH | TCP | 22 | My IP | Only YOU can SSH in |
| HTTP | TCP | 80 | 0.0.0.0/0 | Public web traffic |
| HTTPS | TCP | 443 | 0.0.0.0/0 | Secure web traffic |

### 2.4 — Storage
- Set to **20 GB** (free tier gives you 30 GB total, we use 20 to be safe)
- Type: **gp2**

### 2.5 — Launch it
Click **Launch Instance** → wait 1-2 minutes → click **View Instances**

You'll see your instance with a green dot "Running". Note the **Public IPv4 address** — you'll need it.

### 2.6 — Assign an Elastic IP (IMPORTANT)
Without this, your server's IP changes every time it restarts, breaking your domain.

1. Left sidebar → **Elastic IPs** → **Allocate Elastic IP address** → **Allocate**
2. Select the new IP → **Actions** → **Associate Elastic IP address**
3. Choose your `interview-lens-server` instance → **Associate**

Your server now has a permanent IP address. Write it down.

---

## Phase 3 — Launch RDS PostgreSQL

> RDS is the managed database. It lives separately from your EC2 for safety and reliability.

### 3.1 — Open RDS
AWS Console → search "RDS" → click **RDS** → click **Create database**

### 3.2 — Configure the database

**Creation method:** Standard Create

**Engine:** PostgreSQL → Version: **PostgreSQL 15.x** (latest 15)

**Templates:** ✅ **Free tier** (this locks in the free settings automatically)

**Settings:**
- DB instance identifier: `interview-lens-db`
- Master username: `postgres`
- Master password: choose a strong password — **write it down**
- Confirm password

**Instance configuration:**
- DB instance class: **db.t3.micro** (auto-selected by free tier)

**Storage:**
- 20 GB gp2 (free tier gives 20 GB)
- ❌ Disable storage autoscaling (prevents surprise charges)

**Connectivity:**
- VPC: default VPC
- Public access: **No** ← CRITICAL — database must NOT be public
- VPC security group: **Create new** → name it `interview-lens-rds-sg`
- Availability Zone: No preference

**Additional configuration (expand this section):**
- Initial database name: `interviewerlens`
- ✅ Enable automated backups
- Backup retention: **7 days**
- ❌ Disable Enhanced monitoring (costs money)
- ❌ Disable Performance Insights (costs money)

Click **Create database** — takes 5-10 minutes to spin up.

### 3.3 — Get your RDS endpoint
Once status shows "Available":
- Click on your database → **Connectivity & security** tab
- Copy the **Endpoint** — looks like: `interview-lens-db.xxxxxxx.us-east-1.rds.amazonaws.com`
- Port: `5432`

---

## Phase 4 — Configure Security Groups (Firewall Rules)

> Security groups control who can talk to what. This is the most important security step.

### 4.1 — Fix the RDS security group
Right now RDS created a security group but it doesn't allow your EC2 in yet.

1. Go to **EC2** → left sidebar → **Security Groups**
2. Find `interview-lens-rds-sg` → click it
3. Click **Inbound rules** tab → **Edit inbound rules**
4. **Delete** any existing rules
5. Click **Add rule**:
   - Type: **PostgreSQL**
   - Protocol: TCP
   - Port: 5432
   - Source: **Custom** → in the search box, type `interview-lens-ec2-sg` and select it
6. Click **Save rules**

This means: only your EC2 server (by its security group) can reach the database. No one else.

### 4.2 — Verify EC2 security group
1. Find `interview-lens-ec2-sg` → click it
2. Inbound rules should show:
   - Port 22 from **your IP only**
   - Port 80 from **0.0.0.0/0**
   - Port 443 from **0.0.0.0/0**

---

## Phase 5 — SSH Into EC2 and Install Everything

> Now we connect to the server and set it up from scratch.

### 5.1 — Connect via SSH (from your computer terminal)

**On Mac/Linux:**
```bash
# Fix permissions on your key file (required)
chmod 400 ~/Downloads/interview-lens-key.pem

# Connect to your server (replace YOUR_ELASTIC_IP with your actual IP)
ssh -i ~/Downloads/interview-lens-key.pem ubuntu@YOUR_ELASTIC_IP
```

**On Windows:** Use PuTTY or Windows Terminal with the .pem file.

You should see a welcome message from Ubuntu. You're inside your server now!

### 5.2 — Update the system
```bash
sudo apt update && sudo apt upgrade -y
```
This takes 2-3 minutes. Type `Y` if it asks about anything.

### 5.3 — Install Python, Nginx, Redis, Git
```bash
sudo apt install -y python3 python3-pip python3-venv git nginx redis-server postgresql-client curl

# Verify installations
python3 --version     # Should show Python 3.10.x
redis-server --version
nginx -v
```

### 5.4 — Configure Redis (secure it)
Redis should only listen on localhost — never the internet:
```bash
sudo nano /etc/redis/redis.conf
```
Find the line `bind 127.0.0.1 ::1` — make sure it's NOT commented out (no `#` in front).
Find `protected-mode yes` — make sure it says `yes`.

Press `Ctrl+X`, then `Y`, then `Enter` to save.

```bash
sudo systemctl restart redis-server
sudo systemctl enable redis-server

# Test it works
redis-cli ping   # Should respond: PONG
```

### 5.5 — Add a swap file (VERY IMPORTANT for 1 GB RAM)
Without swap, your server crashes when memory runs low:
```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make it permanent across reboots
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Verify
free -h   # Should show 1 GB swap
```

---

## Phase 6 — Deploy Your Django Backend

### 6.1 — Clone your repository
```bash
cd /home/ubuntu
git clone https://github.com/YOUR_GITHUB_USERNAME/Interview-Lens.git
cd Interview-Lens/backend
```

### 6.2 — Create Python virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pip install gunicorn   # in case it's not in requirements.txt
```

### 6.3 — Create your .env file
```bash
nano .env
```

Paste in all your environment variables:
```
# Django core
DJANGO_SECRET_KEY=your-very-long-random-secret-key-here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=YOUR_ELASTIC_IP,yourdomain.com,www.yourdomain.com

# Database — use your RDS endpoint
DATABASE_URL=postgresql://postgres:YOUR_RDS_PASSWORD@YOUR_RDS_ENDPOINT:5432/interviewerlens

# Redis — local on same machine
REDIS_URL=redis://127.0.0.1:6379/0

# CORS — your Vercel frontend URL
CORS_ALLOWED_ORIGINS=https://your-frontend.vercel.app

# Auth0
AUTH0_DOMAIN=YOUR-TENANT.region.auth0.com
AUTH0_API_AUDIENCE=https://your-api-audience
AUTH0_ISSUER=https://YOUR-TENANT.region.auth0.com/

# AI providers
AI_PROVIDER=anthropic
AI_MODEL=claude-sonnet-4-6
AI_DEFAULT_PROVIDER=anthropic
ANTHROPIC_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=your-anthropic-api-key
OPENAI_API_KEY=your-openai-api-key
AI_SELECTION_STRATEGY=auto
AI_PROVIDER_PRIORITY=anthropic,openai

# Rate limiting
DAILY_RATELIMIT=200
```

Press `Ctrl+X`, `Y`, `Enter` to save.

**Generate a proper Django secret key:**
```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
Copy the output and paste it as your `DJANGO_SECRET_KEY` value.

### 6.4 — Run migrations and collect static files
```bash
export $(cat .env | grep -v '^#' | xargs)

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check   # Should output "System check identified no issues"
```

### 6.5 — Test Gunicorn manually
```bash
gunicorn interviewerlens.wsgi --bind 0.0.0.0:8000
```
Open a browser and go to `http://YOUR_ELASTIC_IP:8000` — you should see your Django API.
Press `Ctrl+C` to stop it. We'll run it properly with systemd next.

---

## Phase 7 — Set Up systemd Services

> systemd keeps Gunicorn and Celery running 24/7 and auto-restarts them if they crash.

### 7.1 — Create the Gunicorn service file
```bash
sudo nano /etc/systemd/system/gunicorn.service
```

Paste this exactly:
```ini
[Unit]
Description=Interview Lens - Gunicorn Django Server
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/Interview-Lens/backend
EnvironmentFile=/home/ubuntu/Interview-Lens/backend/.env
ExecStart=/home/ubuntu/Interview-Lens/backend/.venv/bin/gunicorn \
    interviewerlens.wsgi \
    --workers 2 \
    --bind unix:/run/gunicorn.sock \
    --access-logfile - \
    --error-logfile -
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

### 7.2 — Create the Celery service file
```bash
sudo nano /etc/systemd/system/celery.service
```

Paste this exactly:
```ini
[Unit]
Description=Interview Lens - Celery Worker
After=network.target redis-server.service

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/Interview-Lens/backend
EnvironmentFile=/home/ubuntu/Interview-Lens/backend/.env
ExecStart=/home/ubuntu/Interview-Lens/backend/.venv/bin/celery \
    -A interviewerlens worker \
    --pool=solo \
    --concurrency=1 \
    --without-gossip \
    --without-mingle \
    --without-heartbeat \
    --prefetch-multiplier=1 \
    --loglevel=info
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

### 7.3 — Enable and start both services
```bash
sudo systemctl daemon-reload

sudo systemctl enable gunicorn celery
sudo systemctl start gunicorn celery

# Both should say "active (running)"
sudo systemctl status gunicorn
sudo systemctl status celery
```

If there's an error, check logs:
```bash
sudo journalctl -u gunicorn -n 50
sudo journalctl -u celery -n 50
```

---

## Phase 8 — Configure Nginx + HTTPS

> Nginx receives internet traffic and forwards it to Gunicorn. It also handles HTTPS.

### 8.1 — Create Nginx config
```bash
sudo nano /etc/nginx/sites-available/interview-lens
```

Paste this (replace `yourdomain.com` with your actual domain):
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com YOUR_ELASTIC_IP;

    # Uncomment after SSL is set up:
    # return 301 https://$host$request_uri;

    location / {
        proxy_pass http://unix:/run/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    location /static/ {
        alias /home/ubuntu/Interview-Lens/backend/staticfiles/;
    }
}
```

### 8.2 — Enable the site
```bash
sudo ln -s /etc/nginx/sites-available/interview-lens /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

sudo nginx -t   # Should say "syntax is ok" and "test is successful"
sudo systemctl restart nginx
sudo systemctl enable nginx
```

### 8.3 — Test it works
Open your browser and go to `http://YOUR_ELASTIC_IP` — you should see your Django API responding.

---

## Phase 9 — Domain Setup (Route53 + ACM + HTTPS)

### 9.1 — Request an SSL certificate with ACM
1. AWS Console → **Certificate Manager** → **Request a certificate** → **Request a public certificate** → Next
2. Add domain names: `yourdomain.com` and `*.yourdomain.com`
3. Validation method: **DNS validation**
4. Click **Request**

### 9.2 — Set up Route53
1. AWS Console → **Route53** → **Hosted zones** → **Create hosted zone**
2. Domain name: `yourdomain.com` → Type: **Public hosted zone** → Create
3. Copy the 4 NS (nameserver) values
4. Update nameservers at your domain registrar (Namecheap, GoDaddy, etc.) to the 4 Route53 values

### 9.3 — Add DNS records in Route53

**Root domain → EC2:**
- Type: **A** | Value: `YOUR_ELASTIC_IP` | TTL: 300

**www subdomain → EC2:**
- Record name: `www` | Type: **A** | Value: `YOUR_ELASTIC_IP` | TTL: 300

**ACM validation record:**
- In ACM → click your certificate → **Create records in Route53** (adds the CNAME automatically)

Wait 5–30 minutes for the certificate status to show "Issued".

### 9.4 — Enable HTTPS with Certbot
```bash
sudo apt install -y certbot python3-certbot-nginx

# Replace with your domain
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
# Select "Redirect HTTP to HTTPS" when prompted

# Test auto-renewal
sudo certbot renew --dry-run
```

### 9.5 — Final Nginx check
```bash
sudo nginx -t
sudo systemctl reload nginx
```

Now visit `https://yourdomain.com` — you should see your API with a valid SSL certificate.

---

## Phase 10 — Connect Vercel Frontend to Your API

### 10.1 — Update Django ALLOWED_HOSTS and CORS
```bash
nano /home/ubuntu/Interview-Lens/backend/.env
```

Update:
```
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CORS_ALLOWED_ORIGINS=https://your-frontend.vercel.app
```

```bash
sudo systemctl restart gunicorn
```

### 10.2 — Update Auth0 settings
In your Auth0 dashboard:
1. Go to your API → **Settings** → add `https://yourdomain.com` to **Allowed Origins**
2. Go to your Application → **Settings** → add your domain to **Allowed Callback URLs**, **Allowed Logout URLs**, **Allowed Web Origins**

### 10.3 — Update Vercel environment variables
In Vercel dashboard → your project → **Settings** → **Environment Variables**:
```
VITE_API_URL=https://yourdomain.com
```
Redeploy your Vercel frontend.

---

## Phase 11 — Test Everything End-to-End

```bash
# Check all services are running
sudo systemctl status gunicorn     # active (running) ✅
sudo systemctl status celery       # active (running) ✅
sudo systemctl status redis-server # active (running) ✅
sudo systemctl status nginx        # active (running) ✅

# Check Gunicorn socket exists
ls -la /run/gunicorn.sock

# Test database connection
cd /home/ubuntu/Interview-Lens/backend
source .venv/bin/activate
export $(cat .env | grep -v '^#' | xargs)
python manage.py dbshell   # Should open psql prompt — type \q to exit

# Test Redis
redis-cli ping   # PONG ✅

# Test Celery can reach Redis
celery -A interviewerlens inspect ping
```

**Browser tests:**
- `https://yourdomain.com/api/` — Django API responds ✅
- `https://yourdomain.com/admin/` — Django admin loads ✅
- Open your Vercel frontend → log in with Auth0 → submit a form → check Celery processes it ✅

---

## Useful Commands for Daily Use

```bash
# View live logs
sudo journalctl -u gunicorn -f
sudo journalctl -u celery -f
sudo journalctl -u nginx -f

# Deploy code changes
cd /home/ubuntu/Interview-Lens/backend
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt        # only if requirements changed
python manage.py migrate               # only if migrations exist
sudo systemctl restart gunicorn celery

# Check resource usage
free -h   # memory
df -h     # disk
```

---

## Troubleshooting Quick Reference

| Problem | Diagnose | Fix |
|---------|----------|-----|
| Site not loading | `sudo systemctl status nginx` | `sudo systemctl restart nginx` |
| 502 Bad Gateway | `sudo systemctl status gunicorn` | `sudo journalctl -u gunicorn -n 30` |
| Celery tasks not running | `sudo systemctl status celery` | `sudo journalctl -u celery -n 30` |
| Database connection error | `python manage.py dbshell` | Check `DATABASE_URL` in `.env` |
| Redis connection error | `redis-cli ping` | `sudo systemctl restart redis-server` |
| SSL cert expired | `sudo certbot certificates` | `sudo certbot renew` |
| Out of memory | `free -h` | `sudo systemctl restart gunicorn celery` |

---

*Estimated total setup time: 2–3 hours for first-time deployment*
*Monthly cost: ~$0.50 (Route53 only) for the first 12 months on AWS free tier*

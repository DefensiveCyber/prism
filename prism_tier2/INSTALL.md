# PRISM - Installation Guide (Tier 2 Production)

This guide covers three installation paths:
- **Path A** — Linux native (dedicated server, no venv)
- **Path B** — WSL2 on Windows (with venv)
- **Path C** — Systemd auto-start (Linux, runs on boot)

---

## Architecture

```
Browser → Gunicorn (web server)
               ↓
            Redis (task queue)
           ↙        ↘
  Celery priority   Celery classify
  worker (fast,     worker (bulk scans,
  UI requests)      24/7 file watching)
           ↓
       PostgreSQL
  (audit, queue, jobs)
           ↓
      Landing Zones
           ↑
    Watchdog Watcher
  (inotify/Win32 events)
```

---

## Prerequisites

| Component | Purpose |
|---|---|
| Python 3.10+ | Runtime |
| PostgreSQL 14+ | Audit log, review queue, job state |
| Redis 7+ | Celery task broker and result backend |
| pip packages | See requirements.txt |

---

## PATH A: Linux Native (No venv)

Use this on a dedicated server where PRISM is the only application.

### 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-pip postgresql postgresql-contrib redis-server
```

### 2. Extract PRISM

```bash
sudo mkdir -p /opt/prism
sudo tar -xzf prism_tier2.tar.gz -C /opt/prism --strip-components=1
cd /opt/prism
```

### 3. Install Python packages

```bash
pip3 install -r requirements.txt --break-system-packages
```

### 4. Create PostgreSQL database

```bash
sudo service postgresql start

sudo -u postgres psql << 'EOF'
CREATE USER prism WITH PASSWORD 'prism';
CREATE DATABASE prism OWNER prism;
GRANT ALL PRIVILEGES ON DATABASE prism TO prism;
\c prism
GRANT ALL ON SCHEMA public TO prism;
EOF
```

### 5. Configure environment

```bash
cp .env.example .env
nano .env
```

Set these values:
```
PRISM_REDIS_URL=redis://localhost:6379/0
PRISM_DB_URL=postgresql+psycopg2://prism:prism@localhost:5432/prism
```

### 6. Initialize database schema

```bash
export PYTHONPATH=/opt/prism
python3 -c "import db; db.init_db(); print('DB ready')"
```

### 7. Start everything

```bash
sudo service redis-server start
./start.sh
```

### 8. Open PRISM

```
http://localhost:5000
```

---

## PATH B: WSL2 on Windows (with venv)

Use this when running PRISM inside Windows Subsystem for Linux 2.

### 1. Install WSL2 (if not already installed)

Open PowerShell as Administrator:
```powershell
wsl --install
```
Reboot when prompted. Ubuntu is installed by default.

### 2. Open Ubuntu terminal and install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-full python3-venv python3-pip \
    postgresql postgresql-contrib redis-server
```

### 3. Place project files

**Important:** Keep PRISM in the WSL2 filesystem, not on a Windows drive.
Working from `/mnt/c/...` causes permission issues with venv.

```bash
# Copy from Windows desktop into WSL2 home directory
cp -r /mnt/c/Users/YourName/Desktop/prism_tier2 ~/prism
cd ~/prism
```

If you prefer to keep it on your Windows desktop, use the full `/mnt/c/...`
path everywhere but note that venv must be created in the WSL2 filesystem:

```bash
# Venv in WSL2 filesystem even if code is on Windows drive
python3 -m venv ~/prism_venv
source ~/prism_venv/bin/activate
pip install -r /mnt/c/Users/YourName/Desktop/LogClassifier/prism_tier2/requirements.txt
```

**The simpler approach** — copy to WSL2 home and work from there:
```bash
cd ~/prism
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Create PostgreSQL database

```bash
sudo service postgresql start

sudo -u postgres psql << 'EOF'
CREATE USER prism WITH PASSWORD 'prism';
CREATE DATABASE prism OWNER prism;
GRANT ALL PRIVILEGES ON DATABASE prism TO prism;
\c prism
GRANT ALL ON SCHEMA public TO prism;
EOF
```

### 5. Configure environment

```bash
cp .env.example .env
nano .env
```

Set these values:
```
PRISM_REDIS_URL=redis://localhost:6379/0
PRISM_DB_URL=postgresql+psycopg2://prism:prism@localhost:5432/prism
PYTHONPATH=/home/YourLinuxUser/prism
```

Replace `/home/YourLinuxUser/prism` with the actual path shown by `pwd`.

### 6. Initialize database schema

```bash
source venv/bin/activate
export PYTHONPATH=$(pwd)
python -c "import db; db.init_db(); print('DB ready')"
```

### 7. Start everything

```bash
source venv/bin/activate
./start_wsl2.sh
```

`start_wsl2.sh` automatically:
- Activates the venv
- Starts Redis and PostgreSQL via `service` if not already running
- Exports PYTHONPATH
- Starts both Celery workers in the background
- Starts the file watcher
- Starts Gunicorn

### 8. Open PRISM

```
http://localhost:5000
```

WSL2 forwards ports to Windows automatically — open this in your normal
Windows browser (Chrome, Edge, Firefox).

### 9. Accessing Windows files from PRISM

Your Windows drives are mounted at `/mnt/c/`, `/mnt/d/`, etc.
In the PRISM UI, use these paths for watched directories and bulk scans:

```
/mnt/c/Users/YourName/Documents/Logs
/mnt/d/LogCollection
```

### 10. Stopping PRISM

```bash
./stop.sh
```

### 11. Starting again after reboot

WSL2 does not auto-start services on Windows boot. Run this each time:

```bash
cd ~/prism
./start_wsl2.sh
```

Or add it to your `.bashrc` / `.profile` to run automatically when you open
a WSL2 terminal:

```bash
echo "cd ~/prism && ./start_wsl2.sh" >> ~/.bashrc
```

---

## PATH C: Systemd Auto-Start (Linux, runs on boot)

Use this on a dedicated Linux server after completing Path A.

### 1. Create the prism system user

```bash
sudo useradd -r -s /bin/false -d /opt/prism prism
sudo chown -R prism:prism /opt/prism
```

### 2. Create the venv as the prism user

```bash
sudo -u prism python3 -m venv /opt/prism/venv
sudo -u prism /opt/prism/venv/bin/pip install -r /opt/prism/requirements.txt
```

### 3. Move .env to a secure location

```bash
sudo cp /opt/prism/.env /etc/prism.env
sudo chmod 600 /etc/prism.env
sudo chown prism:prism /etc/prism.env
```

Update the `EnvironmentFile=` line in each service file to point to
`/etc/prism.env` instead of `/opt/prism/.env`.

### 4. Install systemd service files

```bash
sudo cp /opt/prism/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### 5. Enable and start all services

```bash
# Enable (auto-start on boot)
sudo systemctl enable prism-web
sudo systemctl enable prism-worker-priority
sudo systemctl enable prism-worker-classify
sudo systemctl enable prism-watcher

# Start now
sudo systemctl start prism-worker-priority
sudo systemctl start prism-worker-classify
sudo systemctl start prism-watcher
sudo systemctl start prism-web
```

### 6. Verify everything is running

```bash
sudo systemctl status prism-web
sudo systemctl status prism-worker-classify
sudo systemctl status prism-watcher
```

All should show `active (running)`.

### 7. View live logs

```bash
# Web server
sudo journalctl -u prism-web -f

# Classify worker (bulk scans)
sudo journalctl -u prism-worker-classify -f

# Or tail log files directly
tail -f /opt/prism/logs/celery_classify.log
tail -f /opt/prism/logs/gunicorn_error.log
```

---

## Troubleshooting

### "No module named 'classifier'"
Celery workers can't find PRISM's Python files.
```bash
# Make sure PYTHONPATH is set before starting workers
export PYTHONPATH=/path/to/prism
# This is already handled by start.sh and start_wsl2.sh
```

### "Password authentication failed for user prism"
Reset the DB password:
```bash
sudo -u postgres psql -c "ALTER USER prism WITH PASSWORD 'prism';"
```
And make sure `.env` has the matching password.

### "Cannot connect to Redis"
```bash
sudo service redis-server start
redis-cli ping   # should return PONG
```

### "Cannot connect to PostgreSQL"
```bash
sudo service postgresql start
sudo -u postgres psql -c "\l"   # list databases
```

### Workers not picking up tasks
Check that PYTHONPATH is set and both workers are running:
```bash
celery -A celery_app inspect active
celery -A celery_app inspect ping
```

### Port 5000 already in use
```bash
sudo lsof -i :5000        # find what's using it
# Or change the port in gunicorn.conf.py:
# bind = "0.0.0.0:5001"
```

---

## Monitoring

### Celery task dashboard (Flower)

```bash
# Install
pip3 install flower --break-system-packages   # Linux
pip install flower                             # WSL2 venv

# Run
celery -A celery_app flower --port=5555
# Open: http://localhost:5555
```

### Check job backlog in Redis

```bash
redis-cli llen classify    # files waiting to be classified
redis-cli llen priority    # single-file requests waiting
```

### Database row counts

```bash
psql -U prism -d prism -c "SELECT COUNT(*) FROM audit_log;"
psql -U prism -d prism -c "SELECT COUNT(*) FROM review_queue WHERE reviewed = false;"
psql -U prism -d prism -c "SELECT status, COUNT(*) FROM scan_jobs GROUP BY status;"
```

---

## Backup

```bash
# Config (signatures, settings)
cp -r /opt/prism/config /backup/prism-config-$(date +%Y%m%d)

# Database
pg_dump -U prism prism | gzip > /backup/prism-db-$(date +%Y%m%d).sql.gz

# Restore database
gunzip -c /backup/prism-db-20240315.sql.gz | psql -U prism prism
```

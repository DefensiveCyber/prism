# PRISM
**Pattern Recognition & Intelligent Structure Mining**

A production log classification engine. PRISM ingests raw log files,
identifies their sourcetype using a signature engine, routes them into
landing zones for Cribl pickup, and provides AI-powered analysis via the
Lens module.

<img width="1916" height="1026" alt="image" src="https://github.com/user-attachments/assets/aa633db2-85e5-44b3-8317-20354d571072" />
<img width="1916" height="1026" alt="image" src="https://github.com/user-attachments/assets/4432814b-ad11-4877-afd2-e6b8c6cfe5e9" />
<img width="1917" height="1027" alt="image" src="https://github.com/user-attachments/assets/f40b8653-5552-4e1f-9c5e-f5cea51c62cb" />
<img width="1916" height="1024" alt="image" src="https://github.com/user-attachments/assets/f60de3e2-f592-425a-8798-18c54cc072cc" />
<img width="1913" height="1029" alt="image" src="https://github.com/user-attachments/assets/7b906edb-bc30-47fb-997a-d9f14b57ac7c" />
<img width="1914" height="1029" alt="image" src="https://github.com/user-attachments/assets/14370319-5f1c-4840-9d0f-942f01be2e2a" />
<img width="1911" height="1029" alt="image" src="https://github.com/user-attachments/assets/7263dbd1-85de-425f-ba03-9cb560d92e9f" />
<img width="683" height="482" alt="image" src="https://github.com/user-attachments/assets/7c6ea630-640c-4e55-8d97-a5e639dcd723" />
<img width="1917" height="1027" alt="image" src="https://github.com/user-attachments/assets/309f4aae-dab8-4945-b92d-aaebc81b2c6a" />


---

## Table of Contents
1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Services](#services)
6. [Starting & Stopping](#starting--stopping)
7. [File Structure](#file-structure)
8. [Signatures](#signatures)
9. [Classification Engine](#classification-engine)
10. [Lens AI Module](#lens-ai-module)
11. [API Reference](#api-reference)
12. [UI Pages](#ui-pages)
13. [Landing Zones](#landing-zones)
14. [Troubleshooting](#troubleshooting)

---

## Architecture

```
Browser
  └─→ Gunicorn (sync workers, :5000)
        └─→ Redis (Celery broker)
              ├─→ Celery priority worker  (single file classify)
              └─→ Celery classify worker  (bulk scans)

Watchdog watcher ─→ Redis ─→ Celery classify worker

PostgreSQL
  ├── audit_log       (every classification result)
  ├── review_queue    (files below confidence threshold)
  ├── scan_jobs       (bulk scan tracking)
  └── lens_sessions   (AI analysis history)

Ollama (local LLM server, :11434)
  └── mistral         (log summarization + chat)

LogWhisperer
  └── ~/prism/logwhisperer/   (AI log summarization tool)
```

---

## Prerequisites

### System Requirements
- **OS:** Ubuntu 22.04 / 24.04 (or WSL2 with Ubuntu-24.04)
- **RAM:** 8 GB minimum, 16 GB recommended (Mistral needs ~5 GB)
- **Disk:** 10 GB free (Mistral model ~4.1 GB)
- **CPU:** 4+ cores recommended

### Required Services
| Service | Version | Purpose |
|---|---|---|
| Python | 3.10+ | Runtime |
| PostgreSQL | 14+ | Audit log, review queue, scan jobs, Lens sessions |
| Redis | 6+ | Celery message broker + result backend |
| Ollama | latest | Local LLM server for Lens AI module |

### Required Python Packages
See `requirements.txt`. Key packages:

| Package | Purpose |
|---|---|
| `flask` | Web framework |
| `gunicorn` | Production WSGI server |
| `celery` | Distributed task queue |
| `redis` | Celery broker client |
| `psycopg2-binary` | PostgreSQL driver |
| `sqlalchemy` | ORM for audit log / queue |
| `pyyaml` | Signature + settings parsing |
| `watchdog` | File system event watcher |
| `python-evtx` | Windows `.evtx` binary log parser |
| `requests` | Ollama API client |
| `flower` | Celery task monitor (optional) |

---

## Installation

### 1. Clone / extract PRISM
```bash
cd ~
# Extract from archive:
tar -xzf prism_tier2.tar.gz
mv prism_tier2 prism
cd prism
```

### 2. Install Python dependencies
```bash
pip3 install -r requirements.txt --break-system-packages
```

### 3. Install and configure PostgreSQL
```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib

# Start PostgreSQL
sudo service postgresql start

# Create database and user
sudo -u postgres psql << 'SQL'
CREATE USER prism WITH PASSWORD 'prism';
CREATE DATABASE prism OWNER prism;
GRANT ALL PRIVILEGES ON DATABASE prism TO prism;
SQL
```

### 4. Install and start Redis
```bash
sudo apt install -y redis-server
sudo service redis-server start

# Verify
redis-cli ping   # should return PONG
```

### 5. Install Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 6. Pull Mistral model
```bash
ollama pull mistral
# Downloads ~4.1 GB — runs locally, no data leaves your machine
# Mistral is made by Mistral AI (Paris, France)
```

### 7. Clone LogWhisperer
```bash
cd ~/prism
git clone https://github.com/binary-knight/logwhisperer logwhisperer
pip3 install -r logwhisperer/requirements.txt --break-system-packages
```

### 8. Configure environment
```bash
cp .env.example .env   # if it exists, otherwise create:
cat > .env << 'ENV'
PRISM_REDIS_URL=redis://localhost:6379/0
PRISM_DB_URL=postgresql+psycopg2://prism:prism@localhost:5432/prism
PRISM_OLLAMA_URL=http://localhost:11434
PRISM_OLLAMA_MODEL=mistral
ENV
```

### 9. Initialize database schema
```bash
python3 -c "import db; db.init_db(); print('Schema ready')"
```

### 10. Start everything
```bash
./start.sh
```

---

## Configuration

### `.env`
| Variable | Default | Description |
|---|---|---|
| `PRISM_REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `PRISM_DB_URL` | `postgresql+psycopg2://prism:prism@localhost:5432/prism` | PostgreSQL DSN |
| `PRISM_OLLAMA_URL` | `http://localhost:11434` | Ollama API base URL |
| `PRISM_OLLAMA_MODEL` | `mistral` | LLM model for Lens AI |

| `PRISM_WSL_DISTRO` | `Ubuntu-24.04` | WSL2 distro name for folder open |

> **Note:** `PYTHONPATH` is set automatically by `start.sh` from its own location. Do not add it to `.env`.

### `config/settings.yaml`
| Setting | Default | Description |
|---|---|---|
| `review_queue_threshold` | `0.60` | Files below this confidence go to review queue |
| `high_confidence_threshold` | `0.85` | Threshold for "high confidence" display |
| `max_sample_lines` | `20` | Lines read from file for classification |
| `file_read_bytes` | `8192` | Bytes read from file for classification |
| `move_files` | `true` | Move files to landing zones (false = copy) |
| `watched_dirs` | `[]` | Directories auto-classified by watcher |
| `include_extensions` | `.log .txt .csv .json .xml .gz` | Extensions watcher processes |

### `gunicorn.conf.py`
| Setting | Value | Description |
|---|---|---|
| `bind` | `0.0.0.0:5000` | Listen address |
| `worker_class` | `sync` | Worker type (sync required for WSL2) |
| `workers` | `CPU*2+1` | Number of worker processes |
| `threads` | `4` | Threads per worker |
| `timeout` | `120s` | Request timeout |
| `max_requests` | `10000` | Worker recycle threshold |

---

## Services

PRISM runs 7 services. All are managed by `start.sh` / `stop.sh`.

### 1. Redis
- **Port:** 6379
- **Purpose:** Message broker for Celery task queue; result backend
- **Managed by:** `sudo service redis-server start/stop`
- **Logs:** `/var/log/redis/`

### 2. PostgreSQL
- **Port:** 5432
- **Database:** `prism`
- **Purpose:** Persists audit log, review queue, scan jobs, Lens AI sessions
- **Managed by:** `sudo service postgresql start/stop`
- **Tables:**
  - `audit_log` — every classified file with result + confidence
  - `review_queue` — files requiring manual review
  - `scan_jobs` — bulk scan tracking
  - `lens_sessions` — AI analysis sessions with full conversation history

### 3. Celery Priority Worker
- **Queue:** `priority`
- **Concurrency:** 4
- **Purpose:** Handles single-file classification requests from the web UI (fast path)
- **Logs:** `logs/celery_priority.log`
- **PID:** `logs/celery_priority.pid`

### 4. Celery Classify Worker
- **Queue:** `classify`
- **Concurrency:** 8
- **Purpose:** Handles bulk directory scans and watchdog-triggered files
- **Logs:** `logs/celery_classify.log`
- **PID:** `logs/celery_classify.pid`

### 5. Watchdog File Watcher
- **Purpose:** Monitors configured directories for new files; auto-classifies on arrival
- **Config:** Add directories via UI → Watched Dirs page, or edit `config/settings.yaml`
- **Logs:** `logs/watcher.log`
- **PID:** `logs/watcher.pid`

### 6. Gunicorn Web Server
- **Port:** 5000
- **Purpose:** Serves the PRISM web UI and REST API
- **Logs:** `logs/gunicorn_access.log`, `logs/gunicorn_error.log`
- **PID:** `logs/gunicorn.pid`

### 7. Ollama
- **Port:** 11434
- **Purpose:** Local LLM inference server for the Lens AI module
- **Model:** mistral (French-owned Mistral AI, runs 100% locally)
- **Logs:** `logs/ollama.log`
- **PID:** `logs/ollama.pid`

### 8. Flower (optional)
- **Port:** 5555
- **Purpose:** Celery task monitoring dashboard
- **URL:** http://localhost:5555
- **Logs:** `logs/flower.log`
- **Install:** `pip3 install flower --break-system-packages`

---

## Starting & Stopping

### Start all services
```bash
cd ~/prism
./start.sh
```

Startup order: Redis → PostgreSQL → Ollama → Mistral warm-up → Celery workers → Watcher → Gunicorn → Flower

### Stop PRISM services only
```bash
./stop.sh
```
Redis and PostgreSQL keep running. Safe for quick restarts.

### Full shutdown (stops everything + shuts down WSL2)
```bash
./stop.sh --shutdown
```
Stops all services including Redis and PostgreSQL, then runs `wsl --shutdown`.

### Restart Gunicorn only (after code/template changes)
```bash
sudo fuser -k 5000/tcp
gunicorn -c gunicorn.conf.py server:app >> logs/gunicorn_error.log 2>&1 &
echo $! > logs/gunicorn.pid
```

---

## File Structure

```
~/prism/
├── start.sh                  # Start all services
├── stop.sh                   # Stop all services (--shutdown for full teardown)
├── server.py                 # Flask application + all API endpoints
├── classifier.py             # Classification engine (signature matching)
├── tasks.py                  # Celery task definitions
├── celery_app.py             # Celery factory
├── db.py                     # PostgreSQL models + CRUD (SQLAlchemy)
├── router.py                 # Routes classified files to landing zones
├── watcher.py                # Watchdog file system watcher
├── lens.py                   # Lens AI module (LogWhisperer + Ollama)
├── audit.py                  # Audit log helpers
├── review_queue.py           # Review queue helpers
├── gunicorn.conf.py          # Gunicorn production configuration
├── requirements.txt          # Python package dependencies
├── .env                      # Environment variables (create from .env.example)
│
├── config/
│   ├── signatures.yaml       # 144 classification signatures
│   └── settings.yaml         # App settings, watched dirs, thresholds
│
├── parsers/
│   ├── csv_parser.py         # CSV log extraction
│   ├── evtx_parser.py        # Windows .evtx binary parser
│   └── elastic_parser.py     # Elasticsearch NDJSON unwrapper
│
├── templates/
│   └── index.html            # Full single-page UI
│
├── static/                   # Static assets (favicon, etc.)
│
├── logwhisperer/             # LogWhisperer AI log summarization tool
│   └── logwhisperer.py       # Entry point called by lens.py
│
├── logs/                     # Runtime logs (created on first start)
│   ├── gunicorn_access.log
│   ├── gunicorn_error.log
│   ├── celery_priority.log
│   ├── celery_classify.log
│   ├── watcher.log
│   ├── ollama.log
│   └── flower.log
│
├── landing/                  # Routed log files (created on first start)
│   ├── cisco_asa/
│   ├── WinEventLog_Security/
│   ├── pan_traffic/
│   ├── _review_queue/        # Files below confidence threshold
│   └── _unknown/             # Files with no signature match
│
└── state/                    # Watcher state persistence
```

---

## Signatures

PRISM ships with **144 signatures** across 15 categories.

| Category | Count | Examples |
|---|---|---|
| network | 34 | Palo Alto, Fortinet, Check Point, Juniper, F5, Zeek, SonicWall, Zscaler |
| security | 19 | Suricata, Snort, CrowdStrike, Okta, CyberArk, CEF, LEEF, Qualys |
| windows | 14 | Security, System, Application, Sysmon, PowerShell, Defender, EVTX |
| cloud | 12 | AWS CloudTrail, VPC Flow, Azure Audit, GCP Audit, CloudWatch |
| endpoint | 11 | CrowdStrike Falcon, SentinelOne, Carbon Black, osquery, Defender ATP |
| cisco | 9 | ASA/FTD, IOS, NX-OS, ISE, Meraki, Firepower, Umbrella |
| web | 9 | Apache, Nginx, IIS, HAProxy, Squid, Traefik, Tomcat |
| database | 8 | MSSQL, MySQL, PostgreSQL, Oracle, MongoDB, Redis, Elasticsearch |
| linux | 7 | secure, syslog, audit, auditd, cron, iptables, syslog-RFC |
| email | 6 | O365, Exchange, Proofpoint, Mimecast, Barracuda Spam |
| middleware | 6 | Kafka, RabbitMQ, ActiveMQ, ZooKeeper, IBM MQ, NATS |
| monitoring | 3 | Nagios, Prometheus, Icinga2 |
| storage | 3 | NetApp ONTAP, Dell EMC VNX, Rubrik |
| ot | 2 | Generic OT/ICS syslog, Claroty |
| unknown | 1 | Generic JSON fallback |

### Signature structure (`config/signatures.yaml`)
```yaml
- sourcetype: cisco:asa
  category: cisco
  vendor: Cisco
  product: ASA/FTD Firewall
  confidence: 0.97          # Base confidence (0.0–1.0)
  required_patterns:        # ALL must match — hard gate
    - '%ASA-\d+-\d+|%FTD-\d+-\d+'
  line_patterns:            # Optional boosters — each match raises confidence
    - 'Built (inbound|outbound)'
    - 'Teardown (TCP|UDP|ICMP)'
    - 'Deny (tcp|udp|icmp)'
  min_matches: 1            # Minimum optional patterns to proceed
```

### Confidence scoring
```
Required patterns all match  →  80% of base confidence
Each optional pattern match  →  contributes remaining 20% proportionally
Final score < 60%            →  file sent to Review Queue
Final score ≥ 60%            →  file routed to landing zone
```

### Managing signatures
- **View/edit:** UI → Signatures page → Edit Patterns
- **Add new:** UI → Signatures → + New Signature
- **Rebuild from scratch:** `python3 build_signatures.py`

---

## Classification Engine

**File:** `classifier.py`

### How it works
1. Reads up to `file_read_bytes` (8192) bytes from the file
2. Extracts text via format-specific parsers:
   - `.evtx` → `parsers/evtx_parser.py` (Windows Event Log binary)
   - `.csv` → `parsers/csv_parser.py`
   - Elasticsearch NDJSON → `parsers/elastic_parser.py`
   - All others → raw text read
3. Tests every signature's `required_patterns` against the text
4. Signatures that pass required patterns are scored using optional patterns
5. Highest scoring signature wins
6. Tiebreaker: first signature in file (position in `signatures.yaml`)
7. File is routed to `landing/<sourcetype>/` or `_review_queue/` if confidence < 0.60

### Supported input formats
| Format | Extension | Parser |
|---|---|---|
| Plain text logs | `.log`, `.txt` | Raw read |
| CSV exports | `.csv` | `csv_parser.py` |
| Windows Event Log | `.evtx` | `evtx_parser.py` (python-evtx) |
| Elasticsearch NDJSON | `.json` | `elastic_parser.py` |
| Compressed | `.gz` | Auto-decompressed |
| Other | any | Raw read |

---

## Lens AI Module

**File:** `lens.py`

The Lens module provides AI-powered log analysis using LogWhisperer and Ollama.

### How it works
1. User clicks **◎ Analyze in Lens** on any classified file (or submits manually)
2. PRISM calls LogWhisperer (`logwhisperer/logwhisperer.py`) on the file
3. LogWhisperer uses Ollama + Mistral to generate a plain-English summary
4. If LogWhisperer fails, PRISM falls back to calling Ollama directly
5. Summary + file context stored in `lens_sessions` PostgreSQL table
6. User can ask follow-up questions — full conversation history maintained

### Lens page features
- **Path tab** — analyze any file by its Linux path (WSL UNC paths auto-converted)
- **Upload File tab** — upload a file, classify and analyze in one step
- **Directory tab** — scan an entire directory, create one session per file
- **Sourcetype selector** — searchable combobox with all 144 sourcetypes
- **Session sidebar** — browse and reload previous analysis sessions
- **Chat interface** — ask follow-up questions about the log content

### WSL2 path handling
Windows paths like `\\wsl$\Ubuntu-24.04\home\youruser\prism\landing\file.log`
are automatically converted to `~/prism/landing/file.log`.

### Ollama status indicator
The Lens page shows a status bar:
- 🟢 Green — Ollama running, model available
- 🟡 Amber — Ollama running, model not found (`ollama pull mistral`)
- 🔴 Red — Ollama not running (`ollama serve`)

---

## API Reference

### Classification
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/classify` | Classify an uploaded file |
| `POST` | `/api/classify-text` | Classify pasted text |
| `POST` | `/api/scan` | Start a bulk directory scan |
| `GET` | `/api/scan/<job_id>` | Poll scan job status |
| `GET` | `/api/scan/<job_id>/results` | Get scan results |

### Review Queue
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/queue` | List review queue items |
| `POST` | `/api/queue/resolve` | Resolve an item (assign sourcetype + route) |
| `POST` | `/api/queue/clear` | Clear entire queue |
| `DELETE` | `/api/queue/delete-item` | Delete a single item |

### Signatures
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/signatures` | List all signatures |
| `POST` | `/api/signatures` | Create a new signature |
| `PUT` | `/api/signatures/<sourcetype>/patterns` | Update patterns |
| `DELETE` | `/api/signatures/<sourcetype>` | Delete a signature |

### Landing Zones
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/landing` | List all landing zones |
| `POST` | `/api/landing/add` | Create a new landing zone |
| `GET` | `/api/browse` | Browse directory tree |
| `GET` | `/api/browse/files` | List files in a directory |
| `GET` | `/api/open-folder` | Open folder in Windows Explorer (WSL2) |

### Dashboard & Stats
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/stats` | Rolling 24h classification stats |

### Lens AI
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/lens/status` | Ollama health + model availability |
| `POST` | `/api/lens/analyze` | Start AI analysis on a file |
| `POST` | `/api/lens/chat` | Send a follow-up message in a session |
| `GET` | `/api/lens/sessions` | List recent Lens sessions |
| `GET` | `/api/lens/session/<id>` | Get full session with messages |
| `DELETE` | `/api/lens/session/<id>` | Delete a session |

### System
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/watched-dirs` | List watched directories |
| `POST` | `/api/watched-dirs/add` | Add a watched directory |
| `DELETE` | `/api/watched-dirs/remove` | Remove a watched directory |
| `GET` | `/api/watcher/status` | Watcher running state |
| `POST` | `/api/watcher/toggle` | Start/stop watcher |

---

## UI Pages

| Page | Nav Section | Description |
|---|---|---|
| Single File | Classify | Upload a file or paste log text for immediate classification |
| Bulk Scan | Classify | Point at a directory to classify thousands of files at once |
| Dashboard | Monitor | Rolling 24h stats — classifications by category and sourcetype |
| Review Queue | Monitor | Files PRISM wasn't confident about — manually assign sourcetype |
| Landing Zones | Monitor | Browse routed files, view file counts, open folders |
| Signatures | Configure | View/edit all 144 rules, add new signatures, confidence scale |
| Watched Dirs | Configure | Directories auto-classified when a new file appears |
| Lens | Analyze | AI-powered log analysis and chat — powered by LogWhisperer + Mistral |

---

## Landing Zones

Files are routed to folders under `landing/` named after their sourcetype:

```
landing/
  cisco_asa/          ← Cisco ASA/FTD firewall logs
  WinEventLog_Security/
  pan_traffic/        ← Palo Alto traffic logs
  linux_secure/       ← /var/log/secure (SSH, sudo, PAM)
  aws_cloudtrail/
  suricata_eve/
  ...
  _review_queue/      ← Confidence < 60%, needs manual review
  _unknown/           ← No signature matched
```

Colons in sourcetype names are replaced with underscores in folder names
(e.g. `cisco:asa` → `cisco_asa/`).

---

## Troubleshooting

### Gunicorn won't start
```bash
# Check what's on port 5000
sudo fuser -k 5000/tcp
tail -20 logs/gunicorn_error.log
```

### Celery workers not processing jobs
```bash
# Check workers are running
celery -A celery_app inspect active
tail -20 logs/celery_priority.log

# Restart workers
pkill -f "celery.*celery_app"
./start.sh
```

### PostgreSQL connection failed
```bash
sudo service postgresql status
sudo service postgresql start
# Test connection:
psql -U prism -d prism -h localhost -c "SELECT 1"
```

### Ollama not responding
```bash
# Check if running
curl http://localhost:11434/api/tags
# Start manually:
ollama serve
# Check model is pulled:
ollama list
```

### Lens shows "File not found" with Windows paths
WSL UNC paths (`\\wsl$\...`) are auto-converted. If you see this error,
ensure the file exists at the Linux path:
```bash
ls ~/prism/landing/<sourcetype>/<filename>
```

### Review queue empty / not populating
Files below 60% confidence go to `_review_queue/` and are written to the
`review_queue` PostgreSQL table. Check:
```bash
psql -U prism -d prism -h localhost -c "SELECT COUNT(*) FROM review_queue"
tail -20 logs/celery_classify.log
```

### Check all service status at once
```bash
ps aux | grep -E "(gunicorn|celery|ollama|redis|postgres|watcher)" | grep -v grep
```

---

## Quick Reference

```bash
# Start everything
cd ~/prism && ./start.sh

# Stop PRISM services (Redis + PostgreSQL keep running)
./stop.sh

# Stop everything + shut down WSL2
./stop.sh --shutdown

# View live logs
tail -f logs/gunicorn_error.log
tail -f logs/celery_priority.log
tail -f logs/watcher.log

# Rebuild signatures
python3 build_signatures.py

# Initialize / migrate database schema
python3 -c "import db; db.init_db()"

# Test classifier directly
python3 -c "
from classifier import LogClassifier
clf = LogClassifier('config/signatures.yaml')
r = clf.classify('/path/to/logfile.log')
print(r.sourcetype, r.confidence)
"

# Check Ollama model
ollama list
ollama pull mistral

# Pull a different model (must also update .env PRISM_OLLAMA_MODEL)
ollama pull llama3.1
```

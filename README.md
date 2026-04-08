# PRISM
**Pattern Recognition & Intelligent Structure Mining**

A production log classification engine. PRISM ingests raw log files,
identifies their sourcetype using a signature engine, routes them into
landing zones for Cribl pickup, and provides AI-powered analysis via the
Lens module.

<img width="1901" height="1025" alt="image" src="https://github.com/user-attachments/assets/4252fa0e-c955-4acb-b652-5337a6de115e" />

<img width="1912" height="1028" alt="image" src="https://github.com/user-attachments/assets/38495a74-69ec-49f3-bf92-f9bcdd33f21d" />

<img width="1917" height="1027" alt="image" src="https://github.com/user-attachments/assets/9c4abfac-9fff-4e6a-8f87-6829b942e03b" />

<img width="1918" height="1025" alt="image" src="https://github.com/user-attachments/assets/7835bd3b-0673-4444-9875-3e44d4b5386e" />

<img width="1897" height="1023" alt="image" src="https://github.com/user-attachments/assets/46f47e7f-b6b6-4ece-8f3b-e4d3d7f43b1c" />

<img width="1910" height="1023" alt="image" src="https://github.com/user-attachments/assets/dfea434a-f20e-46cf-a5a0-1024202217aa" />

<img width="1899" height="1025" alt="image" src="https://github.com/user-attachments/assets/2596bb60-b218-4b92-87a1-a56a527b099c" />

<img width="683" height="482" alt="image" src="https://github.com/user-attachments/assets/7c6ea630-640c-4e55-8d97-a5e639dcd723" />

<img width="1917" height="1027" alt="image" src="https://github.com/user-attachments/assets/309f4aae-dab8-4945-b92d-aaebc81b2c6a" />


---

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
10. [Log Cleaning](#log-cleaning)
11. [Lens AI Module](#lens-ai-module)
12. [API Reference](#api-reference)
13. [UI Pages](#ui-pages)
14. [Landing Zones](#landing-zones)
15. [Troubleshooting](#troubleshooting)

---

## Architecture

```
Browser
  └─→ Gunicorn (sync workers, :5000)
        └─→ Redis (Celery broker)
              ├─→ Celery priority worker  (single file classify)
              └─→ Celery classify worker  (bulk scans + watcher)

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
sudo service postgresql start

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
```

### 7. Clone LogWhisperer
```bash
cd ~/prism
git clone https://github.com/binary-knight/logwhisperer logwhisperer
pip3 install -r logwhisperer/requirements.txt --break-system-packages
```

### 8. Configure environment
```bash
cp .env.example .env
# Edit .env and fill in your values
```

> **Note:** `PYTHONPATH` is set automatically by `start.sh`. Do not add it to `.env`.

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

> **Note:** `PYTHONPATH` is set automatically by `start.sh` from its own location. Do not add it here.

### `config/settings.yaml`
| Setting | Default | Description |
|---|---|---|
| `review_queue_threshold` | `0.60` | Files below this confidence go to review queue |
| `high_confidence_threshold` | `0.88` | Threshold for teal (high confidence) display |
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

### 2. PostgreSQL
- **Port:** 5432
- **Database:** `prism`
- **Purpose:** Persists audit log, review queue, scan jobs, Lens AI sessions
- **Managed by:** `sudo service postgresql start/stop`
- **Tables:** `audit_log`, `review_queue`, `scan_jobs`, `lens_sessions`

### 3. Celery Priority Worker
- **Queue:** `priority` | **Concurrency:** 4
- **Purpose:** Single-file classification from the web UI
- **Logs:** `logs/celery_priority.log`

### 4. Celery Classify Worker
- **Queue:** `classify` | **Concurrency:** 8
- **Purpose:** Bulk directory scans and watchdog-triggered files
- **Logs:** `logs/celery_classify.log`

### 5. Watchdog File Watcher
- **Purpose:** Monitors configured directories; auto-classifies new files on arrival
- **Toggle:** UI → Watcher button (top-right header) — glows teal when running
- **Logs:** `logs/watcher.log`

### 6. Gunicorn Web Server
- **Port:** 5000
- **Purpose:** Serves the PRISM web UI and REST API
- **Logs:** `logs/gunicorn_access.log`, `logs/gunicorn_error.log`

### 7. Ollama
- **Port:** 11434
- **Purpose:** Local LLM inference for Lens AI (Mistral by Mistral AI, runs 100% locally)
- **Logs:** `logs/ollama.log`

### 8. Flower (optional)
- **Port:** 5555
- **Purpose:** Celery task monitoring dashboard
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

### Restart Gunicorn only (after template changes)
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
├── cleaner.py                # Log file cleaning engine (strips dirty lines before routing)
├── tasks.py                  # Celery task definitions
├── celery_app.py             # Celery factory
├── db.py                     # PostgreSQL models + CRUD (SQLAlchemy)
├── router.py                 # Routes classified files to landing zones, calls cleaner
├── watcher.py                # Watchdog file system watcher
├── lens.py                   # Lens AI module (LogWhisperer + Ollama)
├── audit.py                  # Audit log helpers
├── review_queue.py           # Review queue helpers
├── gunicorn.conf.py          # Gunicorn production configuration
├── requirements.txt          # Python package dependencies
├── .env                      # Environment variables (never commit — in .gitignore)
├── .env.example              # Template — copy to .env and fill in values
├── .gitignore                # Excludes .env, logs/, landing/, logwhisperer/, etc.
│
├── config/
│   ├── signatures.yaml       # 327 classification signatures
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
├── static/                   # Static assets
│
├── logwhisperer/             # LogWhisperer AI log summarization (cloned separately)
│
├── logs/                     # Runtime logs (created on first start)
│
├── landing/                  # Routed log files (created on first start)
│   ├── cisco_asa/
│   ├── WinEventLog_Security/
│   ├── _review_queue/        # Confidence < 60%
│   └── _unknown/             # No signature matched
│
└── state/                    # Watcher state persistence
```

---

## Signatures

PRISM ships with **327 signatures** across 16 categories.

| Category | Count | Examples |
|---|---|---|
| network | 79 | Palo Alto, Fortinet, Check Point, Juniper, F5, Zeek, Zscaler, Netskope, Infoblox, Arista, Bluecoat |
| security | 40 | Suricata, Snort, Okta, CyberArk, CEF, LEEF, Qualys, Wazuh, HashiCorp Vault, SailPoint, GitHub, GitLab |
| cloud | 38 | AWS (17 sourcetypes), Azure/Entra (10), GCP (5), Zoom |
| cisco | 31 | ASA, FTD, IOS, NX-OS, ISE, Meraki, SD-WAN (11), Duo, AMP, DNA Center, Stealthwatch, ThousandEyes |
| windows | 24 | Security, Sysmon, PowerShell, Defender, AppLocker, Code Integrity, Firewall, BITS, DNS Client, Print |
| endpoint | 21 | CrowdStrike (3), SentinelOne (3), Carbon Black, osquery, Defender ATP, Trend Micro, Cisco AMP |
| infrastructure | 13 | VMware (10), Kubernetes (3), Docker (5), Arista CloudVision |
| email | 13 | O365, Exchange, Proofpoint (2), Mimecast (2), Barracuda |
| linux | 9 | secure, syslog, audit, auditd, cron, iptables, auth |
| web | 9 | Apache, Nginx, IIS, HAProxy, Squid, Traefik, Tomcat |
| database | 8 | MSSQL, MySQL, PostgreSQL, Oracle, MongoDB, Redis, Elasticsearch |
| middleware | 6 | Kafka, RabbitMQ, ActiveMQ, ZooKeeper, IBM MQ, NATS |
| monitoring | 6 | Nagios, Prometheus, Icinga2, PagerDuty, ServiceNow |
| storage | 3 | NetApp ONTAP, Dell EMC VNX, Rubrik |
| ot | 2 | Generic OT/ICS syslog, Claroty |
| unknown | 1 | Generic JSON fallback |

### Signature structure (`config/signatures.yaml`)
```yaml
- sourcetype: cisco:asa
  category: cisco
  vendor: Cisco
  product: ASA/FTD Firewall
  confidence: 0.97          # Base confidence ceiling (0.0–1.0)
  required_patterns:        # ALL must match — hard gate; drive 85% of floor score
    - '%ASA-\d+-\d+|%FTD-\d+-\d+'
  line_patterns:            # Optional boosters — each match raises score toward ceiling
    - 'Built (inbound|outbound)'
    - 'Teardown (TCP|UDP|ICMP)'
  min_matches: 1            # Minimum optional patterns that must match
  # Optional cleaning overrides (auto-derived if omitted):
  filter_mode: line
  line_filter: '%ASA-\d+-\d+|%FTD-\d+-\d+'
  multiline_mode: ''
  cleaning_enabled: true
```

**Full signature catalog:** [SIGNATURES.md](SIGNATURES.md) — all 327 sourcetypes organized by vendor.

**Key vendor coverage:**
- **VMware:** 35 signatures — ESXi (vmkernel, hostd, vpxa, fdm, vobd, shell, auth, storage, vSAN), vCenter (vpxd, eam, sts, rhttpproxy), NSX, Horizon, Aria, Workspace ONE, Carbon Black
- **Cisco:** 31 signatures — ASA/FTD, IOS, NX-OS, SD-WAN (12), ISE, Duo, AMP, DNA Center, Stealthwatch, ThousandEyes
- **AWS:** 17 signatures — CloudTrail, VPC Flow, GuardDuty, Security Hub, WAF, Config, Inspector, Route53, ELB, IAM
- **Azure/Entra:** 10 signatures — Sign-In, Audit, Provisioning, Activity, Sentinel, Defender for Cloud, Risk Detection
- **GCP:** 7 signatures — Audit, VPC Flow, Firewall, DNS, IAM, Pub/Sub, Security Command Center

### Confidence scoring

PRISM uses a **Floor + Boost** model:

- **Required patterns** all match → establishes a floor of **85%** of the signature's base confidence
- **Optional patterns** each matched → boost the score proportionally from the floor up to the full base confidence
- **Score is always ≤ base confidence** — never inflated above the signature ceiling

```
Score = base_confidence × (0.85 + 0.15 × (optional_matched / optional_total))
```

| Scenario | cisco:asa (base 97%) | Display color |
|---|---|---|
| Required only, 0 optionals matched | 82.5% | 🟡 Amber |
| Required + some optionals | 85–96% | 🟢 Teal |
| Required + all optionals | 97.0% | 🟢 Teal |
| Score < 60% | — | 🔴 Review Queue |

**UI color bands:**
- 🟢 Teal ≥ 88% — strong match with optional pattern evidence
- 🟡 Amber 76–88% — required patterns matched, fewer optionals (still confident)
- 🔴 Red < 76% — routed to review queue

### Matched patterns display
The result card shows two types of matched patterns with distinct styling:
- **Teal chips** — required patterns (hard gate — must all match)
- **Indigo/purple chips** — optional patterns that matched (confidence boosters)

### Managing signatures
- **View/edit:** UI → Configure → Signatures → Edit Patterns
- **Add new:** UI → Configure → Signatures → + New Signature
- **Edit cleaning:** UI → Configure → Cleaning Rules
- **Full catalog:** See [SIGNATURES.md](SIGNATURES.md) for the complete list of all 327 sourcetypes organized by vendor and category

---

## Classification Engine

**File:** `classifier.py`

### How it works
1. Reads up to `file_read_bytes` (8192) bytes from the file
2. Extracts text via format-specific parsers (`.evtx`, `.csv`, Elasticsearch NDJSON, plain text)
3. Tests every signature's `required_patterns` against the text
4. Signatures that pass required patterns are scored using optional patterns
5. Highest scoring signature wins; tiebreaker is position in `signatures.yaml`
6. File is routed to `landing/<sourcetype>/` or `_review_queue/` if confidence < 0.60
7. Score uses Floor + Boost model — required match = 85% floor, optionals boost to ceiling

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

## Log Cleaning

**File:** `cleaner.py`

When a file is classified and routed to a landing zone, PRISM first strips
non-conforming content — banners, headers, separator lines, and anything that
doesn't match the expected log format. Clean events go to the landing zone
file. Stripped content goes to a `.noise.log` sidecar file in the same folder.

Cleaning runs automatically for all three classification paths: single file,
bulk scan, and watched directory.

### Filter Modes

| Mode | Description | Typical sourcetypes |
|---|---|---|
| `auto` | Derived automatically from `required_patterns` at classification time | All (default) |
| `line` | One event per line. Lines matching `line_filter` are kept, others stripped | Cisco ASA, PAN CSV, Linux syslog, CEF, LEEF, auditd |
| `multiline` | Events span multiple lines. Complete blocks extracted, noise stripped | WinEvent XML, CloudTrail JSON, Suricata EVE, Zeek TSV |
| `passthrough` | No cleaning. File routed as-is | Formats without a reliable filter |

### Multiline Sub-modes

| Sub-mode | Format | How it works |
|---|---|---|
| `json_lines` | NDJSON, one JSON object per line | Each line parsed as JSON; invalid lines stripped |
| `json_object` | Multi-line JSON (CloudTrail, Azure, Okta) | Brace depth tracking to find complete objects |
| `xml_event` | XML blocks (WinEvent, EVTX) | `<Event>...</Event>` blocks extracted; preamble stripped |
| `zeek_tsv` | Zeek/Bro TSV logs | `#fields` headers kept; data rows validated by column count |
| `iis` | IIS W3C logs | `#Fields:` headers kept; data rows kept |
| `csv_with_header` | CSV exports | First non-banner line is header; subsequent rows kept |

### Built-in Banner Detection

Regardless of filter mode, these are always stripped:
- Pure separator lines (`===`, `---`, `###`, `***`)
- `SHOW LOGGING` and similar Cisco CLI output headers
- `CISCO:IOS:XE VER. x.x` version headers
- Blank lines at the start of a file

### Noise Files

Stripped lines are written to `<filename>.noise.log` in the same landing zone
folder as the clean file. They are never permanently deleted.

```
landing/cisco_asa/
  20240101_120000_firewall.log        ← 268 clean %ASA-* events
  20240101_120000_firewall.noise.log  ← 4 stripped header lines
```

### Configuring Cleaning Rules (UI)

Go to **Configure → Cleaning Rules**. The page shows all 327 signatures with:
- **Summary stats** — total, auto-derived, line, multiline, passthrough, custom counts
- **Search bar** — filter by sourcetype or category (sticky above the table)
- **Mode filter** — filter table by cleaning mode
- **Enabled toggle** — enable or disable cleaning per signature without removing the rule
- **Edit modal** — click any row or its Edit button to open the edit modal

The edit modal provides:
- **Filter Mode** dropdown — Auto / line / multiline / passthrough with plain-English description of each
- **Line Filter** field — regex a valid line must match; shows the auto-derived value for reference
- **Multiline Mode** dropdown — choose the sub-mode for your log format
- **Live Test** area — paste sample log lines and see instantly which are kept (✓ green) and which are stripped (✗ red) before saving

**Reset** — removes any custom rule for a signature and returns it to auto-derivation.

### Configuring Cleaning Rules (YAML)

Add fields directly to any signature in `config/signatures.yaml`:

```yaml
- sourcetype: cisco:ios:show_log
  filter_mode: line
  line_filter: '%[A-Z][A-Z0-9_-]+-\d+-[A-Z0-9_]+:|Syslog logging:'
  multiline_mode: ''
  cleaning_enabled: true
```

| Field | Values | Default |
|---|---|---|
| `filter_mode` | `line` \| `multiline` \| `passthrough` \| `""` | auto-derived |
| `line_filter` | regex string | auto-derived from `required_patterns[0]` |
| `multiline_mode` | `json_lines` \| `json_object` \| `xml_event` \| `zeek_tsv` \| `iis` \| `csv_with_header` \| `""` | auto-derived |
| `cleaning_enabled` | `true` \| `false` | `true` |

---

## Lens AI Module

**File:** `lens.py`

### How it works
1. User clicks **◎ Analyze in Lens** on any classified file
2. PRISM calls LogWhisperer (`logwhisperer/logwhisperer.py`) on the file
3. LogWhisperer uses Ollama + Mistral to generate a plain-English summary
4. If LogWhisperer fails, PRISM falls back to calling Ollama directly
5. Summary + file context stored in `lens_sessions` PostgreSQL table
6. User can ask follow-up questions — full conversation history maintained

### Lens page features
- **Path tab** — analyze any file by its Linux path (WSL UNC paths auto-converted)
- **Upload File tab** — upload a file, classify and analyze in one step
- **Directory tab** — scan an entire directory, create one session per file
- **Sourcetype selector** — searchable combobox with all 327 sourcetypes
- **Session sidebar** — browse and reload previous analysis sessions
- **Chat interface** — ask follow-up questions about the log content

### WSL2 path handling
Windows paths like `\\wsl$\Ubuntu-24.04\home\youruser\prism\landing\file.log`
are automatically converted to `/home/youruser/prism/landing/file.log`.

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
| `GET` | `/api/signatures/<sourcetype>` | Get raw signature detail (YAML dict) |
| `PUT` | `/api/signatures/<sourcetype>/patterns` | Update patterns and cleaning config |
| `DELETE` | `/api/signatures/<sourcetype>` | Delete a signature |

### Cleaning Rules
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/cleaning/derived` | All signatures with effective cleaning config (explicit + auto-derived) |
| `POST` | `/api/cleaning/<sourcetype>/toggle` | Enable or disable cleaning for a signature |

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
| `GET` | `/api/file/view` | View file contents (used by queue file viewer) |

---

## UI Pages

| Page | Nav Section | Description |
|---|---|---|
| Single File | Classify | Upload a file or paste log text for immediate classification |
| Bulk Scan | Classify | Point at a directory to classify thousands of files at once |
| Dashboard | Monitor | Rolling 24h stats — classifications by category and sourcetype |
| Review Queue | Monitor | Files PRISM wasn't confident about — manually assign sourcetype |
| Landing Zones | Monitor | Browse routed files, view file counts, open folders |
| Signatures | Configure | View/edit all 327 rules, add new signatures, required vs optional pattern display |
| Cleaning Rules | Configure | Per-signature cleaning config — modes, filters, enable/disable, live test |
| Watched Dirs | Configure | Directories auto-classified when a new file appears |
| Lens | Analyze | AI-powered log analysis and chat — powered by LogWhisperer + Mistral |

### Signatures page
- Required patterns displayed as **teal chips**, optional as **indigo chips**
- Edit Patterns modal — check a pattern to make it required; uncheck for optional
- Confidence bar shown per signature

### Cleaning Rules page
- Summary stats bar: total / auto / line / multiline / passthrough / custom counts
- Sticky search bar above the table — filter by sourcetype or category as you type
- Mode filter dropdown — show only signatures of a given cleaning mode
- Row count shown ("32 of 144 signatures")
- **Enabled toggle** per row — disable cleaning without deleting the rule; disabled rows dim to 50% opacity
- Click any row to open the Edit modal
- Edit modal shows: Filter Mode with description, Line Filter with auto-derived hint, Multiline Mode, Live Test area
- **Reset** button removes custom rule and returns to auto-derivation

### Watcher button
The **WATCHER** indicator in the top-right header shows:
- **Dim grey dot + grey text** — watcher is OFF
- **Glowing teal dot + teal text** — watcher is ON and monitoring directories

---

## Landing Zones

Files are routed to folders under `landing/` named after their sourcetype:

```
landing/
  cisco_asa/                                    ← clean %ASA-* events
    20240101_120000_firewall.log
    20240101_120000_firewall.noise.log           ← stripped banner lines
  WinEventLog_Security/
  pan_traffic/
  linux_secure/
  aws_cloudtrail/
  _review_queue/                                ← confidence < 60%
  _unknown/                                     ← no signature matched
```

Colons in sourcetype names are replaced with underscores in folder names
(e.g. `cisco:asa` → `cisco_asa/`).

Clean files and their `.noise.log` sidecars always share the same timestamp
prefix so they stay paired in directory listings.

---

## Troubleshooting

### Gunicorn won't start
```bash
sudo fuser -k 5000/tcp
tail -20 logs/gunicorn_error.log
```

### Celery workers not processing jobs
```bash
celery -A celery_app inspect active
tail -20 logs/celery_priority.log
pkill -f "celery.*celery_app"
./start.sh
```

### PostgreSQL connection failed
```bash
sudo service postgresql status
sudo service postgresql start
psql -U prism -d prism -h localhost -c "SELECT 1"
```

### Ollama not responding
```bash
curl http://localhost:11434/api/tags
ollama serve
ollama list
```

### Cleaning not stripping lines
Check that the signature's `sig_dict` is being passed from tasks.py via
`clf.get_signature_detail(result.sourcetype)` — this returns the raw YAML dict
with string patterns that `derive_filter_config` requires. Using the compiled
`Signature` dataclass object will silently skip cleaning.

Also verify `cleaning_enabled` is `true` for the signature on the Cleaning
Rules page.

### Lens shows "File not found" with Windows paths
WSL UNC paths (`\\wsl$\...`) are auto-converted. Verify the file exists:
```bash
ls /home/youruser/prism/landing/<sourcetype>/<filename>
```

### Cleaning Rules page loads blank
If the table appears empty, open browser DevTools console and run:
```javascript
await loadCleaning()
```
If this populates it, there is a timing issue. This was fixed by ensuring a
single `go()` function handles all page navigation — check that only one
`go()` definition exists in `templates/index.html`.

### Check all service status
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

# Full shutdown + WSL2
./stop.sh --shutdown

# View live logs
tail -f logs/gunicorn_error.log
tail -f logs/celery_priority.log
tail -f logs/watcher.log
tail -f logs/ollama.log

# Test classifier directly
python3 -c "
from classifier import LogClassifier
clf = LogClassifier('config/signatures.yaml')
r = clf.classify('/path/to/logfile.log')
print(r.sourcetype, r.confidence)
"

# Test cleaner directly
python3 -c "
from cleaner import clean_file, derive_filter_config
sig = {'sourcetype':'cisco:asa','required_patterns':['%ASA-\d+-\d+']}
cfg = derive_filter_config(sig)
stats = clean_file('dirty.log', 'clean.log', cfg['filter_mode'], cfg['line_filter'])
print(stats)
"

# Hit the cleaning/derived API
curl http://localhost:5000/api/cleaning/derived | python3 -m json.tool | head -30

# Check Ollama
ollama list
ollama pull mistral

# Initialize / migrate database schema
python3 -c "import db; db.init_db()"
```

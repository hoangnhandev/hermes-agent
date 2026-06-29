# Hermes Agent — Server Deployment Guide (Contabo)

> Deploy Hermes native trên server thay vì Docker container. Giúp Hermes có quyền quản lý toàn bộ server: Dokku apps, Docker containers, systemd services, packages.

## Architecture

```
Server Contabo (withly-server)
├── Hermes (native, systemd service)
│   └── user: withlyvn (sudo NOPASSWD, groups: docker, dokku)
├── Dokku 0.38.0
│   ├── shp-paytrim-staging
│   ├── shp-withly-inbox
│   └── shp-withly-inbox-staging
└── Docker (host daemon)
    └── các container do Dokku quản lý + standalone containers
```

**Tại sao native thay vì container:**
- Container cách ly quyền — không mount docker.sock = không điều khiển được container khác
- Native kế thừa đúng quyền user: docker group (docker ps), dokku group, sudo NOPASSWD
- Không overhead container layer, dễ debug trực tiếp

## Server Info

| Item | Value |
|---|---|
| Hostname | withly-server |
| OS | Ubuntu 24.04 |
| SSH alias | `contabo_withlyvn` |
| User | `withlyvn` (uid=1000) |
| Groups | sudo, docker, dokku |
| Python | 3.12 (system), 3.11 (hermes via uv) |
| Sudoers | `/etc/sudoers.d/dokku` → `withlyvn ALL=(ALL) NOPASSWD: ALL` |

## Deployment Layout

```
/home/withlyvn/
├── hermes-agent/              # repo (git clone)
│   ├── venv/                  # Python venv created by setup-hermes.sh
│   ├── setup-hermes.sh        # installer script
│   └── ...
├── .hermes/                   # HERMES_HOME — data, config, state
│   ├── config.yaml            # hermes config (terminal backend: local)
│   ├── hermes.env             # env secrets (API keys)
│   ├── state.db               # sqlite state
│   ├── skills/                # user skills
│   ├── sessions/              # chat sessions
│   └── ...
└── .local/
    └── bin/
        ├── hermes → hermes-agent/venv/bin/hermes  # symlink
        └── uv                                         # package manager
```

## Systemd Service

File: `/etc/systemd/system/hermes-gateway.service`

```ini
[Unit]
Description=Hermes Agent Gateway
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=withlyvn
Group=withlyvn
Environment=PATH=/home/withlyvn/.local/bin:/home/withlyvn/hermes-agent/venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=HERMES_HOME=/home/withlyvn/.hermes
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
WorkingDirectory=/home/withlyvn/hermes-agent
ExecStart=/home/withlyvn/hermes-agent/venv/bin/hermes gateway run --replace
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Commands

```bash
sudo systemctl status hermes-gateway     # status
sudo systemctl restart hermes-gateway    # restart
sudo systemctl stop hermes-gateway       # stop
sudo journalctl -u hermes-gateway -f     # follow logs
```

## Setup từ zero (fresh install)

```bash
# 1. SSH vào server
ssh contabo_withlyvn

# 2. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env

# 3. Clone repo (nếu chưa có)
cd ~
git clone <hermes-repo-url> hermes-agent
cd hermes-agent

# 4. Setup native
bash setup-hermes.sh

# 5. Fix symlink (nếu setup không tạo)
ln -sf ~/hermes-agent/venv/bin/hermes ~/.local/bin/hermes

# 6. Verify
hermes --version

# 7. Tạo systemd service
sudo tee /etc/systemd/system/hermes-gateway.service << 'EOF'
# ... (nội dung như trên)
EOF
sudo systemctl daemon-reload
sudo systemctl enable hermes-gateway
sudo systemctl start hermes-gateway
```

## Update Hermes

```bash
cd ~/hermes-agent
git pull
bash setup-hermes.sh
ln -sf ~/hermes-agent/venv/bin/hermes ~/.local/bin/hermes
sudo systemctl restart hermes-gateway
```

## Hermes capabilities trên server

Hermes terminal backend = `local`, chạy với quyền user `withlyvn`:

| Capability | Command | Works? |
|---|---|---|
| Docker containers | `docker ps / logs / exec / stop / restart` | ✅ |
| Dokku apps | `dokku apps:list / config / deploy / logs` | ✅ |
| Service management | `sudo systemctl start/stop/restart <service>` | ✅ |
| Package management | `sudo apt-get install / upgrade` | ✅ |
| Log viewing | `sudo journalctl -u <unit>` | ✅ |
| File system | full read/write trong home + sudo | ✅ |
| SSH outbound | `ssh` tới các server khác | ✅ |

## Lưu ý

- **Không dùng Docker container cho Hermes** trên server này — mất quyền quản lý host
- Terminal backend phải là `local` (đã config trong `~/.hermes/config.yaml`)
- Data dir `~/.hermes` chứa state DB, skills, sessions — backup thường xuyên
- Sudoers file `/etc/sudoers.d/dokku` cấp NOPASSWD ALL — cẩn thận nếu thay đổi
- Hermes gateway dùng `--replace` flag — chỉ 1 instance chạy tại một thời điểm
- Config secrets trong `~/.hermes/hermes.env` — không commit vào git

## History

- **2026-06-25**: Migrated từ Docker container sang native install. Xóa container `hermes` + image `hermes-agent`. Tạo systemd service.

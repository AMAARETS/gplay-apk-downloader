# GPlay APK Downloader

Download APKs from Google Play Store. Automatically merges split APKs (App Bundles) into single installable APKs.

## Features

- Download any free app from Google Play
- Automatically merges split APKs into single installable APK
- Architecture selector (arm64-v8a, armeabi-v7a, x86_64, x86)
- Web UI with real-time progress
- CLI tool for scripting

## Quick Install

```bash
git clone <repo-url> gplay-downloader
cd gplay-downloader
chmod +x setup.sh
./setup.sh
```

## Requirements

The setup script will check for and help install:

- **Python 3.8+** with venv
- **Java 17+** (for APKEditor)
- **apksigner** (for APK signing)

On Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install -y openjdk-17-jre-headless apksigner python3 python3-venv python3-pip curl
```

## Usage

### Web Server

```bash
./start-server.sh
```

Open http://localhost:5000 in your browser.

### CLI

```bash
# Authenticate (uses anonymous tokens)
./gplay auth

# Search for apps
./gplay search "youtube"

# Download an app
./gplay download com.google.android.youtube
```

## How It Works

1. Uses Aurora Store's anonymous token dispenser for authentication
2. Downloads base APK + split APKs from Google Play
3. Merges splits using [APKEditor](https://github.com/REAndroid/APKEditor)
4. Signs merged APK with debug keystore
5. Returns single installable APK

## Running as a Service (systemd)

```bash
sudo tee /etc/systemd/system/gplay.service << EOF
[Unit]
Description=GPlay APK Downloader
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/start-server.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable gplay
sudo systemctl start gplay
```

## Files

- `server.py` - Flask web server with APK merging
- `index.html` - Web UI
- `gplay-downloader.py` - CLI tool
- `APKEditor.jar` - Split APK merger (downloaded by setup)
- `setup.sh` - Installation script
- `start-server.sh` - Server startup script

## License

MIT

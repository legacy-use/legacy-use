<!-- legacy-use README -->
<p align="center">
  <img src="https://legacy-use-public-content.s3.eu-central-1.amazonaws.com/legacy_use_logo_white_large_shaded.png" width="420" alt="legacy-use logo" />
  <h3 align="center">🚀  Turn any legacy application into a modern REST API, powered by AI.</h3>
</p>

<p align="center">
  <a href="https://discord.gg/9CV42YxKz9">
    <img src="https://img.shields.io/badge/Discord-%235865F2.svg?&logo=discord&logoColor=white" alt="Join us on Discord" />
  </a>
  <a href="https://www.legacy-use.com/">
    <img src="https://img.shields.io/badge/Try_Now-legacy--use.com-blue" alt="Try Now" />
  </a>
  <a href="https://github.com/legacy-use/legacy-use">
    <img src="https://img.shields.io/github/stars/legacy-use?style=social" alt="GitHub stars" />
  </a>
</p>

---

## ✨ Why legacy-use?

- **Add API Endpoints via Prompt** — Dynamically generate and customize REST API endpoints for any legacy or desktop application.
- **Access systems running legacy software** — Use established tools like RDP/VNC to run your prompts.
- **Logging & Debugging** — Track, analyze, and resolve issues effortlessly with built-in observability tools.
- **Safety & Reliability** — Ensure secure, compliant automation that delivers dependable performance.
- **Model Provider Independence** — Choose your model provider and avoid vendor lock-in.
- **Enterprise-Grade Security and Compliance** — Deploy and run locally to ensure security and compliance.

[![legacy-use demo](https://framerusercontent.com/images/zbuaI2v5TNWWs9eVaW0dBad5LE.png)](https://framerusercontent.com/assets/Z6Dsz4JSIW0JIypHSZFcu5DVCU.mp4)

---

## 🚀 Quick start (5 min)

### Prerequisites

#### Required

- **Docker** - All services run in containers
  - [Get Docker](https://www.docker.com/get-started/) for your platform
  - **Note**: Make sure Docker is running before proceeding with setup

#### API Keys (choose one provider)

- **Anthropic API Key** - For Claude models (default)
  - [Get your API key](https://console.anthropic.com/) from Anthropic Console
  - **Note**: You'll need credits in your Anthropic account for API usage

- **OpenAI API Key** - For GPT models
  - [Get your API key](https://platform.openai.com/) from OpenAI Platform

- **Google API Key** - For Gemini 3 Pro models
  - [Get your API key](https://aistudio.google.com/) from Google AI Studio
  - Or use Vertex AI with GCP credentials for enterprise deployments

#### For Development Only

Want to contribute or modify the code? You'll need Node.js and Python locally for development.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete development setup guide.

### Setup Steps

```bash
# 1. Clone the repository
git clone https://github.com/legacy-use/legacy-use
cd legacy-use

# 2. Create and configure environment file
cp .env.template .env
# Edit .env file with your favorite editor and add:
# ANTHROPIC_API_KEY=sk-your-anthropic-key-here
# (Optional) Add any configuration options from above

# 3. Build docker containers
make docker-build

# 4. Start all services
make docker-dev
```

**🔑 Automatic API Key Generation**

During the initial database migration, the system will automatically:

- Generate a secure API key for the default tenant
- Display the credentials in the console output
- Store the key securely in the database

You'll see output like this:
```
============================================================
🚀 LEGACY-USE SETUP COMPLETE
============================================================
📡 Server URL: http://tenant-default.local.legacy-use.com:5173/
🔑 API Key: AbC123XyZ789...

💡 To access your instance:
   1. Open the URL in your browser
   2. Enter the API key when prompted
   3. Configure your AI provider in Settings

⚠️  Keep this API key secure - it provides full access to your instance!
============================================================
```

### Verification

Once the setup completes:

1. **Check the console output** - You should see the setup credentials displayed
2. **Frontend**: Open <http://tenant-default.local.legacy-use.com:5173> - you should see the legacy-use dashboard
3. **API Documentation**: Visit <http://tenant-default.local.legacy-use.com:8088/redoc> - to explore the REST API
4. **Configure AI Provider**: Go to Settings (http://tenant-default.local.legacy-use.com:5173/settings) and configure your Anthropic API key

🎉 **You're all set!** The complete setup usually takes 2-5 minutes depending on your internet connection.

### Troubleshooting

**Docker not starting?**

- Ensure Docker Desktop is running
- Check if ports 8077 and 8088 are available: `lsof -i :8077` and `lsof -i :8088`

**Build failing?**

- Ensure you have sufficient disk space (~2GB)
- Try: `docker system prune` to clean up space, then rebuild

**Can't access the UI?**

- Wait 30-60 seconds for all services to fully start
- Check logs: `docker logs legacy-use-mgmt`

---

## 🖥️ Add your first target (Windows VM)

Ready to automate your own Windows applications? Here's how to add a Windows VM as a target:

### Step 1: Set up a Windows VM

Choose your virtualization platform:

- **macOS**: [UTM](https://mac.getutm.app/) (recommended) or [Parallels](https://www.parallels.com/)
- **Windows**: [VirtualBox](https://www.virtualbox.org/) or [VMware](https://www.vmware.com/)
- **Linux**: [VirtualBox](https://www.virtualbox.org/) or [QEMU/KVM](https://www.qemu.org/)

### Step 2: Install VNC Server in Windows VM

1. Download and install [UltraVNC](https://uvnc.com/downloads/ultravnc/159-ultravnc-1-4-3-6.html)
2. During setup, set a VNC password (remember this!)
3. Ensure the VNC server starts automatically

### Step 3: Get VM Network Details

Find your VM's IP address:

**Inside the Windows VM:**

1. Open Command Prompt (`Win+R` → `cmd`)
2. Run: `ipconfig`
3. Look for **IPv4 Address** (e.g., `192.168.64.2`, `10.0.2.15`)

**Alternative - From host machine:**

- Check your VM software's network settings for the assigned IP

### Step 4: Configure VM Display Settings

For optimal performance, configure your VM's display resolution:

**Recommended Screen Resolutions:**

- **1024 × 768**
- **1280 × 800**

**Note**: Larger resolutions can be used, but performance may degrade—especially when working with very small UI elements.

### Step 5: Add Target in Legacy-Use

1. Open the legacy-use web interface: `http://localhost:8077`
2. Navigate to **Targets** → **New Target**
3. Fill in the details:
   ```
   Name:     my-windows-vm
   Type:     VNC
   Host:     [YOUR_VM_IP]    # IP from Step 3
   Port:     5900            # Default VNC port
   Password: ••••••••       # Password from Step 2
   ```
4. Click **Test Connection** to verify, then **Save**

✅ **Success!** Your Windows VM is now ready for AI automation.

---

## ✅ Run your first job (Windows Calculator)

1. **Sessions → Create Session** for your target.
2. **APIs → Import** → select `sample_prompts/WindowsCalc.json`.
3. Choose your session & click **Execute**.
4. Integrate via REST ➜ three-dot menu → **cURL**.

---

## ✍️ Writing Effective Prompts

Creating custom automation scripts for your applications? Check out our comprehensive guide:

📖 **[HOW_TO_PROMPT.md](HOW_TO_PROMPT.md)** - Learn the best practices for writing prompts that work reliably with legacy-use.

---

## 🛠️ Supported connectivity

| Technology | Category | Status |
| ---------- | -------- | ------ |
| OpenVPN    | VPN      | ✅     |
| Tailscale  | VPN      | ✅     |
| WireGuard  | VPN      | ✅     |
| VNC        | Remote   | ✅     |
| RDP        | Remote   | ✅     |
| TeamViewer | Remote   | 🚧     |

---

## 📡 Telemetry

We collect minimal anonymous usage data to improve the product. This helps us understand:

- Which features are most useful
- Performance bottlenecks
- Common error patterns

**What we collect**: Usage statistics, error logs, feature interactions
**What we DON'T collect**: Your API keys, target machine data, or sensitive information

**Disable anytime** by adding to your `.env` file:

```bash
VITE_PUBLIC_DISABLE_TRACKING=true
```

**Full transparency**: See exactly what we track in the code:
`app/main.tsx`, `app/services/telemetryService.tsx`, `server/server.py`, `server/utils/telemetry.py`

---

## 🤖 Supported AI Providers

| Provider | Models | Status | Configuration |
|----------|--------|--------|---------------|
| **Anthropic** | Claude Sonnet 4, Claude Opus 4.5 | ✅ Default | `ANTHROPIC_API_KEY` |
| **AWS Bedrock** | Claude models via AWS | ✅ | AWS credentials |
| **Google Vertex AI** | Claude models via GCP | ✅ | GCP project credentials |
| **OpenAI** | GPT-5 | ✅ | `OPENAI_API_KEY` |
| **Google AI Studio** | Gemini 3 Pro | ✅ New | `GOOGLE_API_KEY` |
| **Google Vertex AI (Gemini)** | Gemini 3 Pro | ✅ New | GCP project + ADC |

Configure your preferred provider in **Settings** after initial setup, or set tenant-specific API keys via the database.

---

## Optional Configuration

- `VITE_ALLOW_OPENVPN`: Set to `true` to enable OpenVPN target creation. **⚠️ Security Warning**: OpenVPN requires elevated system privileges (NET_ADMIN capabilities) which may pose security risks. Only enable this if you understand the security implications and trust your target environments

- `SHOW_DOCS`: Set to `true` to make backend endpoints documentation available via `/redoc`

## 🤝 Contributing

We love contributors! Read [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

---

<p align="center">
Made with ❤️ in Munich
</p>

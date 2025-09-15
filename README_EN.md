**Languages**: [🇨🇳 中文](README.md) | [🇺🇸 English](README_EN.md)

---

# Claude Code Intelligent Proxy Server 🚀

**A proxy server that enables Claude Code to seamlessly use multiple AI models**

Supports OpenAI, Google Gemini, and Anthropic platforms through a unified API interface, with real-time model switching, three-tier model architecture, super model support, intelligent transparent proxy, and smart conversation management.

![Claude Code Proxy](pic.png)

## ✨ Core Features

- 🔄 **Real-time Model Switching**: Seamlessly switch between models during conversations
- ⚡ **Three-tier Model Architecture**: super_model + big_model + small_model intelligent calling
- 🎛️ **Rich Preset Configurations**: 8 preset combinations including reasoning optimization and cross-platform setups
- 🔀 **Intelligent Transparent Proxy**: Automatically detects and supports both Claude Pro subscribers and API key users
- 💬 **Smart Conversation Management**: Complete conversation history recovery, log parsing, and deduplication
- 🌐 **Cross-platform Configuration**: Three-tier models can come from different providers for flexible combinations
- 🖥️ **Optimized Interactive Interface**: Status bar display, request log toggle, direct preset application
- 🛠️ **Enhanced Tool Support**: Comprehensive tool call handling and message conversion logic

## 🚀 Quick Start

### 📦 Basic Installation and Configuration

```bash
# 1. Clone the project
git clone https://github.com/catclever/claude-code-flexible-proxy.git
cd claude-code-flexible-proxy

# 2. Install UV package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install project dependencies
uv sync

# 4. Configure API keys
cp .env.example .env
# Edit .env file and fill in your API Keys

# 5. Configure providers and models
cp providers.json.example providers.json
# Optional: customize models and presets in providers.json
```

---

## 🎛️ Interactive Mode (Recommended)

**Suitable for daily use with visual management interface**

### Start Interactive Application

```bash
# Start interactive management interface
uv run python interactive.py

# Or specify custom port
uv run python interactive.py --port 8080
```

### Interactive Features List

| Command | Icon | Feature Description |
|---------|------|---------------------|
| `preset` | 🎛️ | **Apply Preset Configuration** - Quick switch between 8 model combination presets |
| `config` | 🔧 | **Custom Model Configuration** - Manually configure three-tier model architecture |
| `toggle` | 🔄 | **Switch Proxy Status** - Enable/disable proxy mode |
| `test` | 🧪 | **Test Current Configuration** - Send test requests to verify connections |
| `record` | 📝 | **Conversation Record Control** - Manage conversation recording features |
| `load` | 📂 | **Load Conversation Record File** - Read and restore conversation records from files |
| `logs` | 📜 | **View Debug Logs** - View and manage system debug logs |
| `verbose` | 🔊 | **Toggle Request Log Display** - Control whether to show detailed API request logs |
| `providers` | 📡 | **View Provider Information** - Display API key status and model lists |
| `presets` | 📋 | **View Preset List** - Browse all available model combination presets |
| `env` | ⚙️ | **Reconfigure Environment Variables** - Fix Claude Code environment configuration |
| `help` | ❓ | **Help Information** - Display detailed usage instructions |
| `quit` | 🚪 | **Exit Program** - Safe exit with automatic resource cleanup |

### Interactive Usage Workflow

```bash
# 1. After startup, it will automatically:
#    - 🚀 Start proxy server
#    - 🔧 Configure Claude Code environment variables
#    - 🖥️ Display interactive management menu

# 2. Select preset configuration
preset → Choose suitable model combination

# 3. Test configuration
test → Verify API connections and model responses

# 4. Use Claude Code
# Now you can directly use Claude Code, it will automatically connect to proxy server
```

---

## 💻 Server Mode
(Not thoroughly tested, please report any issues)

**Suitable for server deployment or scenarios requiring API access**

### Start Server

```bash
# Start server directly
uv run uvicorn server:app --host 0.0.0.0 --port 8082

# Development mode (auto-reload)
uv run uvicorn server:app --host 0.0.0.0 --port 8082 --reload
```

### Manual Claude Code Environment Configuration

```bash
# Set environment variable (temporary)
ANTHROPIC_BASE_URL=http://localhost:8082 claude

# Or permanent setting (bash/zsh)
echo 'export ANTHROPIC_BASE_URL=http://localhost:8082' >> ~/.bashrc
source ~/.bashrc

# fish shell
echo 'set -gx ANTHROPIC_BASE_URL http://localhost:8082' >> ~/.config/fish/config.fish
```

### Server Mode API Endpoints

```bash
# View server status
curl http://localhost:8082/status

# View current configuration
curl http://localhost:8082/config

# View all available models
curl http://localhost:8082/models

# View all presets
curl http://localhost:8082/presets

# Switch model configuration
curl -X POST http://localhost:8082/switch_model \
  -H "Content-Type: application/json" \
  -d '{"preset": "openai_reasoning", "preserve_conversation": true}'

# Proxy control
curl -X POST http://localhost:8082/proxy_server/disable  # Disable proxy
curl -X POST http://localhost:8082/proxy_server/enable   # Enable proxy
```

---

## ⚙️ Configuration Guide

### 🔑 API Keys Configuration (.env)

```dotenv
# API Keys (at least one required)
OPENAI_API_KEY="sk-your-openai-key-here"
GEMINI_API_KEY="your-google-gemini-key-here"
ANTHROPIC_API_KEY="sk-ant-your-anthropic-key-here"

# Optional: Default model configuration
DEFAULT_PRESET="default"           # Use preset configuration
# Or directly specify models
SUPER_MODEL="gpt-4o"
BIG_MODEL="gpt-4o"
SMALL_MODEL="gpt-4o-mini"

# Optional: Server configuration
PORT=8082                          # Server port
LOG_LEVEL=INFO                     # Log level
```

### 📦 Provider Configuration (providers.json)

**Fully customizable provider and model configuration system**

#### Configuration Structure

```json
{
  "providers": {
    "provider_id": {
      "name": "Display Name",
      "base_url": "API Base URL",
      "api_key_env": "Environment Variable Name",
      "models": ["Model List"]
    }
  },
  "presets": {
    "preset_id": {
      "name": "Preset Name",
      "description": "Description",
      "super_model": "Super Model",
      "big_model": "Big Model",
      "small_model": "Small Model",
      "provider": "Provider ID or mixed"
    }
  }
}
```

#### Default Provider Configurations

**OpenAI Provider**
```json
"openai": {
  "name": "OpenAI",
  "base_url": "https://api.openai.com/v1",
  "api_key_env": "OPENAI_API_KEY",
  "models": [
    "o3-mini", "o1", "o1-mini", "o1-pro", "o1-preview",
    "gpt-4o", "gpt-4o-2024-11-20", "gpt-4o-mini",
    "gpt-4-turbo", "gpt-4", "chatgpt-4o-latest"
  ]
}
```

**Google Gemini Provider**
```json
"google": {
  "name": "Google Gemini",
  "base_url": "https://generativelanguage.googleapis.com/v1beta",
  "api_key_env": "GEMINI_API_KEY",
  "models": [
    "gemini-2.0-flash-exp", "gemini-2.0-flash",
    "gemini-1.5-pro", "gemini-1.5-flash",
    "gemini-exp-1114", "gemini-2.5-pro"
  ]
}
```

**Anthropic Provider**
```json
"anthropic": {
  "name": "Anthropic",
  "base_url": "https://api.anthropic.com",
  "api_key_env": "ANTHROPIC_API_KEY",
  "models": [
    "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229", "claude-3-sonnet-20240229"
  ]
}
```

#### Custom Provider Examples

**Adding Third-party API Providers (e.g., Moonshot, DeepSeek)**

```json
"moonshot": {
  "name": "Kimi AI",
  "base_url": "https://api.moonshot.cn/v1",
  "api_key_env": "MOONSHOT_API_KEY",
  "models": ["kimi-latest", "kimi-k2-0711-preview"]
},
"deepseek": {
  "name": "DeepSeek",
  "base_url": "https://api.deepseek.com/v1",
  "api_key_env": "DEEPSEEK_API_KEY",
  "models": ["deepseek-v3", "deepseek-coder"]
}
```

**Corresponding .env Configuration**
```dotenv
MOONSHOT_API_KEY="sk-your-moonshot-key"
DEEPSEEK_API_KEY="sk-your-deepseek-key"
```


---


### 📊 API Interface Operations

**View Current Configuration**
```bash
GET /config
```

**Quick Switch with Presets**
```bash
POST /switch_model
{
  "preset": "openai_reasoning",
  "preserve_conversation": true
}
```

**Custom Three-tier Configuration**
```bash
POST /switch_model
{
  "super_model": "o1-preview",
  "big_model": "claude-3-5-sonnet-20241022",
  "small_model": "gpt-4o-mini",
  "preserve_conversation": true
}
```

**View All Available Models**
```bash
GET /models
```

**View All Presets**
```bash
GET /presets
```


### 📊 API Interface Operations

**View Current Configuration**
```bash
GET /config
```

**Quick Switch with Presets**
```bash
POST /switch_model
{
  "preset": "openai_reasoning",
  "preserve_conversation": true
}
```

**Custom Three-tier Configuration**
```bash
POST /switch_model
{
  "super_model": "o1-preview",
  "big_model": "claude-3-5-sonnet-20241022",
  "small_model": "gpt-4o-mini",
  "preserve_conversation": true
}
```

**View All Available Models**
```bash
GET /models
```

**View All Presets**
```bash
GET /presets
```

### Interactive Management

```bash
# In interactive interface
record → enable/disable    # Enable/disable recording
load → select file         # Read historical records
logs → detail/export       # View/export logs
```

**Other Common APIs**
```bash
# View server status
curl http://localhost:8082/status

# View current configuration
curl http://localhost:8082/config

# View all available models
curl http://localhost:8082/models

# View all presets
curl http://localhost:8082/presets
```

## 🤝 Contributing

Welcome to contribute code! Please Fork the repository and submit a Pull Request.

## 📄 License

This project is licensed under the MIT License.

---

**中文版本**: [README.md](README.md)
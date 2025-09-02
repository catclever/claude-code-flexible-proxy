**Languages**: [🇨🇳 中文](README.md) | [🇺🇸 English](README_EN.md)

---

# Claude Code Intelligent Proxy Server 🚀

**A proxy server that enables Claude Code to seamlessly use multiple AI models**

Supports OpenAI, Google Gemini, and Anthropic platforms through a unified API interface, with real-time model switching, intelligent transparent proxy, and conversation history management.

![Claude Code Proxy](pic.png)

## ✨ Core Features

- 🔄 **Real-time Model Switching**: Seamlessly switch between models during conversations
- 🎛️ **Preset Configurations**: One-click switching to optimal model combinations
- 🔀 **Intelligent Transparent Proxy**: Automatically detects and supports both Claude Pro subscribers and API key users
- 💬 **Conversation History Management**: Automatic recording and management of conversation context
- 🌐 **Cross-platform Configuration**: Large and small models can come from different providers
- 🖥️ **Interactive Terminal**: Visual configuration and management interface

## 🚀 Quick Start

### Method 1: Interactive Launch (Recommended)

```bash
# Clone the project
git clone https://github.com/catclever/claude-code-flexible-proxy.git
cd claude-code-flexible-proxy

# Configure environment variables
cp .env.example .env
# Edit .env file and fill in your API Keys

# Start interactive application
uv run python interactive.py
```

### Method 2: Server Mode

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Configure environment variables
cp .env.example .env
# Edit .env file

# Start server
uv run uvicorn server:app --host 0.0.0.0 --port 8082
```

### Integration with Claude Code

```bash
# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Connect to proxy server
ANTHROPIC_BASE_URL=http://localhost:8082 claude
```

## ⚙️ Configuration

### Environment Variables

Create `.env` file:

```dotenv
# API Keys (at least one required)
OPENAI_API_KEY="your-openai-key"
GEMINI_API_KEY="your-google-key"
ANTHROPIC_API_KEY="your-anthropic-key"

# Optional: Default model configuration
BIG_MODEL="gpt-4o"
SMALL_MODEL="gpt-4o-mini"
```

## 🔄 Real-time Model Switching

### Quick Switch with Presets

```bash
POST /switch_model
{
  "preset": "cross_premium",
  "preserve_conversation": true
}
```

### Custom Cross-platform Configuration

```bash
POST /switch_model
{
  "big_model": "claude-3-5-sonnet-20241022",
  "small_model": "gpt-4o-mini",
  "preserve_conversation": true
}
```

### View Current Configuration

```bash
GET /config
```

### 🔀 Transparent Proxy Mode

Intelligent transparent proxy support for Claude Pro subscribers and API key users:

```bash
# Switch in interactive interface
toggle
```

- **Claude Pro Users**: Zero configuration, automatic authentication passthrough
- **API Key Users**: Set `ANTHROPIC_API_KEY` environment variable

## 💬 Conversation History Management

```bash
# View conversation history
GET /conversation?limit=10

# Clear conversation history
DELETE /conversation

# Continue historical conversation
POST /conversation/continue
```

## 🐳 Docker Deployment

### Docker Compose (Recommended)

```yaml
services:
  claude-proxy:
    image: ghcr.io/1rgs/claude-code-proxy:latest
    restart: unless-stopped
    env_file: .env
    ports:
      - "8082:8082"
```

### Direct Run

```bash
docker run -d --env-file .env -p 8082:8082 ghcr.io/1rgs/claude-code-proxy:latest
```

## 🎯 Usage Examples

### Scenario 1: Switch Models During Conversation

```bash
# 1. Start conversation with small model
curl -X POST http://localhost:8082/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model": "haiku", "messages": [{"role": "user", "content": "Hello"}]}'

# 2. Switch to large model
curl -X POST http://localhost:8082/switch_model \
  -d '{"preset": "cross_premium", "preserve_conversation": true}'

# 3. Continue conversation with new model but preserve history
curl -X POST http://localhost:8082/v1/messages \
  -d '{"model": "sonnet", "messages": [{"role": "user", "content": "Explain in detail"}]}'
```

### Scenario 2: Interactive Management

```bash
# Start interactive application
uv run python interactive.py

# In the interface:
# - View current status
# - Select preset configurations
# - Test configurations
# - View conversation history
```

## 🔧 Supported Models

### OpenAI Models (30+)
- **O Series**: `o3-mini`, `o1`, `o1-mini`, `o1-pro`
- **GPT-4o Series**: `gpt-4o`, `gpt-4o-mini`, `chatgpt-4o-latest`
- **GPT-4 Series**: `gpt-4-turbo`, `gpt-4`

### Google Gemini Models (15+)
- **Gemini 2.0**: `gemini-2.0-flash`, `gemini-2.0-flash-exp`
- **Gemini 1.5**: `gemini-1.5-pro`, `gemini-1.5-flash`
- **Experimental**: `gemini-exp-1114`, `gemini-2.5-pro`

### Anthropic Models (13+)
- **Claude 3.5**: `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`
- **Claude 3**: `claude-3-opus-20240229`, `claude-3-sonnet-20240229`

## 🔧 Troubleshooting

### Common Issues

**Q: Incorrect response format after model switching**  
A: Check if the target model supports the current request format

**Q: Invalid API Key error**  
A: Verify that the API Key in `.env` file is correct

**Q: Conversation history lost**  
A: Check if `preserve_conversation` parameter is set to `true`

### Debug Mode

```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG
uv run python interactive.py

# View real-time logs
curl http://localhost:8082/debug_logs?log_type=all&limit=100
```

## 🤝 Contributing

Welcome to contribute code! Please Fork the repository and submit a Pull Request.

## 📄 License

This project is licensed under the MIT License.

---

**中文版本**: [README.md](README.md)
**Languages**: [🇨🇳 中文](README.md) | [🇺🇸 English](README_EN.md)

---

# Claude Code 智能代理服务器 🚀

**让 Claude Code 无缝使用多种 AI 模型的代理服务器**

通过统一的 API 接口，支持 OpenAI、Google Gemini、Anthropic 三大平台模型，具备实时模型切换、透明代理和对话历史管理功能。

![Claude Code Proxy](pic.png)

## ✨ 核心特性

- 🔄 **实时模型切换**: 对话中无缝切换不同模型
- 🎛️ **预设配置**: 一键切换最佳模型组合
- 🔀 **智能透明代理**: 自动检测并支持Claude Pro订阅用户和API密钥用户
- 💬 **对话历史管理**: 自动记录和管理对话上下文
- 🌐 **跨平台配置**: 大小模型可来自不同提供商
- 🖥️ **交互式终端**: 可视化配置和管理界面

## 🚀 快速开始

### 方式一：交互式启动（推荐）

```bash
# 克隆项目
git clone https://github.com/catclever/claude-code-flexible-proxy.git
cd claude-code-flexible-proxy

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 API Keys

# 启动交互式应用
uv run python interactive.py
```

### 方式二：服务器模式

```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 启动服务器
uv run uvicorn server:app --host 0.0.0.0 --port 8082
```

### 与 Claude Code 集成

```bash
# 安装 Claude Code
npm install -g @anthropic-ai/claude-code

# 连接到代理服务器
ANTHROPIC_BASE_URL=http://localhost:8082 claude
```

## ⚙️ 配置说明

### 环境变量配置

创建 `.env` 文件：

```dotenv
# API Keys (至少需要一个)
OPENAI_API_KEY="your-openai-key"
GEMINI_API_KEY="your-google-key"
ANTHROPIC_API_KEY="your-anthropic-key"

# 可选：默认模型配置
BIG_MODEL="gpt-4o"
SMALL_MODEL="gpt-4o-mini"
```

## 🔄 实时模型切换

### 使用预设快速切换

```bash
POST /switch_model
{
  "preset": "cross_premium",
  "preserve_conversation": true
}
```

### 自定义跨平台配置

```bash
POST /switch_model
{
  "big_model": "claude-3-5-sonnet-20241022",
  "small_model": "gpt-4o-mini",
  "preserve_conversation": true
}
```

### 查看当前配置

```bash
GET /config
```

### 🔀 透明代理模式

支持Claude Pro订阅用户和API密钥用户的智能透明代理：

```bash
# 在交互式界面中切换
toggle
```

- **Claude Pro用户**: 零配置，自动透传认证
- **API密钥用户**: 设置 `ANTHROPIC_API_KEY` 环境变量

## 💬 对话历史管理

```bash
# 查看对话历史
GET /conversation?limit=10

# 清空对话历史
DELETE /conversation

# 继续历史对话
POST /conversation/continue
```

## 🐳 Docker 部署

### Docker Compose（推荐）

```yaml
services:
  claude-proxy:
    image: ghcr.io/1rgs/claude-code-proxy:latest
    restart: unless-stopped
    env_file: .env
    ports:
      - "8082:8082"
```

### 直接运行

```bash
docker run -d --env-file .env -p 8082:8082 ghcr.io/1rgs/claude-code-proxy:latest
```

## 🎯 使用场景示例

### 场景1：对话中切换模型

```bash
# 1. 用小模型开始对话
curl -X POST http://localhost:8082/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model": "haiku", "messages": [{"role": "user", "content": "你好"}]}'

# 2. 切换到大模型
curl -X POST http://localhost:8082/switch_model \
  -d '{"preset": "cross_premium", "preserve_conversation": true}'

# 3. 继续对话，使用新模型但保持历史
curl -X POST http://localhost:8082/v1/messages \
  -d '{"model": "sonnet", "messages": [{"role": "user", "content": "详细解释"}]}'
```

### 场景2：交互式管理

```bash
# 启动交互式应用
uv run python interactive.py

# 在界面中：
# - 查看当前状态
# - 选择预设配置
# - 测试配置
# - 查看对话历史
```

## 🔧 支持的模型

### OpenAI 模型 (30+)
- **O 系列**: `o3-mini`, `o1`, `o1-mini`, `o1-pro`
- **GPT-4o 系列**: `gpt-4o`, `gpt-4o-mini`, `chatgpt-4o-latest`
- **GPT-4 系列**: `gpt-4-turbo`, `gpt-4`

### Google Gemini 模型 (15+)
- **Gemini 2.0**: `gemini-2.0-flash`, `gemini-2.0-flash-exp`
- **Gemini 1.5**: `gemini-1.5-pro`, `gemini-1.5-flash`
- **实验版本**: `gemini-exp-1114`, `gemini-2.5-pro`

### Anthropic 模型 (13+)
- **Claude 3.5**: `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`
- **Claude 3**: `claude-3-opus-20240229`, `claude-3-sonnet-20240229`

## 🔧 故障排除

### 常见问题

**Q: 模型切换后响应格式不正确**  
A: 检查目标模型是否支持当前请求格式

**Q: API Key 无效错误**  
A: 确认 `.env` 文件中的 API Key 正确

**Q: 对话历史丢失**  
A: 检查 `preserve_conversation` 参数是否设置为 `true`

### 调试模式

```bash
# 启用详细日志
export LOG_LEVEL=DEBUG
uv run python interactive.py

# 查看实时日志
curl http://localhost:8082/debug_logs?log_type=all&limit=100
```

## 🤝 贡献

欢迎贡献代码！请 Fork 仓库并提交 Pull Request。

## 📄 许可证

本项目采用 MIT 许可证。

---

**English Version**: [README_EN.md](README_EN.md)

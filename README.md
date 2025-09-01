# 智能多模型代理服务器 🔄

**让 Claude Code 等 Anthropic 客户端无缝使用 60+ 种 AI 模型** 🤝

一个强大的代理服务器，支持 OpenAI、Google Gemini、Anthropic 三大平台的 60+ 种模型，具备实时模型切换、对话历史管理、跨平台配置等高级功能。通过 LiteLLM 实现统一的 API 接口。🌉

![Anthropic API Proxy](pic.png)

## ✨ 核心特性

- 🚀 **60+ 模型支持**: OpenAI (30+) + Gemini (15+) + Anthropic (13+)
- 🔄 **实时模型切换**: 对话中无缝切换不同模型
- 🎛️ **7种预设配置**: 一键切换最佳模型组合
- 💬 **对话历史管理**: 自动记录和管理对话上下文
- 🌐 **跨平台配置**: 大小模型可来自不同提供商
- 🖥️ **交互式终端**: 可视化配置和管理界面
- 📊 **智能模型映射**: 自动识别模型提供商并添加正确前缀

## Quick Start ⚡

### 方式一：交互式启动（推荐） 🎮

```bash
# 克隆项目
git clone https://github.com/1rgs/claude-code-proxy.git
cd claude-code-proxy

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 API Keys

# 启动交互式应用
uv run python interactive.py
```

交互式应用提供：
- 🎛️ 可视化配置界面
- 🔄 实时模型切换
- 📊 服务器状态监控
- 💬 对话历史管理
- 🧪 配置测试功能

### 方式二：传统服务器模式 🖥️

#### Prerequisites

- OpenAI API key 🔑
- Google AI Studio (Gemini) API key (可选) 🔑
- Anthropic API key (可选) 🔑
- [uv](https://github.com/astral-sh/uv) installed

#### From source

1. **Clone this repository**:
   ```bash
   git clone https://github.com/1rgs/claude-code-proxy.git
   cd claude-code-proxy
   ```

2. **Install uv** (if you haven't already):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   *(`uv` will handle dependencies based on `pyproject.toml` when you run the server)*

3. **Configure Environment Variables**:
   Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and fill in your API keys and model configurations:

   *   `ANTHROPIC_API_KEY`: (Optional) Needed only if proxying *to* Anthropic models.
   *   `OPENAI_API_KEY`: Your OpenAI API key (Required if using the default OpenAI preference or as fallback).
   *   `GEMINI_API_KEY`: Your Google AI Studio (Gemini) API key (Required if PREFERRED_PROVIDER=google).
   *   `PREFERRED_PROVIDER` (Optional): Set to `openai` (default), `google`, or `anthropic`. This determines the primary backend for mapping `haiku`/`sonnet`.
   *   `BIG_MODEL` (Optional): The model to map `sonnet` requests to. Defaults to `gpt-4.1` (if `PREFERRED_PROVIDER=openai`) or `gemini-2.5-pro-preview-03-25`. Ignored when `PREFERRED_PROVIDER=anthropic`.
   *   `SMALL_MODEL` (Optional): The model to map `haiku` requests to. Defaults to `gpt-4.1-mini` (if `PREFERRED_PROVIDER=openai`) or `gemini-2.0-flash`. Ignored when `PREFERRED_PROVIDER=anthropic`.

   **Mapping Logic:**
   - If `PREFERRED_PROVIDER=openai` (default), `haiku`/`sonnet` map to `SMALL_MODEL`/`BIG_MODEL` prefixed with `openai/`.
   - If `PREFERRED_PROVIDER=google`, `haiku`/`sonnet` map to `SMALL_MODEL`/`BIG_MODEL` prefixed with `gemini/` *if* those models are in the server's known `GEMINI_MODELS` list (otherwise falls back to OpenAI mapping).
   - If `PREFERRED_PROVIDER=anthropic`, `haiku`/`sonnet` requests are passed directly to Anthropic with the `anthropic/` prefix without remapping to different models.

4. **Run the server**:
   ```bash
   uv run uvicorn server:app --host 0.0.0.0 --port 8082 --reload
   ```
   *(`--reload` is optional, for development)*

#### Docker

If using docker, download the example environment file to `.env` and edit it as described above.
```bash
curl -O .env https://raw.githubusercontent.com/1rgs/claude-code-proxy/refs/heads/main/.env.example
```

Then, you can either start the container with [docker compose](https://docs.docker.com/compose/) (preferred):

```yml
services:
  proxy:
    image: ghcr.io/1rgs/claude-code-proxy:latest
    restart: unless-stopped
    env_file: .env
    ports:
      - 8082:8082
```

Or with a command:

```bash
docker run -d --env-file .env -p 8082:8082 ghcr.io/1rgs/claude-code-proxy:latest
```

### Using with Claude Code 🎮

1. **Install Claude Code** (if you haven't already):
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```

2. **Connect to your proxy**:
   ```bash
   ANTHROPIC_BASE_URL=http://localhost:8082 claude
   ```

3. **That's it!** Your Claude Code client will now use the configured backend models (defaulting to Gemini) through the proxy. 🎯

## 🎯 智能模型映射与配置

### 模型映射逻辑

代理服务器自动将 Claude 模型映射到配置的后端模型：

| Claude 模型 | 映射目标 | 说明 |
|------------|---------|------|
| `haiku` | `SMALL_MODEL` | 快速响应模型 |
| `sonnet` | `BIG_MODEL` | 高性能模型 |

### 🚀 支持的 60+ 模型

#### OpenAI 模型 (30+)
**O 系列 (推理优化)**
- `o3-mini`, `o1`, `o1-mini`, `o1-pro`, `o1-preview`

**GPT-4o 系列 (最新旗舰)**
- `gpt-4o`, `gpt-4o-2024-11-20`, `gpt-4o-2024-08-06`, `gpt-4o-mini`
- `gpt-4o-audio-preview`, `gpt-4o-realtime-preview`, `chatgpt-4o-latest`

**GPT-4 Turbo 系列**
- `gpt-4-turbo`, `gpt-4-turbo-2024-04-09`, `gpt-4-0125-preview`

**经典 GPT 系列**
- `gpt-4`, `gpt-3.5-turbo`, `gpt-3.5-turbo-16k`

#### Google Gemini 模型 (15+)
**Gemini 2.0 系列 (最新)**
- `gemini-2.0-flash-exp`, `gemini-2.0-flash-thinking-exp`, `gemini-2.0-flash`

**Gemini 1.5 系列 (主力)**
- `gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-1.5-flash-8b`
- `gemini-1.5-pro-002`, `gemini-1.5-flash-002`

**实验版本**
- `gemini-exp-1114`, `gemini-exp-1121`, `gemini-2.5-pro`

#### Anthropic 模型 (13+)
**Claude 3.5 系列 (最新)**
- `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`

**Claude 3 系列**
- `claude-3-opus-20240229`, `claude-3-sonnet-20240229`, `claude-3-haiku-20240307`

**经典版本**
- `claude-2.1`, `claude-2.0`, `claude-instant-1.2`

### 🎛️ 7种预设配置

| 预设名称 | 大模型 | 小模型 | 适用场景 |
|---------|--------|--------|----------|
| `openai_premium` | GPT-4o | GPT-4o Mini | OpenAI 高端体验 |
| `gemini_balanced` | Gemini 1.5 Pro | Gemini 1.5 Flash | Google AI 平衡 |
| `anthropic_pure` | Claude 3.5 Sonnet | Claude 3.5 Haiku | 原生 Claude 体验 |
| `cross_premium` | GPT-4o | Gemini Flash | 跨平台高端 |
| `cross_balanced` | Gemini Pro | GPT-4o Mini | 跨平台经济 |
| `openai_reasoning` | O1 Preview | GPT-4o Mini | 推理优化 |
| `cross_speed` | Claude Haiku | Gemini Flash | 速度优先 |

## ⚙️ 配置管理

### 环境变量配置

创建 `.env` 文件并配置以下变量：

```dotenv
# API Keys (至少需要一个)
OPENAI_API_KEY="your-openai-key"
GEMINI_API_KEY="your-google-key"
ANTHROPIC_API_KEY="your-anthropic-key"

# 可选：默认模型配置
BIG_MODEL="gpt-4o"
SMALL_MODEL="gpt-4o-mini"

# 可选：代理服务器设置
PROXY_SERVER_ENABLED="true"
```

### 配置方式对比

| 配置方式 | 优势 | 适用场景 |
|---------|------|----------|
| **交互式终端** | 可视化、实时切换 | 开发调试、配置管理 |
| **API 接口** | 程序化控制 | 自动化、集成应用 |
| **环境变量** | 简单稳定 | 生产部署、容器化 |
| **预设配置** | 一键切换 | 快速体验、场景切换 |

### 高级配置选项

#### 1. 跨平台模型组合
```bash
# 大模型用 Claude，小模型用 Gemini
POST /switch_model
{
  "big_model": "claude-3-5-sonnet-20241022",
  "small_model": "gemini-1.5-flash"
}
```

#### 2. 对话历史持久化
```bash
# 启用对话记录到文件
POST /conversation/enable
{
  "file_path": "/path/to/conversation.json"
}
```

#### 3. 调试和监控
```bash
# 查看调试日志
GET /debug_logs?log_type=model_mapping&limit=50

# 查看请求统计
GET /conversation/status
```

## 🔄 实时模型切换与对话管理

### 模型切换 API

#### 查看当前配置
```bash
GET /config
```

#### 使用预设快速切换
```bash
POST /switch_model
Content-Type: application/json

{
  "preset": "cross_premium",
  "preserve_conversation": true
}
```

#### 自定义跨平台配置
```bash
POST /switch_model
Content-Type: application/json

{
  "big_model": "claude-3-5-sonnet-20241022",
  "small_model": "gpt-4o-mini",
  "preserve_conversation": true
}
```

#### 查看所有可用模型和预设
```bash
GET /models
```

### 对话历史管理 API

#### 查看对话历史
```bash
GET /conversation?limit=10
```

返回示例：
```json
{
  "messages": [
    {
      "timestamp": "2024-01-01T12:00:00",
      "role": "user",
      "content": "你好",
      "model_used": "openai/gpt-4o-mini"
    },
    {
      "timestamp": "2024-01-01T12:00:01",
      "role": "assistant",
      "content": "你好！我是助手...",
      "model_used": "openai/gpt-4o-mini"
    }
  ],
  "total_count": 2
}
```

#### 清空对话历史
```bash
DELETE /conversation
```

#### 使用历史对话继续聊天
```bash
POST /conversation/continue
Content-Type: application/json

{
  "model": "sonnet",
  "max_tokens": 200,
  "messages": [
    {"role": "user", "content": "总结一下我们刚才的对话"}
  ]
}
```

## 🎯 使用场景与示例

### 场景1：在对话中切换模型
```bash
# 1. 用 Claude Haiku 开始对话
curl -X POST http://localhost:8082/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "haiku",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "介绍一下你自己"}]
  }'

# 2. 切换到更强大的模型
curl -X POST http://localhost:8082/switch_model \
  -H "Content-Type: application/json" \
  -d '{
    "preset": "cross_premium",
    "preserve_conversation": true
  }'

# 3. 继续对话，现在使用新模型但保持历史
curl -X POST http://localhost:8082/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sonnet",
    "max_tokens": 200,
    "messages": [{"role": "user", "content": "详细解释一下你的能力"}]
  }'
```

### 场景2：使用交互式终端管理
```bash
# 启动交互式应用
uv run python interactive.py

# 在交互界面中：
# 1. 查看当前状态
# 2. 选择预设配置
# 3. 测试配置
# 4. 查看对话历史
# 5. 管理调试日志
```

### 场景3：Claude Code 集成
```bash
# 设置环境变量
export ANTHROPIC_BASE_URL=http://localhost:8082

# 启动 Claude Code
claude

# 现在 Claude Code 会通过代理使用配置的模型
# 可以在对话中实时切换模型而不中断会话
```

## 🔧 工作原理

这个代理服务器的工作流程：

1. **接收请求** - 接收 Anthropic API 格式的请求 📥
2. **智能路由** - 根据配置将请求路由到对应的提供商 🎯
3. **格式转换** - 通过 LiteLLM 进行 API 格式转换 🔄
4. **模型映射** - 自动添加正确的模型前缀 📊
5. **发送请求** - 向目标提供商发送请求 📤
6. **响应转换** - 将响应转换回 Anthropic 格式 🔄
7. **历史记录** - 自动记录对话历史 💾
8. **返回结果** - 返回格式化的响应给客户端 ✅

支持流式和非流式响应，与所有 Claude 客户端完全兼容。🌊

## 🌟 高级特性

### 智能模型前缀处理
- 自动识别模型所属提供商
- 智能添加 `openai/`、`gemini/`、`anthropic/` 前缀
- 支持模型名称验证和错误提示

### 对话上下文管理
- 自动记录所有对话历史
- 支持跨模型切换时保持上下文
- 可配置历史记录数量限制
- 支持对话导出和导入

### 调试和监控
- 实时请求日志记录
- 模型映射过程可视化
- 性能统计和错误追踪
- 支持日志导出和分析

### 安全和稳定性
- API Key 安全存储
- 请求频率限制
- 错误重试机制
- 优雅的服务降级

## 🐳 Docker 部署

### 使用 Docker Compose（推荐）
```yaml
services:
  claude-proxy:
    image: ghcr.io/1rgs/claude-code-proxy:latest
    restart: unless-stopped
    env_file: .env
    ports:
      - "8082:8082"
    volumes:
      - ./conversations:/app/conversations
      - ./logs:/app/logs
```

### 直接运行 Docker
```bash
docker run -d \
  --name claude-proxy \
  --env-file .env \
  -p 8082:8082 \
  -v $(pwd)/conversations:/app/conversations \
  ghcr.io/1rgs/claude-code-proxy:latest
```

## 🔧 故障排除

### 常见问题

**Q: 模型切换后响应格式不正确**
A: 检查目标模型是否支持当前请求格式，某些模型可能不支持特定功能

**Q: API Key 无效错误**
A: 确认 `.env` 文件中的 API Key 正确，并且对应的提供商服务可用

**Q: 对话历史丢失**
A: 检查 `preserve_conversation` 参数是否设置为 `true`

**Q: 交互式终端无法启动**
A: 确保安装了所有依赖：`uv sync`

### 调试模式
```bash
# 启用详细日志
export LOG_LEVEL=DEBUG
uv run python interactive.py

# 查看实时日志
curl http://localhost:8082/debug_logs?log_type=all&limit=100
```

## 🤝 贡献指南

我们欢迎各种形式的贡献！🎁

### 如何贡献
1. Fork 这个仓库
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'Add amazing feature'`
4. 推送分支：`git push origin feature/amazing-feature`
5. 创建 Pull Request

### 开发环境设置
```bash
# 克隆仓库
git clone https://github.com/1rgs/claude-code-proxy.git
cd claude-code-proxy

# 安装依赖
uv sync

# 运行测试
uv run pytest

# 启动开发服务器
uv run uvicorn server:app --reload --host 0.0.0.0 --port 8082
```

### 贡献类型
- 🐛 Bug 修复
- ✨ 新功能开发
- 📚 文档改进
- 🎨 UI/UX 优化
- ⚡ 性能优化
- 🧪 测试覆盖

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [LiteLLM](https://github.com/BerriAI/litellm) - 统一的 LLM API 接口
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的 Web 框架
- [Rich](https://github.com/Textualize/rich) - 美观的终端界面
- [Anthropic](https://www.anthropic.com/) - Claude API
- [OpenAI](https://openai.com/) - GPT API
- [Google](https://ai.google.dev/) - Gemini API

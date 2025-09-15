**Languages**: [🇨🇳 中文](README.md) | [🇺🇸 English](README_EN.md)

---

# Claude Code 智能代理服务器 🚀

**让 Claude Code 无缝使用多种 AI 模型的代理服务器**

通过统一的 API 接口，支持 OpenAI、Google Gemini、Anthropic 三大平台模型，具备实时模型切换、超级模型支持、透明代理和智能对话管理功能。

![Claude Code Proxy](pic.png)

## ✨ 核心特性

- 🌐 **自动代理**: 启动/关闭项目时，自动设置/清理claude code代理（仅交互式模式）
- ⚡ **三层模型**: super_model + big_model + small_model 模型组合，对应claude code的 opus、sonnet、haiku 三级模型；三层模型可来自不同提供商，灵活搭配
- 🔄 **模型切换**: 对话中无缝切换不同模型，无需重启服务
- 🎛️ **预设配置**: 可以预设不同的模式组合，在使用过程中一键切换
- 🔀 **透明代理**: 自动检测并支持Claude Pro订阅用户和API密钥用户（推荐，按token计费完全抗不住claude code的霍霍）
- 💬 **对话管理**: 完整对话历史恢复、日志解析和去重功能


## 📦 基础安装和配置

```bash
# 1. 克隆项目
git clone https://github.com/catclever/claude-code-flexible-proxy.git
cd claude-code-flexible-proxy

# 2. 安装 UV 包管理器
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. 安装项目依赖
uv sync

# 4. 配置 API 密钥
cp .env.example .env
# 编辑 .env 文件，填入你的 API Keys

# 5. 配置提供商和模型
cp providers.json.example providers.json
# 可选：自定义 providers.json 中的模型和预设
```

---

## ⚙️ 配置说明

### 🔑 API 密钥配置 (.env)

```dotenv
# API Keys (至少配置一个)
OPENAI_API_KEY="sk-your-openai-key-here"
GEMINI_API_KEY="your-google-gemini-key-here"
ANTHROPIC_API_KEY="sk-ant-your-anthropic-key-here"

# 可选：默认模型配置
DEFAULT_PRESET="default"           # 使用预设配置
# 或者直接指定模型
SUPER_MODEL="gpt-4o"
BIG_MODEL="gpt-4o"
SMALL_MODEL="gpt-4o-mini"

# 可选：服务器配置
PORT=8082                          # 服务器端口
LOG_LEVEL=INFO                     # 日志级别
```

### 📦 提供商配置 (providers.json)

**完全自定义的提供商和模型配置系统**

#### 配置结构说明

```json
{
  "providers": {
    "提供商ID": {
      "name": "显示名称",
      "base_url": "API基础URL",
      "api_key_env": "环境变量名",
      "models": ["模型列表"]
    }
  },
  "presets": {
    "预设ID": {
      "name": "预设名称",
      "description": "描述信息",
      "super_model": "超级模型",
      "big_model": "大模型",
      "small_model": "小模型",
      "provider": "提供商ID 或 mixed"
    }
  }
}
```
使用的模型必须在配置的提供商模型列表中。
如果提供商id是 mixed， 可以选择配置过的任何一个提供商的模型；如果提供商提供的模型存在重名，则会选择配置中位置靠前的提供商。
预设ID为Default的配置会被默认使用。


**对应的 .env 配置**
```dotenv
MOONSHOT_API_KEY="sk-your-moonshot-key"
DEEPSEEK_API_KEY="sk-your-deepseek-key"
```


---

## 🎛️ 交互式模式（推荐）

**适合日常使用，提供可视化管理界面**

### 启动交互式应用

```bash
# 启动交互式管理界面
uv run python interactive.py

# 或指定端口
uv run python interactive.py --port 8080
```

### 交互式功能列表

| 命令 | 图标 | 功能描述 |
|------|------|----------|
| `preset` | 🎛️ | **应用预设配置** - 快速切换8种模型组合预设 |
| `config` | 🔧 | **自定义模型配置** - 手动配置三层模型架构 |
| `toggle` | 🔄 | **切换代理状态** - 启用/禁用代理模式 |
| `test` | 🧪 | **测试当前配置** - 发送测试请求验证连接 |
| `record` | 📝 | **对话记录控制** - 管理对话记录功能 |
| `load` | 📂 | **读取对话记录文件** - 从文件读取并恢复对话记录 |
| `logs` | 📜 | **查看调试日志** - 查看和管理系统调试日志 |
| `verbose` | 🔊 | **切换请求日志显示** - 控制是否显示详细的API请求日志 |
| `providers` | 📡 | **查看提供商信息** - 显示API密钥状态和模型列表 |
| `presets` | 📋 | **查看预设列表** - 浏览所有可用的模型组合预设 |
| `env` | ⚙️ | **重新配置环境变量** - 修复Claude Code环境配置 |
| `help` | ❓ | **帮助信息** - 显示详细使用说明 |
| `quit` | 🚪 | **退出程序** - 安全退出并自动清理资源 |

### 交互式使用流程

```bash
# 1. 启动后会自动：
#    - 🚀 启动代理服务器
#    - 🔧 配置 Claude Code 环境变量
#    - 🖥️ 显示交互式管理菜单

# 2. 选择预设配置
preset → 选择适合的模型组合

# 3. 测试配置
test → 验证API连接和模型响应

# 4. 使用 Claude Code
# 现在可以直接使用 Claude Code，它会自动连接到代理服务器
```

---

## 💻 服务器模式
（未经过严格测试，如有问题请随时提出）

**适合部署到服务器或需要API访问的场景**

### 启动服务器

```bash
# 直接启动服务器
uv run uvicorn server:app --host 0.0.0.0 --port 8082

# 开发模式（自动重载）
uv run uvicorn server:app --host 0.0.0.0 --port 8082 --reload
```

### 手动配置 Claude Code 环境

```bash
# 设置环境变量（临时）
ANTHROPIC_BASE_URL=http://localhost:8082 claude

# 或永久设置（bash/zsh）
echo 'export ANTHROPIC_BASE_URL=http://localhost:8082' >> ~/.bashrc
source ~/.bashrc

# fish shell
echo 'set -gx ANTHROPIC_BASE_URL http://localhost:8082' >> ~/.config/fish/config.fish
```

### 服务器模式 API 接口

```bash
# 查看服务器状态
curl http://localhost:8082/status

# 查看当前配置
curl http://localhost:8082/config

# 查看所有可用模型
curl http://localhost:8082/models

# 查看所有预设
curl http://localhost:8082/presets

# 切换模型配置
curl -X POST http://localhost:8082/switch_model \
  -H "Content-Type: application/json" \
  -d '{"preset": "openai_reasoning", "preserve_conversation": true}'

# 代理控制
curl -X POST http://localhost:8082/proxy_server/disable  # 禁用代理
curl -X POST http://localhost:8082/proxy_server/enable   # 启用代理
```

---


### 📊 API 接口操作

**查看当前配置**
```bash
GET /config
```

**使用预设快速切换**
```bash
POST /switch_model
{
  "preset": "openai_reasoning",
  "preserve_conversation": true
}
```

**自定义三层配置**
```bash
POST /switch_model
{
  "super_model": "o1-preview",
  "big_model": "claude-3-5-sonnet-20241022",
  "small_model": "gpt-4o-mini",
  "preserve_conversation": true
}
```

**查看所有可用模型**
```bash
GET /models
```

**查看所有预设**
```bash
GET /presets
```

### 🔀 透明代理模式

**智能透明代理支持Claude Pro订阅用户和API密钥用户**

#### 交互式切换
```bash
# 在交互式界面中
toggle → 一键切换代理/透明模式
```

#### API切换
```bash
# 禁用代理（透明模式）
POST /proxy_server/disable

# 启用代理
POST /proxy_server/enable
```

#### 用户类型支持
- **👑 Claude Pro用户**: 零配置，自动透传认证cookie和session
- **🔑 API密钥用户**: 设置 `ANTHROPIC_API_KEY` 环境变量即可

## 💬 智能对话管理

### 对话记录功能

- **默认禁用**: 保护用户隐私，不自动记录
- **用户控制**: 通过交互界面手动启用/禁用
- **智能去重**: 自动删除重复或部分重复内容
- **完整恢复**: 支持从文件恢复完整对话历史
- **日志解析**: 详细的对话日志分析和导出

### API接口

```bash
# 查看对话历史
GET /conversation?limit=10

# 清空对话历史
DELETE /conversation

# 继续历史对话
POST /conversation/continue

# 获取对话统计
GET /conversation/stats
```

### 交互式管理

```bash
# 在交互界面中
record → enable/disable    # 启用/禁用记录
load → 选择文件           # 读取历史记录
logs → detail/export      # 查看/导出日志
```

**其他常用API**
```bash
# 查看服务器状态
curl http://localhost:8082/status

# 查看当前配置
curl http://localhost:8082/config

# 查看所有可用模型
curl http://localhost:8082/models

# 查看所有预设
curl http://localhost:8082/presets
```


## 🤝 贡献

欢迎贡献代码！请 Fork 仓库并提交 Pull Request。

## 📄 许可证

本项目采用 MIT 许可证。

---

**English Version**: [README_EN.md](README_EN.md)
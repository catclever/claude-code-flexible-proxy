# 对话历史和增强的多模型切换功能

这个项目现在支持强大的新功能：

## 1. 增强的实时模型切换

### 🚀 核心特性

- **跨提供商配置**: 大小模型可以来自不同的提供商
- **智能模型映射**: 自动识别模型所属提供商并添加正确前缀
- **预设配置**: 7种预设组合，一键切换
- **60+模型支持**: OpenAI (30+) + Gemini (15+) + Anthropic (13+)

### 📊 支持的模型

#### OpenAI (30+ 模型)
- **O系列**: o3-mini, o1, o1-mini, o1-pro, o1-preview
- **GPT-4o系列**: gpt-4o, gpt-4o-mini, gpt-4o-audio-preview 等
- **GPT-4 Turbo**: gpt-4-turbo, gpt-4-turbo-2024-04-09 等
- **GPT-3.5系列**: gpt-3.5-turbo, gpt-3.5-turbo-16k 等

#### Gemini (15+ 模型)  
- **Gemini 2.0系列**: gemini-2.0-flash-exp, gemini-2.0-flash-thinking-exp
- **Gemini 1.5系列**: gemini-1.5-pro, gemini-1.5-flash, gemini-1.5-flash-8b
- **实验版本**: gemini-exp-1114, gemini-exp-1121

#### Anthropic (13+ 模型)
- **Claude 3.5系列**: claude-3-5-sonnet-20241022, claude-3-5-haiku-20241022
- **Claude 3系列**: claude-3-opus-20240229, claude-3-sonnet-20240229
- **经典版本**: claude-2.1, claude-instant-1.2

### 🎛️ 预设配置

#### 查看所有模型和预设
```bash
GET /models
```

#### 7种预设配置
1. **openai_only**: GPT-4o + GPT-4o Mini (纯OpenAI)
2. **gemini_only**: Gemini 1.5 Pro + Flash (纯Gemini)  
3. **anthropic_only**: Claude 3.5 Sonnet + Haiku (纯Anthropic)
4. **mixed_premium**: GPT-4o + Gemini Flash (混合高端)
5. **mixed_cost_effective**: Gemini Pro + GPT-4o Mini (混合经济)
6. **reasoning_focused**: O1 + GPT-4o Mini (推理优化)
7. **speed_focused**: Claude Haiku + Gemini Flash (速度优化)

### API 接口

#### 查看当前配置
```bash
GET /config
```

#### 使用预设快速切换
```bash
POST /switch_model
```

```json
{
  "preset": "mixed_premium"  // 使用预设配置
}
```

#### 自定义跨提供商配置
```json
{
  "big_model": "claude-3-5-sonnet-20241022",   // Anthropic
  "small_model": "gpt-4o-mini",                // OpenAI  
  "preserve_conversation": true
}
```

#### 传统配置模式
```json
{
  "preferred_provider": "openai",
  "big_model": "gpt-4o", 
  "small_model": "gpt-4o-mini",
  "preserve_conversation": true
}
```

## 2. 对话历史管理

系统会自动记录所有对话历史，包括用户消息和助手回复，以及使用的模型信息。

### API 接口

#### 查看对话历史
```bash
GET /conversation?limit=10  # limit参数可选
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
```

这个接口会将历史对话与新消息合并，让模型能够看到完整的上下文。

## 使用场景

### 场景1：在对话中切换模型
```bash
# 1. 用Claude Haiku开始对话
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
    "preferred_provider": "openai",
    "big_model": "gpt-4o",
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

### 场景2：查看和管理对话历史
```bash
# 查看对话历史
curl http://localhost:8082/conversation

# 清空对话重新开始
curl -X DELETE http://localhost:8082/conversation

# 使用历史继续对话
curl -X POST http://localhost:8082/conversation/continue \
  -H "Content-Type: application/json" \
  -d '{
    "model": "haiku",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "总结一下我们刚才的对话"}]
  }'
```

## 特性

1. **无缝切换**: 模型切换不会中断当前会话
2. **历史保持**: 切换模型时可以选择保持对话历史
3. **灵活配置**: 支持OpenAI、Google Gemini、Anthropic三种提供商
4. **自动记录**: 所有对话都会自动记录，无需额外配置
5. **兼容性**: 保持与现有API的完全兼容

## 测试

运行测试脚本：
```bash
python conversation_test.py
```

这会测试所有新功能的完整流程。
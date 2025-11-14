from fastapi import FastAPI, Request, HTTPException
import uvicorn
import logging
import json
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional, Union, Literal
import httpx
import os
from fastapi.responses import JSONResponse, StreamingResponse
import litellm
import uuid
import time
import re
from datetime import datetime
import sys
from config import config_manager as global_config

# Configure logging
logging.basicConfig(
    level=logging.WARN,  # Change to INFO level to show more details
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Configure uvicorn to be quieter
import uvicorn
# Tell uvicorn's loggers to be quiet
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

# Create a filter to block any log messages containing specific strings
class MessageFilter(logging.Filter):
    def filter(self, record):
        # Block messages containing these strings
        blocked_phrases = [
            "LiteLLM completion()",
            "HTTP Request:", 
            "selected model name for cost calculation",
            "utils.py",
            "cost_calculator"
        ]
        
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            for phrase in blocked_phrases:
                if phrase in record.msg:
                    return False
        return True

# Apply the filter to the root logger to catch all messages
root_logger = logging.getLogger()
root_logger.addFilter(MessageFilter())

# Custom formatter for model mapping logs
class ColorizedFormatter(logging.Formatter):
    """Custom formatter to highlight model mappings"""
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    def format(self, record):
        if record.levelno == logging.debug and "MODEL MAPPING" in record.msg:
            # Apply colors and formatting to model mapping logs
            return f"{self.BOLD}{self.GREEN}{record.msg}{self.RESET}"
        return super().format(record)

# Apply custom formatter to console handler
for handler in logger.handlers:
    if isinstance(handler, logging.StreamHandler):
        handler.setFormatter(ColorizedFormatter('%(asctime)s - %(levelname)s - %(message)s'))

app = FastAPI()

# Get API keys from environment
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Get OpenAI base URL from environment (if set)
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")

# Dynamic Configuration Manager
class DynamicConfig:
    """动态配置管理类，用于在运行时存储和更新模型配置"""
    def __init__(self):
        # 从环境变量初始化配置
        self.preferred_provider = os.environ.get("PREFERRED_PROVIDER", "openai").lower()
        self.big_model = os.environ.get("BIG_MODEL", "gpt-4.1")
        self.small_model = os.environ.get("SMALL_MODEL", "gpt-4.1-mini")
        self.conversation_history = []  # 存储对话历史（无限制，由Claude Code管理）
        
        # 代理服务器模式控制
        self.proxy_server_enabled = os.environ.get("PROXY_SERVER_ENABLED", "true").lower() == "true"
        self.bypass_message = "Proxy server is disabled. Please use direct API endpoints."
        
        logger.info(f"代理服务器状态: enabled={self.proxy_server_enabled}")
    
    def update_config(self, preferred_provider=None, big_model=None, small_model=None):
        """更新配置"""
        if preferred_provider is not None:
            self.preferred_provider = preferred_provider.lower()
        if big_model is not None:
            self.big_model = big_model
        if small_model is not None:
            self.small_model = small_model
        
        logger.info(f"配置已更新: provider={self.preferred_provider}, big_model={self.big_model}, small_model={self.small_model}")
    
    def toggle_proxy_server(self, enabled=None):
        """切换代理服务器模式"""
        if enabled is not None:
            self.proxy_server_enabled = enabled
        else:
            self.proxy_server_enabled = not self.proxy_server_enabled
        
        status = "启用" if self.proxy_server_enabled else "禁用"
        logger.info(f"代理服务器模式已{status}")
        return self.proxy_server_enabled
    
    def get_config(self):
        """获取当前配置"""
        return {
            "preferred_provider": self.preferred_provider,
            "big_model": self.big_model,
            "small_model": self.small_model,
            "proxy_server_enabled": self.proxy_server_enabled
        }
    
    def sync_with_global_config(self):
        """与全局配置同步"""
        global_status = global_config.get_status()
        self.proxy_server_enabled = global_status["proxy_enabled"]
        self.big_model = global_status["big_model"]
        self.small_model = global_status["small_model"]
    
    def add_conversation_message(self, role, content, model_used, timestamp=None):
        """添加对话消息到历史记录"""
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        message = {
            "timestamp": timestamp,
            "role": role,
            "content": content,
            "model_used": model_used
        }
        
        self.conversation_history.append(message)
    
    def get_conversation_history(self, limit=None):
        """获取对话历史"""
        if limit:
            return self.conversation_history[-limit:]
        return self.conversation_history
    
    def get_conversation_for_model(self):
        """获取适合传递给模型的对话格式"""
        messages = []
        for msg in self.conversation_history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        return messages
    
    def clear_conversation(self):
        """清空对话历史"""
        self.conversation_history = []
    
    def update_conversation_from_messages(self, messages, model_used="unknown"):
        """从完整messages列表更新对话历史"""
        # 清空当前历史，用新的messages列表替换
        self.conversation_history = []
        
        for msg in messages:
            if msg.get('role') in ['user', 'assistant']:
                self.add_conversation_message(
                    role=msg['role'],
                    content=msg.get('content', ''),
                    model_used=model_used
                )
    
    def add_request_log(self, request_data):
        """保持原有接口兼容性，但现在主要用于内部记录"""
        # 用完整messages列表更新对话历史
        if request_data.get('body') and request_data.get('method') == 'POST':
            body = request_data['body']
            if 'messages' in body:
                # 全量更新对话历史（Claude Code每次发送完整消息列表）
                self.update_conversation_from_messages(
                    messages=body['messages'],
                    model_used=request_data.get('model', 'unknown')
                )
    
    def get_request_logs(self, limit=None):
        """保持原有接口兼容性，转换格式"""
        history = self.get_conversation_history(limit)
        # 转换为原来期望的日志格式
        logs = []
        for msg in history:
            logs.append({
                "timestamp": msg["timestamp"],
                "method": "POST",
                "path": "/v1/messages",
                "headers": {},
                "body": {"messages": [{"role": msg["role"], "content": msg["content"]}]},
                "model": msg["model_used"],
                "original_model": msg["model_used"]
            })
        return logs
    
    def clear_request_logs(self):
        """保持原有接口兼容性"""
        self.clear_conversation()

# 使用新的配置系统 (global_config 来自 config.py)
# config_manager = DynamicConfig() # 已移除旧配置系统

# 透明转发函数将在MessagesRequest定义后声明

# 为了向后兼容，保留原有的全局变量，但它们现在从新配置系统获取
status = global_config.get_status()
PREFERRED_PROVIDER = "mixed"  # 新配置系统不使用单一首选提供商
BIG_MODEL = status["big_model"]
SMALL_MODEL = status["small_model"]

# List of OpenAI models
OPENAI_MODELS = [
    # O系列 - 推理模型
    "o3-mini",
    "o1", 
    "o1-mini",
    "o1-pro",
    "o1-preview",
    
    # GPT-4系列 - 最新版本
    "gpt-4o",
    "gpt-4o-2024-11-20",
    "gpt-4o-2024-08-06", 
    "gpt-4o-2024-05-13",
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
    "gpt-4o-audio-preview",
    "gpt-4o-realtime-preview",
    "chatgpt-4o-latest",
    
    # GPT-4 Turbo系列
    "gpt-4-turbo",
    "gpt-4-turbo-2024-04-09",
    "gpt-4-turbo-preview",
    "gpt-4-0125-preview",
    "gpt-4-1106-preview",
    
    # GPT-4经典版本
    "gpt-4",
    "gpt-4-0613",
    "gpt-4-0314",
    
    # GPT-3.5系列
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-0125",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-16k",
    
    # 其他特殊版本
    "gpt-4.5-preview",
    "gpt-4.1",  # Added default big model
    "gpt-4.1-mini", # Added default small model
    "gpt-4o-mini-audio-preview"
]

# List of Gemini models
GEMINI_MODELS = [
    # Gemini 2.0系列
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash-thinking-exp", 
    "gemini-2.0-flash",
    
    # Gemini 1.5系列
    "gemini-1.5-pro",
    "gemini-1.5-pro-002",
    "gemini-1.5-pro-001", 
    "gemini-1.5-pro-exp-0827",
    "gemini-1.5-flash",
    "gemini-1.5-flash-002",
    "gemini-1.5-flash-001",
    "gemini-1.5-flash-8b",
    
    # Gemini 1.0系列
    "gemini-1.0-pro",
    "gemini-1.0-pro-001",
    "gemini-1.0-pro-latest",
    
    # 实验版本
    "gemini-exp-1114",
    "gemini-exp-1121",
    
    # 向后兼容（旧版本名称）
    "gemini-2.5-flash",
    "gemini-2.5-pro"
]

# List of Anthropic models  
ANTHROPIC_MODELS = [
    # Claude 3.5系列
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-20240620", 
    "claude-3-5-haiku-20241022",
    
    # Claude 3系列
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
    
    # Claude 2系列
    "claude-2.1",
    "claude-2.0",
    
    # Claude Instant
    "claude-instant-1.2"
]

# Helper function to determine model provider
def get_model_provider(model_name: str) -> str:
    """确定模型属于哪个提供商 - 使用动态配置"""
    provider_name = global_config.find_model_provider(model_name)
    if provider_name:
        return provider_name
    
    # 回退到硬编码检查（向后兼容）
    if model_name in OPENAI_MODELS:
        return "openai"
    elif model_name in GEMINI_MODELS:
        return "gemini"
    elif model_name in ANTHROPIC_MODELS:
        return "anthropic"
    else:
        return "unknown"

# Helper function to add correct provider prefix
def add_model_prefix(model_name: str) -> str:
    """为模型添加正确的提供商前缀"""
    if model_name.startswith(('openai/', 'gemini/', 'anthropic/')):
        return model_name
    
    provider = get_model_provider(model_name)
    if provider != "unknown":
        return f"{provider}/{model_name}"
    return model_name

# Enhanced mapping presets for common scenarios
MAPPING_PRESETS = {
    "openai_only": {
        "description": "OpenAI模型组合",
        "big_model": "gpt-4o",
        "small_model": "gpt-4o-mini"
    },
    "gemini_only": {
        "description": "Gemini模型组合", 
        "big_model": "gemini-1.5-pro",
        "small_model": "gemini-1.5-flash"
    },
    "anthropic_only": {
        "description": "Anthropic模型组合",
        "big_model": "claude-3-5-sonnet-20241022",
        "small_model": "claude-3-5-haiku-20241022"
    },
    "mixed_premium": {
        "description": "混合高端组合：GPT-4o + Gemini Flash",
        "big_model": "gpt-4o", 
        "small_model": "gemini-1.5-flash"
    },
    "mixed_cost_effective": {
        "description": "混合经济组合：Gemini Pro + GPT-4o Mini", 
        "big_model": "gemini-1.5-pro",
        "small_model": "gpt-4o-mini"
    },
    "reasoning_focused": {
        "description": "推理优化组合：O1 + GPT-4o Mini",
        "big_model": "o1-preview", 
        "small_model": "gpt-4o-mini"
    },
    "speed_focused": {
        "description": "速度优化组合：Claude Haiku + Gemini Flash",
        "big_model": "claude-3-5-haiku-20241022",
        "small_model": "gemini-1.5-flash"
    }
}

# Helper function to clean schema for Gemini
def clean_gemini_schema(schema: Any) -> Any:
    """Recursively removes unsupported fields from a JSON schema for Gemini."""
    if isinstance(schema, dict):
        # Remove specific keys unsupported by Gemini tool parameters
        schema.pop("additionalProperties", None)
        schema.pop("default", None)

        # Check for unsupported 'format' in string types
        if schema.get("type") == "string" and "format" in schema:
            allowed_formats = {"enum", "date-time"}
            if schema["format"] not in allowed_formats:
                logger.debug(f"Removing unsupported format '{schema['format']}' for string type in Gemini schema.")
                schema.pop("format")

        # Recursively clean nested schemas (properties, items, etc.)
        for key, value in list(schema.items()): # Use list() to allow modification during iteration
            schema[key] = clean_gemini_schema(value)
    elif isinstance(schema, list):
        # Recursively clean items in a list
        return [clean_gemini_schema(item) for item in schema]
    return schema

# Models for Anthropic API requests
class ContentBlockText(BaseModel):
    type: Literal["text"]
    text: str

class ContentBlockImage(BaseModel):
    type: Literal["image"]
    source: Dict[str, Any]

class ContentBlockToolUse(BaseModel):
    type: Literal["tool_use"]
    id: str
    name: str
    input: Dict[str, Any]

class ContentBlockToolResult(BaseModel):
    type: Literal["tool_result"]
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]], Dict[str, Any], List[Any], Any]

class SystemContent(BaseModel):
    type: Literal["text"]
    text: str

class Message(BaseModel):
    role: Literal["user", "assistant"] 
    content: Union[str, List[Union[ContentBlockText, ContentBlockImage, ContentBlockToolUse, ContentBlockToolResult]]]

class Tool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any]

class ThinkingConfig(BaseModel):
    enabled: bool = True

class MessagesRequest(BaseModel):
    model: str
    max_tokens: int
    messages: List[Message]
    system: Optional[Union[str, List[SystemContent]]] = None
    stop_sequences: Optional[List[str]] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Dict[str, Any]] = None
    thinking: Optional[ThinkingConfig] = None
    original_model: Optional[str] = None  # Will store the original model name
    
    @field_validator('model')
    def validate_model_field(cls, v, info): # Renamed to avoid conflict
        original_model = v
        new_model = v # Default to original value

        # 从新配置系统获取当前设置
        current_config = global_config.get_status()
        super_model = current_config["super_model"]
        big_model = current_config["big_model"]
        small_model = current_config["small_model"]
        
        logger.debug(f"📋 MODEL VALIDATION: Original='{original_model}', SUPER='{super_model}', BIG='{big_model}', SMALL='{small_model}'")

        # Remove provider prefixes for easier matching
        clean_v = v
        if clean_v.startswith('anthropic/'):
            clean_v = clean_v[10:]
        elif clean_v.startswith('openai/'):
            clean_v = clean_v[7:]
        elif clean_v.startswith('gemini/'):
            clean_v = clean_v[7:]

        # --- Enhanced Mapping Logic --- START ---
        mapped = False
        
        # Map Opus to super_model
        if 'opus' in clean_v.lower():
            new_model = super_model
            mapped = True
            logger.debug(f"🔄 OPUS MAPPING: '{original_model}' → '{new_model}' (super_model={super_model})")
        
        # Map Haiku to small_model
        elif 'haiku' in clean_v.lower():
            new_model = small_model
            mapped = True
            logger.debug(f"🔄 HAIKU MAPPING: '{original_model}' → '{new_model}' (small_model={small_model})")

        # Map Sonnet to big_model
        elif 'sonnet' in clean_v.lower():
            new_model = big_model
            mapped = True
            logger.debug(f"🔄 SONNET MAPPING: '{original_model}' → '{new_model}' (big_model={big_model})")

        # Add prefixes to direct model names if they match known lists
        elif not mapped:
            if clean_v in ANTHROPIC_MODELS and not v.startswith('anthropic/'):
                new_model = f"anthropic/{clean_v}"
                mapped = True
            elif clean_v in GEMINI_MODELS and not v.startswith('gemini/'):
                new_model = f"gemini/{clean_v}"
                mapped = True
            elif clean_v in OPENAI_MODELS and not v.startswith('openai/'):
                new_model = f"openai/{clean_v}"
                mapped = True
        # --- Enhanced Mapping Logic --- END ---

        if mapped:
            logger.debug(f"📌 MODEL MAPPING: '{original_model}' ➡️ '{new_model}'")
        else:
             # If no mapping occurred and no prefix exists, log warning or decide default
             if not v.startswith(('openai/', 'gemini/', 'anthropic/')):
                 logger.warning(f"⚠️ No prefix or mapping rule for model: '{original_model}'. Using as is.")
             new_model = v # Ensure we return the original if no rule applied

        # Store the original model in the values dictionary
        values = info.data
        if isinstance(values, dict):
            values['original_model'] = original_model

        return new_model

class TokenCountRequest(BaseModel):
    model: str
    messages: List[Message]
    system: Optional[Union[str, List[SystemContent]]] = None
    tools: Optional[List[Tool]] = None
    thinking: Optional[ThinkingConfig] = None
    tool_choice: Optional[Dict[str, Any]] = None
    original_model: Optional[str] = None  # Will store the original model name
    
    @field_validator('model')
    def validate_model_token_count(cls, v, info): # Renamed to avoid conflict
        # Use the same logic as MessagesRequest validator
        original_model = v
        new_model = v # Default to original value

        # 从新配置系统获取当前设置
        current_config = global_config.get_status()
        super_model = current_config["super_model"]
        big_model = current_config["big_model"]
        small_model = current_config["small_model"]
        
        logger.debug(f"📋 TOKEN COUNT VALIDATION: Original='{original_model}', SUPER='{super_model}', BIG='{big_model}', SMALL='{small_model}'")

        # Remove provider prefixes for easier matching
        clean_v = v
        if clean_v.startswith('anthropic/'):
            clean_v = clean_v[10:]
        elif clean_v.startswith('openai/'):
            clean_v = clean_v[7:]
        elif clean_v.startswith('gemini/'):
            clean_v = clean_v[7:]

        # --- Mapping Logic --- START ---
        mapped = False
        # Map Opus to super_model
        if 'opus' in clean_v.lower():
            new_model = super_model
            mapped = True
            logger.debug(f"🔄 OPUS TOKEN MAPPING: '{original_model}' → '{new_model}' (super_model={super_model})")
        
        # Map Haiku to small_model
        elif 'haiku' in clean_v.lower():
            new_model = small_model
            mapped = True
            logger.debug(f"🔄 HAIKU TOKEN MAPPING: '{original_model}' → '{new_model}' (small_model={small_model})")

        # Map Sonnet to big_model
        elif 'sonnet' in clean_v.lower():
            new_model = big_model
            mapped = True
            logger.debug(f"🔄 SONNET TOKEN MAPPING: '{original_model}' → '{new_model}' (big_model={big_model})")

        # Add prefixes to non-mapped models if they match known lists
        elif not mapped:
            if clean_v in GEMINI_MODELS and not v.startswith('gemini/'):
                new_model = f"gemini/{clean_v}"
                mapped = True # Technically mapped to add prefix
            elif clean_v in OPENAI_MODELS and not v.startswith('openai/'):
                new_model = f"openai/{clean_v}"
                mapped = True # Technically mapped to add prefix
        # --- Mapping Logic --- END ---

        if mapped:
            logger.debug(f"📌 TOKEN COUNT MAPPING: '{original_model}' ➡️ '{new_model}'")
        else:
             if not v.startswith(('openai/', 'gemini/', 'anthropic/')):
                 logger.warning(f"⚠️ No prefix or mapping rule for token count model: '{original_model}'. Using as is.")
             new_model = v # Ensure we return the original if no rule applied

        # Store the original model in the values dictionary
        values = info.data
        if isinstance(values, dict):
            values['original_model'] = original_model

        return new_model

class TokenCountResponse(BaseModel):
    input_tokens: int

# 动态配置相关的数据模型
class ConfigUpdateRequest(BaseModel):
    preferred_provider: Optional[str] = None
    big_model: Optional[str] = None
    small_model: Optional[str] = None
    preserve_conversation: Optional[bool] = True  # 默认保持对话历史
    preset: Optional[str] = None  # 使用预设配置

class ModelListResponse(BaseModel):
    openai_models: List[str]
    gemini_models: List[str] 
    anthropic_models: List[str]
    mapping_presets: Dict[str, Dict[str, str]]
    total_models: int

class ProxyServerToggleRequest(BaseModel):
    enabled: bool
    message: Optional[str] = None

class ProxyServerStatusResponse(BaseModel):
    proxy_server_enabled: bool
    message: str
    claude_code_should_use_proxy: bool

class ConfigResponse(BaseModel):
    preferred_provider: str
    big_model: str
    small_model: str
    message: str

class RequestLogEntry(BaseModel):
    timestamp: str
    method: str
    path: str
    headers: Dict[str, str]
    body: Optional[Dict[str, Any]] = None
    model: Optional[str] = None
    original_model: Optional[str] = None

class ConversationMessage(BaseModel):
    timestamp: str
    role: str
    content: Union[str, List[Dict[str, Any]]]
    model_used: str

class ConversationHistoryResponse(BaseModel):
    messages: List[ConversationMessage]
    total_count: int

class RequestLogsResponse(BaseModel):
    logs: List[RequestLogEntry]
    total_count: int

class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

class MessagesResponse(BaseModel):
    id: str
    model: str
    role: Literal["assistant"] = "assistant"
    content: List[Union[ContentBlockText, ContentBlockToolUse]]
    type: Literal["message"] = "message"
    stop_reason: Optional[Literal["end_turn", "max_tokens", "stop_sequence", "tool_use"]] = None
    stop_sequence: Optional[str] = None
    usage: Usage

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Get request details
    method = request.method
    path = request.url.path
    
    # 截取请求数据
    request_data = {
        "timestamp": datetime.now().isoformat(),
        "method": method,
        "path": path,
        "headers": dict(request.headers),
        "body": None,
        "model": None,
        "original_model": None
    }
    
    # 如果是POST请求，尝试读取请求体
    if method == "POST" and path in ["/v1/messages", "/v1/messages/count_tokens"]:
        try:
            # 读取请求体
            body = await request.body()
            if body:
                body_str = body.decode('utf-8')
                body_json = json.loads(body_str)
                request_data["body"] = body_json
                
                # 提取模型信息
                if "model" in body_json:
                    request_data["model"] = body_json["model"]
                if "original_model" in body_json:
                    request_data["original_model"] = body_json["original_model"]
                
                # 重新创建请求对象，因为body已经被读取
                from fastapi import Request as FastAPIRequest
                from starlette.requests import Request as StarletteRequest
                
                # 创建新的请求对象
                scope = request.scope.copy()
                receive = lambda: {"type": "http.request", "body": body}
                request = StarletteRequest(scope, receive)
        except Exception as e:
            logger.debug(f"Error reading request body: {e}")
    
    # Log only basic request details at debug level
    logger.debug(f"Request: {method} {path}")
    
    # Process the request and get the response
    response = await call_next(request)
    
    # 添加到新配置系统的日志中
    global_config.add_debug_log(
        "request",
        f"{method} {path}",
        {"method": method, "path": path, "status_code": response.status_code}
    )
    
    return response

# Not using validation function as we're using the environment API key

def parse_tool_result_content(content):
    """Helper function to properly parse and normalize tool result content."""
    if content is None:
        return "No content provided"
        
    if isinstance(content, str):
        return content
        
    if isinstance(content, list):
        result = ""
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                result += item.get("text", "") + "\n"
            elif isinstance(item, str):
                result += item + "\n"
            elif isinstance(item, dict):
                if "text" in item:
                    result += item.get("text", "") + "\n"
                else:
                    try:
                        result += json.dumps(item) + "\n"
                    except:
                        result += str(item) + "\n"
            else:
                try:
                    result += str(item) + "\n"
                except:
                    result += "Unparseable content\n"
        return result.strip()
        
    if isinstance(content, dict):
        if content.get("type") == "text":
            return content.get("text", "")
        try:
            return json.dumps(content)
        except:
            return str(content)
            
    # Fallback for any other type
    try:
        return str(content)
    except:
        return "Unparseable content"

def convert_anthropic_to_litellm(anthropic_request: MessagesRequest) -> Dict[str, Any]:
    """Convert Anthropic API request format to LiteLLM format (which follows OpenAI)."""
    # LiteLLM already handles Anthropic models when using the format model="anthropic/claude-3-opus-20240229"
    # So we just need to convert our Pydantic model to a dict in the expected format
    
    messages = []
    
    # Add system message if present
    if anthropic_request.system:
        # Handle different formats of system messages
        if isinstance(anthropic_request.system, str):
            # Simple string format
            messages.append({"role": "system", "content": anthropic_request.system})
        elif isinstance(anthropic_request.system, list):
            # List of content blocks
            system_text = ""
            for block in anthropic_request.system:
                if hasattr(block, 'type') and block.type == "text":
                    system_text += block.text + "\n\n"
                elif isinstance(block, dict) and block.get("type") == "text":
                    system_text += block.get("text", "") + "\n\n"
            
            if system_text:
                messages.append({"role": "system", "content": system_text.strip()})
    
    # Add conversation messages
    for msg in anthropic_request.messages:
        content = msg.content
        role = msg.role
        
        # Check if content is a list of blocks
        if isinstance(content, list):
            is_tool_result_message = any(getattr(block, 'type', None) == 'tool_result' for block in content)
            is_tool_use_message = any(getattr(block, 'type', None) == 'tool_use' for block in content)

            # --- BUG FIX: Correctly handle tool_result from user ---
            if role == "user" and is_tool_result_message:
                for block in content:
                    if getattr(block, 'type', None) == 'tool_result':
                        # Convert to OpenAI's 'tool' role message
                        messages.append({
                            "role": "tool",
                            "tool_call_id": block.tool_use_id,
                            "content": parse_tool_result_content(block.content)
                        })
                    elif getattr(block, 'type', None) == 'text' and block.text.strip():
                        # If there's other text, add it as a separate user message
                        messages.append({"role": "user", "content": block.text})
                    elif getattr(block, 'type', None) == 'thinking':
                        # Filter out thinking blocks in user tool_result messages
                        continue
            
            # --- BUG FIX: Correctly handle tool_use from assistant history ---
            elif role == "assistant" and is_tool_use_message:
                tool_calls = []
                text_parts = []
                for block in content:
                    if getattr(block, 'type', None) == 'tool_use':
                        # Arguments must be a JSON string for OpenAI format
                        arguments_str = json.dumps(block.input)
                        tool_calls.append({
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": arguments_str
                            }
                        })
                    elif getattr(block, 'type', None) == 'text':
                        text_parts.append(block.text)
                    elif getattr(block, 'type', None) == 'thinking':
                        # Filter out thinking blocks in assistant tool_use messages
                        continue
                
                # Create an assistant message with tool_calls
                assistant_message = {
                    "role": "assistant",
                    "content": " ".join(text_parts).strip() or None,
                    "tool_calls": tool_calls
                }
                # content can be None if there are only tool_calls, which is valid
                if assistant_message["content"] is None:
                    del assistant_message["content"]
                    
                messages.append(assistant_message)

            # --- Original logic for other complex content (e.g., images) ---
            else:
                # Fallback for messages with other kinds of blocks (like images)
                # This part might need refinement if you use other block types
                processed_content = []
                for block in content:
                    if hasattr(block, "type"):
                        if block.type == "text":
                            processed_content.append({"type": "text", "text": block.text})
                        elif block.type == "image":
                            processed_content.append({"type": "image", "source": block.source})
                        elif block.type == "thinking":
                            # Filter out thinking blocks - they are Claude's internal reasoning
                            # and not compatible with other API providers
                            continue
                messages.append({"role": role, "content": processed_content})
        
        # Handle simple string content
        else:
            messages.append({"role": role, "content": content})
    
    # Cap max_tokens for OpenAI models to their limit of 16384
    max_tokens = anthropic_request.max_tokens
    if anthropic_request.model.startswith("openai/") or anthropic_request.model.startswith("gemini/"):
        max_tokens = min(max_tokens, 16384)
        logger.debug(f"Capping max_tokens to 16384 for OpenAI/Gemini model (original value: {anthropic_request.max_tokens})")
    
    # Create LiteLLM request dict
    litellm_request = {
        "model": anthropic_request.model,  # it understands "anthropic/claude-x" format
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": anthropic_request.temperature,
        "stream": anthropic_request.stream,
    }

    # Only include thinking field for Anthropic models
    if anthropic_request.thinking and anthropic_request.model.startswith("anthropic/"):
        litellm_request["thinking"] = anthropic_request.thinking

    # Add optional parameters if present
    if anthropic_request.stop_sequences:
        litellm_request["stop"] = anthropic_request.stop_sequences
    
    if anthropic_request.top_p:
        litellm_request["top_p"] = anthropic_request.top_p
    
    if anthropic_request.top_k:
        litellm_request["top_k"] = anthropic_request.top_k
    
    # Convert tools to OpenAI format
    if anthropic_request.tools:
        openai_tools = []
        is_gemini_model = anthropic_request.model.startswith("gemini/")

        for tool in anthropic_request.tools:
            # Convert to dict if it's a pydantic model
            if hasattr(tool, 'dict'):
                tool_dict = tool.dict()
            else:
                # Ensure tool_dict is a dictionary, handle potential errors if 'tool' isn't dict-like
                try:
                    tool_dict = dict(tool) if not isinstance(tool, dict) else tool
                except (TypeError, ValueError):
                     logger.error(f"Could not convert tool to dict: {tool}")
                     continue # Skip this tool if conversion fails

            # Clean the schema if targeting a Gemini model
            input_schema = tool_dict.get("input_schema", {})

            # --- FIX: Validate and normalize the input schema ---
            # Some backends hang on invalid or empty schemas (e.g., {}).
            # A valid JSON Schema for function parameters must be an object.
            if not isinstance(input_schema, dict) or "type" not in input_schema or "properties" not in input_schema:
                logger.warning(f"Tool '{tool_dict['name']}' has an invalid or empty input_schema. Normalizing to a valid empty schema. Original: {input_schema}")
                input_schema = {"type": "object", "properties": {}}
            
            if is_gemini_model:
                 logger.debug(f"Cleaning schema for Gemini tool: {tool_dict.get('name')}")
                 input_schema = clean_gemini_schema(input_schema)

            # Create OpenAI-compatible function tool
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool_dict["name"],
                    "description": tool_dict.get("description", ""),
                    "parameters": input_schema # Use potentially cleaned schema
                }
            }
            openai_tools.append(openai_tool)

        litellm_request["tools"] = openai_tools
    
    # Convert tool_choice to OpenAI format if present
    if anthropic_request.tool_choice:
        if hasattr(anthropic_request.tool_choice, 'dict'):
            tool_choice_dict = anthropic_request.tool_choice.dict()
        else:
            tool_choice_dict = anthropic_request.tool_choice
            
        # Handle Anthropic's tool_choice format
        choice_type = tool_choice_dict.get("type")
        if choice_type == "auto":
            litellm_request["tool_choice"] = "auto"
        elif choice_type == "any":
            litellm_request["tool_choice"] = "any"
        elif choice_type == "tool" and "name" in tool_choice_dict:
            litellm_request["tool_choice"] = {
                "type": "function",
                "function": {"name": tool_choice_dict["name"]}
            }
        else:
            # Default to auto if we can't determine
            litellm_request["tool_choice"] = "auto"
    
    return litellm_request

def convert_litellm_to_anthropic(litellm_response: Union[Dict[str, Any], Any], 
                                 original_request: MessagesRequest) -> MessagesResponse:
    """Convert LiteLLM (OpenAI format) response to Anthropic API response format."""
    
    # Enhanced response extraction with better error handling
    try:
        # Get the clean model name to check capabilities
        clean_model = original_request.model
        if clean_model.startswith("anthropic/"):
            clean_model = clean_model[len("anthropic/"):]
        elif clean_model.startswith("openai/"):
            clean_model = clean_model[len("openai/"):]
        
        # Check if this is a Claude model (which supports content blocks)
        is_claude_model = clean_model.startswith("claude-")
        
        # Handle ModelResponse object from LiteLLM
        if hasattr(litellm_response, 'choices') and hasattr(litellm_response, 'usage'):
            # Extract data from ModelResponse object directly
            choices = litellm_response.choices
            message = choices[0].message if choices and len(choices) > 0 else None
            content_text = message.content if message and hasattr(message, 'content') else ""
            tool_calls = message.tool_calls if message and hasattr(message, 'tool_calls') else None
            finish_reason = choices[0].finish_reason if choices and len(choices) > 0 else "stop"
            usage_info = litellm_response.usage
            response_id = getattr(litellm_response, 'id', f"msg_{uuid.uuid4()}")
        else:
            # For backward compatibility - handle dict responses
            # If response is a dict, use it, otherwise try to convert to dict
            try:
                response_dict = litellm_response if isinstance(litellm_response, dict) else litellm_response.dict()
            except AttributeError:
                # If .dict() fails, try to use model_dump or __dict__ 
                try:
                    response_dict = litellm_response.model_dump() if hasattr(litellm_response, 'model_dump') else litellm_response.__dict__
                except AttributeError:
                    # Fallback - manually extract attributes
                    response_dict = {
                        "id": getattr(litellm_response, 'id', f"msg_{uuid.uuid4()}"),
                        "choices": getattr(litellm_response, 'choices', [{}]),
                        "usage": getattr(litellm_response, 'usage', {})
                    }
                    
            # Extract the content from the response dict
            choices = response_dict.get("choices", [{}])
            message = choices[0].get("message", {}) if choices and len(choices) > 0 else {}
            content_text = message.get("content", "")
            tool_calls = message.get("tool_calls", None)
            finish_reason = choices[0].get("finish_reason", "stop") if choices and len(choices) > 0 else "stop"
            usage_info = response_dict.get("usage", {})
            response_id = response_dict.get("id", f"msg_{uuid.uuid4()}")
        
        # Create content list for Anthropic format
        content = []
        
        # Add text content block if present (text might be None or empty for pure tool call responses)
        if content_text is not None and content_text != "":
            content.append({"type": "text", "text": content_text})
        
        # Add tool calls if present (tool_use in Anthropic format)
        if tool_calls:
            logger.debug(f"Processing tool calls: {tool_calls}")
            
            # Convert to list if it's not already
            if not isinstance(tool_calls, list):
                tool_calls = [tool_calls]
                
            for idx, tool_call in enumerate(tool_calls):
                logger.debug(f"Processing tool call {idx}: {tool_call}")
                
                # Extract function data based on whether it's a dict or object
                if isinstance(tool_call, dict):
                    function = tool_call.get("function", {})
                    tool_id = tool_call.get("id", f"tool_{uuid.uuid4()}")
                    name = function.get("name", "")
                    arguments = function.get("arguments", "{}")
                else:
                    function = getattr(tool_call, "function", None)
                    tool_id = getattr(tool_call, "id", f"tool_{uuid.uuid4()}")
                    name = getattr(function, "name", "") if function else ""
                    arguments = getattr(function, "arguments", "{}") if function else "{}"
                
                # Convert string arguments to dict if needed
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse tool arguments as JSON: {arguments}")
                        arguments = {"raw": arguments}
                
                logger.debug(f"Adding tool_use block: id={tool_id}, name={name}, input={arguments}")
                
                content.append({
                    "type": "tool_use",
                    "id": tool_id,
                    "name": name,
                    "input": arguments
                })
        
        # Get usage information - extract values safely from object or dict
        if isinstance(usage_info, dict):
            prompt_tokens = usage_info.get("prompt_tokens", 0)
            completion_tokens = usage_info.get("completion_tokens", 0)
        else:
            prompt_tokens = getattr(usage_info, "prompt_tokens", 0)
            completion_tokens = getattr(usage_info, "completion_tokens", 0)
        
        # Map OpenAI finish_reason to Anthropic stop_reason
        stop_reason = None
        if finish_reason == "stop":
            stop_reason = "end_turn"
        elif finish_reason == "length":
            stop_reason = "max_tokens"
        elif finish_reason == "tool_calls":
            stop_reason = "tool_use"
        else:
            stop_reason = "end_turn"  # Default
        
        # Make sure content is never empty
        if not content:
            content.append({"type": "text", "text": ""})
        
        # Create Anthropic-style response
        anthropic_response = MessagesResponse(
            id=response_id,
            model=original_request.model,
            role="assistant",
            content=content,
            stop_reason=stop_reason,
            stop_sequence=None,
            usage=Usage(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens
            )
        )
        
        return anthropic_response
        
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        error_message = f"Error converting response: {str(e)}\n\nFull traceback:\n{error_traceback}"
        logger.error(error_message)
        
        # In case of any error, create a fallback response
        return MessagesResponse(
            id=f"msg_{uuid.uuid4()}",
            model=original_request.model,
            role="assistant",
            content=[{"type": "text", "text": f"Error converting response: {str(e)}. Please check server logs."}],
            stop_reason="end_turn",
            usage=Usage(input_tokens=0, output_tokens=0)
        )

async def handle_streaming(response_generator, original_request: MessagesRequest):
    """Handle streaming responses from LiteLLM and convert to Anthropic format."""
    try:
        # Send message_start event
        message_id = f"msg_{uuid.uuid4().hex[:24]}"  # Format similar to Anthropic's IDs
        
        message_data = {
            'type': 'message_start',
            'message': {
                'id': message_id,
                'type': 'message',
                'role': 'assistant',
                'model': original_request.model,
                'content': [],
                'stop_reason': None,
                'stop_sequence': None,
                'usage': {
                    'input_tokens': 0,
                    'cache_creation_input_tokens': 0,
                    'cache_read_input_tokens': 0,
                    'output_tokens': 0
                }
            }
        }
        yield f"event: message_start\ndata: {json.dumps(message_data)}\n\n"
        
        # Content block index for the first text block
        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"
        
        # Send a ping to keep the connection alive (Anthropic does this)
        yield f"event: ping\ndata: {json.dumps({'type': 'ping'})}\n\n"
        
        tool_index = None
        current_tool_call = None
        tool_content = ""
        accumulated_text = ""  # Track accumulated text content
        text_sent = False  # Track if we've sent any text content
        text_block_closed = False  # Track if text block is closed
        input_tokens = 0
        output_tokens = 0
        has_sent_stop_reason = False
        last_tool_index = 0
        
        # 用于记录对话历史
        full_response_text = ""
        
        # Process each chunk
        async for chunk in response_generator:
            try:

                
                # Check if this is the end of the response with usage data
                if hasattr(chunk, 'usage') and chunk.usage is not None:
                    if hasattr(chunk.usage, 'prompt_tokens'):
                        input_tokens = chunk.usage.prompt_tokens
                    if hasattr(chunk.usage, 'completion_tokens'):
                        output_tokens = chunk.usage.completion_tokens
                
                # Handle text content
                if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                    choice = chunk.choices[0]
                    
                    # Get the delta from the choice
                    if hasattr(choice, 'delta'):
                        delta = choice.delta
                    else:
                        # If no delta, try to get message
                        delta = getattr(choice, 'message', {})
                    
                    # Check for finish_reason to know when we're done
                    finish_reason = getattr(choice, 'finish_reason', None)
                    
                    # Process text content
                    delta_content = None
                    
                    # Handle different formats of delta content
                    if hasattr(delta, 'content'):
                        delta_content = delta.content
                    elif isinstance(delta, dict) and 'content' in delta:
                        delta_content = delta['content']
                    
                    # Accumulate text content
                    if delta_content is not None and delta_content != "":
                        accumulated_text += delta_content
                        full_response_text += delta_content  # 记录完整响应文本
                        
                        # Always emit text deltas if no tool calls started
                        if tool_index is None and not text_block_closed:
                            text_sent = True
                            yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': delta_content}})}\n\n"
                    
                    # Process tool calls
                    delta_tool_calls = None
                    
                    # Handle different formats of tool calls
                    if hasattr(delta, 'tool_calls'):
                        delta_tool_calls = delta.tool_calls
                    elif isinstance(delta, dict) and 'tool_calls' in delta:
                        delta_tool_calls = delta['tool_calls']
                    
                    # Process tool calls if any
                    if delta_tool_calls:
                        # First tool call we've seen - need to handle text properly
                        if tool_index is None:
                            # If we've been streaming text, close that text block
                            if text_sent and not text_block_closed:
                                text_block_closed = True
                                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
                            # If we've accumulated text but not sent it, we need to emit it now
                            # This handles the case where the first delta has both text and a tool call
                            elif accumulated_text and not text_sent and not text_block_closed:
                                # Send the accumulated text
                                text_sent = True
                                yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': accumulated_text}})}\n\n"
                                # Close the text block
                                text_block_closed = True
                                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
                            # Close text block even if we haven't sent anything - models sometimes emit empty text blocks
                            elif not text_block_closed:
                                text_block_closed = True
                                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
                                
                        # Convert to list if it's not already
                        if not isinstance(delta_tool_calls, list):
                            delta_tool_calls = [delta_tool_calls]
                        
                        for tool_call in delta_tool_calls:
                            # Get the index of this tool call (for multiple tools)
                            current_index = None
                            if isinstance(tool_call, dict) and 'index' in tool_call:
                                current_index = tool_call['index']
                            elif hasattr(tool_call, 'index'):
                                current_index = tool_call.index
                            else:
                                current_index = 0
                            
                            # Check if this is a new tool or a continuation
                            if tool_index is None or current_index != tool_index:
                                # New tool call - create a new tool_use block
                                tool_index = current_index
                                last_tool_index += 1
                                anthropic_tool_index = last_tool_index
                                
                                # Extract function info
                                if isinstance(tool_call, dict):
                                    function = tool_call.get('function', {})
                                    name = function.get('name', '') if isinstance(function, dict) else ""
                                    tool_id = tool_call.get('id', f"toolu_{uuid.uuid4().hex[:24]}")
                                else:
                                    function = getattr(tool_call, 'function', None)
                                    name = getattr(function, 'name', '') if function else ''
                                    tool_id = getattr(tool_call, 'id', f"toolu_{uuid.uuid4().hex[:24]}")
                                
                                # Start a new tool_use block
                                yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': anthropic_tool_index, 'content_block': {'type': 'tool_use', 'id': tool_id, 'name': name, 'input': {}}})}\n\n"
                                current_tool_call = tool_call
                                tool_content = ""
                            
                            # Extract function arguments
                            arguments = None
                            if isinstance(tool_call, dict) and 'function' in tool_call:
                                function = tool_call.get('function', {})
                                arguments = function.get('arguments', '') if isinstance(function, dict) else ''
                            elif hasattr(tool_call, 'function'):
                                function = getattr(tool_call, 'function', None)
                                arguments = getattr(function, 'arguments', '') if function else ''
                            
                            # If we have arguments, send them as a delta
                            if arguments:
                                # Try to detect if arguments are valid JSON or just a fragment
                                try:
                                    # If it's already a dict, use it
                                    if isinstance(arguments, dict):
                                        args_json = json.dumps(arguments)
                                    else:
                                        # Otherwise, try to parse it
                                        json.loads(arguments)
                                        args_json = arguments
                                except (json.JSONDecodeError, TypeError):
                                    # If it's a fragment, treat it as a string
                                    args_json = arguments
                                
                                # Add to accumulated tool content
                                tool_content += args_json if isinstance(args_json, str) else ""
                                
                                # Send the update
                                yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': anthropic_tool_index, 'delta': {'type': 'input_json_delta', 'partial_json': args_json}})}\n\n"
                    
                    # Process finish_reason - end the streaming response
                    if finish_reason and not has_sent_stop_reason:
                        has_sent_stop_reason = True
                        
                        # Close any open tool call blocks
                        if tool_index is not None:
                            for i in range(1, last_tool_index + 1):
                                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': i})}\n\n"
                        
                        # If we accumulated text but never sent or closed text block, do it now
                        if not text_block_closed:
                            if accumulated_text and not text_sent:
                                # Send the accumulated text
                                yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': accumulated_text}})}\n\n"
                            # Close the text block
                            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
                        
                        # Map OpenAI finish_reason to Anthropic stop_reason
                        stop_reason = "end_turn"
                        if finish_reason == "length":
                            stop_reason = "max_tokens"
                        elif finish_reason == "tool_calls":
                            stop_reason = "tool_use"
                        elif finish_reason == "stop":
                            stop_reason = "end_turn"
                        
                        # Send message_delta with stop reason and usage
                        usage = {"output_tokens": output_tokens}
                        
                        yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop_reason, 'stop_sequence': None}, 'usage': usage})}\n\n"
                        
                        # Send message_stop event
                        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
                        
                        # Send final [DONE] marker to match Anthropic's behavior
                        yield "data: [DONE]\n\n"
                        
                        # 记录对话历史
                        try:
                            # 记录用户消息
                            for msg in original_request.messages:
                                if msg.role in ['user', 'assistant']:
                                    content_text = ""
                                    if isinstance(msg.content, str):
                                        content_text = msg.content
                                    elif isinstance(msg.content, list):
                                        for block in msg.content:
                                            if hasattr(block, "type") and block.type == "text":
                                                content_text += block.text + "\n"
                                            elif isinstance(block, dict) and block.get("type") == "text":
                                                content_text += block.get("text", "") + "\n"
                                    
                                    if content_text.strip():
                                        global_config.add_conversation_message(
                                            role=msg.role,
                                            content=content_text.strip(),
                                            model_used=original_request.model
                                        )
                            
                            # 记录助手回复
                            if full_response_text.strip():
                                global_config.add_conversation_message(
                                    role="assistant",
                                    content=full_response_text.strip(),
                                    model_used=original_request.model
                                )
                        except Exception as conv_error:
                            logger.error(f"Error recording streaming conversation history: {conv_error}")
                        
                        return
            except Exception as e:
                # Log error but continue processing other chunks
                logger.error(f"Error processing chunk: {str(e)}")
                continue
        
        # If we didn't get a finish reason, close any open blocks
        if not has_sent_stop_reason:
            # Close any open tool call blocks
            if tool_index is not None:
                for i in range(1, last_tool_index + 1):
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': i})}\n\n"
            
            # Close the text content block
            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
            
            # Send final message_delta with usage
            usage = {"output_tokens": output_tokens}
            
            yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': usage})}\n\n"
            
            # Send message_stop event
            yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
            
            # Send final [DONE] marker to match Anthropic's behavior
            yield "data: [DONE]\n\n"
            
            # 记录对话历史
            try:
                # 记录用户消息
                for msg in original_request.messages:
                    if msg.role in ['user', 'assistant']:
                        content_text = ""
                        if isinstance(msg.content, str):
                            content_text = msg.content
                        elif isinstance(msg.content, list):
                            for block in msg.content:
                                if hasattr(block, "type") and block.type == "text":
                                    content_text += block.text + "\n"
                                elif isinstance(block, dict) and block.get("type") == "text":
                                    content_text += block.get("text", "") + "\n"
                        
                        if content_text.strip():
                            global_config.add_conversation_message(
                                role=msg.role,
                                content=content_text.strip(),
                                model_used=original_request.model
                            )
                
                # 记录助手回复
                if full_response_text.strip():
                    global_config.add_conversation_message(
                        role="assistant",
                        content=full_response_text.strip(),
                        model_used=original_request.model
                    )
            except Exception as conv_error:
                logger.error(f"Error recording streaming conversation history (fallback): {conv_error}")
    
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        error_message = f"Error in streaming: {str(e)}\n\nFull traceback:\n{error_traceback}"
        logger.error(error_message)
        
        # 记录失败的响应日志
        global_config.add_debug_log(
            "response",
            f"Streaming response error for: {original_request.model}",
            {
                "model": original_request.model,
                "error": error_message,
                "stop_reason": "error",
                "usage": {"input_tokens": 0, "output_tokens": 0}
            }
        )
        
        # Send error message_delta
        yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'error', 'stop_sequence': None}, 'usage': {'output_tokens': 0}})}\n\n"
        
        # Send message_stop event
        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
        
        # Send final [DONE] marker
        yield "data: [DONE]\n\n"
    finally:
        # --- 日志记录 ---
        # 在流式传输成功结束后，记录完整的响应日志
        if not has_sent_stop_reason: # Fallback for streams that end without a finish_reason
            stop_reason = "end_turn"
        
        # 记录完整的对话历史
        try:
            # 记录用户消息
            for msg in original_request.messages:
                if msg.role in ['user', 'assistant']:
                    content_text = ""
                    if isinstance(msg.content, str):
                        content_text = msg.content
                    elif isinstance(msg.content, list):
                        for block in msg.content:
                            if hasattr(block, "type") and block.type == "text":
                                content_text += block.text + "\n"
                            elif isinstance(block, dict) and block.get("type") == "text":
                                content_text += block.get("text", "") + "\n"
                    
                    if content_text.strip():
                        global_config.add_conversation_message(
                            role=msg.role,
                            content=content_text.strip(),
                            model_used=original_request.model
                        )
            
            # 记录助手回复
            if full_response_text.strip():
                global_config.add_conversation_message(
                    role="assistant",
                    content=full_response_text.strip(),
                    model_used=original_request.model
                )
        except Exception as conv_error:
            logger.error(f"Error recording streaming conversation history (finally block): {conv_error}")

        # 记录完整的调试日志
        global_config.add_debug_log(
            "response",
            f"Streaming response complete for: {original_request.model}",
            {
                "response_id": message_id,
                "model": original_request.model,
                "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
                "content": full_response_text,
                "stop_reason": stop_reason,
                "full_response": {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": full_response_text}],
                    "model": original_request.model,
                    "stop_reason": stop_reason,
                    "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}
                }
            }
        )


async def forward_to_anthropic(request: Union[MessagesRequest, TokenCountRequest], raw_request: Request):
    """Forward requests directly to Anthropic API when proxy is disabled."""
    try:
        # Debug: Log all request headers to understand what Claude Code is sending
        logger.info(f"🔍 透明代理调试 - 收到的请求头部: {dict(raw_request.headers)}")
        
        # For Claude Pro users, we should use the original authentication completely
        # Check if we have ANTHROPIC_API_KEY set (manual API key users)
        has_env_api_key = bool(ANTHROPIC_API_KEY)
        
        logger.info(f"🔍 透明代理调试 - 环境变量API密钥: {'存在' if has_env_api_key else '不存在'}")
        
        # If no manual API key is set, this is likely a Claude Pro user
        # and we should preserve ALL original authentication
        if not has_env_api_key:
            logger.info("🔍 透明代理调试 - 检测到Claude Pro用户，保持原始认证")
            # Don't modify any headers - pass everything through as-is
            pass
        else:
            logger.info("🔍 透明代理调试 - 检测到API密钥用户，使用环境变量密钥")
            # For users with manual API keys, ensure they're used
        
        # Determine the endpoint based on the request path
        path = raw_request.url.path
        if path == "/v1/messages/count_tokens":
            anthropic_url = "https://api.anthropic.com/v1/messages/count_tokens"
        else:
            anthropic_url = "https://api.anthropic.com/v1/messages"
        
        # Get the original request body
        body = await raw_request.body()
        
        # --- Start: Consistent Logging ---
        try:
            body_json = json.loads(body.decode('utf-8'))
            global_config.add_debug_log(
                "request",
                f"Transparent forward request: {body_json.get('model', 'unknown')}",
                {
                    "model": body_json.get('model', 'unknown'),
                    "messages_count": len(body_json.get('messages', [])),
                    "stream": body_json.get('stream', False),
                    "full_request": body_json
                }
            )
        except json.JSONDecodeError:
            logger.warning("Could not parse request body for transparent forward logging.")
        # --- End: Consistent Logging ---
        
        # Start with all original headers except host
        headers = dict(raw_request.headers)
        headers.pop("host", None)
        
        # Handle authentication based on user type
        if not has_env_api_key:
            # Claude Pro user - keep all original headers as-is
            logger.info("🔍 透明代理调试 - Claude Pro用户，保持所有原始头部")
        else:
            # API key user - use environment variable
            logger.info("🔍 透明代理调试 - API密钥用户，覆盖认证头部")
            headers["x-api-key"] = ANTHROPIC_API_KEY
            # Remove any existing authorization to avoid conflicts
            headers.pop("authorization", None)
        
        # Ensure anthropic-version is set
        if "anthropic-version" not in headers:
            headers["anthropic-version"] = "2023-06-01"
            
        logger.info(f"🔍 透明代理调试 - 发送到Anthropic的头部: {dict(headers)}")
        
        # Forward the request to Anthropic API
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                anthropic_url,
                headers=headers,
                content=body
            )
            
            # Check if the request was successful
            if response.status_code != 200:
                logger.error(f"Anthropic API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Anthropic API error: {response.text}"
                )
            
            # For streaming responses
            if request.stream if hasattr(request, 'stream') else False:
                async def stream_and_log_response():
                    full_response_bytes = b""
                    async for chunk in response.aiter_bytes():
                        full_response_bytes += chunk
                        yield chunk
                    
                    try:
                        full_response_text = full_response_bytes.decode('utf-8')
                        response_content = ""
                        for line in full_response_text.splitlines():
                            if line.startswith('data:'):
                                data_str = line[len('data:'):].strip()
                                if data_str != '[DONE]':
                                    try:
                                        data_json = json.loads(data_str)
                                        if data_json.get('type') == 'content_block_delta':
                                            delta = data_json.get('delta', {})
                                            if delta.get('type') == 'text_delta':
                                                response_content += delta.get('text', '')
                                    except json.JSONDecodeError:
                                        pass
                        
                        global_config.add_debug_log(
                            "response",
                            f"Transparent streaming response complete for: {request.model}",
                            {
                                "model": request.model,
                                "content": response_content,
                                "stop_reason": "end_turn",
                                "full_response": full_response_text
                            }
                        )
                    except Exception as log_e:
                        logger.error(f"Error logging transparent streaming response: {log_e}")

                return StreamingResponse(
                    stream_and_log_response(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
                )
            else:
                # For non-streaming responses, return JSON
                response_json = response.json()
                
                response_content = ""
                if 'content' in response_json and isinstance(response_json['content'], list):
                    for block in response_json['content']:
                        if block.get('type') == 'text':
                            response_content += block.get('text', '')
                
                global_config.add_debug_log(
                    "response",
                    f"Transparent response: {request.model}",
                    {
                        "model": request.model,
                        "usage": response_json.get('usage'),
                        "content": response_content,
                        "stop_reason": response_json.get('stop_reason'),
                        "full_response": response_json
                    }
                )
                
                return JSONResponse(
                    content=response_json,
                    status_code=response.status_code
                )
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error forwarding to Anthropic API: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error forwarding to Anthropic API: {str(e)}"
        )

@app.post("/v1/messages")
async def create_message(
    request: MessagesRequest,
    raw_request: Request
):
    try:
        # 检查代理服务器是否启用
        if not global_config.current_config["proxy_enabled"]:
            # 透明模式：直接转发到 Anthropic API
            logger.info("🔄 代理禁用，透明转发到 Anthropic API")
            return await forward_to_anthropic(request, raw_request)
        
        # print the body here
        body = await raw_request.body()
    
        # Parse the raw body as JSON since it's bytes
        body_json = json.loads(body.decode('utf-8'))
        original_model = body_json.get("model", "unknown")
        
        # Get the display name for logging, just the model name without provider prefix
        display_model = original_model
        if "/" in display_model:
            display_model = display_model.split("/")[-1]
        
        # Clean model name for capability check
        clean_model = request.model
        if clean_model.startswith("anthropic/"):
            clean_model = clean_model[len("anthropic/"):]
        elif clean_model.startswith("openai/"):
            clean_model = clean_model[len("openai/"):]
        
        logger.debug(f"📊 PROCESSING REQUEST: Model={request.model}, Stream={request.stream}")
        
        # 记录调试日志 - 包含完整Anthropic请求内容
        global_config.add_debug_log(
            "request",
            f"Anthropic messages request: {request.model}",
            {
                "model": request.model,
                "messages_count": len(request.messages),
                "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "stream": request.stream,
                "full_request": {
                    "model": request.model,
                    "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature,
                    "stream": request.stream,
                    "top_k": getattr(request, 'top_k', None),
                    "top_p": getattr(request, 'top_p', None),
                    "stop_sequences": getattr(request, 'stop_sequences', None)
                }
            }
        )
        
        # Convert Anthropic request to LiteLLM format
        litellm_request = convert_anthropic_to_litellm(request)
        
        # Determine which API key to use based on the model using new config system
        provider_name = global_config.find_model_provider(request.model)
        if provider_name and provider_name in global_config.providers:
            provider = global_config.providers[provider_name]
            litellm_request["api_key"] = provider.api_key
            litellm_request["api_base"] = provider.base_url  # LiteLLM will append /chat/completions automatically
            logger.debug(f"Using {provider.name} API key and base URL {litellm_request['api_base']} for model: {request.model}")
            
            # Add provider prefix to model name for LiteLLM
            if provider.api_format == "openai":
                # For OpenAI-compatible providers, use openai/ prefix with the actual model name
                if not request.model.startswith("openai/"):
                    litellm_request["model"] = f"openai/{request.model}"
            else:
                # For other providers, add provider-specific prefix if needed
                if not request.model.startswith(f"{provider_name}/"):
                    litellm_request["model"] = f"{provider_name}/{request.model}"
        else:
            # Fallback to old logic for backward compatibility
            if request.model.startswith("openai/"):
                litellm_request["api_key"] = OPENAI_API_KEY
                if OPENAI_BASE_URL:
                    litellm_request["api_base"] = OPENAI_BASE_URL
            elif request.model.startswith("gemini/"):
                litellm_request["api_key"] = GEMINI_API_KEY
            else:
                litellm_request["api_key"] = ANTHROPIC_API_KEY
            logger.debug(f"Using fallback API key selection for model: {request.model}")
        
        # For OpenAI models - modify request format to work with limitations
        if "openai" in litellm_request["model"] and "messages" in litellm_request:
            logger.debug(f"Processing OpenAI model request: {litellm_request['model']}")
            
            # For OpenAI models, we need to convert content blocks to simple strings
            # and handle other requirements
            for i, msg in enumerate(litellm_request["messages"]):
                # Special case - handle message content directly when it's a list of tool_result
                # This is a specific case we're seeing in the error
                if "content" in msg and isinstance(msg["content"], list):
                    is_only_tool_result = True
                    for block in msg["content"]:
                        if not isinstance(block, dict) or block.get("type") != "tool_result":
                            is_only_tool_result = False
                            break
                    
                    if is_only_tool_result and len(msg["content"]) > 0:
                        logger.warning(f"Found message with only tool_result content - special handling required")
                        # Extract the content from all tool_result blocks
                        all_text = ""
                        for block in msg["content"]:
                            all_text += "Tool Result:\n"
                            result_content = block.get("content", [])
                            
                            # Handle different formats of content
                            if isinstance(result_content, list):
                                for item in result_content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        all_text += item.get("text", "") + "\n"
                                    elif isinstance(item, dict):
                                        # Fall back to string representation of any dict
                                        try:
                                            item_text = item.get("text", json.dumps(item))
                                            all_text += item_text + "\n"
                                        except:
                                            all_text += str(item) + "\n"
                            elif isinstance(result_content, str):
                                all_text += result_content + "\n"
                            else:
                                try:
                                    all_text += json.dumps(result_content) + "\n"
                                except:
                                    all_text += str(result_content) + "\n"
                        
                        # Replace the list with extracted text
                        litellm_request["messages"][i]["content"] = all_text.strip() or "..."
                        logger.warning(f"Converted tool_result to plain text: {all_text.strip()[:200]}...")
                        continue  # Skip normal processing for this message
                
                # 1. Handle content field - normal case
                if "content" in msg:
                    # Check if content is a list (content blocks)
                    if isinstance(msg["content"], list):
                        # Convert complex content blocks to simple string
                        text_content = ""
                        for block in msg["content"]:
                            if isinstance(block, dict):
                                # Handle different content block types
                                if block.get("type") == "text":
                                    text_content += block.get("text", "") + "\n"
                                
                                # Handle tool_result content blocks - extract nested text
                                elif block.get("type") == "tool_result":
                                    tool_id = block.get("tool_use_id", "unknown")
                                    text_content += f"[Tool Result ID: {tool_id}]\n"
                                    
                                    # Extract text from the tool_result content
                                    result_content = block.get("content", [])
                                    if isinstance(result_content, list):
                                        for item in result_content:
                                            if isinstance(item, dict) and item.get("type") == "text":
                                                text_content += item.get("text", "") + "\n"
                                            elif isinstance(item, dict):
                                                # Handle any dict by trying to extract text or convert to JSON
                                                if "text" in item:
                                                    text_content += item.get("text", "") + "\n"
                                                else:
                                                    try:
                                                        text_content += json.dumps(item) + "\n"
                                                    except:
                                                        text_content += str(item) + "\n"
                                    elif isinstance(result_content, dict):
                                        # Handle dictionary content
                                        if result_content.get("type") == "text":
                                            text_content += result_content.get("text", "") + "\n"
                                        else:
                                            try:
                                                text_content += json.dumps(result_content) + "\n"
                                            except:
                                                text_content += str(result_content) + "\n"
                                    elif isinstance(result_content, str):
                                        text_content += result_content + "\n"
                                    else:
                                        try:
                                            text_content += json.dumps(result_content) + "\n"
                                        except:
                                            text_content += str(result_content) + "\n"
                                
                                # Handle tool_use content blocks
                                elif block.get("type") == "tool_use":
                                    tool_name = block.get("name", "unknown")
                                    tool_id = block.get("id", "unknown")
                                    tool_input = json.dumps(block.get("input", {}))
                                    text_content += f"[Tool: {tool_name} (ID: {tool_id})]\nInput: {tool_input}\n\n"
                                
                                # Handle image content blocks
                                elif block.get("type") == "image":
                                    text_content += "[Image content - not displayed in text format]\n"
                        
                        # Make sure content is never empty for OpenAI models
                        if not text_content.strip():
                            text_content = "..."
                        
                        litellm_request["messages"][i]["content"] = text_content.strip()
                    # Also check for None or empty string content
                    elif msg["content"] is None:
                        litellm_request["messages"][i]["content"] = "..." # Empty content not allowed
                
                # 2. Remove any fields OpenAI doesn't support in messages
                for key in list(msg.keys()):
                    if key not in ["role", "content", "name", "tool_call_id", "tool_calls"]:
                        logger.warning(f"Removing unsupported field from message: {key}")
                        del msg[key]
            
            # 3. Final validation - check for any remaining invalid values and dump full message details
            for i, msg in enumerate(litellm_request["messages"]):
                # Log the message format for debugging
                logger.debug(f"Message {i} format check - role: {msg.get('role')}, content type: {type(msg.get('content'))}")
                
                # If content is still a list or None, replace with placeholder
                if isinstance(msg.get("content"), list):
                    logger.warning(f"CRITICAL: Message {i} still has list content after processing: {json.dumps(msg.get('content'))}")
                    # Last resort - stringify the entire content as JSON
                    litellm_request["messages"][i]["content"] = f"Content as JSON: {json.dumps(msg.get('content'))}"
                elif msg.get("content") is None:
                    logger.warning(f"Message {i} has None content - replacing with placeholder")
                    litellm_request["messages"][i]["content"] = "..." # Fallback placeholder
        
        # Only log basic info about the request, not the full details
        logger.debug(f"Request for model: {litellm_request.get('model')}, stream: {litellm_request.get('stream', False)}")
        
        # Add a timeout to the request
        litellm_request['timeout'] = 300  # 300 seconds timeout

        # Handle streaming mode
        if request.stream:
            # Use LiteLLM for streaming
            num_tools = len(request.tools) if request.tools else 0
            
            log_request_beautifully(
                "POST", 
                raw_request.url.path, 
                display_model, 
                litellm_request.get('model'),
                len(litellm_request['messages']),
                num_tools,
                200  # Assuming success at this point
            )
            # Ensure we use the async version for streaming
            response_generator = await litellm.acompletion(**litellm_request)
            
            return StreamingResponse(
                handle_streaming(response_generator, request),
                media_type="text/event-stream"
            )
        else:
            # Use LiteLLM for regular completion
            num_tools = len(request.tools) if request.tools else 0
            
            log_request_beautifully(
                "POST", 
                raw_request.url.path, 
                display_model, 
                litellm_request.get('model'),
                len(litellm_request['messages']),
                num_tools,
                200  # Assuming success at this point
            )
            start_time = time.time()
            litellm_response = litellm.completion(**litellm_request)
            logger.debug(f"✅ RESPONSE RECEIVED: Model={litellm_request.get('model')}, Time={time.time() - start_time:.2f}s")
            
            # Convert LiteLLM response to Anthropic format
            anthropic_response = convert_litellm_to_anthropic(litellm_response, request)
            
            # 记录对话历史
            try:
                # 记录用户消息
                for msg in request.messages:
                    if msg.role in ['user', 'assistant']:
                        content_text = ""
                        if isinstance(msg.content, str):
                            content_text = msg.content
                        elif isinstance(msg.content, list):
                            # 从复杂内容块中提取文本
                            for block in msg.content:
                                if hasattr(block, "type") and block.type == "text":
                                    content_text += block.text + "\n"
                                elif isinstance(block, dict) and block.get("type") == "text":
                                    content_text += block.get("text", "") + "\n"
                        
                        if content_text.strip():
                            global_config.add_conversation_message(
                                role=msg.role,
                                content=content_text.strip(),
                                model_used=request.model
                            )
                
                # 记录助手回复
                if anthropic_response.content:
                    assistant_text = ""
                    for content_block in anthropic_response.content:
                        # 处理 Pydantic 模型对象
                        if hasattr(content_block, 'type') and content_block.type == "text":
                            assistant_text += content_block.text + "\n"
                        # 处理字典格式
                        elif isinstance(content_block, dict) and content_block.get("type") == "text":
                            assistant_text += content_block.get("text", "") + "\n"
                    
                    if assistant_text.strip():
                        global_config.add_conversation_message(
                            role="assistant",
                            content=assistant_text.strip(),
                            model_used=request.model
                        )
                        
            except Exception as conv_error:
                logger.error(f"Error recording conversation history: {conv_error}")
            
            # 记录调试日志 - 包含完整响应内容
            response_content = ""
            if hasattr(anthropic_response, 'content') and anthropic_response.content:
                for content_block in anthropic_response.content:
                    if hasattr(content_block, 'text'):
                        response_content += content_block.text
            
            global_config.add_debug_log(
                "response",
                f"Anthropic messages response: {request.model}",
                {
                    "response_id": getattr(anthropic_response, 'id', 'unknown'),
                    "model": request.model,
                    "usage": getattr(anthropic_response, 'usage', None).__dict__ if hasattr(anthropic_response, 'usage') else None,
                    "content": response_content,
                    "stop_reason": getattr(anthropic_response, 'stop_reason', None),
                    "full_response": {
                        "id": getattr(anthropic_response, 'id', 'unknown'),
                        "type": getattr(anthropic_response, 'type', 'message'),
                        "role": getattr(anthropic_response, 'role', 'assistant'),
                        "content": [{"type": "text", "text": response_content}] if response_content else [],
                        "model": getattr(anthropic_response, 'model', request.model),
                        "stop_reason": getattr(anthropic_response, 'stop_reason', None),
                        "usage": getattr(anthropic_response, 'usage', None).__dict__ if hasattr(anthropic_response, 'usage') else None
                    }
                }
            )
            
            return anthropic_response
                
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        
        # Capture as much info as possible about the error
        error_details = {
            "error": str(e),
            "type": type(e).__name__,
            "traceback": error_traceback
        }
        
        # Check for LiteLLM-specific attributes
        for attr in ['message', 'status_code', 'response', 'llm_provider', 'model']:
            if hasattr(e, attr):
                error_details[attr] = getattr(e, attr)
        
        # Check for additional exception details in dictionaries
        if hasattr(e, '__dict__'):
            for key, value in e.__dict__.items():
                if key not in error_details and key not in ['args', '__traceback__']:
                    error_details[key] = str(value)
        
        # Helper function to safely serialize objects for JSON
        def sanitize_for_json(obj):
            """递归地清理对象使其可以JSON序列化"""
            if isinstance(obj, dict):
                return {k: sanitize_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [sanitize_for_json(item) for item in obj]
            elif hasattr(obj, '__dict__'):
                return sanitize_for_json(obj.__dict__)
            elif hasattr(obj, 'text'):
                return str(obj.text)
            else:
                try:
                    json.dumps(obj)
                    return obj
                except (TypeError, ValueError):
                    return str(obj)
        
        # Log all error details with safe serialization
        sanitized_details = sanitize_for_json(error_details)
        logger.error(f"Error processing request: {json.dumps(sanitized_details, indent=2)}")
        
        # 记录调试日志 - 包含完整错误详情
        global_config.add_debug_log(
            "error",
            f"Request processing error: {type(e).__name__}",
            {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "model": getattr(request, 'model', 'unknown'),
                "full_error_details": sanitized_details,
                "request_summary": {
                    "model": getattr(request, 'model', 'unknown'),
                    "messages_count": len(getattr(request, 'messages', [])),
                    "stream": getattr(request, 'stream', False),
                    "max_tokens": getattr(request, 'max_tokens', None)
                }
            }
        )
        
        # Format error for response
        error_message = f"Error: {str(e)}"
        if 'message' in error_details and error_details['message']:
            error_message += f"\nMessage: {error_details['message']}"
        if 'response' in error_details and error_details['response']:
            error_message += f"\nResponse: {error_details['response']}"
        
        # Return detailed error
        status_code = error_details.get('status_code', 500)
        raise HTTPException(status_code=status_code, detail=error_message)

@app.post("/v1/messages/count_tokens")
async def count_tokens(
    request: TokenCountRequest,
    raw_request: Request
):
    try:
        # 检查代理服务器是否启用
        if not global_config.current_config["proxy_enabled"]:
            # 透明模式：直接转发到 Anthropic API
            logger.info("🔄 代理禁用，透明转发 count_tokens 到 Anthropic API")
            return await forward_to_anthropic(request, raw_request)
        # Log the incoming token count request
        original_model = request.original_model or request.model
        
        # Get the display name for logging, just the model name without provider prefix
        display_model = original_model
        if "/" in display_model:
            display_model = display_model.split("/")[-1]
        
        # Clean model name for capability check
        clean_model = request.model
        if clean_model.startswith("anthropic/"):
            clean_model = clean_model[len("anthropic/"):]
        elif clean_model.startswith("openai/"):
            clean_model = clean_model[len("openai/"):]
        
        # Convert the messages to a format LiteLLM can understand
        converted_request = convert_anthropic_to_litellm(
            MessagesRequest(
                model=request.model,
                max_tokens=100,  # Arbitrary value not used for token counting
                messages=request.messages,
                system=request.system,
                tools=request.tools,
                tool_choice=request.tool_choice,
                thinking=request.thinking
            )
        )
        
        # Use LiteLLM's token_counter function
        try:
            # Import token_counter function
            from litellm import token_counter
            
            # Log the request beautifully
            num_tools = len(request.tools) if request.tools else 0
            
            log_request_beautifully(
                "POST",
                raw_request.url.path,
                display_model,
                converted_request.get('model'),
                len(converted_request['messages']),
                num_tools,
                200  # Assuming success at this point
            )
            
            # Prepare token counter arguments
            token_counter_args = {
                "model": converted_request["model"],
                "messages": converted_request["messages"],
            }
            
            # Add custom base URL for OpenAI models if configured
            if request.model.startswith("openai/") and OPENAI_BASE_URL:
                token_counter_args["api_base"] = OPENAI_BASE_URL
            
            # Count tokens
            token_count = token_counter(**token_counter_args)
            
            # Return Anthropic-style response
            return TokenCountResponse(input_tokens=token_count)
            
        except ImportError:
            logger.error("Could not import token_counter from litellm")
            # Fallback to a simple approximation
            return TokenCountResponse(input_tokens=1000)  # Default fallback
            
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error counting tokens: {str(e)}\n{error_traceback}")
        raise HTTPException(status_code=500, detail=f"Error counting tokens: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Anthropic Proxy for LiteLLM"}

@app.get("/models")
async def get_available_models():
    """获取所有可用的模型列表和预设配置"""
    return ModelListResponse(
        openai_models=OPENAI_MODELS,
        gemini_models=GEMINI_MODELS,
        anthropic_models=ANTHROPIC_MODELS,
        mapping_presets=MAPPING_PRESETS,
        total_models=len(OPENAI_MODELS) + len(GEMINI_MODELS) + len(ANTHROPIC_MODELS)
    )

@app.post("/switch_model")
async def switch_model(request: ConfigUpdateRequest):
    """动态切换模型配置"""
    try:
        # 如果使用预设配置
        if request.preset:
            if request.preset not in MAPPING_PRESETS:
                available_presets = list(MAPPING_PRESETS.keys())
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid preset '{request.preset}'. Available presets: {available_presets}"
                )
            
            preset_config = MAPPING_PRESETS[request.preset]
            logger.info(f"Applying preset '{request.preset}': {preset_config['description']}")
            
            # 应用预设配置
            global_config.set_models(
                big_model=preset_config["big_model"],
                small_model=preset_config["small_model"]
            )
            
            # 获取更新后的配置
            current_config = global_config.get_status()
            
            return ConfigResponse(
                preferred_provider=current_config["preferred_provider"],
                big_model=current_config["big_model"],
                small_model=current_config["small_model"],
                message=f"Applied preset '{request.preset}': {preset_config['description']}"
            )
        
        # 验证提供商
        if request.preferred_provider and request.preferred_provider not in ["openai", "google", "anthropic"]:
            raise HTTPException(status_code=400, detail="Invalid provider. Must be one of: openai, google, anthropic")
        
        # 验证模型（现在支持所有三个提供商的模型）
        all_models = OPENAI_MODELS + GEMINI_MODELS + ANTHROPIC_MODELS
        
        if request.big_model and request.big_model not in all_models:
            logger.warning(f"Big model '{request.big_model}' not in known model lists")
        
        if request.small_model and request.small_model not in all_models:
            logger.warning(f"Small model '{request.small_model}' not in known model lists")
        
        # 更新配置
        global_config.set_models(
            big_model=request.big_model,
            small_model=request.small_model
        )
        
        # 获取更新后的配置
        current_config = global_config.get_status()
        
        # 检查是否是跨提供商配置
        big_provider = get_model_provider(current_config["big_model"])
        small_provider = get_model_provider(current_config["small_model"])
        
        message = "Configuration updated successfully"
        if big_provider != small_provider and big_provider != "unknown" and small_provider != "unknown":
            message += f" (Cross-provider setup: {big_provider.upper()} + {small_provider.upper()})"
        
        return ConfigResponse(
            preferred_provider=current_config["preferred_provider"],
            big_model=current_config["big_model"],
            small_model=current_config["small_model"],
            message=message
        )
        
    except Exception as e:
        logger.error(f"Error updating configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating configuration: {str(e)}")

@app.get("/config")
async def get_config():
    """获取当前配置"""
    # 获取全局配置状态
    current_config = global_config.get_status()
    return ConfigResponse(
        preferred_provider=current_config["preferred_provider"],
        big_model=current_config["big_model"],
        small_model=current_config["small_model"],
        message="Current configuration"
    )

@app.post("/sync_config")
async def sync_config():
    """与全局配置同步"""
    # 无需同步，直接使用全局配置
    global_status = global_config.get_status()
    
    return {
        "message": "Configuration synced with global settings",
        "proxy_enabled": global_status["proxy_enabled"],
        "big_model": global_status["big_model"],
        "small_model": global_status["small_model"],
        "current_preset": global_status["current_preset"]
    }

@app.get("/debug_logs")
async def get_debug_logs(log_type: Optional[str] = None, limit: Optional[int] = None):
    """获取调试日志"""
    logs = global_config.get_debug_logs(log_type=log_type, limit=limit)
    return {
        "logs": logs,
        "total_count": len(global_config.debug_logs),
        "available_types": ["request", "response", "error", "config", "model_switch"]
    }

@app.delete("/debug_logs")
async def clear_debug_logs():
    """清空调试日志"""
    global_config.clear_debug_logs()
    return {"message": "Debug logs cleared successfully"}

# 对话记录控制API端点
@app.get("/conversation/status")
async def get_conversation_recording_status():
    """获取对话记录状态"""
    return global_config.get_conversation_status()

@app.post("/conversation/enable")
async def enable_conversation_recording(file_path: str):
    """启用对话记录功能"""
    success = global_config.enable_conversation_recording(file_path)
    if success:
        return {"message": f"Conversation recording enabled, saving to: {file_path}"}
    else:
        raise HTTPException(status_code=400, detail="Failed to enable conversation recording")

@app.post("/conversation/disable")
async def disable_conversation_recording():
    """禁用对话记录功能"""
    global_config.disable_conversation_recording()
    return {"message": "Conversation recording disabled"}

@app.post("/conversation/flush")
async def flush_conversation_buffer():
    """强制刷新对话记录缓冲区"""
    global_config.force_flush_conversations()
    return {"message": "Conversation buffer flushed to file"}

@app.post("/conversation/load")
async def load_conversation_from_file(file_path: str):
    """从文件读取对话记录并替换当前记录"""
    result = global_config.load_conversation_from_file(file_path)
    
    if result["success"]:
        return {
            "message": result["message"],
            "file_path": result["file_path"],
            "last_record": result["last_record"],
            "total_records": result["total_records"]
        }
    else:
        raise HTTPException(status_code=400, detail=result["error"])

@app.get("/proxy_server/status")
async def get_proxy_server_status():
    """获取代理服务器状态"""
    return ProxyServerStatusResponse(
        proxy_server_enabled=global_config.current_config["proxy_enabled"],
        message="Proxy server is " + ("enabled" if global_config.current_config["proxy_enabled"] else "disabled"),
        claude_code_should_use_proxy=global_config.current_config["proxy_enabled"]
    )

@app.post("/proxy_server/toggle")
async def toggle_proxy_server(request: ProxyServerToggleRequest):
    """切换代理服务器启用/禁用状态"""
    try:
        old_status = global_config.current_config["proxy_enabled"]
        global_config.current_config["proxy_enabled"] = request.enabled
        new_status = request.enabled
        
        action = "enabled" if new_status else "disabled"
        change_info = f"changed from {'enabled to disabled' if old_status else 'disabled to enabled'}"
        
        return ProxyServerStatusResponse(
            proxy_server_enabled=new_status,
            message=f"Proxy server {action} ({change_info})",
            claude_code_should_use_proxy=new_status
        )
        
    except Exception as e:
        logger.error(f"Error toggling proxy server: {e}")
        raise HTTPException(status_code=500, detail=f"Error toggling proxy server: {str(e)}")

@app.post("/proxy_server/enable")
async def enable_proxy_server():
    """启用代理服务器"""
    return await toggle_proxy_server(ProxyServerToggleRequest(enabled=True))

@app.post("/proxy_server/disable")
async def disable_proxy_server():
    """禁用代理服务器"""
    return await toggle_proxy_server(ProxyServerToggleRequest(enabled=False))

@app.post("/conversation/continue")
async def continue_with_history(request: MessagesRequest):
    """使用历史对话继续聊天"""
    try:
        # 获取历史对话
        history_messages = global_config.get_conversation_for_model()
        
        # 将历史对话与新消息合并
        all_messages = history_messages + request.messages
        
        # 创建新的请求，包含完整的对话历史
        enhanced_request = MessagesRequest(
            model=request.model,
            max_tokens=request.max_tokens,
            messages=all_messages,
            system=request.system,
            stop_sequences=request.stop_sequences,
            stream=request.stream,
            temperature=request.temperature,
            top_p=request.top_p,
            top_k=request.top_k,
            metadata=request.metadata,
            tools=request.tools,
            tool_choice=request.tool_choice,
            thinking=request.thinking
        )
        
        return {"message": "History integrated", "total_messages": len(all_messages), "messages": all_messages}
        
    except Exception as e:
        logger.error(f"Error continuing with history: {e}")
        raise HTTPException(status_code=500, detail=f"Error continuing with history: {str(e)}")

# Define ANSI color codes for terminal output
class Colors:
    CYAN = "\033[96m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    DIM = "\033[2m"
def log_request_beautifully(method, path, claude_model, openai_model, num_messages, num_tools, status_code):
    """Log requests in a beautiful, twitter-friendly format showing Claude to OpenAI mapping."""
    # 检查是否应该显示控制台日志（可通过环境变量控制）
    import os
    show_console_logs = os.getenv("CLAUDE_PROXY_CONSOLE_LOGS", "true").lower() == "true"
    
    if not show_console_logs:
        return  # 不显示控制台日志
    
    # Format the Claude model name nicely
    claude_display = f"{Colors.CYAN}{claude_model}{Colors.RESET}"
    
    # Extract endpoint name
    endpoint = path
    if "?" in endpoint:
        endpoint = endpoint.split("?")[0]
    
    # Extract just the OpenAI model name without provider prefix
    openai_display = openai_model
    if "/" in openai_display:
        openai_display = openai_display.split("/")[-1]
    openai_display = f"{Colors.GREEN}{openai_display}{Colors.RESET}"
    
    # Format tools and messages
    tools_str = f"{Colors.MAGENTA}{num_tools} tools{Colors.RESET}"
    messages_str = f"{Colors.BLUE}{num_messages} messages{Colors.RESET}"
    
    # Format status code
    status_str = f"{Colors.GREEN}✓ {status_code} OK{Colors.RESET}" if status_code == 200 else f"{Colors.RED}✗ {status_code}{Colors.RESET}"
    

    # Put it all together in a clear, beautiful format
    log_line = f"{Colors.BOLD}{method} {endpoint}{Colors.RESET} {status_str}"
    model_line = f"{claude_display} → {openai_display} {tools_str} {messages_str}"
    
    # Print to console
    print(log_line)
    print(model_line)
    sys.stdout.flush()

# OpenAI兼容接口 - 用于Claude Code
class OpenAIMessage(BaseModel):
    role: str
    content: str

class OpenAIChatRequest(BaseModel):
    model: str
    messages: List[OpenAIMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: Optional[bool] = False

@app.post("/v1/chat/completions")
async def openai_chat_completions(request: OpenAIChatRequest, raw_request: Request):
    """OpenAI兼容的chat completions接口，专门用于Claude Code"""
    try:
        # 记录调试日志 - 包含完整请求内容
        messages_content = []
        for msg in request.messages:
            messages_content.append({
                "role": msg.role,
                "content": msg.content
            })
        
        global_config.add_debug_log(
            "request",
            f"OpenAI chat completions request: {request.model}",
            {
                "model": request.model,
                "messages_count": len(request.messages),
                "messages": messages_content,  # 完整消息内容
                "stream": request.stream,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "full_request": {
                    "model": request.model,
                    "messages": messages_content,
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                    "stream": request.stream,
                    "top_p": getattr(request, 'top_p', None),
                    "frequency_penalty": getattr(request, 'frequency_penalty', None),
                    "presence_penalty": getattr(request, 'presence_penalty', None),
                    "stop": getattr(request, 'stop', None)
                }
            }
        )
        
        # 转换为Anthropic格式的消息
        anthropic_messages = []
        for msg in request.messages:
            anthropic_messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # 创建Anthropic请求
        anthropic_request = MessagesRequest(
            model=request.model,
            messages=anthropic_messages,
            max_tokens=request.max_tokens or 1000,
            temperature=request.temperature,
            stream=request.stream
        )
        
        # 调用现有的处理函数
        response = await create_message(anthropic_request, raw_request)
        
        # 如果是流式响应，直接返回
        if request.stream:
            return response
        
        # 转换为OpenAI格式
        if hasattr(response, 'content') and response.content:
            openai_response = {
                "id": f"chatcmpl-{response.id}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": request.model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response.content[0].text if response.content else ""
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": response.usage.input_tokens if hasattr(response, 'usage') else 0,
                    "completion_tokens": response.usage.output_tokens if hasattr(response, 'usage') else 0,
                    "total_tokens": (response.usage.input_tokens + response.usage.output_tokens) if hasattr(response, 'usage') else 0
                }
            }
            
            # 记录调试日志 - 包含完整响应内容
            global_config.add_debug_log(
                "response",
                f"OpenAI chat completions response: {request.model}",
                {
                    "response_id": openai_response["id"],
                    "model": request.model,
                    "finish_reason": "stop",
                    "usage": openai_response["usage"],
                    "content": openai_response["choices"][0]["message"]["content"],  # 完整响应内容
                    "full_response": openai_response  # 完整响应对象
                }
            )
            
            return openai_response
        else:
            return response
            
    except Exception as e:
        # 记录错误日志
        global_config.add_debug_log(
            "error",
            f"OpenAI chat completions error: {str(e)}",
            {
                "model": request.model,
                "error": str(e),
                "messages_count": len(request.messages)
            }
        )
        raise e

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Run with: uvicorn server:app --reload --host 0.0.0.0 --port 8082")
        sys.exit(0)
    
    # Configure uvicorn to run with minimal logs
    uvicorn.run(app, host="0.0.0.0", port=8082, log_level="error")

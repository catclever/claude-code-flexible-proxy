"""
配置管理系统
从 providers.json 加载提供商配置和预设组合
"""

import os
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

@dataclass
class ProviderConfig:
    """提供商配置"""
    name: str
    base_url: str
    api_key_env: str  # 环境变量名
    api_format: str = "openai"  # API格式: "openai" 或 "anthropic"
    endpoint: str = "/chat/completions"  # API端点
    api_key: Optional[str] = None
    models: List[str] = None
    
    def __post_init__(self):
        # 从环境变量读取 API Key
        if not self.api_key:
            self.api_key = os.environ.get(self.api_key_env)
        
        # 初始化模型列表
        if self.models is None:
            self.models = []
    
    @property
    def is_available(self) -> bool:
        """检查提供商是否可用（有API Key）"""
        return bool(self.api_key)

def load_providers_config():
    """加载提供商配置"""
    config_file = "providers.json"
    example_file = "providers.json.example"
    
    # 优先加载 providers.json，如果不存在则加载示例文件
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        elif os.path.exists(example_file):
            with open(example_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            raise FileNotFoundError("找不到配置文件")
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return None

# 加载配置
_config_data = load_providers_config()
if not _config_data:
    raise RuntimeError("无法加载提供商配置")

# 创建提供商对象
PROVIDERS = {}
for provider_id, provider_data in _config_data["providers"].items():
    PROVIDERS[provider_id] = ProviderConfig(
        name=provider_data["name"],
        base_url=provider_data["base_url"],
        api_key_env=provider_data["api_key_env"],
        models=provider_data["models"]
    )

# 加载预设配置
MODEL_PRESETS = _config_data["presets"]

class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        # 重新加载最新配置
        config_data = load_providers_config()
        if config_data:
            self.providers = {}
            for provider_id, provider_data in config_data["providers"].items():
                self.providers[provider_id] = ProviderConfig(
                    name=provider_data["name"],
                    base_url=provider_data["base_url"], 
                    api_key_env=provider_data["api_key_env"],
                    api_format=provider_data.get("api_format", "openai"),
                    endpoint=provider_data.get("endpoint", "/chat/completions"),
                    models=provider_data["models"]
                )
            self.presets = config_data["presets"].copy()
        else:
            self.providers = PROVIDERS.copy()
            self.presets = MODEL_PRESETS.copy()
        
        # 初始化调试日志（内存存储，退出时清空）
        self.debug_logs = []
        self.max_debug_logs = 50  # 最大调试日志数量
        
        # 初始化对话记录功能（文件持久化，可选开关）
        self.conversation_recording_enabled = False  # 默认关闭
        self.conversation_file_path = None  # 保存路径
        self.conversation_buffer = []  # 缓冲区，批量写入文件
        self.buffer_size = 10  # 每10条记录写入一次文件
        self.last_conversations = []  # 用于去重的最近对话记录
        
        # 初始化配置，尝试加载default预设
        self.current_config = {
            "proxy_enabled": True,
            "big_model": None,
            "small_model": None,
            "current_preset": None
        }
        
        # 尝试自动加载default预设
        self._load_default_preset()
    
    def _load_default_preset(self):
        """尝试加载default预设，如果不存在或无效则保持None"""
        if "default" in self.presets:
            preset = self.presets["default"]
            # 验证default预设的模型是否可用
            if (self.validate_model(preset["big_model"]) and 
                self.validate_model(preset["small_model"])):
                self.current_config.update({
                    "big_model": preset["big_model"],
                    "small_model": preset["small_model"],
                    "current_preset": "default"
                })
                print(f"✅ 已自动加载默认预设: {preset['name']}")
            else:
                print("⚠️ default预设模型不可用，需要手动配置模型")
        else:
            print("⚠️ 未找到default预设，需要手动配置模型")
    
    def get_available_providers(self) -> Dict[str, ProviderConfig]:
        """获取可用的提供商（有API Key的）"""
        return {k: v for k, v in self.providers.items() if v.is_available}
    
    def get_all_models(self) -> Dict[str, List[str]]:
        """获取所有模型，按提供商分组"""
        return {name: provider.models for name, provider in self.providers.items()}
    
    def find_model_provider(self, model_name: str) -> Optional[str]:
        """找到模型属于哪个提供商"""
        for provider_name, provider in self.providers.items():
            if model_name in provider.models:
                return provider_name
        return None
    
    def validate_model(self, model_name: str) -> bool:
        """验证模型是否存在且提供商可用"""
        provider_name = self.find_model_provider(model_name)
        if not provider_name:
            return False
        return self.providers[provider_name].is_available
    
    def apply_preset(self, preset_name: str) -> bool:
        """应用预设配置"""
        if preset_name not in self.presets:
            return False
            
        preset = self.presets[preset_name]
        
        # 验证模型可用性
        if not self.validate_model(preset["big_model"]):
            return False
        if not self.validate_model(preset["small_model"]):
            return False
        
        old_config = self.current_config.copy()
        self.current_config.update({
            "big_model": preset["big_model"],
            "small_model": preset["small_model"], 
            "current_preset": preset_name
        })
        
        # 记录调试日志
        self.add_debug_log(
            "config", 
            f"Applied preset: {preset_name}",
            {
                "preset_name": preset_name,
                "old_big_model": old_config.get("big_model"),
                "old_small_model": old_config.get("small_model"),
                "new_big_model": preset["big_model"],
                "new_small_model": preset["small_model"]
            }
        )
        return True
    
    def set_models(self, big_model: str, small_model: str) -> bool:
        """手动设置模型"""
        if not self.validate_model(big_model) or not self.validate_model(small_model):
            return False
            
        old_config = self.current_config.copy()
        self.current_config.update({
            "big_model": big_model,
            "small_model": small_model,
            "current_preset": None  # 清除预设
        })
        
        # 记录调试日志
        self.add_debug_log(
            "config", 
            "Manual model configuration",
            {
                "old_big_model": old_config.get("big_model"),
                "old_small_model": old_config.get("small_model"),
                "new_big_model": big_model,
                "new_small_model": small_model
            }
        )
        return True
    
    def toggle_proxy(self) -> bool:
        """切换代理状态"""
        self.current_config["proxy_enabled"] = not self.current_config["proxy_enabled"]
        return self.current_config["proxy_enabled"]
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        available_providers = list(self.get_available_providers().keys())
        
        return {
            "proxy_enabled": self.current_config["proxy_enabled"],
            "big_model": self.current_config["big_model"],
            "small_model": self.current_config["small_model"],
            "current_preset": self.current_config["current_preset"],
            "available_providers": available_providers,
            "total_models": sum(len(p.models) for p in self.providers.values()),
            "available_models": sum(len(p.models) for p in self.get_available_providers().values())
        }
    
    def export_config(self) -> str:
        """导出配置为JSON"""
        return json.dumps(self.current_config, indent=2)
    
    def load_config(self, config_str: str) -> bool:
        """从JSON加载配置"""
        try:
            config = json.loads(config_str)
            # 验证配置有效性
            if "big_model" in config and "small_model" in config:
                return self.set_models(config["big_model"], config["small_model"])
            return False
        except (json.JSONDecodeError, KeyError):
            return False
    
    def add_debug_log(self, log_type: str, message: str, details: Optional[Dict[str, Any]] = None):
        """添加调试日志"""
        from datetime import datetime
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": log_type,  # "request", "response", "error", "config", "model_switch"
            "message": message,
            "details": details or {}
        }
        self.debug_logs.append(log_entry)
        
        # 保持日志数量在限制内
        if len(self.debug_logs) > self.max_debug_logs:
            self.debug_logs = self.debug_logs[-self.max_debug_logs:]
    
    def get_debug_logs(self, log_type: Optional[str] = None, limit: Optional[int] = None):
        """获取调试日志"""
        logs = self.debug_logs
        
        # 过滤日志类型
        if log_type:
            logs = [log for log in logs if log["type"] == log_type]
        
        # 限制数量
        if limit:
            logs = logs[-limit:]
            
        return logs
    
    def clear_debug_logs(self):
        """清空调试日志"""
        self.debug_logs = []
    
    def enable_conversation_recording(self, file_path: str) -> bool:
        """启用对话记录功能"""
        import os
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            self.conversation_file_path = file_path
            self.conversation_recording_enabled = True
            
            # 如果文件已存在，加载最近的记录用于去重
            self._load_recent_conversations()
            
            print(f"✅ 对话记录已启用，保存到: {file_path}")
            return True
        except Exception as e:
            print(f"❌ 启用对话记录失败: {e}")
            return False
    
    def disable_conversation_recording(self):
        """禁用对话记录功能"""
        # 先将缓冲区的记录写入文件
        if self.conversation_buffer:
            self._flush_conversation_buffer()
        
        self.conversation_recording_enabled = False
        self.conversation_file_path = None
        self.conversation_buffer = []
        self.last_conversations = []
        print("✅ 对话记录已禁用")
    
    def add_conversation_message(self, role: str, content: str, model_used: str, timestamp: Optional[str] = None):
        """添加对话消息到记录（仅记录用户发送给AI的内容）"""
        if not self.conversation_recording_enabled or role != "user":
            return  # 只记录用户消息，不记录助手回复
        
        from datetime import datetime
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        # 简化记录格式，只保留核心信息
        message = {
            "user_input": content,
            "timestamp": timestamp,
            "model_used": model_used
        }
        
        # 执行去重检查
        if not self._is_duplicate_message(content):
            self.conversation_buffer.append(message)
            self.last_conversations.append(content)
            
            # 保持最近对话记录在合理范围内
            if len(self.last_conversations) > 50:
                self.last_conversations = self.last_conversations[-50:]
            
            # 当缓冲区满时，写入文件
            if len(self.conversation_buffer) >= self.buffer_size:
                self._flush_conversation_buffer()
    
    def _is_duplicate_message(self, content: str) -> bool:
        """检查是否为重复消息（子串去重）"""
        for prev_content in reversed(self.last_conversations[-20:]):  # 只检查最近20条
            if content in prev_content:  # 当前内容是之前内容的子串
                return True
            if prev_content in content:  # 之前内容是当前内容的子串，删除之前的记录
                self._remove_conversation_by_content(prev_content)
        return False
    
    def _remove_conversation_by_content(self, content: str):
        """从最近对话记录中移除指定内容"""
        self.last_conversations = [c for c in self.last_conversations if c != content]
        # 注意：这里不删除已写入文件的记录，因为文件操作成本太高
        # 实际项目中可以考虑定期清理文件或使用数据库
    
    def _flush_conversation_buffer(self):
        """将缓冲区内容写入文件"""
        if not self.conversation_buffer or not self.conversation_file_path:
            return
        
        try:
            import json
            with open(self.conversation_file_path, 'a', encoding='utf-8') as f:
                for message in self.conversation_buffer:
                    f.write(json.dumps(message, ensure_ascii=False) + '\n')
            
            print(f"📝 已保存 {len(self.conversation_buffer)} 条对话记录到文件")
            self.conversation_buffer = []  # 清空缓冲区
        except Exception as e:
            print(f"❌ 写入对话记录失败: {e}")
    
    def _load_recent_conversations(self):
        """从文件加载最近的对话记录用于去重"""
        if not self.conversation_file_path or not os.path.exists(self.conversation_file_path):
            return
        
        try:
            import json
            with open(self.conversation_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # 只加载最近50条记录用于去重
                recent_lines = lines[-50:] if len(lines) > 50 else lines
                
                for line in recent_lines:
                    try:
                        message = json.loads(line.strip())
                        self.last_conversations.append(message.get('content', ''))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"⚠️ 加载历史对话记录失败: {e}")
    
    def get_conversation_status(self) -> Dict[str, Any]:
        """获取对话记录状态"""
        return {
            "recording_enabled": self.conversation_recording_enabled,
            "file_path": self.conversation_file_path,
            "buffer_size": len(self.conversation_buffer),
            "total_recent_conversations": len(self.last_conversations)
        }
    
    def force_flush_conversations(self):
        """强制刷新对话记录缓冲区"""
        if self.conversation_buffer:
            self._flush_conversation_buffer()
    
    def load_conversation_from_file(self, file_path: str) -> Dict[str, Any]:
        """从文件读取对话记录并替换当前记录"""
        try:
            import os
            import json
            
            if not os.path.exists(file_path):
                return {"success": False, "error": f"文件不存在: {file_path}"}
            
            # 验证文件格式和读取内容
            validation_result = self._validate_conversation_file(file_path)
            if not validation_result["valid"]:
                return {"success": False, "error": validation_result["error"]}
            
            # 读取最后一条有效记录
            last_record = validation_result["last_record"]
            if not last_record:
                return {"success": False, "error": "文件中没有找到有效的对话记录"}
            
            # 先禁用当前记录（如果启用的话）
            was_enabled = self.conversation_recording_enabled
            if was_enabled:
                self.disable_conversation_recording()
            
            # 清空当前记录状态
            self.conversation_buffer = []
            self.last_conversations = []
            
            # 重新启用记录功能，指向读取的文件
            success = self.enable_conversation_recording(file_path)
            if not success:
                return {"success": False, "error": "无法启用对话记录功能"}
            
            # 将读取的记录添加到缓存中用于去重
            self.last_conversations = [last_record.get("user_input", "")]
            
            return {
                "success": True, 
                "message": f"成功读取对话记录并启用记录功能",
                "file_path": file_path,
                "last_record": last_record,
                "total_records": validation_result["total_records"]
            }
            
        except Exception as e:
            return {"success": False, "error": f"读取失败: {str(e)}"}
    
    def _validate_conversation_file(self, file_path: str) -> Dict[str, Any]:
        """验证对话记录文件格式"""
        try:
            import json
            
            valid_records = []
            total_lines = 0
            
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    total_lines += 1
                    line = line.strip()
                    if not line:  # 跳过空行
                        continue
                    
                    try:
                        # 尝试解析JSON
                        record = json.loads(line)
                        
                        # 验证记录格式
                        if self._is_valid_conversation_record(record):
                            valid_records.append(record)
                        else:
                            print(f"⚠️ 第 {line_num} 行格式无效，已跳过")
                            
                    except json.JSONDecodeError as e:
                        print(f"⚠️ 第 {line_num} 行JSON格式错误: {e}")
                        continue
            
            if not valid_records:
                return {
                    "valid": False,
                    "error": "文件中没有找到有效的对话记录",
                    "total_records": 0
                }
            
            # 返回最后一条有效记录
            return {
                "valid": True,
                "last_record": valid_records[-1],
                "total_records": len(valid_records),
                "total_lines": total_lines
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"文件验证失败: {str(e)}",
                "total_records": 0
            }
    
    def _is_valid_conversation_record(self, record: dict) -> bool:
        """验证单条对话记录格式是否有效"""
        required_fields = ["user_input", "timestamp", "model_used"]
        
        # 检查必需字段
        if not all(field in record for field in required_fields):
            return False
        
        # 检查字段类型
        if not isinstance(record["user_input"], str) or not record["user_input"].strip():
            return False
        
        if not isinstance(record["timestamp"], str):
            return False
        
        if not isinstance(record["model_used"], str) or not record["model_used"].strip():
            return False
        
        # 验证时间戳格式（ISO格式）
        try:
            from datetime import datetime
            datetime.fromisoformat(record["timestamp"].replace('Z', '+00:00'))
        except ValueError:
            return False
        
        return True

# 全局配置管理器实例
config_manager = ConfigManager()
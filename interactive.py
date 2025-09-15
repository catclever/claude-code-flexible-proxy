#!/usr/bin/env python3
"""
交互式终端应用
同时运行服务器和提供交互式配置管理
"""

import asyncio
import threading
import sys
import os
import signal
import atexit
import subprocess
import psutil
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
import uvicorn
from config import config_manager, MODEL_PRESETS
import time

console = Console()

class InteractiveApp:
    def __init__(self):
        self.server_thread = None
        self.server_process = None
        self.server_running = False
        self.port = 8082
        self.original_anthropic_base_url = None
        
        # 注册清理函数
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
    def get_shell_type(self):
        """检测当前 shell 类型"""
        shell = os.environ.get('SHELL', '')
        if 'zsh' in shell:
            return 'zsh'
        elif 'bash' in shell:
            return 'bash'
        elif 'fish' in shell:
            return 'fish'
        else:
            return 'bash'  # 默认
    
    def get_shell_config_file(self, shell_type):
        """获取 shell 配置文件路径"""
        home = os.path.expanduser("~")
        if shell_type == 'zsh':
            return os.path.join(home, '.zshrc')
        elif shell_type == 'bash':
            # 检查常见的 bash 配置文件
            for config_file in ['.bashrc', '.bash_profile', '.profile']:
                path = os.path.join(home, config_file)
                if os.path.exists(path):
                    return path
            return os.path.join(home, '.bashrc')  # 默认
        elif shell_type == 'fish':
            config_dir = os.path.join(home, '.config', 'fish')
            return os.path.join(config_dir, 'config.fish')
        else:
            return os.path.join(home, '.bashrc')
    
    def set_claude_code_env(self):
        """设置 Claude Code 环境变量"""
        try:
            # 保存原有的环境变量
            self.original_anthropic_base_url = os.environ.get('ANTHROPIC_BASE_URL')
            
            # 设置新的环境变量
            proxy_url = f"http://localhost:{self.port}"
            os.environ['ANTHROPIC_BASE_URL'] = proxy_url
            
            # 尝试持久化设置到 shell 配置文件
            shell_type = self.get_shell_type()
            config_file = self.get_shell_config_file(shell_type)
            
            # 创建备注行标识
            marker_start = "# Claude Code Proxy - AUTO GENERATED - DO NOT EDIT"
            marker_end = "# Claude Code Proxy - END"
            export_line = f"export ANTHROPIC_BASE_URL='{proxy_url}'"
            
            try:
                # 读取现有配置
                if os.path.exists(config_file):
                    with open(config_file, 'r') as f:
                        lines = f.readlines()
                else:
                    lines = []
                
                # 移除之前的配置（如果存在）
                filtered_lines = []
                skip = False
                for line in lines:
                    if marker_start in line:
                        skip = True
                        continue
                    elif marker_end in line:
                        skip = False
                        continue
                    elif not skip:
                        filtered_lines.append(line)
                
                # 添加新的配置
                filtered_lines.extend([
                    f"\n{marker_start}\n",
                    f"{export_line}\n",
                    f"{marker_end}\n"
                ])
                
                # 写回配置文件
                with open(config_file, 'w') as f:
                    f.writelines(filtered_lines)
                
                console.print(f"[green]✅ 已设置 Claude Code 环境变量到 {config_file}[/green]")
                console.print(f"[cyan]   ANTHROPIC_BASE_URL = {proxy_url}[/cyan]")
                
                # 提示用户重新加载 shell
                if shell_type == 'zsh':
                    reload_cmd = "source ~/.zshrc"
                elif shell_type == 'bash':
                    reload_cmd = f"source {config_file}"
                elif shell_type == 'fish':
                    reload_cmd = "source ~/.config/fish/config.fish"
                else:
                    reload_cmd = f"source {config_file}"
                    
                console.print(f"[yellow]💡 提示: 新终端会自动使用代理，或运行: {reload_cmd}[/yellow]")
                
            except Exception as e:
                console.print(f"[yellow]⚠️ 无法写入配置文件 {config_file}: {e}[/yellow]")
                console.print("[yellow]   环境变量仅在当前进程生效[/yellow]")
                
        except Exception as e:
            console.print(f"[red]❌ 设置环境变量失败: {e}[/red]")
    
    def unset_claude_code_env(self):
        """取消 Claude Code 环境变量设置"""
        try:
            # 恢复原有环境变量
            if self.original_anthropic_base_url:
                os.environ['ANTHROPIC_BASE_URL'] = self.original_anthropic_base_url
            else:
                os.environ.pop('ANTHROPIC_BASE_URL', None)
            
            # 从 shell 配置文件中移除
            shell_type = self.get_shell_type()
            config_file = self.get_shell_config_file(shell_type)
            
            marker_start = "# Claude Code Proxy - AUTO GENERATED - DO NOT EDIT"
            marker_end = "# Claude Code Proxy - END"
            
            try:
                if os.path.exists(config_file):
                    with open(config_file, 'r') as f:
                        lines = f.readlines()
                    
                    # 移除自动生成的配置
                    filtered_lines = []
                    skip = False
                    for line in lines:
                        if marker_start in line:
                            skip = True
                            continue
                        elif marker_end in line:
                            skip = False
                            continue
                        elif not skip:
                            filtered_lines.append(line)
                    
                    # 写回配置文件
                    with open(config_file, 'w') as f:
                        f.writelines(filtered_lines)
                    
                    console.print(f"[green]✅ 已从 {config_file} 移除 Claude Code 配置[/green]")
                
            except Exception as e:
                console.print(f"[yellow]⚠️ 无法修改配置文件: {e}[/yellow]")
                
        except Exception as e:
            console.print(f"[red]❌ 取消环境变量设置失败: {e}[/red]")
    
    def start_server(self):
        """启动 FastAPI 服务器"""
        def run_server():
            try:
                # 配置环境变量，默认显示控制台日志
                import os
                os.environ["CLAUDE_PROXY_CONSOLE_LOGS"] = "true"
                
                # 配置uvicorn日志，减少控制台输出
                import logging
                # 禁用uvicorn的访问日志，只保留错误日志
                logging.getLogger("uvicorn.access").disabled = True
                logging.getLogger("uvicorn").setLevel(logging.WARNING)
                
                uvicorn.run(
                    "server:app",
                    host="0.0.0.0", 
                    port=self.port,
                    reload=False,
                    log_level="warning",  # 只显示警告和错误，隐藏请求日志
                    access_log=False      # 禁用访问日志
                )
            except Exception as e:
                console.print(f"[red]服务器启动失败: {e}[/red]")
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.server_running = True
        
        # 等待服务器启动
        time.sleep(2)
        console.print(f"[green]✅ 服务器已启动在 http://localhost:{self.port}[/green]")
        
        # 设置 Claude Code 环境变量
        self.set_claude_code_env()
    
    def cleanup(self):
        """清理资源"""
        if self.server_running:
            console.print("\n[yellow]🧹 正在清理资源...[/yellow]")
            
            # 取消环境变量设置
            self.unset_claude_code_env()
            
            # 保存对话记录并清空调试日志
            try:
                # 强制保存对话记录缓冲区
                requests.post(f"http://localhost:{self.port}/conversation/flush", timeout=2)
                console.print("[green]💾 已保存对话记录[/green]")
            except:
                pass  # 忽略保存失败（可能服务器已关闭）
            
            # 清空调试日志（仅内存中的调试信息）
            config_manager.clear_debug_logs()
            console.print("[green]🗑️  已清空调试日志[/green]")
            
            # 停止服务器
            self.server_running = False
            console.print("[green]✅ 清理完成[/green]")
    
    def signal_handler(self, signum, frame):
        """信号处理器"""
        console.print(f"\n[yellow]收到信号 {signum}，正在退出...[/yellow]")
        self.cleanup()
        sys.exit(0)
    
    def show_status(self):
        """显示当前状态"""
        status = config_manager.get_status()
        
        # 创建状态表格
        table = Table(title="🚀 Claude Code 代理服务器状态", show_header=True, header_style="bold magenta")
        table.add_column("配置项", style="cyan", no_wrap=True)
        table.add_column("当前值", style="green")
        table.add_column("说明", style="yellow")
        
        proxy_status = "🟢 启用" if status["proxy_enabled"] else "🔴 禁用"
        proxy_desc = "模型映射 + 对话历史" if status["proxy_enabled"] else "透明转发到 Anthropic"
        
        table.add_row("代理状态", proxy_status, proxy_desc)
        
        # 处理模型配置显示
        big_model_display = status["big_model"] or "🔴 未配置"
        small_model_display = status["small_model"] or "🔴 未配置"
        table.add_row("大模型 (sonnet)", big_model_display, "复杂任务、长文本处理")
        table.add_row("小模型 (haiku)", small_model_display, "快速响应、简单任务")
        
        if status["current_preset"]:
            if status["current_preset"] in config_manager.presets:
                preset_info = config_manager.presets[status["current_preset"]]
                table.add_row("当前预设", f"{preset_info['name']}", preset_info['description'])
            else:
                table.add_row("当前预设", status["current_preset"], "预设配置")
        else:
            if status["big_model"] is None or status["small_model"] is None:
                table.add_row("当前预设", "🔴 需要配置", "请配置模型")
            else:
                table.add_row("当前预设", "自定义配置", "手动配置的模型组合")
        
        table.add_row("可用提供商", " | ".join(status["available_providers"]), f"共 {len(status['available_providers'])} 个")
        table.add_row("可用模型", f"{status['available_models']} / {status['total_models']}", "可用/总数")
        table.add_row("服务端口", f":{self.port}", "Claude Code 连接地址")
        
        # 显示 Claude Code 环境变量状态
        current_anthropic_url = os.environ.get('ANTHROPIC_BASE_URL', '未设置')
        expected_url = f"http://localhost:{self.port}"
        
        if current_anthropic_url == expected_url:
            env_status = "🟢 已配置"
        else:
            env_status = "🔴 未配置"
            
        table.add_row("Claude Code 环境", env_status, f"ANTHROPIC_BASE_URL")
        
        console.print(table)
        
    def show_providers(self):
        """显示提供商信息"""
        available = config_manager.get_available_providers()
        
        table = Table(title="📡 提供商状态", show_header=True, header_style="bold blue")
        table.add_column("提供商", style="cyan")
        table.add_column("状态", justify="center")
        table.add_column("模型数量", justify="center")
        table.add_column("代表模型", style="green")
        
        for name, provider in config_manager.providers.items():
            status = "🟢 可用" if provider.is_available else "🔴 未配置"
            model_count = len(provider.models)
            sample_models = ", ".join(provider.models[:3])
            if len(provider.models) > 3:
                sample_models += f" ... (+{len(provider.models)-3})"
            
            table.add_row(provider.name, status, str(model_count), sample_models)
        
        console.print(table)
    
    def show_presets(self):
        """显示预设配置"""
        table = Table(title="🎛️ 预设配置", show_header=True, header_style="bold green")
        table.add_column("预设名", style="cyan")
        table.add_column("名称", style="yellow")
        table.add_column("Super 模型", style="red", no_wrap=True)
        table.add_column("大模型", style="green", no_wrap=True)
        table.add_column("小模型", style="blue", no_wrap=True)
        table.add_column("类型", style="magenta")
        table.add_column("描述")
        
        for preset_id, preset in MODEL_PRESETS.items():
            provider_type = "🌐 跨平台" if preset["provider"] == "mixed" else f"🔸 {preset['provider']}"
            
            # 如果模型字段缺失，则显示 N/A
            super_model = preset.get("super_model") or "[red]🔴 N/A[/red]"
            big_model = preset.get("big_model") or "[red]🔴 N/A[/red]"
            small_model = preset.get("small_model") or "[red]🔴 N/A[/red]"
            
            table.add_row(
                preset_id,
                preset["name"],
                super_model,
                big_model,
                small_model, 
                provider_type,
                preset["description"]
            )
        
        console.print(table)

    def apply_preset_by_name(self, preset_id: str):
        """通过名称应用预设"""
        if preset_id not in MODEL_PRESETS:
            console.print(f"[red]❌ 预设 '{preset_id}' 不存在。[/red]")
            console.print(f"   可用预设: {', '.join(MODEL_PRESETS.keys())}")
            return

        success, message = config_manager.apply_preset(preset_id)

        if success:
            preset = MODEL_PRESETS[preset_id]
            console.print(f"[green]✅ 已应用预设: {preset['name']}[/green]")
            console.print(f"   Super 模型: {preset.get('super_model', preset.get('big_model', 'N/A'))}")
            console.print(f"   大模型: {preset['big_model']}")
            console.print(f"   小模型: {preset['small_model']}")
        else:
            console.print(f"[red]❌ 预设应用失败: {message}[/red]")
    
    def apply_preset_interactive(self):    
        """交互式应用预设"""
        self.show_presets()
        
        preset_choices = list(MODEL_PRESETS.keys())
        
        console.print("\n[bold cyan]选择预设配置:[/bold cyan]")
        for i, preset_id in enumerate(preset_choices, 1):
            preset = MODEL_PRESETS[preset_id]
            console.print(f"  {i}. {preset['name']} - {preset['description']}")
        
        while True:
            try:
                choice = Prompt.ask("请输入预设编号", choices=[str(i) for i in range(1, len(preset_choices)+1)])
                preset_id = preset_choices[int(choice) - 1]
                self.apply_preset_by_name(preset_id)
                break
            except (ValueError, KeyError):
                console.print("[red]无效选择，请重新输入[/red]")
    
    def custom_model_config(self):
        """自定义模型配置"""
        console.print("[bold cyan]🔧 自定义模型配置[/bold cyan]\n")
        
        # 显示所有可用模型
        all_models = config_manager.get_all_models()
        available_providers = config_manager.get_available_providers()
        
        for provider_name in available_providers:
            provider = config_manager.providers[provider_name]
            console.print(f"[bold green]{provider.name}[/bold green]:")
            models_text = ", ".join(provider.models)
            console.print(f"  {models_text}\n")
        
        # 输入大模型
        while True:
            big_model = Prompt.ask("请输入大模型名称 (sonnet映射)")
            if config_manager.validate_model(big_model):
                break
            else:
                console.print("[red]❌ 模型不存在或提供商不可用[/red]")
        
        # 输入小模型
        while True:
            small_model = Prompt.ask("请输入小模型名称 (haiku映射)")
            if config_manager.validate_model(small_model):
                break
            else:
                console.print("[red]❌ 模型不存在或提供商不可用[/red]")
        
        # 应用配置
        if config_manager.set_models(big_model, small_model):
            console.print("[green]✅ 模型配置已更新[/green]")
            console.print(f"   大模型: {big_model}")
            console.print(f"   小模型: {small_model}")
        else:
            console.print("[red]❌ 配置失败[/red]")
    
    def toggle_proxy_interactive(self):
        """交互式切换代理状态"""
        current = config_manager.current_config["proxy_enabled"]
        new_status = config_manager.toggle_proxy()
        
        if new_status:
            console.print("[green]✅ 代理已启用 - 模型映射和对话历史功能可用[/green]")
        else:
            console.print("[yellow]🔄 代理已禁用 - 现在将透明转发到 api.anthropic.com[/yellow]")
            console.print("   注意: 需要有效的 ANTHROPIC_API_KEY 或 Claude Pro 认证")
    
    def toggle_request_logs(self):
        """切换请求日志显示"""
        import os
        
        current_status = os.getenv("CLAUDE_PROXY_CONSOLE_LOGS", "true").lower() == "true"
        new_status = not current_status
        
        os.environ["CLAUDE_PROXY_CONSOLE_LOGS"] = "true" if new_status else "false"
        
        if new_status:
            console.print("[green]🔊 请求日志显示已启用[/green]")
            console.print("   现在会在交互区域上方显示：模型映射、工具数量、消息数量等")
        else:
            console.print("[yellow]🔇 请求日志显示已禁用[/yellow]")
            console.print("   现在只显示交互区域的状态信息")
    
    def show_help(self):
        """显示帮助信息"""
        console.print("[bold cyan]📋 所有可用命令:[/bold cyan]")
        
        menu_options = {
            "preset": "🎛️  应用预设配置",
            "config": "🔧 自定义模型配置", 
            "toggle": "🔄 切换代理状态",
            "test": "🧪 测试当前配置",
            "record": "📝 对话记录控制",
            "load": "📂 读取对话记录文件",
            "logs": "📜 查看调试日志",
            "verbose": "🔊 切换请求日志显示",
            "providers": "📡 查看提供商信息",
            "presets": "📋 查看预设列表", 
            "env": "⚙️  重新配置环境变量",
            "help": "❓ 帮助信息",
            "quit": "🚪 退出程序（自动清理）"
        }
        
        for key, desc in menu_options.items():
            console.print(f"  [green]{key}[/green] - {desc}")
        
        help_text = """

[bold yellow]功能说明:[/bold yellow]
• [green]代理启用[/green]: 支持多提供商模型切换、对话历史管理
• [yellow]代理禁用[/yellow]: 透明转发到 api.anthropic.com，原生 Claude 体验

[bold yellow]使用方式:[/bold yellow]
• Claude Code 设置: [cyan]ANTHROPIC_BASE_URL=http://localhost:{port}[/cyan]
• 切换模式: 在命令行输入相应命令

[bold yellow]支持的提供商:[/bold yellow]  
• 支持任意 OpenAI 兼容 API 提供商
• 通过 providers.json 动态配置模型列表
        """.format(port=self.port)
        
        console.print(Panel(help_text, title="系统功能说明", border_style="blue"))
    
    def test_current_config(self):
        """测试当前配置"""
        import requests
        import json
        
        console.print("[bold cyan]🧪 测试当前配置[/bold cyan]")
        
        # 检查服务器状态
        try:
            response = requests.get(f"http://localhost:{self.port}/config", timeout=5)
            if response.status_code != 200:
                console.print("[red]❌ 服务器未响应，请检查服务器状态[/red]")
                return
        except requests.exceptions.RequestException:
            console.print(f"[red]❌ 无法连接到服务器 (http://localhost:{self.port})[/red]")
            return
        
        # 获取当前状态
        status = config_manager.get_status()
        
        if not status["proxy_enabled"]:
            console.print("[yellow]🔄 当前为透明转发模式[/yellow]")
            console.print("测试将直接转发到 api.anthropic.com")
            test_model = "claude-3-5-haiku-20241022"
        else:
            console.print("[green]🎛️ 当前为代理映射模式[/green]")
            console.print(f"大模型: {status['big_model']} | 小模型: {status['small_model']}")
            test_model = "haiku"  # 使用映射名称
        
        # 发送测试请求
        test_message = {
            "model": test_model,
            "max_tokens": 50,
            "messages": [
                {"role": "user", "content": "Hello! Please respond with 'Test successful' if you can see this message."}
            ]
        }
        
        console.print(f"\n📤 发送测试请求到模型: [cyan]{test_model}[/cyan]")
        
        try:
            response = requests.post(
                f"http://localhost:{self.port}/v1/messages",
                json=test_message,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                reply = result['content'][0]['text']
                console.print(f"[green]✅ 测试成功![/green]")
                console.print(f"📨 模型回复: [blue]{reply}[/blue]")
                
                # 显示实际使用的模型信息
                if status["proxy_enabled"]:
                    actual_model = status['small_model'] if test_model == "haiku" else status['big_model']
                    provider = config_manager.find_model_provider(actual_model)
                    console.print(f"🔗 实际调用: [yellow]{provider}[/yellow] 的 [cyan]{actual_model}[/cyan]")
                else:
                    console.print("🔗 直接调用: [yellow]Anthropic API[/yellow]")
                    
            elif response.status_code == 401:
                console.print("[yellow]⚠️  认证失败 - 请检查 API 密钥配置[/yellow]")
                console.print("   检查 .env 文件中对应提供商的 API Key")
            elif response.status_code == 403:
                console.print("[yellow]⚠️  权限被拒绝 - API 密钥可能无效或无权限[/yellow]")
            else:
                console.print(f"[red]❌ 请求失败: HTTP {response.status_code}[/red]")
                console.print(f"   响应: {response.text[:200]}...")
                
        except requests.exceptions.Timeout:
            console.print("[red]❌ 请求超时 - 模型响应时间过长[/red]")
        except requests.exceptions.RequestException as e:
            console.print(f"[red]❌ 网络错误: {e}[/red]")
        
        # 显示对话历史状态
        try:
            response = requests.get(f"http://localhost:{self.port}/conversation")
            if response.status_code == 200:
                history = response.json()
                console.print(f"\n📚 对话历史: 共 {history['total_count']} 条记录")
        except:
            pass
    
    def reconfigure_env(self):
        """重新配置环境变量"""
        console.print("[bold cyan]⚙️  重新配置 Claude Code 环境变量[/bold cyan]")
        
        # 显示当前状态
        current_url = os.environ.get('ANTHROPIC_BASE_URL', '未设置')
        expected_url = f"http://localhost:{self.port}"
        
        console.print(f"当前设置: [cyan]{current_url}[/cyan]")
        console.print(f"期望设置: [green]{expected_url}[/green]")
        
        if current_url == expected_url:
            console.print("[green]✅ 环境变量已正确配置[/green]")
            return
        
        # 询问是否重新配置
        if Confirm.ask("是否重新配置 Claude Code 环境变量？"):
            self.set_claude_code_env()
            console.print("[green]✅ 环境变量重新配置完成[/green]")
            console.print("\n[yellow]💡 提示:[/yellow]")
            console.print("  • 当前终端: 新开的 Claude Code 会使用代理")
            console.print("  • 其他终端: 需要重新加载 shell 配置或重启终端")
        else:
            console.print("[yellow]⚠️  跳过环境变量配置[/yellow]")
    
    def _check_model_configuration(self):
        """检查模型配置，如果未配置则提示用户"""
        status = config_manager.get_status()
        
        if status["big_model"] is None or status["small_model"] is None:
            console.print("\n[yellow]⚠️  未检测到有效的模型配置![/yellow]")
            console.print("[cyan]请选择以下操作之一来配置模型:[/cyan]")
            console.print("  1. 应用预设配置")
            console.print("  2. 自定义模型配置")
            
            # 自动进入配置菜单，不需要暂停
    
    def _show_input_area(self):
        """显示用户输入提示区域"""
        # 简洁的分隔和状态显示
        console.print("\n" + "═" * 30 + " 🎮 用户输入 " + "═" * 30)
        
        # 单行状态摘要
        try:
            status = config_manager.get_status()
            if status["proxy_enabled"]:
                status_line = f"🟢 代理模式 | {status['big_model']} & {status['small_model']} | 端口:{self.port}"
            else:
                status_line = f"🔄 透明转发 → api.anthropic.com | 端口:{self.port}"
        except:
            status_line = f"⚠️ 配置加载失败 | 端口:{self.port}"
        
        console.print(f"[dim]{status_line}[/dim]")
    
    def get_valid_commands(self):
        """获取所有有效命令列表"""
        return ["preset", "config", "toggle", "test", "record", "load", 
                "logs", "verbose", "providers", "presets", "env", "help", "quit"]
    
    def _draw_bottom_status(self):
        """在终端底部绘制状态栏"""
        # 获取终端大小
        try:
            import shutil
            terminal_width = shutil.get_terminal_size().columns
        except:
            terminal_width = 80
            
        # 状态信息
        try:
            status = config_manager.get_status()
            if status["proxy_enabled"]:
                status_text = f"🟢 代理模式 | {status['big_model']} & {status['small_model']} | 端口:{self.port}"
            else:
                status_text = f"🔄 透明转发 → api.anthropic.com | 端口:{self.port}"
        except:
            status_text = f"⚠️ 配置加载失败 | 端口:{self.port}"
        
        # 绘制分隔线和状态
        console.print("\n" + "═" * terminal_width)
        console.print(f"[dim]{status_text}[/dim]")
        console.print("─" * terminal_width)

    def main_menu(self):
        """主菜单 - 简洁的命令循环"""
        # 首次显示欢迎信息
        console.clear()
        console.print(Panel.fit(
            "[bold blue]🚀 Claude Code 代理服务器[/bold blue]\n"
            f"服务器状态: {'🟢 运行中' if self.server_running else '🔴 未启动'} | "
            f"地址: http://localhost:{self.port}",
            border_style="green"
        ))
        
        console.print("\n[bold cyan]🎯 快速开始:[/bold cyan]")
        console.print("  • 输入 [green]help[/green] 查看所有可用命令")
        console.print("  • 输入 [green]test[/green] 测试当前配置")
        console.print("  • 输入 [green]quit[/green] 安全退出")
        console.print("\n[dim]服务器请求日志将在上方显示...[/dim]")
        
        while True:
            try:
                # 绘制底部状态栏
                self._draw_bottom_status()
                
                # 获取用户输入
                user_input = Prompt.ask("[bold cyan]claude-proxy>[/bold cyan]")
                parts = user_input.strip().split()
                if not parts:
                    continue
                
                command = parts[0].lower()
                args = parts[1:]
                
                # 验证命令
                if command not in self.get_valid_commands():
                    console.print(f"[red]❌ 未知命令: '{command}'[/red]")
                    console.print("   输入 [green]help[/green] 查看所有可用命令。")
                    continue

                # 处理命令
                if command == "preset":
                    if args:
                        self.apply_preset_by_name(args[0])
                    else:
                        self.apply_preset_interactive()
                elif command == "config":
                    self.custom_model_config()
                elif command == "toggle":
                    self.toggle_proxy_interactive()
                elif command == "test":
                    self.test_current_config()
                elif command == "record":
                    self.conversation_record_control()
                elif command == "load":
                    self.load_conversation_file()
                elif command == "logs":
                    self.view_debug_logs()
                elif command == "verbose":
                    self.toggle_request_logs()
                elif command == "providers":
                    self.show_providers()
                elif command == "presets":
                    if args:
                        self.apply_preset_by_name(args[0])
                    else:
                        self.show_presets()
                elif command == "env":
                    self.reconfigure_env()
                elif command == "help":
                    self.show_help()
                elif command == "quit":
                    console.print("[yellow]👋 正在安全退出...[/yellow]")
                    self.cleanup()
                    break
                
            except KeyboardInterrupt:
                console.print("\n[yellow]👋 程序被中断，正在退出...[/yellow]")
                self.cleanup()
                break
    
    def run(self, port=None):
        """运行应用"""
        console.print("[bold green]🚀 启动 Claude Code 代理服务器...[/bold green]")
        
        # 设置端口
        if port:
            self.port = port
        
        console.print(f"[cyan]📡 服务器将启动在端口 {self.port}[/cyan]")
        
        # 检查环境配置
        available = config_manager.get_available_providers()
        if not available:
            console.print("[red]❌ 没有检测到可用的API密钥，请配置 .env 文件[/red]")
            # 动态显示当前配置的提供商环境变量
            required_keys = [provider.api_key_env for provider in config_manager.providers.values()]
            console.print(f"   需要至少一个: {', '.join(required_keys)}")
            return
        
        # 启动服务器
        self.start_server()
        
        # 检查是否需要配置模型
        self._check_model_configuration()
        
        # 运行交互式菜单
        try:
            self.main_menu()
        except KeyboardInterrupt:
            console.print("\n[yellow]👋 程序被中断，正在退出...[/yellow]")
            self.cleanup()
        except Exception as e:
            console.print(f"[red]❌ 程序错误: {e}[/red]")
            self.cleanup()
    
    def conversation_record_control(self):
        """对话记录控制菜单"""
        try:
            # 获取当前对话记录状态
            response = requests.get(f"http://localhost:{self.port}/conversation/status", timeout=5)
            if response.status_code == 200:
                status = response.json()
                
                console.print("\n[bold cyan]📝 对话记录状态[/bold cyan]")
                console.print(f"📊 记录状态: {'🟢 启用' if status['recording_enabled'] else '🔴 禁用'}")
                if status['recording_enabled']:
                    console.print(f"📁 保存位置: {status.get('file_path', 'N/A')}")
                    console.print(f"📝 缓冲区大小: {status.get('buffer_size', 0)} 条")
                    console.print(f"🔄 去重缓存: {status.get('total_recent_conversations', 0)} 条")
                
                console.print("\n[bold cyan]📋 可用操作:[/bold cyan]")
                record_options = {
                    "enable": "🟢 启用对话记录",
                    "disable": "🔴 禁用对话记录", 
                    "flush": "💾 强制保存缓冲区",
                    "back": "🔙 返回主菜单"
                }
                
                for key, desc in record_options.items():
                    console.print(f"  [green]{key}[/green] - {desc}")
                
                choice = Prompt.ask("\n请选择操作", choices=list(record_options.keys()))
                
                if choice == "enable":
                    if status['recording_enabled']:
                        console.print("[yellow]⚠️ 对话记录已启用[/yellow]")
                    else:
                        # 获取保存路径
                        default_path = "./conversations/conversation_history.jsonl"
                        file_path = Prompt.ask(f"请输入保存路径", default=default_path)
                        
                        # 启用对话记录
                        enable_response = requests.post(
                            f"http://localhost:{self.port}/conversation/enable",
                            params={"file_path": file_path},
                            timeout=5
                        )
                        
                        if enable_response.status_code == 200:
                            console.print(f"[green]✅ {enable_response.json()['message']}[/green]")
                        else:
                            console.print(f"[red]❌ 启用失败: {enable_response.json().get('detail', '未知错误')}[/red]")
                
                elif choice == "disable":
                    if not status['recording_enabled']:
                        console.print("[yellow]⚠️ 对话记录已禁用[/yellow]")
                    else:
                        disable_response = requests.post(f"http://localhost:{self.port}/conversation/disable", timeout=5)
                        if disable_response.status_code == 200:
                            console.print(f"[green]✅ {disable_response.json()['message']}[/green]")
                        else:
                            console.print(f"[red]❌ 禁用失败[/red]")
                
                elif choice == "flush":
                    if not status['recording_enabled']:
                        console.print("[yellow]⚠️ 对话记录未启用[/yellow]")
                    elif status.get('buffer_size', 0) == 0:
                        console.print("[yellow]⚠️ 缓冲区为空[/yellow]")
                    else:
                        flush_response = requests.post(f"http://localhost:{self.port}/conversation/flush", timeout=5)
                        if flush_response.status_code == 200:
                            console.print(f"[green]✅ {flush_response.json()['message']}[/green]")
                        else:
                            console.print(f"[red]❌ 保存失败[/red]")
                
                elif choice == "back":
                    return
                    
            else:
                console.print("[red]❌ 无法获取对话记录状态[/red]")
                
        except requests.RequestException:
            console.print("[red]❌ 无法连接到服务器[/red]")
        except Exception as e:
            console.print(f"[red]❌ 发生错误: {e}[/red]")
    
    def load_conversation_file(self):
        """读取对话记录文件"""
        try:
            console.print("\n[bold cyan]📂 读取对话记录文件[/bold cyan]")
            
            # 获取文件路径
            file_path = Prompt.ask("请输入对话记录文件路径")
            
            if not file_path.strip():
                console.print("[yellow]⚠️ 文件路径不能为空[/yellow]")
                return
            
            # 显示加载进度
            with console.status(f"[bold green]正在验证和读取文件: {file_path}"):
                # 调用API读取文件
                load_response = requests.post(
                    f"http://localhost:{self.port}/conversation/load",
                    params={"file_path": file_path},
                    timeout=10
                )
            
            if load_response.status_code == 200:
                result = load_response.json()
                
                console.print(f"[green]✅ {result['message']}[/green]")
                console.print(f"[cyan]📁 文件路径: {result['file_path']}[/cyan]")
                console.print(f"[cyan]📊 文件中总记录数: {result['total_records']}[/cyan]")
                
                # 显示读取的最后一条记录
                last_record = result['last_record']
                console.print("\n[bold cyan]📝 读取的最后一条记录:[/bold cyan]")
                console.print(f"🔤 用户输入: {last_record['user_input'][:100]}{'...' if len(last_record['user_input']) > 100 else ''}")
                console.print(f"🤖 使用模型: {last_record['model_used']}")
                console.print(f"⏰ 时间: {last_record['timestamp']}")
                
                console.print("\n[bold green]🎉 对话记录已成功读取并自动启用记录功能！[/bold green]")
                console.print("[yellow]💡 提示: 新的对话将继续保存到该文件中[/yellow]")
                
            else:
                error_detail = load_response.json().get('detail', '未知错误') if load_response.content else '服务器错误'
                console.print(f"[red]❌ 读取失败: {error_detail}[/red]")
                
                # 如果是文件不存在，询问是否创建
                if "文件不存在" in error_detail:
                    create = Prompt.ask("文件不存在，是否创建新的对话记录文件？", choices=["y", "n"], default="n")
                    if create == "y":
                        try:
                            # 尝试启用对话记录功能（会创建文件）
                            enable_response = requests.post(
                                f"http://localhost:{self.port}/conversation/enable",
                                params={"file_path": file_path},
                                timeout=5
                            )
                            
                            if enable_response.status_code == 200:
                                console.print(f"[green]✅ 已创建新的对话记录文件: {file_path}[/green]")
                            else:
                                console.print(f"[red]❌ 创建失败[/red]")
                        except Exception as e:
                            console.print(f"[red]❌ 创建失败: {e}[/red]")
                
        except requests.RequestException:
            console.print("[red]❌ 无法连接到服务器[/red]")
        except Exception as e:
            console.print(f"[red]❌ 发生错误: {e}[/red]")
    
    def view_debug_logs(self):
        """查看调试日志"""
        try:
            console.print("\n[bold cyan]📜 调试日志查看器[/bold cyan]")
            
            # 获取日志信息
            response = requests.get(f"http://localhost:{self.port}/debug_logs", timeout=5)
            if response.status_code == 200:
                data = response.json()
                logs = data.get("logs", [])
                total_count = data.get("total_count", 0)
                available_types = data.get("available_types", [])
                
                if not logs:
                    console.print("[yellow]📭 暂无调试日志[/yellow]")
                    return
                
                console.print(f"[cyan]📊 总日志数量: {total_count}[/cyan]")
                console.print(f"[cyan]📋 可用类型: {', '.join(available_types) if available_types else '无'}[/cyan]")
                
                console.print("\n[bold cyan]📋 查看选项:[/bold cyan]")
                log_options = {
                    "table": "📊 表格视图（概览）",
                    "detail": "📝 详细视图（完整内容）",
                    "recent": "🕒 查看最近10条",
                    "type": "🏷️  按类型筛选",
                    "record": "🔄 记录对话",
                    "export": "💾 导出到文件",
                    "history": "📚 查看历史日志文件",
                    "clear": "🗑️  清空日志",
                    "cleanup": "🧹 清理临时文件",
                    "back": "🔙 返回主菜单"
                }
                
                for key, desc in log_options.items():
                    console.print(f"  [green]{key}[/green] - {desc}")
                
                choice = Prompt.ask("\n请选择操作", choices=list(log_options.keys()))
                
                if choice == "table":
                    self._display_logs_table(logs, "所有日志")
                    
                elif choice == "detail":
                    self._display_logs_detail(logs, "所有日志")
                    
                elif choice == "recent":
                    recent_logs = logs[-10:] if len(logs) > 10 else logs
                    view_mode = Prompt.ask("选择查看方式", choices=["table", "detail"], default="table")
                    if view_mode == "table":
                        self._display_logs_table(recent_logs, "最近10条日志")
                    else:
                        self._display_logs_detail(recent_logs, "最近10条日志")
                    
                elif choice == "type":
                    if not available_types:
                        console.print("[yellow]⚠️ 暂无可筛选的日志类型[/yellow]")
                    else:
                        console.print(f"\n可用类型: {', '.join(available_types)}")
                        log_type = Prompt.ask("请输入日志类型", choices=available_types)
                        
                        # 重新获取指定类型的日志
                        type_response = requests.get(
                            f"http://localhost:{self.port}/debug_logs",
                            params={"log_type": log_type},
                            timeout=5
                        )
                        
                        if type_response.status_code == 200:
                            type_data = type_response.json()
                            type_logs = type_data.get("logs", [])
                            view_mode = Prompt.ask("选择查看方式", choices=["table", "detail"], default="table")
                            if view_mode == "table":
                                self._display_logs_table(type_logs, f"{log_type} 类型日志")
                            else:
                                self._display_logs_detail(type_logs, f"{log_type} 类型日志")
                        else:
                            console.print("[red]❌ 获取日志失败[/red]")
                
                elif choice == "record":
                    self.restore_history()
                    return

                elif choice == "export":
                    self._export_logs_to_file(logs)
                
                elif choice == "history":
                    self._view_history_log_files()
                    
                elif choice == "clear":
                    confirm = Prompt.ask("确定要清空所有调试日志吗？", choices=["y", "n"], default="n")
                    if confirm == "y":
                        clear_response = requests.delete(f"http://localhost:{self.port}/debug_logs", timeout=5)
                        if clear_response.status_code == 200:
                            console.print("[green]✅ 调试日志已清空[/green]")
                        else:
                            console.print("[red]❌ 清空失败[/red]")
                
                elif choice == "cleanup":
                    self._cleanup_temp_log_files()
                    
                elif choice == "back":
                    return
                    
            else:
                console.print("[red]❌ 无法获取调试日志[/red]")
                
        except requests.RequestException:
            console.print("[red]❌ 无法连接到服务器[/red]")
        except Exception as e:
            console.print(f"[red]❌ 发生错误: {e}[/red]")
    
    def _display_logs_table(self, logs, title):
        """以表格形式显示日志内容（概览）"""
        if not logs:
            console.print(f"[yellow]📭 {title}: 暂无日志[/yellow]")
            return
            
        console.print(f"\n[bold cyan]📋 {title} ({len(logs)} 条):[/bold cyan]")
        
        # 使用表格显示日志
        from rich.table import Table
        
        table = Table(show_header=True, header_style="bold magenta", show_lines=True)
        table.add_column("时间", style="cyan", width=20)
        table.add_column("类型", style="yellow", width=12)
        table.add_column("消息", style="white", width=50)
        table.add_column("详情", style="dim", width=30)
        
        for log in logs:
            timestamp = log.get("timestamp", "")[:19].replace("T", " ")  # 简化时间格式
            log_type = log.get("type", "unknown")
            message = log.get("message", "")
            details = str(log.get("details", {}))
            
            # 截断过长的内容
            if len(message) > 50:
                message = message[:47] + "..."
            if len(details) > 30:
                details = details[:27] + "..."
            
            # 根据日志类型设置颜色
            if log_type == "error":
                log_type_colored = f"[red]{log_type}[/red]"
            elif log_type == "config":
                log_type_colored = f"[green]{log_type}[/green]"
            elif log_type == "request":
                log_type_colored = f"[blue]{log_type}[/blue]"
            else:
                log_type_colored = log_type
            
            table.add_row(timestamp, log_type_colored, message, details)
        
        console.print(table)
    
    def _display_logs_detail(self, logs, title):
        """以详细形式显示日志内容（完整信息）"""
        if not logs:
            console.print(f"[yellow]📭 {title}: 暂无日志[/yellow]")
            return
            
        console.print(f"\n[bold cyan]📋 {title} ({len(logs)} 条):[/bold cyan]")
        console.print("[dim]" + "="*80 + "[/dim]")
        
        def truncate_long_strings(data, limit=2000):
            """递归地截断数据结构中过长的字符串"""
            if isinstance(data, dict):
                return {k: truncate_long_strings(v, limit) for k, v in data.items()}
            elif isinstance(data, list):
                return [truncate_long_strings(item, limit) for item in data]
            elif isinstance(data, str) and len(data) > limit:
                return data[:limit] + f"\n\n[bold red]... (内容已截断, 剩余 {len(data) - limit} 字符)[/bold red]"
            return data

        for i, log in enumerate(logs, 1):
            timestamp = log.get("timestamp", "N/A")
            log_type = log.get("type", "unknown")
            message = log.get("message", "")
            details = log.get("details", {})
            
            # 对详情内容进行截断处理
            display_details = truncate_long_strings(details)
            
            # 根据日志类型设置颜色
            if log_type == "error":
                type_color = "red"
            elif log_type == "config":
                type_color = "green" 
            elif log_type == "request":
                type_color = "blue"
            else:
                type_color = "white"
            
            console.print(f"\n[bold cyan]📌 日志 #{i}[/bold cyan]")
            console.print(f"[cyan]⏰ 时间:[/cyan] {timestamp}")
            console.print(f"[cyan]🏷️  类型:[/cyan] [{type_color}]{log_type}[/{type_color}]")
            console.print(f"[cyan]💬 消息:[/cyan] {message}")
            
            if display_details:
                console.print(f"[cyan]📝 详情:[/cyan]")
                
                # 其他类型日志的通用格式化显示
                import json
                try:
                    if isinstance(display_details, str):
                        # 如果details是字符串，尝试解析为JSON
                        try:
                            details_obj = json.loads(display_details)
                            formatted_details = json.dumps(details_obj, indent=2, ensure_ascii=False)
                        except:
                            formatted_details = display_details
                    else:
                        formatted_details = json.dumps(display_details, indent=2, ensure_ascii=False)
                    
                    # 添加缩进
                    for line in formatted_details.split('\n'):
                        console.print(f"   {line}")
                except:
                    console.print(f"   {str(display_details)}")
            
            if i < len(logs):
                console.print("[dim]" + "-"*60 + "[/dim]")
        
        console.print("\n[dim]" + "="*80 + "[/dim]")
    
    def _export_logs_to_file(self, logs):
        """导出日志到文件"""
        if not logs:
            console.print("[yellow]⚠️ 无日志可导出[/yellow]")
            return
        
        try:
            import tempfile
            import json
            from datetime import datetime
            
            # 创建临时文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir = tempfile.gettempdir()
            log_file = f"{temp_dir}/claude_debug_logs_{timestamp}.json"
            
            # 导出数据
            export_data = {
                "export_time": datetime.now().isoformat(),
                "total_logs": len(logs),
                "logs": logs
            }
            
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            console.print(f"[green]✅ 日志已导出到: {log_file}[/green]")
            console.print(f"[yellow]💡 提示: 这是临时文件，如需保留请手动复制到其他位置[/yellow]")
            
        except Exception as e:
            console.print(f"[red]❌ 导出失败: {e}[/red]")
    
    def _cleanup_temp_log_files(self):
        """清理临时日志文件"""
        try:
            import tempfile
            import glob
            import os
            
            temp_dir = tempfile.gettempdir()
            pattern = f"{temp_dir}/claude_debug_logs_*.json"
            temp_files = glob.glob(pattern)
            
            if not temp_files:
                console.print("[yellow]📭 未找到临时日志文件[/yellow]")
                return
            
            console.print(f"[cyan]找到 {len(temp_files)} 个临时日志文件:[/cyan]")
            for file in temp_files:
                file_name = os.path.basename(file)
                file_size = os.path.getsize(file) / 1024  # KB
                console.print(f"  📄 {file_name} ({file_size:.1f} KB)")
            
            confirm = Prompt.ask(f"确定要删除这 {len(temp_files)} 个临时文件吗？", choices=["y", "n"], default="n")
            if confirm == "y":
                deleted_count = 0
                for file in temp_files:
                    try:
                        os.remove(file)
                        deleted_count += 1
                    except Exception as e:
                        console.print(f"[red]❌ 删除 {os.path.basename(file)} 失败: {e}[/red]")
                
                console.print(f"[green]✅ 已删除 {deleted_count} 个临时文件[/green]")
            else:
                console.print("[yellow]取消删除[/yellow]")
                
        except Exception as e:
            console.print(f"[red]❌ 清理失败: {e}[/red]")
    
    def _view_history_log_files(self):
        """查看历史日志文件"""
        try:
            import tempfile
            import glob
            import os
            import json
            from datetime import datetime
            
            temp_dir = tempfile.gettempdir()
            pattern = f"{temp_dir}/claude_debug_logs_*.json"
            log_files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
            
            if not log_files:
                console.print("[yellow]📭 未找到历史日志文件[/yellow]")
                console.print("[dim]💡 提示: 使用 'export' 选项导出当前日志后才会有历史文件[/dim]")
                return
            
            console.print(f"\n[bold cyan]📚 历史日志文件 ({len(log_files)} 个):[/bold cyan]")
            
            # 显示文件列表
            file_info = []
            for i, file_path in enumerate(log_files, 1):
                file_name = os.path.basename(file_path)
                file_size = os.path.getsize(file_path) / 1024  # KB
                mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                # 尝试读取文件获取日志数量
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        log_count = data.get('total_logs', 0)
                        export_time = data.get('export_time', '')
                except:
                    log_count = '?'
                    export_time = ''
                
                file_info.append({
                    'index': i,
                    'path': file_path,
                    'name': file_name,
                    'size': file_size,
                    'mod_time': mod_time,
                    'log_count': log_count,
                    'export_time': export_time
                })
                
                # 解析文件名中的时间戳
                try:
                    # 文件名格式: claude_debug_logs_20250901_143052.json
                    timestamp_part = file_name.replace('claude_debug_logs_', '').replace('.json', '')
                    date_part, time_part = timestamp_part.split('_')
                    formatted_time = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
                except:
                    formatted_time = mod_time.strftime("%Y-%m-%d %H:%M:%S")
                
                console.print(f"  [cyan]{i}.[/cyan] 📄 {file_name}")
                console.print(f"      🕒 导出时间: {formatted_time}")
                console.print(f"      📊 大小: {file_size:.1f} KB | 📋 日志数: {log_count}")
                console.print("")
            
            # 选择要查看的文件
            choices = [str(i) for i in range(1, len(log_files) + 1)] + ["back"]
            choice = Prompt.ask(
                f"选择要查看的文件 (1-{len(log_files)}) 或输入 'back' 返回",
                choices=choices
            )
            
            if choice == "back":
                return
            
            selected_index = int(choice) - 1
            selected_file = file_info[selected_index]
            
            self._load_and_display_log_file(selected_file)
            
        except Exception as e:
            console.print(f"[red]❌ 查看历史文件失败: {e}[/red]")
    
    def _load_and_display_log_file(self, file_info):
        """加载并显示指定的日志文件"""
        try:
            import json
            
            console.print(f"\n[bold cyan]📖 正在读取: {file_info['name']}[/bold cyan]")
            
            with open(file_info['path'], 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logs = data.get('logs', [])
            export_time = data.get('export_time', 'N/A')
            total_logs = data.get('total_logs', len(logs))
            
            console.print(f"[cyan]📊 文件信息:[/cyan]")
            console.print(f"  导出时间: {export_time}")
            console.print(f"  日志总数: {total_logs}")
            console.print(f"  文件大小: {file_info['size']:.1f} KB")
            
            if not logs:
                console.print("[yellow]📭 文件中无日志数据[/yellow]")
                return
            
            # 选择查看方式
            console.print("\n[bold cyan]📋 查看方式:[/bold cyan]")
            view_options = {
                "table": "📊 表格视图（概览）",
                "detail": "📝 详细视图（完整内容）",
                "recent": "🕒 最近10条",
                "search": "🔍 按类型筛选",
                "back": "🔙 返回文件列表"
            }
            
            for key, desc in view_options.items():
                console.print(f"  [green]{key}[/green] - {desc}")
            
            view_choice = Prompt.ask("选择查看方式", choices=list(view_options.keys()))
            
            if view_choice == "back":
                return
            elif view_choice == "table":
                self._display_logs_table(logs, f"历史日志 - {file_info['name']}")
            elif view_choice == "detail":
                self._display_logs_detail(logs, f"历史日志 - {file_info['name']}")
            elif view_choice == "recent":
                recent_logs = logs[-10:] if len(logs) > 10 else logs
                display_mode = Prompt.ask("选择显示模式", choices=["table", "detail"], default="table")
                if display_mode == "table":
                    self._display_logs_table(recent_logs, f"历史日志最近10条 - {file_info['name']}")
                else:
                    self._display_logs_detail(recent_logs, f"历史日志最近10条 - {file_info['name']}")
            elif view_choice == "search":
                # 获取可用的日志类型
                available_types = list(set(log.get("type", "unknown") for log in logs))
                if not available_types:
                    console.print("[yellow]⚠️ 文件中无可筛选的日志类型[/yellow]")
                    return
                
                console.print(f"\n可用类型: {', '.join(available_types)}")
                log_type = Prompt.ask("请输入日志类型", choices=available_types)
                
                filtered_logs = [log for log in logs if log.get("type") == log_type]
                if not filtered_logs:
                    console.print(f"[yellow]⚠️ 未找到 '{log_type}' 类型的日志[/yellow]")
                    return
                
                display_mode = Prompt.ask("选择显示模式", choices=["table", "detail"], default="table")
                title = f"历史日志 - {file_info['name']} - {log_type} 类型"
                if display_mode == "table":
                    self._display_logs_table(filtered_logs, title)
                else:
                    self._display_logs_detail(filtered_logs, title)
            
        except json.JSONDecodeError:
            console.print(f"[red]❌ 文件格式错误: {file_info['name']} 不是有效的JSON文件[/red]")
        except Exception as e:
            console.print(f"[red]❌ 读取文件失败: {e}[/red]")

    def restore_history(self):
        """从调试日志恢复对话历史"""
        console.print("\n[bold cyan]🔄 从调试日志恢复对话历史[/bold cyan]")
        
        # 检查对话记录是否启用
        try:
            response = requests.get(f"http://localhost:{self.port}/conversation/status", timeout=5)
            if response.status_code != 200 or not response.json().get('recording_enabled'):
                console.print("[red]❌ 操作失败: 对话记录功能未启用。[/red]")
                console.print("   请先使用 'record' 命令启用对话记录。")
                return
        except requests.RequestException:
            console.print("[red]❌ 无法连接到服务器检查对话记录状态。[/red]")
            return

        if not config_manager.get_debug_logs():
            console.print("[yellow]⚠️ 暂无调试日志可用于恢复。[/yellow]")
            return

        if Confirm.ask("这将覆盖当前的对话历史文件，是否继续？", default=False):
            count, message = config_manager.restore_conversation_from_logs()
            if count > 0:
                console.print(f"[green]✅ {message}[/green]")
            else:
                console.print(f"[yellow]⚠️ {message}[/yellow]")
        else:
            console.print("[yellow]取消操作。[/yellow]")

def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description='Claude Code 代理服务器')
    parser.add_argument('--port', type=int, default=8082, help='服务器端口 (默认: 8082)')
    args = parser.parse_args()
    
    app = InteractiveApp()
    app.run(port=args.port)

if __name__ == "__main__":
    main()
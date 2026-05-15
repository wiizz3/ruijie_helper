import subprocess
import time
import platform
from utils.supplicant import SupplicantConfig

# Windows API 常量：创建进程时不显示控制台窗口
CREATE_NO_WINDOW = 0x08000000

class HotspotManager:
    """Windows 移动热点管理工具。
    通过 PowerShell 脚本调用 Windows Runtime API 来启动、停止和查询热点状态。
    """

    @staticmethod
    def load_config() -> dict:
        """加载热点配置，若不存在则返回默认值。
        返回字典，包含 ssid、password 和 band（目前未使用频段）。
        """

        full = SupplicantConfig.load()  # 加载完整配置
        config = full.get("hotspot_config") # 获取子配置
        if not isinstance(config, dict):
            config = {}
        return {
            "ssid": config.get("ssid", "sruijiem"), # 默认SSID
            "password": config.get("password", "12345678"), # 默认密码
            "band": config.get("band", "2.4GHz")    # 默认频段
        }

    @staticmethod
    def save_config(hotspot_config: dict):
        """保存热点配置到文件。"""
        full = SupplicantConfig.load()
        full["hotspot_config"] = hotspot_config
        SupplicantConfig.save(full)

    @staticmethod
    def _run_powershell(script: str, timeout: int = 25) -> tuple[int, str, str]:
        """内部方法：以静默方式执行一段 PowerShell 脚本。
        参数：
            script: 要执行的脚本内容。
            timeout: 命令超时时间（秒）。
        返回：
            (返回码, 标准输出字符串, 标准错误字符串)
        """
        startupinfo = None
        if platform.system() == "Windows":
            # 设置启动信息，隐藏窗口
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",  # 不显示版权信息
                    "-NoProfile",   # 不加载用户配置
                    "-NonInteractive",  # 非交互模式
                    "-WindowStyle", "Hidden",   # 隐藏窗口
                    "-ExecutionPolicy", "Bypass",   # 绕过执行策略限制
                    "-Command", script  # 需执行的脚本
                ],
                capture_output=True,    # 捕获标准输出和标准错误
                text=True,  # 返回输出字符串
                encoding="utf-8",
                errors="ignore",
                timeout=timeout,    # 超时设定
                startupinfo=startupinfo,    # 隐藏窗口
                creationflags=CREATE_NO_WINDOW
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", "PowerShell 命令超时"
        except Exception as e:
            return -1, "", str(e)

    @staticmethod
    def get_hotspot_status() -> str:
        """查询当前热点的工作状态。
        返回：
            "已启动" / "未启动" / "正在切换"
        """

        # PowerShell 脚本：通过 Windows.Networking.NetworkOperators API 获取状态
        script = '''$ProgressPreference = 'SilentlyContinue'
$null = Add-Type -AssemblyName System.Runtime.WindowsRuntime
$cp = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]::GetInternetConnectionProfile()
if ($null -eq $cp) { Write-Output "不可用（无网络连接）"; exit 0 }
$mgr = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]::CreateFromConnectionProfile($cp)
if ($null -eq $mgr) { Write-Output "不可用（无法获取管理器）"; exit 0 }
Write-Output $mgr.TetheringOperationalState
'''
        returncode, stdout, stderr = HotspotManager._run_powershell(script)
        if returncode != 0:
            return "Unknown"

        raw = stdout.strip().lower()
        mapping = {
            "off": "未启动",
            "on": "已启动",
            "intransition": "正在切换",
        }
        return mapping.get(raw, f"Unknown({raw})")

    @staticmethod
    def _send_command_and_wait(operation: str, ssid=None, key=None, timeout=15) -> tuple[bool, str]:
        """内部方法：发送启动/停止命令，并轮询等待状态变为预期值。
        参数：
            operation: "start" 或 "stop"
            ssid: 热点名称（仅启动时需要）
            key: 热点密码（仅启动时需要）
            timeout: 最大等待时间（秒）
        返回：
            (成功标志, 错误信息字符串)
        """

        if operation == "start":
            expected_status = "已启动"
            script = f'''$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$null = Add-Type -AssemblyName System.Runtime.WindowsRuntime
$cp = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]::GetInternetConnectionProfile()
if ($null -eq $cp) {{ Write-Output "FAIL:无网络连接"; exit 1 }}
$mgr = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]::CreateFromConnectionProfile($cp)
if ($null -eq $mgr) {{ Write-Output "FAIL:无法获取管理器"; exit 1 }}
try {{
    $config = $mgr.GetCurrentAccessPointConfiguration()
    if ($config.Ssid -ne "{ssid}" -or $config.Passphrase -ne "{key}") {{
        $config.Ssid = "{ssid}"
        $config.Passphrase = "{key}"
        $configAsync = $mgr.ConfigureAccessPointAsync($config)
    }}
}} catch {{}}
try {{
    $null = $mgr.StartTetheringAsync()
    Write-Output "CMD_SENT"
}} catch {{
    Write-Output "FAIL:" + $_.Exception.Message
    exit 1
}}
'''
        else:
            expected_status = "未启动"
            # 停止脚本
            script = '''$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$null = Add-Type -AssemblyName System.Runtime.WindowsRuntime
$cp = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]::GetInternetConnectionProfile()
if ($null -eq $cp) { Write-Output "FAIL:无网络连接"; exit 1 }
$mgr = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]::CreateFromConnectionProfile($cp)
if ($null -eq $mgr) { Write-Output "FAIL:无法获取管理器"; exit 1 }
try {
    $null = $mgr.StopTetheringAsync()
    Write-Output "CMD_SENT"
} catch {
    Write-Output "FAIL:" + $_.Exception.Message
    exit 1
}
'''

        # 发送命令（脚本执行超时设为10秒）
        returncode, stdout, stderr = HotspotManager._run_powershell(script, timeout=10)
        if returncode != 0 or stdout.startswith("FAIL:"):
            err = stdout.replace("FAIL:", "").strip() if stdout else stderr
            return False, err or "命令发送失败"

        # 轮询等待状态切换至目标状态
        for _ in range(timeout):
            time.sleep(1)
            current = HotspotManager.get_hotspot_status()
            if current == expected_status:
                return True, ""
            if current == "错误":
                return False, "热点状态异常（错误）"
        return False, f"{'启动' if operation=='start' else '关闭'}超时，请检查系统热点设置"

    @staticmethod
    def start_hotspot(ssid: str = None, key: str = None) -> tuple[bool, str]:
        """启动移动热点。
        参数：
            ssid: 热点名称，若为 None 则从配置文件读取。
            key: 热点密码，若为 None 则从配置文件读取。
        返回：
            (是否成功, 错误信息)
        """

        if ssid is None or key is None:
            config = HotspotManager.load_config()
            ssid = config.get("ssid")
            key = config.get("password")
        if HotspotManager.get_hotspot_status() == "已启动":
            return True, ""
        return HotspotManager._send_command_and_wait("start", ssid, key, timeout=15)

    @staticmethod
    def stop_hotspot() -> tuple[bool, str]:
        """停止移动热点。
        返回：
            (是否成功, 错误信息)
        """

        if HotspotManager.get_hotspot_status() == "未启动":
            return True, ""
        return HotspotManager._send_command_and_wait("stop", timeout=15)
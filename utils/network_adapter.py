import subprocess
from typing import List, Tuple

# Windows API 常量：创建进程时不显示控制台窗口
CREATE_NO_WINDOW = 0x08000000

class NetworkAdapterManager:
    """网络适配器管理工具，通过 netsh 命令获取和设置网卡状态。"""

    @staticmethod
    def get_adapters() -> List[Tuple[str, str]]:
        """
        获取所有网络适配器的名称及其启用/禁用状态。
        返回一个列表，每个元素为 (适配器名称, 状态字符串 "Enabled" 或 "Disabled")。
        """
        try:
            output = subprocess.check_output(
                ["netsh", "interface", "show", "interface"],
                encoding="utf-8",
                errors="ignore",
                creationflags=CREATE_NO_WINDOW #隐藏控制台
            )
        except subprocess.CalledProcessError:
            return []

        adapters = []
        for line in output.splitlines():
            parts = line.split(None, 3)
            if len(parts) < 4:
                continue

            status_str = parts[0].strip() #状态
            name = parts[3].strip() #适配器名称

            # 判断状态
            if status_str in ("Enabled", "已启用"):
                adapters.append((name, "Enabled"))
            elif status_str in ("Disabled", "已禁用"):
                adapters.append((name, "Disabled"))
        return adapters

    @staticmethod
    def set_adapter_state(name: str, enable: bool) -> bool:
        """
        启用或禁用指定的网络适配器。
        参数：
            name: 适配器的名称（需与 netsh 中显示的名称完全一致）
            enable: True 表示启用，False 表示禁用
        返回：
            操作成功返回 True，失败返回 False
        """

        action = "enable" if enable else "disable"
        cmd = f'netsh interface set interface "{name}" admin={action}'

        try:
            #执行指令
            subprocess.run(
                cmd, shell=True,
                check=True,
                capture_output=True,
                creationflags=CREATE_NO_WINDOW
            )
            return True
        except subprocess.CalledProcessError:
            return False
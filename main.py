import sys
import ctypes
import os
import datetime

def hide_console():
    """隐藏当前进程的控制台窗口（如果存在）。"""
    try:
        kernel32 = ctypes.windll.kernel32
        # 获取控制台窗口句柄
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32 = ctypes.windll.user32
            user32.ShowWindow(hwnd, 0)
    except:
        # 忽略任何错误（如非控制台程序）
        pass

def is_admin():
    """检查当前进程是否以管理员权限运行。"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def setup_logging():
    """设置日志重定向：当程序打包为 exe 时，将 stdout/stderr 写入文件。
    避免没有控制台窗口时因 print 或日志输出导致 IO 阻塞或异常。
    """
    if getattr(sys, 'frozen', False):
        # 使用 LOCALAPPDATA 目录存放日志
        log_dir = os.path.join(os.environ.get("LOCALAPPDATA", "."), "CampusAuth")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "app.log")
        sys.stdout = open(log_path, "w", encoding="utf-8")
        sys.stderr = sys.stdout
        print(f"程序启动 {datetime.datetime.now()}")

if __name__ == "__main__":
    # 如果不是管理员，尝试以管理员权限重新运行自身
    if not is_admin():
        # ShellExecuteW 以 runas 启动，请求管理员提权
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        # 当前非管理员实例直接退出
        sys.exit()

    # 提权成功后隐藏控制台窗口（避免运行时出现黑框）
    hide_console()
    # 重定向日志输出（打包后无控制台时避免阻塞）
    setup_logging()

    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow, load_icon

    app = QApplication(sys.argv)
    # 设置应用图标
    app_icon = load_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    # 设置 AppUserModelID，确保任务栏图标正确（Windows 特色）
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("campus.auth.helper")
    except:
        pass

    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    # 进入 Qt 事件循环
    sys.exit(app.exec())
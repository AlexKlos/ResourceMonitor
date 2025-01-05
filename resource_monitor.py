import ctypes
import os
import shutil
import sys
import subprocess
import winreg


if os.name == 'nt':
    CREATE_NO_WINDOW = 0x08000000
    _orig_popen = subprocess.Popen

    def _no_console_popen(*args, **kwargs):
        if "creationflags" not in kwargs:
            kwargs["creationflags"] = CREATE_NO_WINDOW
        return _orig_popen(*args, **kwargs)

    subprocess.Popen = _no_console_popen

import GPUtil

from PyQt5.QtCore import (
    QDir,
    QSettings,
    QTimer,
    Qt
)
from PyQt5.QtGui import (
    QColor,
    QFontMetrics,
    QIcon,
    QPainter
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QInputDialog,
    QMenu,
    QSystemTrayIcon,
    QWidget
)


class FILETIME(ctypes.Structure):
    """Windows FILETIME structure for GetSystemTimes API."""
    _fields_ = [
        ("dwLowDateTime", ctypes.c_uint32),
        ("dwHighDateTime", ctypes.c_uint32)
    ]


class MEMORYSTATUSEX(ctypes.Structure):
    """Windows MEMORYSTATUSEX structure for GlobalMemoryStatusEx API."""
    _fields_ = [
        ("dwLength", ctypes.c_uint32),
        ("dwMemoryLoad", ctypes.c_uint32),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]


GetSystemTimes = ctypes.windll.kernel32.GetSystemTimes
GlobalMemoryStatusEx = ctypes.windll.kernel32.GlobalMemoryStatusEx

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE_NAME = "ResourceMonitor"


def add_to_startup(file_path=""):
    """Add the application to Windows startup (via registry)."""
    stable_dir = os.path.join(os.getenv("LOCALAPPDATA"), "ResourceMonitor")
    stable_exe_path = os.path.join(stable_dir, "ResourceMonitor.exe")

    if not os.path.exists(stable_dir):
        os.makedirs(stable_dir)

    if not file_path:
        file_path = os.path.realpath(sys.argv[0])

    if not os.path.exists(stable_exe_path):
        shutil.copyfile(file_path, stable_exe_path)

    exe_for_reg = f'"{stable_exe_path}"'
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(
                key, 
                REG_VALUE_NAME, 
                0, 
                winreg.REG_SZ, 
                exe_for_reg
            )
        print("Autostart is configured via registry.")
    except Exception as e:
        print("Error writing to the registry:", e)


def remove_from_startup():
    """Remove the application from Windows startup (via registry)."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, REG_VALUE_NAME)
        print("Autostart disabled (registry entry removed).")
    except FileNotFoundError:
        print("Autostart is not enabled (registry value not found).")
    except Exception as e:
        print(f"Error while disabling autostart: {e}")


def is_autostart_enabled():
    """Check if the app is set to run on startup (via registry).

    Returns:
        bool: True if the 'ResourceMonitor' value is found in HKCU\...\Run,
              otherwise False.
    """
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_RUN_KEY,
            0,
            winreg.KEY_READ
        ) as key:
            value, regtype = winreg.QueryValueEx(key, REG_VALUE_NAME)
            if value:
                return True
    except FileNotFoundError:
        pass
    except Exception as e:
        print("Error checking registry:", e)
    return False


class ResourceMonitor(QWidget):
    """A widget that displays CPU, GPU, and RAM usage with customization.

    This widget is always on top of other windows. It allows customization 
    of the window size, transparency (background and text separately), 
    font size, and update intervals.
    """

    def __init__(self):
        """Initialize ResourceMonitor."""
        super().__init__()
        self.COLOR_MODES = ["System", "Colored"]

        self.prev_idle = 0
        self.prev_kernel = 0
        self.prev_user = 0

        self.load_settings()
        self.tray_icon = None
        self.init_ui()
        self.old_pos = None
        self.check_gpu()

        self.prev_idle, self.prev_kernel, self.prev_user = self.get_system_times()

    def init_ui(self):
        """Initialize the user interface of the widget and set window properties."""
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(
            self.window_x,
            self.window_y,
            self.window_width,
            self.window_height
        )

        icon_path = os.path.join(QDir.currentPath(), 'icon.png')
        self.setWindowIcon(QIcon(icon_path))

        self.cpu_label = QLabel('CPU: 0%', self)
        self.gpu_label = QLabel('GPU: 0%', self)
        self.ram_label = QLabel('RAM: 0%', self)

        self.update_font_size()
        self.update_text_opacity()
        self.update_colors()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_metrics)
        self.timer.start(self.update_interval)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(icon_path))
        self.tray_icon.activated.connect(self.restore_from_tray)

        tray_menu = QMenu(self)
        restore_action = QAction("Restore", self)
        restore_action.triggered.connect(self.show_widget)
        tray_menu.addAction(restore_action)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)

    def get_system_times(self):
        """Return current (idle, kernel, user) times from Windows API.
        
        Returns:
            tuple: A tuple of (idle, kernel, user) 64-bit counters.
        """
        idle_time = FILETIME()
        kernel_time = FILETIME()
        user_time = FILETIME()

        success = GetSystemTimes(
            ctypes.byref(idle_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time)
        )

        if not success:
            return 0, 0, 0

        idle = (idle_time.dwHighDateTime << 32) | idle_time.dwLowDateTime
        kernel = (kernel_time.dwHighDateTime << 32) | kernel_time.dwLowDateTime
        user = (user_time.dwHighDateTime << 32) | user_time.dwLowDateTime

        return idle, kernel, user

    def get_cpu_usage(self):
        """Calculate CPU usage using the difference of system times.

        Returns:
            float: CPU usage percentage (0..100).
        """
        idle, kernel, user = self.get_system_times()

        idle_diff = idle - self.prev_idle
        kernel_diff = kernel - self.prev_kernel
        user_diff = user - self.prev_user
        total_diff = kernel_diff + user_diff

        self.prev_idle = idle
        self.prev_kernel = kernel
        self.prev_user = user

        if total_diff == 0:
            return 0.0

        usage = 100.0 * (1.0 - (idle_diff / float(total_diff)))
        return usage

    def get_ram_usage(self):
        """Get the current RAM usage percentage using GlobalMemoryStatusEx.

        Returns:
            float: RAM usage percentage (0..100).
        """
        mem_status = MEMORYSTATUSEX()
        mem_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not GlobalMemoryStatusEx(ctypes.byref(mem_status)):
            return 0.0
        return float(mem_status.dwMemoryLoad)

    def update_metrics(self):
        """Fetch and update system resource usage metrics (CPU, GPU, and RAM).

        Also bring the widget to the front.
        """
        if self.show_cpu:
            cpu_usage = self.get_cpu_usage()
            self.cpu_label.setText(f'CPU: {cpu_usage:.0f}%')
            self.update_label_color(self.cpu_label, cpu_usage)
        else:
            self.cpu_label.setText("")

        if self.show_gpu:
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu_usage = gpus[0].load * 100
                self.gpu_label.setText(f'GPU: {gpu_usage:.2f}%')
                self.update_label_color(self.gpu_label, gpu_usage)
            else:
                self.gpu_label.setText("GPU: N/A")
        else:
            self.gpu_label.setText("")

        if self.show_ram:
            ram_usage = self.get_ram_usage()
            self.ram_label.setText(f'RAM: {ram_usage:.0f}%')
            self.update_label_color(self.ram_label, ram_usage)
        else:
            self.ram_label.setText("")

        self.raise_()
        self.activateWindow()

    def update_label_color(self, label, usage):
        """Update the color of the label based on usage percentage.

        Args:
            label (QLabel): The label to update.
            usage (float): Resource usage percentage.
        """
        if self.color_mode == "Colored":
            color = self.get_smooth_color_by_usage(usage)
            label.setStyleSheet(
                f"color: {color}; font-size: {self.font_size}px;"
            )
        else:
            label.setStyleSheet(f"font-size: {self.font_size}px;")

    def get_smooth_color_by_usage(self, usage):
        """Get a smoothly interpolated color (green→yellow→red) by usage.

        Args:
            usage (float): Usage percentage.

        Returns:
            str: A string representation of the interpolated color in RGB.
        """
        green = (0, 255, 0)
        yellow = (255, 255, 0)
        red = (255, 0, 0)

        if usage < 50:
            return self.interpolate_color(green, yellow, usage / 50.0)
        return self.interpolate_color(yellow, red, (usage - 50) / 50.0)

    def interpolate_color(self, color1, color2, t):
        """Linearly interpolate between two colors.

        Args:
            color1 (tuple): First color (r, g, b).
            color2 (tuple): Second color (r, g, b).
            t (float): Interpolation factor in [0, 1].

        Returns:
            str: A string in 'rgb(r, g, b)' format.
        """
        r = int(color1[0] + (color2[0] - color1[0]) * t)
        g = int(color1[1] + (color2[1] - color1[1]) * t)
        b = int(color1[2] + (color2[2] - color1[2]) * t)
        return f"rgb({r}, {g}, {b})"

    def mousePressEvent(self, event):
        """Track the initial position of the widget to support dragging.

        Args:
            event (QMouseEvent): Mouse press event.
        """
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        """Move the widget on the screen when dragged.

        Args:
            event (QMouseEvent): Mouse move event.
        """
        if event.buttons() == Qt.LeftButton:
            delta = event.globalPos() - self.old_pos
            self.move(
                self.x() + delta.x(),
                self.y() + delta.y()
            )
            self.old_pos = event.globalPos()

    def closeEvent(self, event):
        """Save settings before the widget closes.

        Args:
            event (QCloseEvent): Close event.
        """
        self.save_settings()

    def show_context_menu(self, pos):
        """Display the context menu for customization options.

        Args:
            pos (QPoint): Position where the context menu is requested.
        """
        context_menu = QMenu(self)

        cpu_action = QAction(
            f"{'Hide' if self.show_cpu else 'Show'} CPU",
            self
        )
        cpu_action.triggered.connect(self.toggle_cpu)
        context_menu.addAction(cpu_action)

        gpu_action = QAction(
            f"{'Hide' if self.show_gpu else 'Show'} GPU",
            self
        )
        gpu_action.triggered.connect(self.toggle_gpu)
        context_menu.addAction(gpu_action)

        ram_action = QAction(
            f"{'Hide' if self.show_ram else 'Show'} RAM",
            self
        )
        ram_action.triggered.connect(self.toggle_ram)
        context_menu.addAction(ram_action)

        interval_menu = context_menu.addMenu("Update Interval")
        for interval in [1000, 2000, 5000]:
            action_interval = QAction(
                f"{interval // 1000} sec",
                self
            )
            action_interval.triggered.connect(
                lambda _, i=interval: self.change_update_interval(i)
            )
            interval_menu.addAction(action_interval)
        context_menu.addMenu(interval_menu)

        font_menu = context_menu.addMenu("Font Size")
        action_font = QAction("Custom Font Size", self)
        action_font.triggered.connect(self.change_font_size)
        font_menu.addAction(action_font)
        context_menu.addMenu(font_menu)

        size_menu = context_menu.addMenu("Size Settings")
        action_width = QAction("Change Width", self)
        action_width.triggered.connect(self.change_width)
        size_menu.addAction(action_width)

        action_height = QAction("Change Height", self)
        action_height.triggered.connect(self.change_height)
        size_menu.addAction(action_height)
        context_menu.addMenu(size_menu)

        color_menu = context_menu.addMenu("Color Mode")
        for mode in self.COLOR_MODES:
            action_color_mode = QAction(mode, self)
            action_color_mode.triggered.connect(
                lambda _, m=mode: self.change_color_mode(m)
            )
            color_menu.addAction(action_color_mode)
        context_menu.addMenu(color_menu)

        opacity_menu = context_menu.addMenu("Transparency Settings")
        action_background_opacity = QAction(
            "Change Background Opacity",
            self
        )
        action_background_opacity.triggered.connect(
            self.change_background_opacity
        )
        opacity_menu.addAction(action_background_opacity)

        action_text_opacity = QAction("Change Text Opacity", self)
        action_text_opacity.triggered.connect(self.change_text_opacity)
        opacity_menu.addAction(action_text_opacity)
        context_menu.addMenu(opacity_menu)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        context_menu.addAction(quit_action)

        if self.is_in_startup():
            action_toggle_autostart = QAction("Disable Autostart", self)
            action_toggle_autostart.triggered.connect(self.disable_autostart)
        else:
            action_toggle_autostart = QAction("Enable Autostart", self)
            action_toggle_autostart.triggered.connect(self.enable_autostart)
        context_menu.addAction(action_toggle_autostart)

        context_menu.exec_(self.mapToGlobal(pos))

    def toggle_cpu(self):
        """Toggle the visibility of CPU usage in the widget."""
        self.show_cpu = not self.show_cpu
        self.update_metrics()
        self.save_settings()

    def toggle_gpu(self):
        """Toggle the visibility of GPU usage in the widget."""
        self.show_gpu = not self.show_gpu
        self.update_metrics()
        self.save_settings()

    def toggle_ram(self):
        """Toggle the visibility of RAM usage in the widget."""
        self.show_ram = not self.show_ram
        self.update_metrics()
        self.save_settings()

    def change_update_interval(self, interval):
        """Change the update interval for fetching system metrics.

        Args:
            interval (int): Update interval in milliseconds.
        """
        self.update_interval = interval
        self.timer.start(self.update_interval)
        self.save_settings()

    def change_font_size(self):
        """Allow the user to input a custom font size."""
        font_size, ok = QInputDialog.getInt(
            self,
            "Change Font Size",
            "Enter new font size:",
            self.font_size,
            8
        )
        if ok:
            self.font_size = font_size
            self.save_settings()
            self.update_font_size()

    def update_font_size(self):
        """Apply the saved font size to the labels."""
        style = f"font-size: {self.font_size}px;"
        self.cpu_label.setStyleSheet(style)
        self.gpu_label.setStyleSheet(style)
        self.ram_label.setStyleSheet(style)

    def update_text_opacity(self):
        """Update the text opacity using QGraphicsOpacityEffect."""
        cpu_opacity_effect = QGraphicsOpacityEffect()
        cpu_opacity_effect.setOpacity(self.text_opacity / 100)
        self.cpu_label.setGraphicsEffect(cpu_opacity_effect)

        gpu_opacity_effect = QGraphicsOpacityEffect()
        gpu_opacity_effect.setOpacity(self.text_opacity / 100)
        self.gpu_label.setGraphicsEffect(gpu_opacity_effect)

        ram_opacity_effect = QGraphicsOpacityEffect()
        ram_opacity_effect.setOpacity(self.text_opacity / 100)
        self.ram_label.setGraphicsEffect(ram_opacity_effect)

    def paintEvent(self, event):
        """Custom paint event to control background color and transparency.

        Args:
            event (QPaintEvent): Paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        background_color = QColor(
            255, 255, 255,
            int(self.background_opacity * 2.55)
        )
        painter.setBrush(background_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 15, 15)
        self.center_metrics()

    def center_metrics(self):
        """Center the CPU, GPU, and RAM metrics horizontally and vertically."""
        metrics = [self.cpu_label, self.gpu_label, self.ram_label]
        active_metrics = [label for label in metrics if label.text() != ""]

        num_metrics = len(active_metrics)
        if num_metrics == 0:
            return

        width_per_metric = self.width() // num_metrics
        for i, label in enumerate(active_metrics):
            font_metrics = QFontMetrics(label.font())
            label_width = font_metrics.width(label.text())
            label_x = width_per_metric * i + (width_per_metric - label_width) // 2
            label_y = (self.height() - label.height()) // 2
            label.setGeometry(
                label_x,
                label_y,
                label_width,
                label.height()
            )

    def change_width(self):
        """Change the width of the widget."""
        width, ok = QInputDialog.getInt(
            self,
            "Change Width",
            "Enter new width:",
            self.window_width,
            1
        )
        if ok:
            self.window_width = width
            self.setFixedSize(self.window_width, self.window_height)
            self.save_settings()

    def change_height(self):
        """Change the height of the widget."""
        height, ok = QInputDialog.getInt(
            self,
            "Change Height",
            "Enter new height:",
            self.window_height,
            1
        )
        if ok:
            self.window_height = height
            self.setFixedSize(self.window_width, self.window_height)
            self.save_settings()

    def change_background_opacity(self):
        """Change the opacity (transparency) of the background."""
        opacity, ok = QInputDialog.getInt(
            self,
            "Change Background Opacity",
            "Enter background opacity (0-100):",
            self.background_opacity,
            0,
            100
        )
        if ok:
            self.background_opacity = opacity
            self.update()
            self.save_settings()

    def change_text_opacity(self):
        """Change the opacity of the text (metrics)."""
        opacity, ok = QInputDialog.getInt(
            self,
            "Change Text Opacity",
            "Enter text opacity (0-100):",
            self.text_opacity,
            0,
            100
        )
        if ok:
            self.text_opacity = opacity
            self.update_text_opacity()
            self.save_settings()

    def change_color_mode(self, mode):
        """Change the color mode (System, Colored).

        Args:
            mode (str): Color mode, either "System" or "Colored".
        """
        self.color_mode = mode
        self.update_colors()
        self.save_settings()

    def update_colors(self):
        """Update colors based on the current color mode."""
        self.update()

    def is_in_startup(self):
        """Check if the app is set to run on startup (registry-based)."""
        return is_autostart_enabled()

    def enable_autostart(self):
        """Enable the widget to run on Windows startup (registry-based)."""
        add_to_startup()
        print("Autostart enabled.")

    def disable_autostart(self):
        """Disable the widget from running on Windows startup (registry-based)."""
        remove_from_startup()
        print("Autostart disabled.")

    def restore_from_tray(self, reason):
        """Restore the widget from the system tray.

        Args:
            reason (QSystemTrayIcon.ActivationReason): Reason for tray icon.
        """
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_widget()

    def show_widget(self):
        """Show the widget and keep it on top of other windows."""
        self.show()
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowStaysOnTopHint
        )
        self.showNormal()
        self.tray_icon.hide()

    def save_settings(self):
        """Save the current settings to QSettings."""
        settings = QSettings("ResourceMonitor", "Settings")
        settings.setValue("show_cpu", self.show_cpu)
        settings.setValue("show_gpu", self.show_gpu)
        settings.setValue("show_ram", self.show_ram)
        settings.setValue("update_interval", self.update_interval)
        settings.setValue("font_size", self.font_size)
        settings.setValue("window_width", self.window_width)
        settings.setValue("window_height", self.window_height)
        settings.setValue("background_opacity", self.background_opacity)
        settings.setValue("text_opacity", self.text_opacity)
        settings.setValue("color_mode", self.color_mode)
        settings.setValue("window_x", self.x())
        settings.setValue("window_y", self.y())

    def load_settings(self):
        """Load saved settings from QSettings."""
        settings = QSettings("ResourceMonitor", "Settings")
        self.show_cpu = settings.value("show_cpu", True, type=bool)
        self.show_gpu = settings.value("show_gpu", True, type=bool)
        self.show_ram = settings.value("show_ram", True, type=bool)
        self.update_interval = settings.value("update_interval", 2000, type=int)
        self.font_size = settings.value("font_size", 16, type=int)
        self.window_width = settings.value("window_width", 300, type=int)
        self.window_height = settings.value("window_height", 50, type=int)
        self.background_opacity = settings.value("background_opacity", 100,
                                                 type=int)
        self.text_opacity = settings.value("text_opacity", 100, type=int)
        self.color_mode = settings.value("color_mode", "System")
        self.window_x = settings.value("window_x", 100, type=int)
        self.window_y = settings.value("window_y", 100, type=int)

    def check_gpu(self):
        """Check if a GPU is present on the system.

        If not, GPU metrics are disabled.
        """
        gpus = GPUtil.getGPUs()
        if not gpus:
            self.show_gpu = False
            self.gpu_label.setText("GPU: N/A")
            self.save_settings()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    monitor = ResourceMonitor()
    monitor.show()
    sys.exit(app.exec_())

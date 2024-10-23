import sys
import os
import psutil
import GPUtil
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QApplication, QMenu, QAction, QSystemTrayIcon, QStyle, QInputDialog
from PyQt5.QtCore import Qt, QTimer, QSettings, QDir
from PyQt5.QtGui import QIcon


class ResourceMonitor(QWidget):
    """A widget that displays CPU, GPU, and RAM usage with customization options.
    
    This widget is always on top of other windows and can be minimized to the system tray.
    It allows customization of the window size, transparency, font size, and update intervals.
    """
    MIN_WIDTH = 200
    MIN_HEIGHT = 50

    def __init__(self):
        super().__init__()
        self.load_settings()
        self.tray_icon = None
        self.initUI()
        self.old_pos = None
        self.check_gpu()

    def initUI(self):
        """Initializes the user interface of the widget and sets window properties."""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.X11BypassWindowManagerHint)

        # Set minimum and fixed window size
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.setFixedSize(self.window_width, self.window_height)

        # Set window transparency
        self.setWindowOpacity(self.window_opacity / 100)

        # Round the corners of the window
        self.setStyleSheet("border-radius: 15px;")

        # Use icon.png as the window and tray icon
        icon_path = os.path.join(QDir.currentPath(), 'icon.png')
        self.setWindowIcon(QIcon(icon_path))

        # Create layout and labels for CPU, GPU, and RAM
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.cpu_label = QLabel('CPU: 0%', self)
        self.gpu_label = QLabel('GPU: 0%', self)
        self.ram_label = QLabel('RAM: 0%', self)

        self.update_font_size()

        self.layout.addWidget(self.cpu_label)
        self.layout.addWidget(self.gpu_label)
        self.layout.addWidget(self.ram_label)

        # Timer to periodically update metrics
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_metrics)
        self.timer.start(self.update_interval)

        # Context menu setup
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        # System tray icon setup
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

    def update_metrics(self):
        """Fetches and updates the system resource usage metrics (CPU, GPU, and RAM)."""
        if self.show_cpu:
            cpu_usage = psutil.cpu_percent(interval=1)
            self.cpu_label.setText(f'CPU: {cpu_usage}%')
        else:
            self.cpu_label.setText("")

        if self.show_gpu:
            gpus = GPUtil.getGPUs()
            gpu_usage = gpus[0].load * 100 if gpus else 0
            self.gpu_label.setText(f'GPU: {gpu_usage:.2f}%') if gpus else self.gpu_label.setText("GPU: N/A")
        else:
            self.gpu_label.setText("")

        if self.show_ram:
            ram_usage = psutil.virtual_memory().percent
            self.ram_label.setText(f'RAM: {ram_usage}%')
        else:
            self.ram_label.setText("")

    def mousePressEvent(self, event):
        """Tracks the initial position of the widget to support dragging."""
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        """Moves the widget on the screen when dragged."""
        if event.buttons() == Qt.LeftButton:
            delta = event.globalPos() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

    def show_context_menu(self, pos):
        """Displays the context menu for customization options."""
        context_menu = QMenu(self)

        cpu_action = QAction(f"{'Hide' if self.show_cpu else 'Show'} CPU", self)
        cpu_action.triggered.connect(self.toggle_cpu)
        context_menu.addAction(cpu_action)

        gpu_action = QAction(f"{'Hide' if self.show_gpu else 'Show'} GPU", self)
        gpu_action.triggered.connect(self.toggle_gpu)
        context_menu.addAction(gpu_action)

        ram_action = QAction(f"{'Hide' if self.show_ram else 'Show'} RAM", self)
        ram_action.triggered.connect(self.toggle_ram)
        context_menu.addAction(ram_action)

        # Update interval options
        interval_menu = context_menu.addMenu("Update Interval")
        for interval in [1000, 2000, 5000]:
            action_interval = QAction(f"{interval // 1000} sec", self)
            action_interval.triggered.connect(lambda checked, i=interval: self.change_update_interval(i))
            interval_menu.addAction(action_interval)

        # Font size options
        font_menu = context_menu.addMenu("Font Size")
        for size in [12, 16, 24]:
            action_font = QAction(f"{size} px", self)
            action_font.triggered.connect(lambda checked, s=size: self.change_font_size(s))
            font_menu.addAction(action_font)

        # Size settings
        size_menu = context_menu.addMenu("Size Settings")
        action_width = QAction("Change Width", self)
        action_width.triggered.connect(self.change_width)
        size_menu.addAction(action_width)
        action_height = QAction("Change Height", self)
        action_height.triggered.connect(self.change_height)
        size_menu.addAction(action_height)

        # Opacity setting
        opacity_action = QAction("Change Opacity", self)
        opacity_action.triggered.connect(self.change_opacity)
        context_menu.addAction(opacity_action)

        # Minimize to tray
        minimize_action = QAction("Minimize to Tray", self)
        minimize_action.triggered.connect(self.minimize_to_tray)
        context_menu.addAction(minimize_action)

        # Autostart settings
        if self.is_in_startup():
            action_toggle_autostart = QAction("Disable Autostart", self)
            action_toggle_autostart.triggered.connect(self.disable_autostart)
        else:
            action_toggle_autostart = QAction("Enable Autostart", self)
            action_toggle_autostart.triggered.connect(self.enable_autostart)
        context_menu.addAction(action_toggle_autostart)

        context_menu.exec_(self.mapToGlobal(pos))

    def toggle_cpu(self):
        """Toggles the visibility of CPU usage in the widget."""
        self.show_cpu = not self.show_cpu
        self.update_metrics()
        self.save_settings()

    def toggle_gpu(self):
        """Toggles the visibility of GPU usage in the widget."""
        self.show_gpu = not self.show_gpu
        self.update_metrics()
        self.save_settings()

    def toggle_ram(self):
        """Toggles the visibility of RAM usage in the widget."""
        self.show_ram = not self.show_ram
        self.update_metrics()
        self.save_settings()

    def change_update_interval(self, interval):
        """Changes the update interval for fetching system metrics."""
        self.update_interval = interval
        self.timer.start(self.update_interval)
        self.save_settings()

    def change_font_size(self, size):
        """Changes the font size of the displayed metrics."""
        self.font_size = size
        self.update_font_size()
        self.save_settings()

    def update_font_size(self):
        """Updates the font size of the displayed metrics."""
        font_style = f"font-size: {self.font_size}px;"
        self.cpu_label.setStyleSheet(font_style)
        self.gpu_label.setStyleSheet(font_style)
        self.ram_label.setStyleSheet(font_style)

    def change_width(self):
        """Changes the width of the widget."""
        width, ok = QInputDialog.getInt(self, "Change Width", "Enter new width:", self.window_width, 200)
        if ok:
            self.window_width = max(width, self.MIN_WIDTH)
            self.setFixedSize(self.window_width, self.window_height)
            self.save_settings()

    def change_height(self):
        """Changes the height of the widget."""
        height, ok = QInputDialog.getInt(self, "Change Height", "Enter new height:", self.window_height, 50)
        if ok:
            self.window_height = max(height, self.MIN_HEIGHT)
            self.setFixedSize(self.window_width, self.window_height)
            self.save_settings()

    def change_opacity(self):
        """Changes the opacity (transparency) of the widget."""
        opacity, ok = QInputDialog.getInt(self, "Change Opacity", "Enter opacity level (0-100):", self.window_opacity, 0, 100)
        if ok:
            self.window_opacity = opacity
            self.setWindowOpacity(self.window_opacity / 100)
            self.save_settings()

    def is_in_startup(self):
        """Checks if the widget is set to run on startup."""
        bat_path = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup', 'ResourceMonitor.bat')
        return os.path.exists(bat_path)

    def enable_autostart(self):
        """Enables the widget to run on Windows startup."""
        add_to_startup(os.path.realpath(__file__))
        print("Autostart enabled.")

    def disable_autostart(self):
        """Disables the widget from running on Windows startup."""
        remove_from_startup()
        print("Autostart disabled.")

    def minimize_to_tray(self):
        """Minimizes the widget to the system tray."""
        self.hide()
        self.tray_icon.show()

    def restore_from_tray(self, reason):
        """Restores the widget from the system tray."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_widget()

    def show_widget(self):
        """Shows the widget and keeps it on top of other windows."""
        self.show()
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.showNormal()
        self.tray_icon.hide()

    def save_settings(self):
        """Saves the current settings to QSettings."""
        settings = QSettings("ResourceMonitor", "Settings")
        settings.setValue("show_cpu", self.show_cpu)
        settings.setValue("show_gpu", self.show_gpu)
        settings.setValue("show_ram", self.show_ram)
        settings.setValue("update_interval", self.update_interval)
        settings.setValue("font_size", self.font_size)
        settings.setValue("window_width", self.window_width)
        settings.setValue("window_height", self.window_height)
        settings.setValue("window_opacity", self.window_opacity)

    def load_settings(self):
        """Loads saved settings from QSettings."""
        settings = QSettings("ResourceMonitor", "Settings")
        self.show_cpu = settings.value("show_cpu", True, type=bool)
        self.show_gpu = settings.value("show_gpu", True, type=bool)
        self.show_ram = settings.value("show_ram", True, type=bool)
        self.update_interval = settings.value("update_interval", 2000, type=int)
        self.font_size = settings.value("font_size", 16, type=int)
        self.window_width = settings.value("window_width", self.MIN_WIDTH, type=int)
        self.window_height = settings.value("window_height", self.MIN_HEIGHT, type=int)
        self.window_opacity = settings.value("window_opacity", 100, type=int)

    def check_gpu(self):
        """Checks if a GPU is present on the system. If not, GPU metrics are disabled."""
        gpus = GPUtil.getGPUs()
        if not gpus:
            self.show_gpu = False
            self.gpu_label.setText("GPU: N/A")
            self.save_settings()


def add_to_startup(file_path=""):
    """Adds the widget to Windows startup."""
    bat_path = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
    with open(os.path.join(bat_path, "ResourceMonitor.bat"), "w+") as bat_file:
        bat_file.write(f'start "" "{file_path}"')


def remove_from_startup():
    """Removes the widget from Windows startup."""
    bat_path = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup', 'ResourceMonitor.bat')
    if os.path.exists(bat_path):
        os.remove(bat_path)
        print("Resource Monitor removed from startup.")
    else:
        print("Resource Monitor not found in startup.")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    monitor = ResourceMonitor()
    monitor.show()
    
    sys.exit(app.exec_())

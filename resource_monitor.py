import os
import sys

import psutil
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


def add_to_startup(file_path=""):
    """Add the widget to Windows startup without console.

    Args:
        file_path (str): Path to the current file. Defaults to "".
    """
    if file_path == "":
        file_path = os.path.realpath(__file__)

    python_executable = os.path.join(
        os.getenv('VIRTUAL_ENV'),
        'Scripts',
        'pythonw.exe'
    )
    if not os.path.exists(python_executable):
        python_executable = 'pythonw'

    bat_path = os.path.join(
        os.getenv('APPDATA'),
        'Microsoft',
        'Windows',
        'Start Menu',
        'Programs',
        'Startup',
        'ResourceMonitor.bat'
    )
    try:
        with open(bat_path, "w+") as bat_file:
            bat_file.write(
                f'@echo off\nstart "" "{python_executable}" "{file_path}"'
            )
        print(f"Autostart enabled. BAT file created at {bat_path}")
    except Exception as e:
        print(f"Error while enabling autostart: {e}")


def remove_from_startup():
    """Remove the widget from Windows startup."""
    bat_path = os.path.join(
        os.getenv('APPDATA'),
        'Microsoft',
        'Windows',
        'Start Menu',
        'Programs',
        'Startup',
        'ResourceMonitor.bat'
    )
    if os.path.exists(bat_path):
        try:
            os.remove(bat_path)
            print("Autostart disabled.")
        except Exception as e:
            print(f"Error while disabling autostart: {e}")
    else:
        print("Autostart is not enabled.")


class ResourceMonitor(QWidget):
    """A widget that displays CPU, GPU, and RAM usage with customization.

    This widget is always on top of other windows and can be minimized
    to the system tray. It allows customization of the window size,
    transparency (background and text separately), font size, and
    update intervals.
    """

    def __init__(self):
        """Initialize ResourceMonitor."""
        super().__init__()
        self.COLOR_MODES = ["System", "Colored"]

        self.load_settings()
        self.tray_icon = None
        self.init_ui()
        self.old_pos = None
        self.check_gpu()

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

    def update_metrics(self):
        """Fetch and update the system resource usage metrics (CPU, GPU, and RAM).

        Also bring the widget to the front.
        """
        if self.show_cpu:
            # Use non-blocking call to avoid freezing
            cpu_usage = psutil.cpu_percent(interval=None)
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
            ram_usage = psutil.virtual_memory().percent
            self.ram_label.setText(f'RAM: {ram_usage:.0f}%')
            self.update_label_color(self.ram_label, ram_usage)
        else:
            self.ram_label.setText("")

        self.raise_()
        self.activateWindow()

    def update_label_color(self, label, usage):
        """Update the color of the label based on the usage percentage.

        Uses a smooth color transition if 'Colored' mode is enabled.
        
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

        minimize_action = QAction("Minimize to Tray", self)
        minimize_action.triggered.connect(self.minimize_to_tray)
        context_menu.addAction(minimize_action)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        context_menu.addAction(quit_action)

        if self.is_in_startup():
            action_toggle_autostart = QAction(
                "Disable Autostart",
                self
            )
            action_toggle_autostart.triggered.connect(
                self.disable_autostart
            )
        else:
            action_toggle_autostart = QAction(
                "Enable Autostart",
                self
            )
            action_toggle_autostart.triggered.connect(
                self.enable_autostart
            )
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
        """Check if the widget is set to run on startup.

        Returns:
            bool: True if autostart script exists, False otherwise.
        """
        bat_path = os.path.join(
            os.getenv('APPDATA'),
            'Microsoft',
            'Windows',
            'Start Menu',
            'Programs',
            'Startup',
            'ResourceMonitor.bat'
        )
        return os.path.exists(bat_path)

    def enable_autostart(self):
        """Enable the widget to run on Windows startup."""
        add_to_startup(os.path.realpath(__file__))
        print("Autostart enabled.")

    def disable_autostart(self):
        """Disable the widget from running on Windows startup."""
        remove_from_startup()
        print("Autostart disabled.")

    def minimize_to_tray(self):
        """Minimize the widget to the system tray."""
        self.hide()
        self.tray_icon.show()

    def restore_from_tray(self, reason):
        """Restore the widget from the system tray.

        Args:
            reason (QSystemTrayIcon.ActivationReason): Reason for tray icon activation.
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
        self.background_opacity = settings.value("background_opacity", 100, type=int)
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

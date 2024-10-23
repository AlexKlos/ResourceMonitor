
# Resource Monitor Widget

A lightweight, always-on-top widget for Windows that displays system resource usage such as CPU, GPU, and RAM. It can be customized, minimized to the system tray, and set to autostart with the OS.

## Features

- Displays current CPU, GPU, and RAM usage
- Customizable update intervals, window size, font size, and transparency
- Minimize to system tray
- Autostart with Windows option
- Always on top of other windows
- Rounded window corners

## Installation

1. Clone the repository and navigate to the project directory:

   ```bash
   git clone https://github.com/AlexKlos/ResourceMonitor.git
   cd resource-monitor
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:

   ```bash
   python resource_monitor.py
   ```

## Customization Options

- **Window Size**: Adjust width and height from the context menu.
- **Transparency**: Set the transparency of the window (0-100%).
- **Font Size**: Customize the font size of the displayed metrics.
- **Update Interval**: Choose how often the metrics are updated (e.g., every 1 second, 2 seconds, or 5 seconds).
- **Autostart**: Enable or disable the application to start automatically with Windows.

## System Tray

The widget can be minimized to the system tray by right-clicking on the widget and selecting "Minimize to Tray." You can restore it by clicking on the tray icon.

## License

This project is licensed under the MIT License.


# Resource Monitor Widget

A simple and customizable resource monitor widget for Windows 11 that displays the current usage of CPU, GPU, and RAM. The widget can be resized and moved freely on the screen or fixed in a specific position. It also supports autostart with the OS and allows for various customizations, such as font size, transparency, and color modes.

## Features
- Monitors CPU, GPU, and RAM usage.
- Resizable and movable widget.
- Can autostart with Windows 11.
- Supports background and text transparency control.
- Allows customization of font size and update interval.
- Color mode options: system colors, dynamic color based on usage.

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/AlexKlos/ResourceMonitor.git
   cd resource-monitor
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate  (for Windows)
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Run the application:
   ```
   python resource_monitor.py
   ```

## Autostart Setup

The application can be set to run at startup. If enabled through the settings, a `.bat` file is created in the startup folder to ensure the application launches without the console window.

## Customization Options

- **Font Size**: Changeable from the context menu.
- **Widget Size**: Both width and height are customizable.
- **Transparency**: Separate settings for background and text opacity.
- **Color Mode**: Choose between system colors or dynamic color based on usage.

## Requirements

- Python 3.x
- PyQt5
- GPUtil
- psutil

## License
MIT License

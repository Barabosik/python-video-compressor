# 🎬 Video Compressor

A standalone, lightweight Python GUI application that compresses videos to a specific target file size (in MB) using FFmpeg. 

Built with `tkinter`, this tool is designed to be as user-friendly as possible. It runs "out of the box" without requiring you to manually install FFmpeg on your system.

## ✨ Features

* **Target Size Compression:** Specify your desired file size (e.g., 50 MB for Discord, email, or forms), and the script automatically calculates the exact video bitrate needed to hit that target.
* **Zero-Setup:** Automatically installs `imageio-ffmpeg` via `pip` on the first run if it's not detected. No need to mess with system PATH variables or manual FFmpeg installations.
* **2-Pass Encoding:** Uses a two-pass libx264 encoding method to ensure the highest possible visual quality for your chosen file size.
* **Modern Dark UI:** A clean, responsive dark-themed interface built natively with `tkinter`.
* **Cross-Platform:** Works seamlessly on Windows, macOS, and Linux.

## 🚀 How to Use

1. **Prerequisites:** Make sure you have [Python 3.x](https://www.python.org/downloads/) installed on your computer.
2. **Download:** Clone this repository or download the `video_compressor.py` file.
3. **Run:** Execute the script from your terminal or command prompt:
   ```bash
   python video_compressor.py

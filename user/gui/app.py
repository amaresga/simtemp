#!/usr/bin/env python3
"""
NXP Simulated Temperature Sensor GUI Application

This application provides a graphical interface to interact with the
nxp_simtemp kernel module. It displays real-time temperature readings,
allows configuration changes, and shows alerts.

Copyright (c) 2025 Armando Mares
"""

import sys
import os
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import matplotlib.dates as mdates
from collections import deque

# Import the CLI module for device interface
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from main import SimtempDevice, SIMTEMP_FLAG_THRESHOLD_CROSSED
except ImportError:
    print("Error: Could not import main.py. Make sure it's in the same directory.")
    sys.exit(1)

class SimtempGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("NXP Simtemp Monitor")
        self.root.geometry("800x600")

        # Device interface
        self.device = SimtempDevice()
        self.monitoring = False
        self.monitor_thread = None

        # Data storage
        self.max_samples = 100
        self.timestamps = deque(maxlen=self.max_samples)
        self.temperatures = deque(maxlen=self.max_samples)
        self.alerts = deque(maxlen=self.max_samples)

        # Current values
        self.current_temp = tk.StringVar(value="--.-°C")
        self.current_alert = tk.StringVar(value="No")
        self.sample_count = tk.StringVar(value="0")
        self.alert_count = tk.StringVar(value="0")

        # Configuration variables
        self.sampling_ms = tk.StringVar(value="100")
        self.threshold_c = tk.StringVar(value="45.0")
        self.mode = tk.StringVar(value="normal")
        self.enabled = tk.BooleanVar(value=False)

        self.setup_ui()
        self.load_config()

        # Set up plot animation
        self.setup_plot()

    def setup_ui(self):
        """Setup the user interface"""
        # Main notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Monitor tab
        monitor_frame = ttk.Frame(notebook)
        notebook.add(monitor_frame, text="Monitor")
        self.setup_monitor_tab(monitor_frame)

        # Configuration tab
        config_frame = ttk.Frame(notebook)
        notebook.add(config_frame, text="Configuration")
        self.setup_config_tab(config_frame)

        # Statistics tab
        stats_frame = ttk.Frame(notebook)
        notebook.add(stats_frame, text="Statistics")
        self.setup_stats_tab(stats_frame)

def main():
    # Check if required modules are available
    try:
        import matplotlib
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.animation import FuncAnimation
        import matplotlib.dates as mdates
    except ImportError:
        print("Error: matplotlib is required for the GUI application.")
        print("Install it with: pip install matplotlib.")
        sys.exit(1)

    root = tk.Tk()
    app = SimtempGUI(root)

    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    # Start the application
    root.mainloop()

if __name__ == "__main__":
    main()
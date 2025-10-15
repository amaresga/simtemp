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

    def setup_monitor_tab(self, parent):
        """Setup the monitoring tab"""
        # Current values frame
        values_frame = ttk.LabelFrame(parent, text="Current Values")
        values_frame.pack(fill=tk.X, padx=5, pady=5)

        # Current temperature
        ttk.Label(values_frame, text="Temperature:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        temp_label = ttk.Label(values_frame, textvariable=self.current_temp, font=("Arial", 14, "bold"))
        temp_label.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        # Current alert status
        ttk.Label(values_frame, text="Alert:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        alert_label = ttk.Label(values_frame, textvariable=self.current_alert, font=("Arial", 12))
        alert_label.grid(row=0, column=3, sticky=tk.W, padx=5, pady=2)

        # Sample and alert counts
        ttk.Label(values_frame, text="Samples:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Label(values_frame, textvariable=self.sample_count).grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(values_frame, text="Alerts:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=2)
        ttk.Label(values_frame, textvariable=self.alert_count).grid(row=1, column=3, sticky=tk.W, padx=5, pady=2)

        # Control buttons
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, padx=5, pady=5)

        self.start_button = ttk.Button(control_frame, text="Start Monitoring", command=self.start_monitoring)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = ttk.Button(control_frame, text="Stop Monitoring", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        ttk.Button(control_frame, text="Clear Data", command=self.clear_data).pack(side=tk.LEFT, padx=5)

        # Plot frame
        plot_frame = ttk.Frame(parent)
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Matplotlib figure
        self.fig, self.ax = plt.subplots(figsize=(10, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def setup_config_tab(self, parent):
        """Setup the configuration tab"""
        # Device control
        device_frame = ttk.LabelFrame(parent, text="Device Control")
        device_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Checkbutton(device_frame, text="Enable Device", variable=self.enabled,
                       command=self.toggle_device).pack(anchor=tk.W, padx=5, pady=2)

        # Sampling configuration
        sampling_frame = ttk.LabelFrame(parent, text="Sampling Configuration")
        sampling_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(sampling_frame, text="Sampling Period (ms):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        sampling_entry = ttk.Entry(sampling_frame, textvariable=self.sampling_ms, width=10)
        sampling_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Button(sampling_frame, text="Set", command=self.set_sampling).grid(row=0, column=2, padx=5, pady=2)

        ttk.Label(sampling_frame, text="Threshold (°C):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        threshold_entry = ttk.Entry(sampling_frame, textvariable=self.threshold_c, width=10)
        threshold_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Button(sampling_frame, text="Set", command=self.set_threshold).grid(row=1, column=2, padx=5, pady=2)

        ttk.Label(sampling_frame, text="Mode:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        mode_combo = ttk.Combobox(sampling_frame, textvariable=self.mode, values=["normal", "noisy", "ramp"],
                                 state="readonly", width=10)
        mode_combo.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Button(sampling_frame, text="Set", command=self.set_mode).grid(row=2, column=2, padx=5, pady=2)

        # Quick actions
        actions_frame = ttk.LabelFrame(parent, text="Quick Actions")
        actions_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(actions_frame, text="Load Current Config", command=self.load_config).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(actions_frame, text="Test Alert", command=self.test_alert).pack(side=tk.LEFT, padx=5, pady=5)

    def setup_stats_tab(self, parent):
        """Setup the statistics tab"""
        self.stats_text = tk.Text(parent, height=20, width=60)
        self.stats_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Scrollbar for stats
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.stats_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.stats_text.config(yscrollcommand=scrollbar.set)

        # Update button
        ttk.Button(parent, text="Refresh Statistics", command=self.update_stats).pack(pady=5)

        # Auto-update stats
        self.update_stats()

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
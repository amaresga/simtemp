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

    def setup_plot(self):
        """Setup the temperature plot"""
        self.ax.set_title("Temperature vs Time")
        self.ax.set_xlabel("Time")
        self.ax.set_ylabel("Temperature (°C)")
        self.ax.grid(True, alpha=0.3)

        # Initialize empty lines
        self.temp_line, = self.ax.plot([], [], 'b-', label='Temperature')
        self.threshold_line = self.ax.axhline(y=45.0, color='r', linestyle='--', alpha=0.7, label='Threshold')

        self.ax.legend()

        # Set up animation
        self.anim = FuncAnimation(self.fig, self.update_plot, interval=1000, blit=False)

    def update_plot(self, frame):
        """Update the temperature plot"""
        if len(self.timestamps) > 0:
            # Convert timestamps to matplotlib dates
            plot_times = [mdates.date2num(ts) for ts in self.timestamps]

            # Update temperature line
            self.temp_line.set_data(plot_times, list(self.temperatures))

            # Update threshold line
            try:
                threshold = float(self.threshold_c.get())
                self.threshold_line.set_ydata([threshold, threshold])
            except ValueError:
                pass

            # Auto-scale axes
            if len(plot_times) > 1:
                self.ax.set_xlim(min(plot_times), max(plot_times))
                temp_min = min(self.temperatures)
                temp_max = max(self.temperatures)
                temp_range = temp_max - temp_min
                if temp_range > 0:
                    self.ax.set_ylim(temp_min - temp_range * 0.1, temp_max + temp_range * 0.1)

                # Format x-axis
                self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
                self.ax.xaxis.set_major_locator(mdates.SecondLocator(interval=10))

        self.canvas.draw()

    def start_monitoring(self):
        """Start temperature monitoring"""
        if not os.path.exists(self.device.device_path):
            messagebox.showerror("Error", f"Device {self.device.device_path} not found.\nMake sure the nxp_simtemp module is loaded.")
            return

        if not self.device.open():
            messagebox.showerror("Error", "Failed to open device")
            return

        self.monitoring = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self.monitor_worker, daemon=True)
        self.monitor_thread.start()

    def stop_monitoring(self):
        """Stop temperature monitoring"""
        self.monitoring = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

        if self.device.fd is not None:
            self.device.close()

    def monitor_worker(self):
        """Worker thread for monitoring temperature"""
        sample_count = 0
        alert_count = 0

        while self.monitoring:
            try:
                result = self.device.read_sample(timeout=0.5)
                if result is None:
                    continue

                timestamp, temp_c, flags = result
                sample_count += 1

                # Update current values
                self.current_temp.set(f"{temp_c:.1f}°C")
                self.sample_count.set(str(sample_count))

                # Check for alert
                if flags & SIMTEMP_FLAG_THRESHOLD_CROSSED:
                    alert_count += 1
                    self.current_alert.set("YES")
                    self.alert_count.set(str(alert_count))
                    # Flash the alert for visual indication
                    self.root.after(0, self.flash_alert)
                else:
                    self.current_alert.set("No")

                # Add to data collections
                self.timestamps.append(timestamp)
                self.temperatures.append(temp_c)
                self.alerts.append(bool(flags & SIMTEMP_FLAG_THRESHOLD_CROSSED))

            except Exception as e:
                print(f"Monitor error: {e}")
                break

    def flash_alert(self):
        """Flash the alert indication"""
        # This could be enhanced with color changes, sounds, etc.
        pass

    def clear_data(self):
        """Clear collected data"""
        self.timestamps.clear()
        self.temperatures.clear()
        self.alerts.clear()
        self.sample_count.set("0")
        self.alert_count.set("0")
        self.current_temp.set("--.-°C")
        self.current_alert.set("No")

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
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
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import matplotlib.dates as mdates
from collections import deque
import numpy as np
from scipy.interpolate import make_interp_spline

# Import the CLI module for device interface
cli_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cli')
sys.path.insert(0, cli_path)
try:
    from main import SimtempDevice, SIMTEMP_FLAG_THRESHOLD_CROSSED
except ImportError:
    print("Error: Could not import main.py from ../cli/")
    print(f"Searched in: {cli_path}")
    sys.exit(1)

class SimtempGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🌡️ NXP Simtemp Monitor - Real-Time Temperature")
        self.root.geometry("900x650")
        self.root.minsize(800, 600)  # Minimum window size

        # Device interface
        self.device = SimtempDevice()
        self.monitoring = False
        self.monitor_thread = None

        # Data storage with smoothing
        self.max_samples = 100
        self.timestamps = deque(maxlen=self.max_samples)
        self.temperatures = deque(maxlen=self.max_samples)
        self.alerts = deque(maxlen=self.max_samples)

        # Smoothing parameters
        self.smooth_temperatures = deque(maxlen=self.max_samples)
        self.alpha = 0.3  # Exponential smoothing factor (lower = smoother)

        # Dynamic timing parameters
        self.start_timestamp = None  # First timestamp for relative time calculation
        self.current_sampling_ms = None  # Current driver sampling period
        self.gui_update_interval = 33  # Default 30 FPS

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

        # Perform initial frame rate adaptation
        self.check_and_adapt_framerate()

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
        """Setup the monitoring tab with enhanced styling"""
        # Current values frame with better styling
        values_frame = ttk.LabelFrame(parent, text="📊 Current Values", padding=10)
        values_frame.pack(fill=tk.X, padx=5, pady=5)

        # Current temperature with color coding
        ttk.Label(values_frame, text="🌡️ Temperature:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.temp_display = ttk.Label(values_frame, textvariable=self.current_temp,
                                      font=("Arial", 16, "bold"), foreground="#3498db")
        self.temp_display.grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)

        # Current alert status with visual indicator
        ttk.Label(values_frame, text="⚠️ Alert:", font=("Arial", 10, "bold")).grid(row=0, column=2, sticky=tk.W, padx=10, pady=5)
        self.alert_display = ttk.Label(values_frame, textvariable=self.current_alert,
                                       font=("Arial", 12, "bold"), foreground="#27ae60")
        self.alert_display.grid(row=0, column=3, sticky=tk.W, padx=10, pady=5)

        # Sample and alert counts with icons
        ttk.Label(values_frame, text="📈 Samples:", font=("Arial", 9)).grid(row=1, column=0, sticky=tk.W, padx=10, pady=2)
        ttk.Label(values_frame, textvariable=self.sample_count, font=("Arial", 10, "bold")).grid(row=1, column=1, sticky=tk.W, padx=10, pady=2)

        ttk.Label(values_frame, text="🔔 Alerts:", font=("Arial", 9)).grid(row=1, column=2, sticky=tk.W, padx=10, pady=2)
        ttk.Label(values_frame, textvariable=self.alert_count, font=("Arial", 10, "bold"),
                 foreground="#e74c3c").grid(row=1, column=3, sticky=tk.W, padx=10, pady=2)

        # Control buttons with better styling
        control_frame = ttk.Frame(parent, padding=5)
        control_frame.pack(fill=tk.X, padx=5, pady=5)

        self.start_button = ttk.Button(control_frame, text="▶ Start Monitoring",
                                       command=self.start_monitoring, width=18)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = ttk.Button(control_frame, text="⏸ Stop Monitoring",
                                      command=self.stop_monitoring, state=tk.DISABLED, width=18)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        ttk.Button(control_frame, text="🗑️ Clear Data",
                  command=self.clear_data, width=15).pack(side=tk.LEFT, padx=5)

        # Plot frame
        plot_frame = ttk.Frame(parent)
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Matplotlib figure with optimized settings for smooth animation
        self.fig, self.ax = plt.subplots(figsize=(10, 4.5), dpi=100)
        self.fig.tight_layout(pad=2.0)

        # Create canvas with optimized backend
        self.canvas = FigureCanvasTkAgg(self.fig, plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Optimize canvas for animation performance
        self.canvas.draw()  # Initial draw
        self.fig.canvas.mpl_connect('draw_event', lambda event: None)  # Reduce overhead

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
        """Setup the temperature plot with enhanced styling and performance"""
        # Set modern style with light background
        self.ax.set_facecolor('#f8f9fa')
        self.fig.patch.set_facecolor('white')

        # Enhanced title with color
        self.ax.set_title("Real-Time Temperature Monitor", fontsize=14, fontweight='bold',
                         color='#2c3e50', pad=15)
        self.ax.set_xlabel("Time (seconds)", fontsize=11, fontweight='semibold', color='#34495e')
        self.ax.set_ylabel("Temperature (°C)", fontsize=11, fontweight='semibold', color='#34495e')

        # Professional grid styling
        self.ax.grid(True, which='major', linestyle='-', linewidth=0.8, alpha=0.5, color='#bdc3c7')
        self.ax.grid(True, which='minor', linestyle=':', linewidth=0.4, alpha=0.3, color='#bdc3c7')
        self.ax.minorticks_on()

        # Beautiful temperature line - reduced markers for smoother rendering
        self.temp_line, = self.ax.plot([], [], color='#3498db', linewidth=2.5,
                                       label='Temperature', marker='o', markersize=3,
                                       markerfacecolor='#3498db', markeredgecolor='white',
                                       markeredgewidth=0.5, alpha=0.9, markevery=2,
                                       antialiased=True)

        # Prominent threshold line
        self.threshold_line = self.ax.axhline(y=45.0, color='#e74c3c', linestyle='--',
                                             linewidth=2.5, alpha=0.8, label='Threshold',
                                             zorder=5)

        # Styled legend with frame
        self.ax.legend(loc='upper left', fontsize=10, framealpha=0.9,
                      shadow=True, fancybox=True, edgecolor='#95a5a6')

        # Optimize borders
        self.ax.spines['top'].set_color('#bdc3c7')
        self.ax.spines['right'].set_color('#bdc3c7')
        self.ax.spines['left'].set_color('#7f8c8d')
        self.ax.spines['bottom'].set_color('#7f8c8d')
        self.ax.spines['left'].set_linewidth(1.5)
        self.ax.spines['bottom'].set_linewidth(1.5)

        # Initialize axis limits to prevent constant rescaling
        self.ax.set_xlim(0, 1)
        self.ax.set_ylim(20, 50)

        # Track last update for throttling
        self.last_xlim = None
        self.last_ylim = None
        self.update_counter = 0

        # Dynamic frame rate adaptation
        self.current_sampling_ms = 10  # Default value
        self.last_sampling_check = datetime.now()
        self.adaptive_interval = 33  # Start with 30 FPS

        # Set up animation with dynamic interval
        self.anim = FuncAnimation(self.fig, self.update_plot, interval=33,
                                 blit=False, cache_frame_data=False)

    def check_and_adapt_framerate(self):
        """Dynamically adapt GUI update rate to match driver sampling period"""
        now = datetime.now()

        # Check sampling period every 2 seconds to avoid overhead
        if (now - self.last_sampling_check).total_seconds() < 2.0:
            return

        self.last_sampling_check = now

        try:
            # Read current sampling period from driver
            with open('/sys/class/misc/simtemp/sampling_ms', 'r') as f:
                sampling_ms = int(f.read().strip())

            # Only update if significantly changed (avoid unnecessary restarts)
            if abs(sampling_ms - self.current_sampling_ms) > 2:
                self.current_sampling_ms = sampling_ms

                # Calculate optimal update interval
                # Strategy: Match sampling rate or use reasonable multiple
                if sampling_ms <= 10:
                    # Very fast sampling: update at sampling rate (max 100 FPS)
                    self.adaptive_interval = sampling_ms
                elif sampling_ms <= 33:
                    # Medium sampling: match 1:1 for smoothness
                    self.adaptive_interval = sampling_ms
                elif sampling_ms <= 100:
                    # Slower sampling: update at 2x rate for interpolation smoothness
                    self.adaptive_interval = sampling_ms // 2
                else:
                    # Very slow sampling: cap at 10 FPS
                    self.adaptive_interval = max(sampling_ms // 3, 100)

                # Restart animation with new interval
                self.anim.event_source.interval = self.adaptive_interval

                # Log the adaptation (for debugging)
                print(f"🎯 Adapted: sampling={sampling_ms}ms → update={self.adaptive_interval}ms ({1000//self.adaptive_interval} FPS)")

        except (IOError, ValueError) as e:
            # Silently fail - driver might not be ready
            pass

    def update_plot(self, frame):
        """Update the temperature plot with ultra-smooth interpolated rendering"""
        self.update_counter += 1

        # Periodically check and adapt frame rate
        self.check_and_adapt_framerate()

        # Quick exit if no data
        if len(self.timestamps) < 2:
            return

        try:
            # Make thread-safe copies efficiently
            timestamps_copy = list(self.timestamps)
            temperatures_copy = list(self.temperatures)

            if not timestamps_copy or len(timestamps_copy) < 2:
                return

            # Convert timestamps to relative seconds (time since monitoring started)
            # Use the first recorded timestamp as reference, not the oldest in the deque
            if self.start_timestamp is not None:
                start_time = self.start_timestamp
            else:
                # Fallback if start_timestamp not set yet
                start_time = timestamps_copy[0]

            plot_times = [(ts - start_time).total_seconds() for ts in timestamps_copy]

            # Apply smooth interpolation for fluid animation
            if len(temperatures_copy) >= 4:
                # Use numpy for smooth cubic interpolation

                # Create smooth curve with 3x more points
                t_array = np.array(plot_times)
                temp_array = np.array(temperatures_copy)

                # Use cubic spline for smooth interpolation
                try:
                    # Create more intermediate points for smoothness
                    num_points = min(len(plot_times) * 3, 300)
                    t_smooth = np.linspace(t_array.min(), t_array.max(), num_points)

                    # B-spline for smooth curve (k=3 for cubic)
                    spl = make_interp_spline(t_array, temp_array, k=min(3, len(t_array)-1))
                    temp_smooth = spl(t_smooth)

                    # Update line with smooth data
                    self.temp_line.set_data(t_smooth, temp_smooth)
                except:
                    # Fallback to original data if interpolation fails
                    self.temp_line.set_data(plot_times, temperatures_copy)
            else:
                # Not enough points for interpolation, use raw data
                self.temp_line.set_data(plot_times, temperatures_copy)

            # Update threshold line (only if changed)
            try:
                threshold = float(self.threshold_c.get())
                self.threshold_line.set_ydata([threshold, threshold])
            except (ValueError, tk.TclError):
                pass

            # Calculate axis limits
            temp_min = min(temperatures_copy)
            temp_max = max(temperatures_copy)
            temp_range = temp_max - temp_min

            # Smart Y-axis limits with nice round numbers
            if temp_range > 0:
                padding = max(temp_range * 0.15, 2)
                y_min = int((temp_min - padding) / 5) * 5
                y_max = int((temp_max + padding) / 5 + 1) * 5
            else:
                y_min = int(temp_min / 5) * 5 - 5
                y_max = int(temp_max / 5) * 5 + 5

            x_min = min(plot_times)
            x_max = max(plot_times)

            # Only update axes if limits changed significantly (reduces flicker)
            new_xlim = (x_min, x_max)
            new_ylim = (y_min, y_max)

            if self.last_xlim != new_xlim:
                self.ax.set_xlim(x_min, x_max)
                self.last_xlim = new_xlim

            if self.last_ylim != new_ylim:
                self.ax.set_ylim(y_min, y_max)
                self.last_ylim = new_ylim

            # Update time formatting only every 4th frame (reduces overhead)
            if self.update_counter % 4 == 0:
                time_span = x_max - x_min

                # Adaptive intervals for cleaner display with seconds
                if time_span < 30:  # < 30 seconds
                    interval = 5
                elif time_span < 120:  # < 2 minutes
                    interval = 10
                elif time_span < 300:  # < 5 minutes
                    interval = 30
                else:
                    interval = 60

                # Format X-axis to show seconds with nice intervals
                from matplotlib.ticker import MaxNLocator
                self.ax.xaxis.set_major_locator(MaxNLocator(nbins=8, integer=True))
                self.ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x)}s'))

                # Efficient label styling (only when updating)
                plt.setp(self.ax.get_xticklabels(), rotation=45, ha='right',
                        fontsize=9, color='#34495e')
                plt.setp(self.ax.get_yticklabels(), fontsize=9, color='#34495e')

            # Use flush_events for ultra-smooth updates
            self.canvas.draw_idle()
            self.canvas.flush_events()

        except Exception as e:
            # Silently handle any errors to prevent crashes
            print(f"Plot update error: {e}")
            pass

    def get_optimal_update_interval(self):
        """Calculate optimal GUI update interval based on driver sampling period"""
        try:
            # Read current sampling period from driver
            sampling_ms = int(self.device.get_sysfs_value("sampling_ms"))
            self.current_sampling_ms = sampling_ms

            # Strategy: GUI updates at same rate or slightly faster for smoothness
            # If sampling is very fast (<50ms), use 30 FPS to save CPU
            # If sampling is slow (>50ms), match it exactly for 1:1 correspondence

            if sampling_ms <= 33:
                # Fast sampling: cap at 30 FPS (33ms) to save CPU
                interval = 33
            elif sampling_ms <= 100:
                # Medium sampling: use sampling rate or 30 FPS, whichever is faster
                interval = min(sampling_ms, 33)
            else:
                # Slow sampling: match exactly for smooth 1:1 updates
                interval = sampling_ms

            print(f"📊 Sampling period: {sampling_ms}ms → GUI update: {interval}ms ({1000//interval} FPS)")
            return interval

        except Exception as e:
            print(f"Warning: Could not read sampling period ({e}), using 33ms default")
            return 33  # Default to 30 FPS

    def start_monitoring(self):
        """Start temperature monitoring"""
        if not os.path.exists(self.device.device_path):
            messagebox.showerror("Error", f"Device {self.device.device_path} not found.\nMake sure the nxp_simtemp module is loaded.")
            return

        if not self.device.open():
            messagebox.showerror("Error", "Failed to open device")
            return

        # Clear old buffer data for fresh start
        print("🔄 Flushing old buffer data...")
        self.device.flush_buffer()

        # Reset timestamp reference
        self.start_timestamp = None

        # Calculate optimal update interval based on current sampling rate
        optimal_interval = self.get_optimal_update_interval()

        # Restart animation with new interval if it changed
        if hasattr(self, 'anim') and optimal_interval != self.gui_update_interval:
            self.gui_update_interval = optimal_interval
            self.anim.event_source.interval = optimal_interval
            print(f"✅ Animation interval updated to {optimal_interval}ms")

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

                # Check for alert with dynamic color coding
                if flags & SIMTEMP_FLAG_THRESHOLD_CROSSED:
                    alert_count += 1
                    self.current_alert.set("⚠️ YES")
                    self.alert_count.set(str(alert_count))
                    # Change alert display color to red
                    self.root.after(0, lambda: self.alert_display.config(foreground="#e74c3c"))
                    # Flash the alert for visual indication
                    self.root.after(0, self.flash_alert)
                else:
                    self.current_alert.set("✓ No")
                    # Change alert display color to green
                    self.root.after(0, lambda: self.alert_display.config(foreground="#27ae60"))

                # Set start timestamp reference on first sample
                if self.start_timestamp is None:
                    self.start_timestamp = timestamp
                    print(f"📍 Time reference set: {timestamp}")

                # Add to data collections
                self.timestamps.append(timestamp)
                self.temperatures.append(temp_c)
                self.alerts.append(bool(flags & SIMTEMP_FLAG_THRESHOLD_CROSSED))

            except Exception as e:
                print(f"Monitor error: {e}")
                break

    def flash_alert(self):
        """Flash the alert indication with visual and audio feedback"""
        # System beep for audio feedback
        self.root.bell()

        # Flash background color (red for 500ms, then back to normal)
        original_bg = self.root.cget('bg')
        self.root.configure(bg='#ffcccc')  # Light red
        self.root.after(500, lambda: self.root.configure(bg=original_bg))

    def clear_data(self):
        """Clear collected data"""
        self.timestamps.clear()
        self.temperatures.clear()
        self.alerts.clear()
        self.sample_count.set("0")
        self.alert_count.set("0")
        self.current_temp.set("--.-°C")
        self.current_alert.set("No")

    def load_config(self):
        """Load current configuration from device"""
        try:
            sampling = self.device.get_sysfs_value("sampling_ms")
            if sampling:
                self.sampling_ms.set(sampling)

            threshold = self.device.get_sysfs_value("threshold_mC")
            if threshold:
                self.threshold_c.set(str(int(threshold) / 1000.0))

            mode = self.device.get_sysfs_value("mode")
            if mode:
                self.mode.set(mode)

            enabled = self.device.get_sysfs_value("enabled")
            if enabled:
                self.enabled.set(enabled == "1")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration: {e}")

    def toggle_device(self):
        """Toggle device enable/disable"""
        try:
            if self.enabled.get():
                self.device.enable_device()
            else:
                self.device.disable_device()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to toggle device: {e}")
            # Revert the checkbox
            self.enabled.set(not self.enabled.get())

    def set_sampling(self):
        """Set sampling period"""
        try:
            period = int(self.sampling_ms.get())

            # Validate range (10ms to 5000ms as per driver limits)
            if period < 10 or period > 5000:
                messagebox.showerror("Error", "Sampling period must be between 10 and 5000 ms")
                return

            if self.device.set_sampling_period(period):
                messagebox.showinfo("Success", f"Sampling period set to {period} ms")
                # Immediately adapt frame rate to new sampling period
                self.last_sampling_check = datetime.now() - timedelta(seconds=10)  # Force check
                self.check_and_adapt_framerate()
            else:
                messagebox.showerror("Error", "Failed to set sampling period")
        except ValueError:
            messagebox.showerror("Error", "Invalid sampling period")

    def set_threshold(self):
        """Set temperature threshold"""
        try:
            threshold = float(self.threshold_c.get())

            # Validate reasonable temperature range (-50°C to 150°C)
            if threshold < -50 or threshold > 150:
                messagebox.showerror("Error", "Threshold must be between -50°C and 150°C")
                return

            threshold_mc = int(threshold * 1000)
            if self.device.set_threshold(threshold_mc):
                messagebox.showinfo("Success", f"Threshold set to {threshold:.1f}°C")
            else:
                messagebox.showerror("Error", "Failed to set threshold")
        except ValueError:
            messagebox.showerror("Error", "Invalid threshold value")

    def set_mode(self):
        """Set simulation mode"""
        try:
            mode = self.mode.get()
            if self.device.set_mode(mode):
                messagebox.showinfo("Success", f"Mode set to {mode}")
            else:
                messagebox.showerror("Error", "Failed to set mode")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to set mode: {e}")

    def test_alert(self):
        """Test alert functionality"""
        try:
            # Set a low threshold to trigger alert quickly
            original_threshold = self.threshold_c.get()
            self.threshold_c.set("25.0")  # Low threshold
            self.set_threshold()

            messagebox.showinfo("Test Alert", "Threshold set to 25°C. Monitor for alert indication.")

            # Restore after a few seconds
            self.root.after(5000, lambda: [self.threshold_c.set(original_threshold), self.set_threshold()])

        except Exception as e:
            messagebox.showerror("Error", f"Failed to test alert: {e}")

    def update_stats(self):
        """Update device statistics"""
        try:
            stats = self.device.get_stats()
            if stats:
                self.stats_text.delete(1.0, tk.END)
                self.stats_text.insert(tk.END, "Device Statistics:\n")
                self.stats_text.insert(tk.END, "=" * 30 + "\n\n")

                for key, value in stats.items():
                    self.stats_text.insert(tk.END, f"{key.replace('_', ' ').title()}: {value}\n")

                # Add timestamp
                self.stats_text.insert(tk.END, f"\nLast Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        except Exception as e:
            self.stats_text.delete(1.0, tk.END)
            self.stats_text.insert(tk.END, f"Error getting statistics: {e}\n")

        # Auto-refresh every 5 seconds if monitoring is active
        if self.monitoring:
            self.root.after(5000, self.update_stats)

    def on_closing(self):
        """Handle application closing"""
        if self.monitoring:
            self.stop_monitoring()

        self.root.destroy()

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
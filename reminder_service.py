"""
Splash Reminders - System Tray Application
A break reminder system with tray icon for start/pause/stop/configure.
"""

import json
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from datetime import datetime, timedelta
import winsound
import sys
import os

# Third-party imports for tray icon
from PIL import Image, ImageDraw, ImageFont
import pystray
from pystray import MenuItem as Item


class SplashReminder:
    def __init__(self, config_path="config.json"):
        self.base_path = Path(__file__).parent
        self.config_path = self.base_path / config_path
        self.icon_path = self.base_path / "icon.ico"
        self.load_config()
        self.timers = []
        self.splash_lock = threading.Lock()
        self.running = False
        self.paused = False
        self.tray_icon = None
        self.stop_event = threading.Event()
        # Queue for combining overlapping reminders
        self.reminder_queue = []
        self.queue_lock = threading.Lock()
        self.queue_timer = None

    def load_config(self):
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            print(f"Config file not found: {self.config_path}")
            self.config = self.get_default_config()
            self.save_config()

    def save_config(self):
        """Save configuration to JSON file."""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

    def get_default_config(self):
        """Return default configuration."""
        return {
            "reminders": [
                {"message": "Stand Up & Stretch!", "interval_minutes": 30, "color": "#FF6B35"},
                {"message": "Drink Water - Stay Hydrated!", "interval_minutes": 20, "color": "#4ECDC4"}
            ],
            "scheduled": [
                {"message": "Lunch Time!", "time": "12:00:00", "color": "#E74C3C"}
            ],
            "display_seconds": 8,
            "font_size": 72,
            "play_sound": True
        }

    def create_icon(self):
        """Create a water drop icon programmatically."""
        size = 64
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw water drop shape
        # Main drop body (circle at bottom)
        center_x, center_y = size // 2, size // 2 + 8
        radius = 20
        drop_color = '#4ECDC4'  # Teal color

        # Draw the teardrop shape using polygon
        points = []
        # Top point of drop
        points.append((size // 2, 8))
        # Right curve
        for i in range(0, 180, 10):
            import math
            angle = math.radians(i - 90)
            x = center_x + int(radius * 1.2 * math.cos(angle))
            y = center_y + int(radius * math.sin(angle))
            points.append((x, y))

        draw.polygon(points, fill=drop_color)

        # Add a highlight
        highlight_points = [(size // 2 - 5, 20), (size // 2 - 10, 30), (size // 2 - 6, 35)]
        draw.polygon(highlight_points, fill='#7EEEE4')

        # Save icon
        img.save(self.icon_path, format='ICO')
        return img

    def get_icon_image(self):
        """Get or create the tray icon image."""
        if not self.icon_path.exists():
            return self.create_icon()
        return Image.open(self.icon_path)

    def queue_reminder(self, message, color):
        """Add reminder to queue and process after a short delay to combine overlapping ones."""
        with self.queue_lock:
            self.reminder_queue.append({"message": message, "color": color})

            # Cancel existing timer if any
            if self.queue_timer:
                self.queue_timer.cancel()

            # Start new timer - wait 2 seconds to collect any other reminders
            self.queue_timer = threading.Timer(2.0, self.process_queue)
            self.queue_timer.start()

    def process_queue(self):
        """Process all queued reminders and show them combined."""
        with self.queue_lock:
            if not self.reminder_queue:
                return

            reminders = self.reminder_queue.copy()
            self.reminder_queue.clear()
            self.queue_timer = None

        if not self.running:
            return

        # Combine messages
        if len(reminders) == 1:
            self.show_splash_internal(reminders[0]["message"], reminders[0]["color"])
        else:
            # Multiple reminders - combine them
            combined_message = "\n\n".join([r["message"] for r in reminders])
            # Use the first reminder's color as primary
            primary_color = reminders[0]["color"]
            all_colors = [r["color"] for r in reminders]
            self.show_combined_splash(combined_message, all_colors)

    def show_combined_splash(self, message, colors):
        """Show a splash with multiple reminders combined."""
        if self.paused:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Paused - showing mini popup (combined)")
            self.show_mini_popup(message.replace("\n\n", " | "), colors[0])
            return

        with self.splash_lock:
            if self.config.get("play_sound", True):
                try:
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except:
                    pass

            bg_color = "#1a1a1a"
            text_muted = "#888888"

            splash = tk.Tk()
            splash.attributes('-fullscreen', True)
            splash.attributes('-topmost', True)
            splash.configure(bg=bg_color)
            splash.overrideredirect(True)

            frame = tk.Frame(splash, bg=bg_color)
            frame.place(relx=0.5, rely=0.5, anchor='center')

            # Multiple colored accent bars
            bar_frame = tk.Frame(frame, bg=bg_color)
            bar_frame.pack(pady=(0, 30))
            for color in colors:
                bar = tk.Frame(bar_frame, bg=color, height=6, width=60)
                bar.pack(side='left', padx=2)

            # Show each message with its color
            messages = message.split("\n\n")
            font_size = min(self.config.get("font_size", 72), 56)  # Smaller for multiple

            for i, msg in enumerate(messages):
                color = colors[i] if i < len(colors) else colors[0]
                label = tk.Label(
                    frame,
                    text=msg,
                    font=("Arial", font_size, "bold"),
                    fg=color,
                    bg=bg_color,
                    wraplength=splash.winfo_screenwidth() - 200
                )
                label.pack(pady=10)

            time_label = tk.Label(
                frame,
                text=datetime.now().strftime("%H:%M"),
                font=("Arial", 36),
                fg="#ffffff",
                bg=bg_color
            )
            time_label.pack(pady=10)

            dismiss_label = tk.Label(
                frame,
                text="Click anywhere or press any key to dismiss",
                font=("Arial", 18),
                fg=text_muted,
                bg=bg_color
            )
            dismiss_label.pack(pady=40)

            display_seconds = self.config.get("display_seconds", 8)
            countdown_var = tk.StringVar(value=f"Auto-closing in {display_seconds}s")
            countdown_label = tk.Label(
                frame,
                textvariable=countdown_var,
                font=("Arial", 14),
                fg=text_muted,
                bg=bg_color
            )
            countdown_label.pack(pady=10)

            def close_splash(event=None):
                try:
                    splash.destroy()
                except:
                    pass

            splash.bind('<Button-1>', close_splash)
            splash.bind('<Key>', close_splash)
            splash.focus_force()

            def countdown(remaining):
                if remaining > 0:
                    countdown_var.set(f"Auto-closing in {remaining}s")
                    splash.after(1000, countdown, remaining - 1)
                else:
                    close_splash()

            splash.after(1000, countdown, display_seconds - 1)
            splash.after(display_seconds * 1000, close_splash)
            splash.mainloop()

    def show_mini_popup(self, message, color):
        """Show a small popup window (works even in Do Not Disturb mode)."""
        # Play sound
        if self.config.get("play_sound", True):
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except:
                pass

        # Create small popup window
        popup = tk.Tk()
        popup.title("Reminder")
        popup.attributes('-topmost', True)
        popup.overrideredirect(True)

        # Dark theme
        bg_color = "#1a1a1a"

        # Size and position (bottom-right corner)
        width, height = 400, 120
        screen_w = popup.winfo_screenwidth()
        screen_h = popup.winfo_screenheight()
        x = screen_w - width - 20
        y = screen_h - height - 60
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.configure(bg=bg_color)

        # Accent bar on left
        accent = tk.Frame(popup, bg=color, width=6)
        accent.pack(side='left', fill='y')

        # Content frame
        content = tk.Frame(popup, bg=bg_color)
        content.pack(side='left', fill='both', expand=True, padx=15, pady=15)

        # Message
        label = tk.Label(
            content,
            text=message,
            font=("Arial", 16, "bold"),
            fg=color,
            bg=bg_color,
            anchor='w',
            wraplength=350
        )
        label.pack(anchor='w')

        # Time
        time_label = tk.Label(
            content,
            text=datetime.now().strftime("%H:%M"),
            font=("Arial", 11),
            fg="#888888",
            bg=bg_color,
            anchor='w'
        )
        time_label.pack(anchor='w', pady=(5, 0))

        # Click to dismiss
        def close(event=None):
            try:
                popup.destroy()
            except:
                pass

        popup.bind('<Button-1>', close)
        label.bind('<Button-1>', close)
        popup.bind('<Key>', close)

        # Auto-close after 5 seconds
        popup.after(5000, close)
        popup.mainloop()

    def show_splash(self, message, color):
        """Queue a reminder to be shown (combines with others if they arrive close together)."""
        if not self.running:
            return
        self.queue_reminder(message, color)

    def show_splash_internal(self, message, color):
        """Show a full-screen splash reminder (or mini popup if paused)."""
        if not self.running:
            return

        # If paused, show small popup instead of full splash
        if self.paused:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Paused - showing mini popup")
            self.show_mini_popup(message, color)
            return

        with self.splash_lock:
            # Play sound if enabled
            if self.config.get("play_sound", True):
                try:
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except:
                    pass

            # Dark theme colors
            bg_color = "#1a1a1a"
            text_muted = "#888888"

            # Create splash window
            splash = tk.Tk()
            splash.attributes('-fullscreen', True)
            splash.attributes('-topmost', True)
            splash.configure(bg=bg_color)
            splash.overrideredirect(True)

            # Center frame
            frame = tk.Frame(splash, bg=bg_color)
            frame.place(relx=0.5, rely=0.5, anchor='center')

            # Accent bar above message
            accent_bar = tk.Frame(frame, bg=color, height=6, width=300)
            accent_bar.pack(pady=(0, 30))

            # Main message (accent color text on dark background)
            font_size = self.config.get("font_size", 72)
            label = tk.Label(
                frame,
                text=message,
                font=("Arial", font_size, "bold"),
                fg=color,
                bg=bg_color,
                wraplength=splash.winfo_screenwidth() - 200
            )
            label.pack(pady=20)

            # Time display
            time_label = tk.Label(
                frame,
                text=datetime.now().strftime("%H:%M"),
                font=("Arial", 36),
                fg="#ffffff",
                bg=bg_color
            )
            time_label.pack(pady=10)

            # Dismiss instruction
            dismiss_label = tk.Label(
                frame,
                text="Click anywhere or press any key to dismiss",
                font=("Arial", 18),
                fg=text_muted,
                bg=bg_color
            )
            dismiss_label.pack(pady=40)

            # Countdown label
            display_seconds = self.config.get("display_seconds", 8)
            countdown_var = tk.StringVar(value=f"Auto-closing in {display_seconds}s")
            countdown_label = tk.Label(
                frame,
                textvariable=countdown_var,
                font=("Arial", 14),
                fg=text_muted,
                bg=bg_color
            )
            countdown_label.pack(pady=10)

            # Close handlers
            def close_splash(event=None):
                try:
                    splash.destroy()
                except:
                    pass

            splash.bind('<Button-1>', close_splash)
            splash.bind('<Key>', close_splash)
            splash.focus_force()

            # Countdown timer
            def countdown(remaining):
                if remaining > 0:
                    countdown_var.set(f"Auto-closing in {remaining}s")
                    splash.after(1000, countdown, remaining - 1)
                else:
                    close_splash()

            splash.after(1000, countdown, display_seconds - 1)
            splash.after(display_seconds * 1000, close_splash)

            # Run the splash window
            splash.mainloop()

    def schedule_interval_reminder(self, reminder):
        """Schedule a recurring interval-based reminder."""
        message = reminder["message"]
        interval = reminder["interval_minutes"] * 60
        color = reminder.get("color", "#3498DB")

        def reminder_loop():
            while not self.stop_event.is_set():
                # Wait for interval, checking stop_event periodically
                for _ in range(interval):
                    if self.stop_event.is_set():
                        return
                    time.sleep(1)

                if self.running and not self.stop_event.is_set():
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Reminder: {message}")
                    self.show_splash(message, color)

        thread = threading.Thread(target=reminder_loop, daemon=True)
        thread.start()
        self.timers.append(thread)

    def schedule_timed_reminder(self, reminder):
        """Schedule a reminder at a specific time each day."""
        message = reminder["message"]
        target_time = reminder["time"]
        color = reminder.get("color", "#3498DB")

        def get_seconds_until_target():
            now = datetime.now()
            time_parts = target_time.split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            second = int(time_parts[2]) if len(time_parts) > 2 else 0
            target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return (target - now).total_seconds()

        def reminder_loop():
            while not self.stop_event.is_set():
                wait_seconds = get_seconds_until_target()

                # Wait, checking stop_event periodically
                waited = 0
                while waited < wait_seconds and not self.stop_event.is_set():
                    time.sleep(min(1, wait_seconds - waited))
                    waited += 1

                if self.running and not self.stop_event.is_set():
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scheduled: {message}")
                    self.show_splash(message, color)
                    time.sleep(1)

        thread = threading.Thread(target=reminder_loop, daemon=True)
        thread.start()
        self.timers.append(thread)

    def start_reminders(self):
        """Start all scheduled reminders."""
        if self.running:
            return

        self.running = True
        self.stop_event.clear()

        print("Starting reminders...")
        for reminder in self.config.get("reminders", []):
            self.schedule_interval_reminder(reminder)
            print(f"  [Interval] {reminder['message']} every {reminder['interval_minutes']} min")

        for reminder in self.config.get("scheduled", []):
            self.schedule_timed_reminder(reminder)
            print(f"  [Scheduled] {reminder['message']} at {reminder['time']}")

        self.update_tray_menu()

    def stop_reminders(self):
        """Stop all reminders."""
        self.running = False
        self.stop_event.set()
        self.timers.clear()
        print("Reminders stopped.")
        self.update_tray_menu()

    def toggle_pause(self):
        """Toggle pause state."""
        self.paused = not self.paused
        status = "paused (mini popups)" if self.paused else "active (full splash)"
        print(f"Reminders {status}")
        self.update_tray_menu()

    def open_config(self):
        """Open config file in default editor."""
        os.startfile(str(self.config_path))

    def reload_config(self):
        """Reload configuration and restart reminders."""
        self.stop_reminders()
        self.load_config()
        self.start_reminders()
        print("Configuration reloaded.")

    def quit_app(self):
        """Quit the application."""
        self.stop_reminders()
        if self.tray_icon:
            self.tray_icon.stop()

    def get_status_text(self):
        """Get current status text for menu."""
        if not self.running:
            return "Status: Stopped"
        elif self.paused:
            return "Status: Paused (Mini Popups)"
        else:
            return "Status: Active"

    def update_tray_menu(self):
        """Update the tray icon menu."""
        if self.tray_icon:
            self.tray_icon.menu = self.create_menu()

    def create_menu(self):
        """Create the system tray menu."""
        return pystray.Menu(
            Item(self.get_status_text(), lambda: None, enabled=False),
            Item('─────────────', lambda: None, enabled=False),
            Item(
                'Start Reminders',
                lambda: self.start_reminders(),
                visible=not self.running
            ),
            Item(
                'Stop Reminders',
                lambda: self.stop_reminders(),
                visible=self.running
            ),
            Item(
                'Pause (Mini Popups)' if not self.paused else 'Resume (Full Splash)',
                lambda: self.toggle_pause(),
                visible=self.running
            ),
            Item('─────────────', lambda: None, enabled=False),
            Item('Edit Schedule...', lambda: self.open_config()),
            Item('Reload Config', lambda: self.reload_config()),
            Item('─────────────', lambda: None, enabled=False),
            Item('Quit', lambda: self.quit_app())
        )

    def run(self):
        """Run the system tray application."""
        print("=" * 50)
        print("  Splash Reminders - System Tray App")
        print("=" * 50)
        print(f"Config: {self.config_path}")
        print("-" * 50)

        # Create icon
        icon_image = self.get_icon_image()

        # Create system tray icon
        self.tray_icon = pystray.Icon(
            "SplashReminders",
            icon_image,
            "Splash Reminders",
            menu=self.create_menu()
        )

        # Auto-start reminders
        self.start_reminders()

        print("-" * 50)
        print("Running in system tray. Right-click icon for menu.")
        print("=" * 50)

        # Run the tray icon (blocks)
        self.tray_icon.run()


if __name__ == "__main__":
    app = SplashReminder()
    app.run()

"""
Splash Reminders - System Tray Application
A break reminder system with tray icon for start/pause/stop/configure.
"""

import json
import threading
import time
import tkinter as tk
from pathlib import Path
from datetime import datetime, timedelta
import winsound
import sys
import os
import queue
import heapq

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
        self.splash_lock = threading.Lock()
        self.running = False
        self.paused = False
        self.tray_icon = None
        self.stop_event = threading.Event()
        # Single scheduler thread with heap-based priority queue
        self.scheduler_heap = []  # (next_fire_time, reminder_id, reminder_data)
        self.scheduler_lock = threading.Lock()
        self.scheduler_thread = None
        self.reminder_counter = 0  # Unique ID for heap tie-breaking
        # Queue for combining overlapping reminders
        self.pending_reminders = []
        self.pending_lock = threading.Lock()
        self.pending_timer = None
        # Thread-safe queue for displaying splashes on main thread
        self.display_queue = queue.Queue()
        # Command queue for menu actions (must run on main thread)
        self.command_queue = queue.Queue()

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

    def queue_reminder(self, message, color, reminder_type="splash"):
        """Add reminder to pending list and process after a short delay to combine overlapping ones."""
        with self.pending_lock:
            self.pending_reminders.append({"message": message, "color": color, "type": reminder_type})

            # Cancel existing timer if any
            if self.pending_timer:
                self.pending_timer.cancel()

            # Start new timer - wait 2 seconds to collect any other reminders
            self.pending_timer = threading.Timer(2.0, self.process_pending)
            self.pending_timer.start()

    def process_pending(self):
        """Process all pending reminders and queue them for display on main thread."""
        with self.pending_lock:
            if not self.pending_reminders:
                return

            reminders = self.pending_reminders.copy()
            self.pending_reminders.clear()
            self.pending_timer = None

        if not self.running:
            return

        # Queue for main thread to display
        # Combine messages
        if len(reminders) == 1:
            r = reminders[0]
            # Check if forced popup type or paused
            if r.get("type") == "popup":
                self.display_queue.put(("popup", r["message"], r["color"]))
            else:
                self.display_queue.put(("splash", r["message"], r["color"]))
        else:
            # Multiple reminders - combine them
            # If any is popup type, show as popup
            has_popup = any(r.get("type") == "popup" for r in reminders)
            combined_message = "\n\n".join([r["message"] for r in reminders])
            all_colors = [r["color"] for r in reminders]

            if has_popup or self.paused:
                self.display_queue.put(("popup", combined_message.replace("\n\n", " | "), all_colors[0]))
            else:
                self.display_queue.put(("combined", combined_message, all_colors))

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

    def show_splash(self, message, color, reminder_type="splash"):
        """Queue a reminder to be shown (combines with others if they arrive close together)."""
        if not self.running:
            return
        self.queue_reminder(message, color, reminder_type)

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

    def add_reminder_to_heap(self, fire_time, reminder_data):
        """Add a reminder to the scheduler heap."""
        with self.scheduler_lock:
            self.reminder_counter += 1
            heapq.heappush(self.scheduler_heap, (fire_time, self.reminder_counter, reminder_data))

    def get_next_fire_time_interval(self, interval_seconds):
        """Calculate next fire time for an interval reminder."""
        return time.time() + interval_seconds

    def get_next_fire_time_scheduled(self, target_time_str):
        """Calculate next fire time for a scheduled reminder."""
        now = datetime.now()
        time_parts = target_time_str.split(":")
        hour = int(time_parts[0])
        minute = int(time_parts[1])
        second = int(time_parts[2]) if len(time_parts) > 2 else 0
        target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target.timestamp()

    def scheduler_loop(self):
        """Single scheduler thread that processes all reminders."""
        while not self.stop_event.is_set():
            now = time.time()

            with self.scheduler_lock:
                if not self.scheduler_heap:
                    # No reminders, sleep briefly and check again
                    pass
                else:
                    # Peek at next reminder
                    next_time, _, _ = self.scheduler_heap[0]

                    if next_time <= now:
                        # Fire this reminder
                        _, _, reminder_data = heapq.heappop(self.scheduler_heap)

                        if self.running:
                            msg = reminder_data["message"]
                            color = reminder_data["color"]
                            rtype = reminder_data.get("type", "splash")
                            kind = reminder_data.get("kind", "interval")

                            print(f"[{datetime.now().strftime('%H:%M:%S')}] {kind.title()}: {msg[:30]}...")
                            self.show_splash(msg, color, rtype)

                        # Reschedule
                        if reminder_data.get("kind") == "interval":
                            interval = reminder_data["interval"]
                            new_time = time.time() + interval
                            self.reminder_counter += 1
                            heapq.heappush(self.scheduler_heap, (new_time, self.reminder_counter, reminder_data))
                        elif reminder_data.get("kind") == "scheduled":
                            new_time = self.get_next_fire_time_scheduled(reminder_data["target_time"])
                            self.reminder_counter += 1
                            heapq.heappush(self.scheduler_heap, (new_time, self.reminder_counter, reminder_data))

                        continue  # Check for more due reminders

            # Sleep until next reminder or max 1 second (to check stop_event)
            with self.scheduler_lock:
                if self.scheduler_heap:
                    next_time, _, _ = self.scheduler_heap[0]
                    sleep_time = min(1.0, max(0.01, next_time - time.time()))
                else:
                    sleep_time = 1.0

            self.stop_event.wait(sleep_time)

    def start_reminders(self):
        """Start all scheduled reminders."""
        if self.running:
            return

        self.running = True
        self.stop_event.clear()

        # Clear any old reminders from heap
        with self.scheduler_lock:
            self.scheduler_heap.clear()
            self.reminder_counter = 0

        print("Starting reminders...")

        # Add interval reminders to heap
        for reminder in self.config.get("reminders", []):
            if "interval_seconds" in reminder:
                interval = reminder["interval_seconds"]
                print(f"  [Interval] {reminder['message']} every {reminder['interval_seconds']} sec")
            else:
                interval = reminder["interval_minutes"] * 60
                print(f"  [Interval] {reminder['message']} every {reminder['interval_minutes']} min")

            reminder_data = {
                "message": reminder["message"],
                "color": reminder.get("color", "#3498DB"),
                "type": reminder.get("type", "splash"),
                "kind": "interval",
                "interval": interval
            }
            fire_time = self.get_next_fire_time_interval(interval)
            self.add_reminder_to_heap(fire_time, reminder_data)

        # Add scheduled reminders to heap
        for reminder in self.config.get("scheduled", []):
            print(f"  [Scheduled] {reminder['message']} at {reminder['time']}")
            reminder_data = {
                "message": reminder["message"],
                "color": reminder.get("color", "#3498DB"),
                "type": reminder.get("type", "splash"),
                "kind": "scheduled",
                "target_time": reminder["time"]
            }
            fire_time = self.get_next_fire_time_scheduled(reminder["time"])
            self.add_reminder_to_heap(fire_time, reminder_data)

        # Add motivation messages to heap
        for motivation in self.config.get("motivation", []):
            print(f"  [Motivation] {motivation['time']}")
            reminder_data = {
                "message": motivation["message"],
                "color": "#FFD700",
                "type": "splash",
                "kind": "scheduled",
                "target_time": motivation["time"]
            }
            fire_time = self.get_next_fire_time_scheduled(motivation["time"])
            self.add_reminder_to_heap(fire_time, reminder_data)

        # Start single scheduler thread
        self.scheduler_thread = threading.Thread(target=self.scheduler_loop, daemon=True)
        self.scheduler_thread.start()

        print(f"  Total: {len(self.scheduler_heap)} reminders using 1 thread")
        self.update_tray_menu()

    def stop_reminders(self):
        """Stop all reminders."""
        self.running = False
        self.stop_event.set()

        # Cancel any pending timer
        if self.pending_timer:
            self.pending_timer.cancel()
            self.pending_timer = None

        # Clear pending reminders
        with self.pending_lock:
            self.pending_reminders.clear()

        # Wait for scheduler thread to finish
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=2.0)
            self.scheduler_thread = None

        # Clear the heap
        with self.scheduler_lock:
            self.scheduler_heap.clear()

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
        # Small delay to ensure threads are fully stopped
        time.sleep(0.5)
        self.load_config()
        self.start_reminders()
        print("Configuration reloaded.")

    def quit_app(self):
        """Quit the application."""
        self.stop_reminders()
        self.stop_event.set()  # Signal main loop to exit
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

    def queue_command(self, cmd):
        """Queue a command to run on the main thread."""
        self.command_queue.put(cmd)

    def create_menu(self):
        """Create the system tray menu."""
        return pystray.Menu(
            Item(self.get_status_text(), lambda: None, enabled=False),
            Item('─────────────', lambda: None, enabled=False),
            Item(
                'Start Reminders',
                lambda: self.queue_command('start'),
                visible=not self.running
            ),
            Item(
                'Stop Reminders',
                lambda: self.queue_command('stop'),
                visible=self.running
            ),
            Item(
                'Pause (Mini Popups)' if not self.paused else 'Resume (Full Splash)',
                lambda: self.queue_command('toggle_pause'),
                visible=self.running
            ),
            Item('─────────────', lambda: None, enabled=False),
            Item('Edit Schedule...', lambda: self.open_config()),
            Item('Reload Config', lambda: self.queue_command('reload')),
            Item('─────────────', lambda: None, enabled=False),
            Item('Quit', lambda: self.queue_command('quit'))
        )

    def show_startup_splash(self):
        """Show a motivational startup splash."""
        import random

        try:
            # Check if startup message is enabled
            startup_config = self.config.get("startup_message", {"enabled": True})
            if not startup_config.get("enabled", True):
                return
        except Exception as e:
            print(f"Error checking startup config: {e}")
            return

        try:
            # Get messages from motivation config or use defaults
            motivation_list = self.config.get("motivation", [])
            if motivation_list:
                messages = [m["message"] for m in motivation_list]
            else:
                messages = [
                    "Rise and grind, you magnificent bastard!\nToday is YOUR day to crush it.",
                    "Welcome back, legend.\nTime to make sh*t happen.",
                    "Another day, another chance\nto be absolutely unstoppable.",
                    "Coffee? Check. Attitude? Fierce.\nLet's f*cking GO.",
                    "They said you couldn't.\nProve those bastards wrong."
                ]

            message = random.choice(messages)
            accent_color = startup_config.get("color", "#FFD700")

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

                # Crown/star accent
                accent_bar = tk.Frame(frame, bg=accent_color, height=6, width=400)
                accent_bar.pack(pady=(0, 30))

                # Greeting
                greeting = tk.Label(
                    frame,
                    text="GOOD MORNING, CHAMPION",
                    font=("Arial", 28, "bold"),
                    fg=text_muted,
                    bg=bg_color
                )
                greeting.pack(pady=(0, 20))

                # Main message
                label = tk.Label(
                    frame,
                    text=message,
                    font=("Arial", 52, "bold"),
                    fg=accent_color,
                    bg=bg_color,
                    justify='center'
                )
                label.pack(pady=20)

                # Time display
                time_label = tk.Label(
                    frame,
                    text=datetime.now().strftime("%A, %B %d • %H:%M"),
                    font=("Arial", 24),
                    fg="#ffffff",
                    bg=bg_color
                )
                time_label.pack(pady=20)

                # Dismiss instruction
                dismiss_label = tk.Label(
                    frame,
                    text="Click anywhere to start your day",
                    font=("Arial", 16),
                    fg=text_muted,
                    bg=bg_color
                )
                dismiss_label.pack(pady=40)

                def close_splash(event=None):
                    try:
                        splash.destroy()
                    except:
                        pass

                splash.bind('<Button-1>', close_splash)
                splash.bind('<Key>', close_splash)
                splash.focus_force()

                # Auto-close after 15 seconds
                splash.after(15000, close_splash)
                splash.mainloop()
        except Exception as e:
            print(f"Error showing startup splash: {e}")

    def process_display_queue(self):
        """Process pending display requests from the main thread."""
        try:
            while True:
                try:
                    item = self.display_queue.get_nowait()
                    display_type, message, color = item

                    if display_type == "popup":
                        self.show_mini_popup(message, color)
                    elif display_type == "splash":
                        self.show_splash_internal(message, color)
                    elif display_type == "combined":
                        self.show_combined_splash(message, color)
                except queue.Empty:
                    break
        except Exception as e:
            print(f"Error processing display queue: {e}")

    def process_command_queue(self):
        """Process pending menu commands from the main thread."""
        try:
            while True:
                try:
                    cmd = self.command_queue.get_nowait()
                    if cmd == 'start':
                        self.start_reminders()
                    elif cmd == 'stop':
                        self.stop_reminders()
                    elif cmd == 'toggle_pause':
                        self.toggle_pause()
                    elif cmd == 'reload':
                        self.reload_config()
                    elif cmd == 'quit':
                        self.quit_app()
                        return False  # Signal to exit main loop
                except queue.Empty:
                    break
        except Exception as e:
            print(f"Error processing command queue: {e}")
        return True

    def run(self):
        """Run the system tray application."""
        print("=" * 50)
        print("  Splash Reminders - System Tray App")
        print("=" * 50)
        print(f"Config: {self.config_path}")
        print("-" * 50)

        # Show motivational startup splash
        self.show_startup_splash()

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

        # Run tray icon in background thread
        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()

        # Main thread handles display and command queues (tkinter must run on main thread)
        try:
            while tray_thread.is_alive() and not self.stop_event.is_set():
                self.process_display_queue()
                if not self.process_command_queue():
                    break  # quit command received
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.quit_app()


if __name__ == "__main__":
    app = SplashReminder()
    app.run()

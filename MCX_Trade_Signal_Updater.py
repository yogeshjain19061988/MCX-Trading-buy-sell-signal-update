import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import threading
import time
from datetime import datetime, timedelta, date
import webbrowser
import pandas as pd
import sqlite3
import xlwings as xw
import csv
from datetime import datetime as dt
current_datetime = dt.now()

try:
    from kiteconnect import KiteConnect
except ImportError:
    print("Please install kiteconnect: pip install kiteconnect")
    exit()

import openpyxl
import os

FILE_NAME = 'MCX_Trading_Platform_Data.xlsx'

def create_initial_file():
    """
    Function to create a new Excel file and add some initial data.
    """
    print(f"--- Creating initial file: {FILE_NAME} ---")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Future Readings"
    
    # Add headers
    sheet['A1'] = 'Date'
    sheet['B1'] = 'Time'
    sheet['C1'] = 'Value'
    
    # Save the workbook
    workbook.save(FILE_NAME)
    print(f"Created and saved {FILE_NAME}\n")

def update_existing_file(value_price):
    #new_row = [current_datetime.date(), current_datetime.time(), ]; 
 
    """
    Function to open an existing Excel file (created by another function), 
    modify a cell, and save the changes.
    """
    print(f"--- Updating file: {FILE_NAME} ---")
    if not os.path.exists(FILE_NAME):
        print(f"Error: {FILE_NAME} not found. Run create_initial_file() first.")
        return

    # Load the existing workbook
    workbook = openpyxl.load_workbook(FILE_NAME)
    sheet = workbook['Future Readings'] # Access the specific sheet by name
    
    # Add a new row of data (optional)
    next_row = sheet.max_row + 1
    sheet.cell(row=next_row, column=1, value=current_datetime.date())
    sheet.cell(row=next_row, column=2, value=current_datetime.time())
    sheet.cell(row=next_row, column=3, value=value_price)
    
    # Save the workbook (overwrites the old one)
    workbook.save(FILE_NAME)
    print(f"Updated and saved {FILE_NAME}\n")


class ZerodhaTradingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MCX Trading Platform - Entry/Exit Signals")
        self.root.geometry("1400x900")
        
        # Initialize variables
        self.kite = None
        self.is_logged_in = False
        self.api_key = ""
        self.access_token = ""
        self.live_data = {}
        self.positions = {}
        self.orders = {}
        self.profit_target = 0
        self.total_pnl = 0
        self.instruments_df = None
        
        # Live data flags
        self.live_data_running = False
        self.futures_data_running = False
        self.options_data_running = False
        
        # Month comparison
        self.month_comparison_running = False
        self.current_month_contract = None
        self.next_month_contract = None
        self.comparison_popup = None
        
        # PREVIOUS DAY CLOSING PRICES storage
        self.previous_day_close_prices = {}
        self.month_comparison_prices = {}
        
        # Daily performance tracking
        self.daily_performance_db = "daily_performance.db"
        
        # NEW: Triggered popup variables
        self.triggered_popup = None
        self.last_trigger_time = None
        self.trigger_cooldown = 60  # seconds between triggers
        self.trigger_threshold = 0.5  # percentage threshold difference
        
        # NEW: Price difference popup
        self.price_diff_popup = None
        
        # NEW: Entry/Exit popup variables
        self.entry_exit_popup = None
        self.last_entry_exit_trigger_time = None
        self.entry_exit_cooldown = 300  # 5 minutes cooldown
        self.entry_threshold = -2.0  # Less than -2 for entry
        self.exit_threshold = 2.0    # More than +2 for exit
        
        # Load credentials
        self.load_credentials()
        
        # Initialize database for daily tracking
        self.init_daily_performance_db()
        
        # Setup GUI
        self.setup_gui()
        
        # Auto login if credentials exist
        if hasattr(self, 'api_key') and hasattr(self, 'access_token') and self.api_key and self.access_token:
            self.root.after(1000, self.auto_login)

    def load_credentials(self):
        """Load API credentials from file"""
        try:
            if os.path.exists('zerodha_credentials.json'):
                with open('zerodha_credentials.json', 'r') as f:
                    creds = json.load(f)
                    self.api_key = creds.get('api_key', '')
                    self.access_token = creds.get('access_token', '')
                    self.log_message("Credentials loaded successfully")
        except Exception as e:
            self.log_message(f"Error loading credentials: {e}")

    def save_credentials(self):
        """Save API credentials to file"""
        try:
            creds = {
                'api_key': self.api_key,
                'access_token': self.access_token
            }
            with open('zerodha_credentials.json', 'w') as f:
                json.dump(creds, f, indent=4)
            self.log_message("Credentials saved successfully")
        except Exception as e:
            self.log_message(f"Error saving credentials: {e}")

    def setup_gui(self):
        """Setup the main GUI interface"""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Login Tab
        self.setup_login_tab(notebook)
        
        # Market Data Tab
        self.setup_market_data_tab(notebook)
        
        # Month Comparison Tab (Updated for Previous Day Close)
        self.setup_month_comparison_tab(notebook)
        
        # Log message area
        self.log_frame = ttk.LabelFrame(self.root, text="Log Messages")
        self.log_frame.pack(fill='x', padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(self.log_frame, height=8)
        self.log_text.pack(fill='both', expand=True, padx=5, pady=5)

    def setup_login_tab(self, notebook):
        """Setup login tab"""
        login_frame = ttk.Frame(notebook)
        notebook.add(login_frame, text="Login")
        
        # API Key
        ttk.Label(login_frame, text="API Key:").grid(row=0, column=0, padx=10, pady=10, sticky='w')
        self.api_key_entry = ttk.Entry(login_frame, width=40)
        self.api_key_entry.grid(row=0, column=1, padx=10, pady=10)
        if hasattr(self, 'api_key'):
            self.api_key_entry.insert(0, self.api_key)
        
        # API Secret
        ttk.Label(login_frame, text="API Secret:").grid(row=1, column=0, padx=10, pady=10, sticky='w')
        self.api_secret_entry = ttk.Entry(login_frame, width=40, show='*')
        self.api_secret_entry.grid(row=1, column=1, padx=10, pady=10)
        
        # Request Token
        ttk.Label(login_frame, text="Request Token:").grid(row=2, column=0, padx=10, pady=10, sticky='w')
        self.request_token_entry = ttk.Entry(login_frame, width=40)
        self.request_token_entry.grid(row=2, column=1, padx=10, pady=10)
        
        # Buttons
        ttk.Button(login_frame, text="Generate Login URL", 
                  command=self.generate_login_url).grid(row=3, column=0, padx=10, pady=10)
        ttk.Button(login_frame, text="Login", 
                  command=self.manual_login).grid(row=3, column=1, padx=10, pady=10)
        ttk.Button(login_frame, text="Auto Login", 
                  command=self.auto_login).grid(row=3, column=2, padx=10, pady=10)
        
        # Status
        self.login_status = ttk.Label(login_frame, text="Not Logged In", foreground='red')
        self.login_status.grid(row=4, column=0, columnspan=3, padx=10, pady=10)
        
        # Instructions
        instructions = """
        Instructions:
        1. Enter your API Key and Secret (get from Zerodha developer console)
        2. Click 'Generate Login URL' and login to Zerodha
        3. After login, copy the request token from URL and paste above
        4. Click 'Login' to authenticate
        5. Use 'Auto Login' for future sessions
        """
        ttk.Label(login_frame, text=instructions, justify='left').grid(row=5, column=0, columnspan=3, padx=10, pady=10)

    def setup_market_data_tab(self, notebook):
        """Setup market data tab"""
        market_frame = ttk.Frame(notebook)
        notebook.add(market_frame, text="Market Data")
        
        # Simple market data display
        self.market_data_text = scrolledtext.ScrolledText(market_frame, height=30)
        self.market_data_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        ttk.Button(market_frame, text="Test Connection", 
                  command=self.test_connection).pack(pady=10)

    def setup_month_comparison_tab(self, notebook):
        """Setup month comparison tab using PREVIOUS DAY CLOSING prices"""
        month_frame = ttk.Frame(notebook)
        notebook.add(month_frame, text="📅 Month Comparison (Prev Day Close)")
        
        # Main container
        main_container = ttk.Frame(month_frame)
        main_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Left panel - Configuration
        left_panel = ttk.Frame(main_container)
        left_panel.pack(side='left', fill='y', padx=(0, 10))
        
        # Right panel - Comparison display
        right_panel = ttk.Frame(main_container)
        right_panel.pack(side='right', fill='both', expand=True)
        
        # Configuration Frame
        config_frame = ttk.LabelFrame(left_panel, text="Month Comparison Configuration")
        config_frame.pack(fill='x', pady=(0, 10))
        
        # Commodity selection
        ttk.Label(config_frame, text="Commodity:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.month_commodity = ttk.Combobox(config_frame, values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC"])
        self.month_commodity.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.month_commodity.set("GOLD")
        
        # Trigger settings frame
        trigger_frame = ttk.LabelFrame(left_panel, text="Trigger Settings")
        trigger_frame.pack(fill='x', pady=5)
        
        # Trigger threshold
        ttk.Label(trigger_frame, text="Trigger Threshold (%):").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.trigger_threshold_var = tk.StringVar(value="0.5")
        self.trigger_threshold_entry = ttk.Entry(trigger_frame, textvariable=self.trigger_threshold_var, width=10)
        self.trigger_threshold_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(trigger_frame, text="% difference").grid(row=0, column=2, padx=5, pady=5)
        
        # Cooldown period
        ttk.Label(trigger_frame, text="Cooldown (sec):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.cooldown_var = tk.StringVar(value="60")
        self.cooldown_entry = ttk.Entry(trigger_frame, textvariable=self.cooldown_var, width=10)
        self.cooldown_entry.grid(row=1, column=1, padx=5, pady=5)
        
        # Test trigger button
        ttk.Button(trigger_frame, text="Test Trigger Popup", 
                  command=self.test_triggered_popup).grid(row=2, column=0, columnspan=3, pady=10)
        
        # Load contracts button
        ttk.Button(config_frame, text="Load Current & Next Month", 
                  command=self.load_month_contracts).grid(row=1, column=0, columnspan=2, pady=10)
        
        # PREVIOUS DAY CLOSE settings
        time_frame = ttk.LabelFrame(left_panel, text="Previous Day Close Settings")
        time_frame.pack(fill='x', pady=5)
        
        ttk.Label(time_frame, text="Using Previous Trading Day Close:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        
        # Fetch previous day close button
        ttk.Button(time_frame, text="Fetch Previous Day Close", 
                  command=self.fetch_previous_day_closes).grid(row=1, column=0, columnspan=2, pady=5)
        
        ttk.Label(time_frame, text="Manual Previous Close:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        ttk.Button(time_frame, text="Set Manually", 
                  command=self.set_manual_previous_close).grid(row=2, column=1, padx=5, pady=5)
        
        # NEW: Entry/Exit Settings Frame
        entry_exit_frame = ttk.LabelFrame(left_panel, text="Entry/Exit Settings")
        entry_exit_frame.pack(fill='x', pady=5)
        
        # Entry threshold (less than -2)
        ttk.Label(entry_exit_frame, text="Entry Threshold (₹):").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.entry_threshold_var = tk.StringVar(value="-2.0")
        self.entry_threshold_entry = ttk.Entry(entry_exit_frame, textvariable=self.entry_threshold_var, width=10)
        self.entry_threshold_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(entry_exit_frame, text="Less than").grid(row=0, column=2, padx=5, pady=5)
        
        # Exit threshold (more than +2)
        ttk.Label(entry_exit_frame, text="Exit Threshold (₹):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.exit_threshold_var = tk.StringVar(value="2.0")
        self.exit_threshold_entry = ttk.Entry(entry_exit_frame, textvariable=self.exit_threshold_var, width=10)
        self.exit_threshold_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Label(entry_exit_frame, text="More than").grid(row=1, column=2, padx=5, pady=5)
        
        # Entry/Exit cooldown
        ttk.Label(entry_exit_frame, text="Cooldown (min):").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.entry_exit_cooldown_var = tk.StringVar(value="5")
        self.entry_exit_cooldown_entry = ttk.Entry(entry_exit_frame, textvariable=self.entry_exit_cooldown_var, width=10)
        self.entry_exit_cooldown_entry.grid(row=2, column=1, padx=5, pady=5)
        ttk.Label(entry_exit_frame, text="minutes").grid(row=2, column=2, padx=5, pady=5)
        
        # Test Entry/Exit button
        ttk.Button(entry_exit_frame, text="Test Entry/Exit Popup", 
                  command=self.test_entry_exit_popup).grid(row=3, column=0, columnspan=3, pady=10)
        
        # Control buttons
        control_frame = ttk.Frame(left_panel)
        control_frame.pack(fill='x', pady=10)
        
        self.start_month_btn = ttk.Button(control_frame, text="Start Month Comparison", 
                                         command=self.start_month_comparison)
        self.start_month_btn.pack(side='left', padx=2)
        
        self.stop_month_btn = ttk.Button(control_frame, text="Stop Comparison", 
                                        command=self.stop_month_comparison, state='disabled')
        self.stop_month_btn.pack(side='left', padx=2)
        
        # Common popup button
        ttk.Button(control_frame, text="Show Comparison Popup", 
                  command=self.show_comparison_popup).pack(side='left', padx=2)
        
        # NEW: Price Difference Popup button
        ttk.Button(control_frame, text="Show Price Difference Popup", 
                  command=self.show_price_difference_popup).pack(side='left', padx=2)
        
        # Historical Performance Frame
        history_frame = ttk.LabelFrame(left_panel, text="Historical Performance (Last 7 Days)")
        history_frame.pack(fill='x', pady=10)
        
        self.history_text = scrolledtext.ScrolledText(history_frame, height=8, width=40)
        self.history_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.history_text.insert(tk.END, "Load contracts and start monitoring to see history")
        
        # Entry/Exit Status Frame
        entry_exit_status_frame = ttk.LabelFrame(left_panel, text="Entry/Exit Status")
        entry_exit_status_frame.pack(fill='x', pady=10)
        
        self.entry_exit_status_label = ttk.Label(entry_exit_status_frame, text="Status: Ready", 
                                                foreground='green', font=('Arial', 10))
        self.entry_exit_status_label.pack(pady=5)
        
        self.last_signal_label = ttk.Label(entry_exit_status_frame, text="Last Signal: None", 
                                          font=('Arial', 9))
        self.last_signal_label.pack(pady=2)
        
        # Comparison Display Panel
        display_frame = ttk.LabelFrame(right_panel, text="Current vs Next Month Comparison (vs Prev Day Close)")
        display_frame.pack(fill='both', expand=True)
        
        # Comparison grid
        self.month_comparison_frame = ttk.Frame(display_frame)
        self.month_comparison_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Initialize display labels
        ttk.Label(self.month_comparison_frame, text="Loading contracts...", font=('Arial', 12)).pack(pady=20)
        
        # Total changes display
        total_frame = ttk.LabelFrame(right_panel, text="Total Changes Summary")
        total_frame.pack(fill='x', pady=5, padx=5)
        
        # Create a grid for total changes
        self.total_changes_grid = ttk.Frame(total_frame)
        self.total_changes_grid.pack(fill='x', padx=10, pady=5)
        
        # Individual changes
        ttk.Label(self.total_changes_grid, text="Current Month Change:").grid(row=0, column=0, sticky='w', pady=2)
        self.total_current_change = ttk.Label(self.total_changes_grid, text="--%", font=('Arial', 10))
        self.total_current_change.grid(row=0, column=1, sticky='w', padx=10, pady=2)
        
        ttk.Label(self.total_changes_grid, text="Next Month Change:").grid(row=1, column=0, sticky='w', pady=2)
        self.total_next_change = ttk.Label(self.total_changes_grid, text="--%", font=('Arial', 10))
        self.total_next_change.grid(row=1, column=1, sticky='w', padx=10, pady=2)
        
        ttk.Label(self.total_changes_grid, text="Performance Difference:").grid(row=2, column=0, sticky='w', pady=2)
        self.total_perf_diff = ttk.Label(self.total_changes_grid, text="--%", font=('Arial', 10))
        self.total_perf_diff.grid(row=2, column=1, sticky='w', padx=10, pady=2)
        
        # TOTAL SUM of changes (NEW FEATURE)
        ttk.Label(self.total_changes_grid, text="TOTAL SUM of Changes:", 
                 font=('Arial', 11, 'bold')).grid(row=3, column=0, sticky='w', pady=5)
        self.total_sum_label = ttk.Label(self.total_changes_grid, text="--%", 
                                        font=('Arial', 12, 'bold'))
        self.total_sum_label.grid(row=3, column=1, sticky='w', padx=10, pady=5)
        
        # NEW: Price Difference in Rupees section
        price_diff_frame = ttk.LabelFrame(right_panel, text="Price Difference in Rupees")
        price_diff_frame.pack(fill='x', pady=5, padx=5)
        
        self.price_diff_grid = ttk.Frame(price_diff_frame)
        self.price_diff_grid.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(self.price_diff_grid, text="Current Month Change (₹):").grid(row=0, column=0, sticky='w', pady=2)
        self.price_diff_current = ttk.Label(self.price_diff_grid, text="₹--", font=('Arial', 10))
        self.price_diff_current.grid(row=0, column=1, sticky='w', padx=10, pady=2)
        
        ttk.Label(self.price_diff_grid, text="Next Month Change (₹):").grid(row=1, column=0, sticky='w', pady=2)
        self.price_diff_next = ttk.Label(self.price_diff_grid, text="₹--", font=('Arial', 10))
        self.price_diff_next.grid(row=1, column=1, sticky='w', padx=10, pady=2)
        
        ttk.Label(self.price_diff_grid, text="Price Difference (₹):", 
                 font=('Arial', 11, 'bold')).grid(row=2, column=0, sticky='w', pady=5)
        self.price_diff_total = ttk.Label(self.price_diff_grid, text="₹--", 
                                         font=('Arial', 12, 'bold'))
        self.price_diff_total.grid(row=2, column=1, sticky='w', padx=10, pady=5)
        
        # NEW: Entry/Exit Signal Display
        signal_frame = ttk.LabelFrame(right_panel, text="Entry/Exit Signal")
        signal_frame.pack(fill='x', pady=5, padx=5)
        
        self.signal_display = tk.Label(signal_frame, text="--", 
                                      font=('Arial', 48), bg='white')
        self.signal_display.pack(pady=10)
        
        self.signal_text = ttk.Label(signal_frame, text="No Signal", 
                                    font=('Arial', 12, 'bold'))
        self.signal_text.pack(pady=5)
        
        # Trigger status label
        self.trigger_status_label = ttk.Label(right_panel, text="Trigger Status: Ready", foreground='green')
        self.trigger_status_label.pack(pady=2)
        
        # Status label
        self.month_status_label = ttk.Label(right_panel, text="Status: Not Monitoring", foreground='red')
        self.month_status_label.pack(pady=2)
        
        # Comparison result label
        self.month_result_label = ttk.Label(right_panel, text="Comparison: --", font=('Arial', 12, 'bold'))
        self.month_result_label.pack(pady=5)

    def test_entry_exit_popup(self):
        """Test the entry/exit popup display"""
        if not hasattr(self, 'current_month_contract') or not hasattr(self, 'next_month_contract'):
            messagebox.showerror("Error", "Please load contracts first")
            return
        
        # Test entry popup
        self.show_entry_exit_popup(-2.5, "ENTRY")
        
        # Test exit popup after 2 seconds
        self.root.after(2000, lambda: self.show_entry_exit_popup(2.5, "EXIT"))

    def check_entry_exit_condition(self, price_difference):
        """
        Check if price difference triggers entry or exit condition
        Returns: (should_trigger, signal_type, price_difference)
        """
        try:
            # Update thresholds from GUI
            self.entry_threshold = float(self.entry_threshold_var.get())
            self.exit_threshold = float(self.exit_threshold_var.get())
            self.entry_exit_cooldown = int(self.entry_exit_cooldown_var.get()) * 60  # Convert to seconds
            
            # Check cooldown
            current_time = time.time()
            if self.last_entry_exit_trigger_time is not None and \
               (current_time - self.last_entry_exit_trigger_time) < self.entry_exit_cooldown:
                return False, None, price_difference
            
            # Check conditions
            if price_difference < self.entry_threshold:
                return True, "ENTRY", price_difference
            elif price_difference > self.exit_threshold:
                return True, "EXIT", price_difference
            
            return False, None, price_difference
            
        except ValueError:
            # If invalid thresholds, use defaults
            if price_difference < -2.0:
                return True, "ENTRY", price_difference
            elif price_difference > 2.0:
                return True, "EXIT", price_difference
            return False, None, price_difference

    def show_entry_exit_popup(self, price_difference, signal_type):
        """Show entry/exit popup based on price difference"""
        # Close existing popup if open
        if self.entry_exit_popup and self.entry_exit_popup.winfo_exists():
            self.entry_exit_popup.destroy()
        
        # Create new popup window
        window = tk.Toplevel(self.root)
        
        # Set window properties based on signal type
        if signal_type == "ENTRY":
            window.title("🎯 ENTRY SIGNAL - Consider Buying")
            smiley = "😊"
            message = "ENTRY SIGNAL - Consider BUYING"
            bg_color = '#E8F5E9'  # Light green
            text_color = 'dark green'
            urgency = "🔥 STRONG BUY SIGNAL"
        else:  # EXIT
            window.title("🚪 EXIT SIGNAL - Consider Selling")
            smiley = "😢"
            message = "EXIT SIGNAL - Consider SELLING"
            bg_color = '#FFEBEE'  # Light red
            text_color = 'dark red'
            urgency = "⚠️ STRONG SELL SIGNAL"
        
        window.geometry("500x400")
        #window.resizable(False, False)
        
        # Make window stay on top and give it focus
        window.attributes('-topmost', True)
        window.focus_force()
        
        # Play system beep (multiple times for urgency)
        for _ in range(3):
            window.bell()
            time.sleep(0.1)
        
        # Store reference
        self.entry_exit_popup = window
        
        # Set urgent color
        window.configure(bg=bg_color)
        
        # Center window
        self.center_window(window)
        
        # Main frame
        main_frame = ttk.Frame(window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Header with smiley
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill='x', pady=10)
        
        smiley_label = tk.Label(header_frame, text=smiley, font=('Arial', 72), bg=bg_color)
        smiley_label.pack(pady=5)
        
        # Urgency message
        urgency_label = ttk.Label(header_frame, 
                                 text=urgency,
                                 font=('Arial', 18, 'bold'),
                                 foreground=text_color)
        urgency_label.pack(pady=5)
        
        # Signal type
        signal_label = ttk.Label(header_frame,
                                text=message,
                                font=('Arial', 16, 'bold'),
                                foreground=text_color)
        signal_label.pack(pady=5)
        
        # Details frame
        details_frame = ttk.LabelFrame(main_frame, text="Signal Details")
        details_frame.pack(fill='both', expand=True, pady=10, padx=5)
        
        # Create a grid for details
        details_grid = ttk.Frame(details_frame)
        details_grid.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Price Difference
        ttk.Label(details_grid, text="Price Difference (₹):", font=('Arial', 12, 'bold')).grid(row=0, column=0, sticky='w', pady=10)
        price_diff_label = ttk.Label(details_grid,
                                    text=f"{price_difference:+.2f}",
                                    font=('Arial', 14, 'bold'),
                                    foreground='green' if price_difference > 0 else 'red')
        price_diff_label.grid(row=0, column=1, sticky='w', pady=10, padx=10)
        
        # Threshold info
        ttk.Label(details_grid, text="Trigger Threshold:", font=('Arial', 11)).grid(row=1, column=0, sticky='w', pady=5)
        if signal_type == "ENTRY":
            threshold_text = f"Less than {self.entry_threshold}"
            threshold_color = 'red'
        else:
            threshold_text = f"More than {self.exit_threshold}"
            threshold_color = 'green'
        
        threshold_label = ttk.Label(details_grid,
                                   text=threshold_text,
                                   font=('Arial', 11, 'bold'),
                                   foreground=threshold_color)
        threshold_label.grid(row=1, column=1, sticky='w', pady=5, padx=10)
        
        # Contract names
        ttk.Label(details_grid, text="Current Contract:", font=('Arial', 10)).grid(row=2, column=0, sticky='w', pady=5)
        ttk.Label(details_grid, text=self.current_month_contract, font=('Arial', 10)).grid(row=2, column=1, sticky='w', pady=5, padx=10)
        
        ttk.Label(details_grid, text="Next Contract:", font=('Arial', 10)).grid(row=3, column=0, sticky='w', pady=5)
        ttk.Label(details_grid, text=self.next_month_contract, font=('Arial', 10)).grid(row=3, column=1, sticky='w', pady=5, padx=10)
        
        # Time of trigger
        trigger_time = datetime.now().strftime("%H:%M:%S")
        ttk.Label(details_grid, text="Signal Time:", font=('Arial', 9)).grid(row=4, column=0, sticky='w', pady=5)
        ttk.Label(details_grid, text=trigger_time, font=('Arial', 9)).grid(row=4, column=1, sticky='w', pady=5, padx=10)
        
        # Market interpretation
        interpretation_frame = ttk.Frame(main_frame)
        interpretation_frame.pack(fill='x', pady=10)
        
        if signal_type == "ENTRY":
            if price_difference < -3.0:
                interpretation = "💪 VERY STRONG ENTRY: Next month significantly outperforming!"
            elif price_difference < -2.0:
                interpretation = "📈 STRONG ENTRY: Next month outperforming current month"
            else:
                interpretation = "📊 ENTRY SIGNAL: Consider position entry"
        else:  # EXIT
            if price_difference > 3.0:
                interpretation = "💪 VERY STRONG EXIT: Current month significantly outperforming!"
            elif price_difference > 2.0:
                interpretation = "📉 STRONG EXIT: Current month outperforming next month"
            else:
                interpretation = "📊 EXIT SIGNAL: Consider position exit"
        
        interpretation_label = ttk.Label(interpretation_frame,
                                        text=interpretation,
                                        font=('Arial', 11, 'italic'),
                                        foreground=text_color,
                                        wraplength=400,
                                        justify='center')
        interpretation_label.pack(pady=5)
        
        # Action buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        # Show detailed analysis button
        ttk.Button(button_frame, text="Show Detailed Analysis",
                  command=self.show_price_difference_popup).pack(side='left', padx=5)
        
        # Show comparison button
        ttk.Button(button_frame, text="Show Comparison",
                  command=self.show_comparison_popup).pack(side='left', padx=5)
        
        # Acknowledge button
        ttk.Button(button_frame, text="Acknowledge Signal",
                  command=lambda: self.acknowledge_entry_exit_signal(window, signal_type)).pack(side='right', padx=5)
        
        # Mute button
        ttk.Button(button_frame, text=f"Mute for {self.entry_exit_cooldown//60} min",
                  command=lambda: self.mute_entry_exit_signals(window)).pack(side='right', padx=5)
        
        # Log this signal
        self.log_message(f"🚨 {signal_type} SIGNAL: Price difference {price_difference:+.2f} (Threshold: {self.entry_threshold if signal_type == 'ENTRY' else self.exit_threshold})")
        
        # Update last trigger time
        self.last_entry_exit_trigger_time = time.time()
        
        # Update status label
        self.last_signal_label.config(text=f"Last Signal: {signal_type} at {trigger_time}")
        
        # Update signal display in main window
        self.update_signal_display(signal_type, price_difference)
        
        # Handle window close
        window.protocol("WM_DELETE_WINDOW", lambda: self.acknowledge_entry_exit_signal(window, signal_type))
        
        # Flash the window for attention
        self.flash_window(window, 5)

    def flash_window(self, window, times=5):
        """Flash window for attention"""
        def flash(count):
            if count > 0 and window.winfo_exists():
                current_color = window.cget('bg')
                if signal_type == "ENTRY":
                    flash_color = '#C8E6C9' if current_color == '#E8F5E9' else '#E8F5E9'
                else:
                    flash_color = '#FFCDD2' if current_color == '#FFEBEE' else '#FFEBEE'
                
                window.configure(bg=flash_color)
                window.after(200, lambda: flash(count-1))
            elif window.winfo_exists():
                # Restore original color
                window.configure(bg='#E8F5E9' if signal_type == "ENTRY" else '#FFEBEE')
        
        flash(times)

    def acknowledge_entry_exit_signal(self, window, signal_type):
        """Acknowledge and close entry/exit popup"""
        window.destroy()
        self.entry_exit_popup = None
        self.entry_exit_status_label.config(text=f"Status: {signal_type} Acknowledged", foreground='orange')
        
        # Reset status after cooldown
        self.root.after(10000, lambda: self.entry_exit_status_label.config(
            text="Status: Ready", 
            foreground='green'
        ))

    def mute_entry_exit_signals(self, window):
        """Mute entry/exit signals for specified time"""
        try:
            minutes = int(self.entry_exit_cooldown_var.get())
            self.entry_exit_cooldown = minutes * 60
            self.last_entry_exit_trigger_time = time.time()
            
            # Close window
            window.destroy()
            self.entry_exit_popup = None
            
            # Update status
            self.entry_exit_status_label.config(
                text=f"Status: Muted for {minutes} min", 
                foreground='gray'
            )
            
            self.log_message(f"🔕 Entry/Exit signals muted for {minutes} minutes")
            
            # Reset after cooldown
            self.root.after(minutes * 60 * 1000, lambda: self.reset_entry_exit_mute())
            
        except ValueError:
            messagebox.showerror("Error", "Please enter valid cooldown minutes")

    def reset_entry_exit_mute(self):
        """Reset entry/exit mute status"""
        try:
            self.entry_exit_cooldown = int(self.entry_exit_cooldown_var.get()) * 60
            self.entry_exit_status_label.config(text="Status: Ready", foreground='green')
            self.log_message("🔔 Entry/Exit signals unmuted")
        except ValueError:
            self.entry_exit_cooldown = 300
            self.entry_exit_status_label.config(text="Status: Ready", foreground='green')

    def update_signal_display(self, signal_type, price_difference):
        """Update the signal display in the main window"""
        if signal_type == "ENTRY":
            self.signal_display.config(text="😊", fg='green')
            self.signal_text.config(text=f"ENTRY SIGNAL\nPrice Diff: {price_difference:+.2f}", foreground='green')
            self.signal_display.configure(bg='#E8F5E9')
        else:  # EXIT
            self.signal_display.config(text="😢", fg='red')
            self.signal_text.config(text=f"EXIT SIGNAL\nPrice Diff: {price_difference:+.2f}", foreground='red')
            self.signal_display.configure(bg='#FFEBEE')
        
        # Reset after 30 seconds
        self.root.after(30000, lambda: self.reset_signal_display())

    def reset_signal_display(self):
        """Reset the signal display to default"""
        self.signal_display.config(text="--", fg='black')
        self.signal_text.config(text="No Signal", foreground='black')
        self.signal_display.configure(bg='white')

    def show_price_difference_popup(self):
        """Show popup with price difference in rupees"""
        if not hasattr(self, 'current_month_contract') or not hasattr(self, 'next_month_contract'):
            messagebox.showerror("Error", "Please load contracts first")
            return
        
        # Close existing popup if open
        if self.price_diff_popup and self.price_diff_popup.winfo_exists():
            self.price_diff_popup.destroy()
        
        # Get current data
        try:
            contracts = [self.current_month_contract, self.next_month_contract]
            instruments = [f"MCX:{contract}" for contract in contracts]
            quote_data = self.kite.quote(instruments)
            
            current_price = quote_data[f"MCX:{self.current_month_contract}"]['last_price']
            next_price = quote_data[f"MCX:{self.next_month_contract}"]['last_price']
            
            # Get PREVIOUS DAY CLOSE prices
            current_prev = self.previous_day_close_prices.get(self.current_month_contract, current_price)
            next_prev = self.previous_day_close_prices.get(self.next_month_contract, next_price)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get current prices: {e}")
            return
        
        # Calculate changes in rupees
        current_change_rupees = current_price - current_prev
        next_change_rupees = next_price - next_prev
        
        # Calculate price difference using the formula:
        # change difference in rs = current month (Current Price - Previous Close) - next month (Current Price - Previous Close)
        price_difference = current_change_rupees - next_change_rupees
        
        # Create new window
        window = tk.Toplevel(self.root)
        window.title(f"💰 Price Difference - {self.month_commodity.get()}")
        window.geometry("600x500")
        #window.resizable(False, False)
        
        # Make window stay on top
        window.attributes('-topmost', True)
        
        # Store reference
        self.price_diff_popup = window
        
        # Center window
        self.center_window(window)
        
        # Main frame
        main_frame = ttk.Frame(window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Title
        title_label = ttk.Label(main_frame, 
                               text=f"💰 Price Difference in Rupees", 
                               font=('Arial', 16, 'bold'))
        title_label.pack(pady=5)
        
        subtitle_label = ttk.Label(main_frame, 
                                  text=f"{self.month_commodity.get()} - Current vs Next Month",
                                  font=('Arial', 12))
        subtitle_label.pack(pady=2)
        
        # Formula explanation
        formula_label = ttk.Label(main_frame,
                                 text="Formula: Price Difference = (Current Month Change ₹) - (Next Month Change ₹)",
                                 font=('Arial', 10, 'italic'))
        formula_label.pack(pady=5)
        
        # Current date/time
        self.price_diff_timestamp = ttk.Label(main_frame, 
                                            text=f"Last update: {datetime.now().strftime('%H:%M:%S')}",
                                            font=('Arial', 9))
        self.price_diff_timestamp.pack(pady=5)
        
        # Create a container for details
        details_frame = ttk.LabelFrame(main_frame, text="Price Change Details")
        details_frame.pack(fill='both', expand=True, pady=10, padx=5)
        
        # Create a grid for details
        details_grid = ttk.Frame(details_frame)
        details_grid.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Current Month Section
        ttk.Label(details_grid, text="Current Month:", 
                 font=('Arial', 11, 'bold')).grid(row=0, column=0, sticky='w', pady=10)
        
        ttk.Label(details_grid, text=f"Contract:").grid(row=1, column=0, sticky='w', pady=2)
        ttk.Label(details_grid, text=self.current_month_contract, 
                 font=('Arial', 10, 'bold')).grid(row=1, column=1, sticky='w', pady=2, padx=10)
        
        ttk.Label(details_grid, text=f"Current Price:").grid(row=2, column=0, sticky='w', pady=2)
        ttk.Label(details_grid, text=f"₹{current_price:.2f}", 
                 font=('Arial', 10)).grid(row=2, column=1, sticky='w', pady=2, padx=10)
        
        ttk.Label(details_grid, text=f"Previous Close:").grid(row=3, column=0, sticky='w', pady=2)
        ttk.Label(details_grid, text=f"₹{current_prev:.2f}", 
                 font=('Arial', 10)).grid(row=3, column=1, sticky='w', pady=2, padx=10)
        
        # Current Month Change in Rupees
        ttk.Label(details_grid, text=f"Change in Rupees:").grid(row=4, column=0, sticky='w', pady=5)
        self.price_diff_popup_current = ttk.Label(details_grid, 
                                                 text=f"₹{current_change_rupees:+.2f}",
                                                 font=('Arial', 12, 'bold'))
        self.price_diff_popup_current.grid(row=4, column=1, sticky='w', pady=5, padx=10)
        
        # Next Month Section
        ttk.Label(details_grid, text="Next Month:", 
                 font=('Arial', 11, 'bold')).grid(row=0, column=2, sticky='w', pady=10, padx=(20, 0))
        
        ttk.Label(details_grid, text=f"Contract:").grid(row=1, column=2, sticky='w', pady=2)
        ttk.Label(details_grid, text=self.next_month_contract, 
                 font=('Arial', 10, 'bold')).grid(row=1, column=3, sticky='w', pady=2, padx=10)
        
        ttk.Label(details_grid, text=f"Current Price:").grid(row=2, column=2, sticky='w', pady=2)
        ttk.Label(details_grid, text=f"₹{next_price:.2f}", 
                 font=('Arial', 10)).grid(row=2, column=3, sticky='w', pady=2, padx=10)
        
        ttk.Label(details_grid, text=f"Previous Close:").grid(row=3, column=2, sticky='w', pady=2)
        ttk.Label(details_grid, text=f"₹{next_prev:.2f}", 
                 font=('Arial', 10)).grid(row=3, column=3, sticky='w', pady=2, padx=10)
        
        # Next Month Change in Rupees
        ttk.Label(details_grid, text=f"Change in Rupees:").grid(row=4, column=2, sticky='w', pady=5)
        self.price_diff_popup_next = ttk.Label(details_grid, 
                                              text=f"₹{next_change_rupees:+.2f}",
                                              font=('Arial', 12, 'bold'))
        self.price_diff_popup_next.grid(row=4, column=3, sticky='w', pady=5, padx=10)
        
        # Separator line
        separator = ttk.Separator(main_frame, orient='horizontal')
        separator.pack(fill='x', pady=10)
        
        # Price Difference Result Frame
        result_frame = ttk.LabelFrame(main_frame, text="💰 Price Difference Result")
        result_frame.pack(fill='x', pady=10, padx=5)
        
        # Formula display
        formula_text = f"Price Difference = (₹{current_change_rupees:+.2f}) - (₹{next_change_rupees:+.2f})"
        formula_display = ttk.Label(result_frame, text=formula_text, font=('Arial', 10))
        formula_display.pack(pady=5)
        
        # Result with color coding
        self.price_diff_popup_result = ttk.Label(result_frame, 
                                                text=f"Price Difference = ₹{price_difference:+.2f}",
                                                font=('Arial', 16, 'bold'))
        self.price_diff_popup_result.pack(pady=10)
        
        # Check entry/exit conditions
        entry_exit_frame = ttk.Frame(result_frame)
        entry_exit_frame.pack(fill='x', pady=10)
        
        # Determine signal based on thresholds
        should_trigger, signal_type, _ = self.check_entry_exit_condition(price_difference)
        
        if should_trigger:
            if signal_type == "ENTRY":
                signal_text = "🎯 ENTRY SIGNAL: Consider BUYING"
                signal_color = 'green'
                signal_bg = '#E8F5E9'
                advice = "Next month is performing significantly better"
            else:  # EXIT
                signal_text = "🚪 EXIT SIGNAL: Consider SELLING"
                signal_color = 'red'
                signal_bg = '#FFEBEE'
                advice = "Current month is performing significantly better"
            
            signal_label = ttk.Label(entry_exit_frame,
                                    text=signal_text,
                                    font=('Arial', 12, 'bold'),
                                    foreground=signal_color)
            signal_label.pack(pady=5)
            
            advice_label = ttk.Label(entry_exit_frame,
                                    text=advice,
                                    font=('Arial', 10, 'italic'),
                                    foreground=signal_color)
            advice_label.pack(pady=2)
            
            # Update window background
            window.configure(bg=signal_bg)
        
        # Interpretation
        interpretation_frame = ttk.Frame(main_frame)
        interpretation_frame.pack(fill='x', pady=10)
        
        # Determine interpretation
        if price_difference > 0:
            if current_change_rupees > 0 and next_change_rupees < 0:
                interpretation = "📈 Current month UP, Next month DOWN - Strong bullish signal for current month"
                bg_color = '#E8F5E9'  # Light green
                result_color = 'green'
            elif current_change_rupees > 0 and next_change_rupees > 0:
                interpretation = "📈 Both months UP, but Current month rising MORE"
                bg_color = '#F1F8E9'  # Light green
                result_color = 'green'
            else:
                interpretation = "📊 Current month performing better than Next month"
                bg_color = '#FFF3E0'  # Light orange
                result_color = 'orange'
        elif price_difference < 0:
            if current_change_rupees < 0 and next_change_rupees > 0:
                interpretation = "📉 Current month DOWN, Next month UP - Strong bearish signal for current month"
                bg_color = '#FFEBEE'  # Light red
                result_color = 'red'
            elif current_change_rupees < 0 and next_change_rupees < 0:
                interpretation = "📉 Both months DOWN, but Next month falling LESS"
                bg_color = '#FFE5E5'  # Light red
                result_color = 'red'
            else:
                interpretation = "📊 Next month performing better than Current month"
                bg_color = '#FFF3E0'  # Light orange
                result_color = 'orange'
        else:
            interpretation = "⚖️ Both months showing equal changes"
            bg_color = 'light yellow'
            result_color = 'orange'
        
        # Update result color
        self.price_diff_popup_result.config(foreground=result_color)
        
        # Set window background (if not already set by signal)
        if not should_trigger:
            window.configure(bg=bg_color)
        
        # Interpretation label
        interpretation_label = ttk.Label(interpretation_frame,
                                        text=interpretation,
                                        font=('Arial', 11, 'italic'),
                                        foreground=result_color,
                                        wraplength=450,
                                        justify='center')
        interpretation_label.pack(pady=5)
        
        # Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        ttk.Button(button_frame, text="Close", 
                  command=lambda: self.on_price_diff_popup_close(window)).pack(side='right', padx=5)
        
        ttk.Button(button_frame, text="Show Full Comparison", 
                  command=self.show_comparison_popup).pack(side='right', padx=5)
        
        # Handle window close
        window.protocol("WM_DELETE_WINDOW", lambda: self.on_price_diff_popup_close(window))
        
        # Start updates
        self.start_price_diff_popup_updates(window)

    def start_price_diff_popup_updates(self, window):
        """Start updating price difference popup window"""
        def update_popup():
            if not window.winfo_exists():
                return
            
            try:
                # Get current prices
                contracts = [self.current_month_contract, self.next_month_contract]
                instruments = [f"MCX:{contract}" for contract in contracts]
                quote_data = self.kite.quote(instruments)
                
                current_price = quote_data[f"MCX:{self.current_month_contract}"]['last_price']
                next_price = quote_data[f"MCX:{self.next_month_contract}"]['last_price']
                
                # Get PREVIOUS DAY CLOSE prices
                current_prev = self.previous_day_close_prices.get(self.current_month_contract, current_price)
                next_prev = self.previous_day_close_prices.get(self.next_month_contract, next_price)
                
                # Calculate changes in rupees
                current_change_rupees = current_price - current_prev
                next_change_rupees = next_price - next_prev
                
                # Calculate price difference using the formula:
                # change difference in rs = current month (Current Price - Previous Close) - next month (Current Price - Previous Close)
                price_difference = current_change_rupees - next_change_rupees
                
                # Update timestamp
                self.price_diff_timestamp.config(text=f"Last update: {datetime.now().strftime('%H:%M:%S')}")
                
                # Update current month change
                current_color = 'green' if current_change_rupees >= 0 else 'red'
                self.price_diff_popup_current.config(
                    text=f"₹{current_change_rupees:+.2f}",
                    foreground=current_color
                )
                
                # Update next month change
                next_color = 'green' if next_change_rupees >= 0 else 'red'
                self.price_diff_popup_next.config(
                    text=f"₹{next_change_rupees:+.2f}",
                    foreground=next_color
                )
                
                # Update result
                result_color = 'green' if price_difference > 0 else 'red' if price_difference < 0 else 'orange'
                self.price_diff_popup_result.config(
                    text=f"Price Difference = ₹{price_difference:+.2f}",
                    foreground=result_color
                )
                
                # Update interpretation
                interpretation_frame = window.winfo_children()[0].winfo_children()[-2]  # Get interpretation frame
                interpretation_label = interpretation_frame.winfo_children()[0]
                
                if price_difference > 0:
                    if current_change_rupees > 0 and next_change_rupees < 0:
                        interpretation = "📈 Current month UP, Next month DOWN - Strong bullish signal for current month"
                        bg_color = '#E8F5E9'
                    elif current_change_rupees > 0 and next_change_rupees > 0:
                        interpretation = "📈 Both months UP, but Current month rising MORE"
                        bg_color = '#F1F8E9'
                    else:
                        interpretation = "📊 Current month performing better than Next month"
                        bg_color = '#FFF3E0'
                elif price_difference < 0:
                    if current_change_rupees < 0 and next_change_rupees > 0:
                        interpretation = "📉 Current month DOWN, Next month UP - Strong bearish signal for current month"
                        bg_color = '#FFEBEE'
                    elif current_change_rupees < 0 and next_change_rupees < 0:
                        interpretation = "📉 Both months DOWN, but Next month falling LESS"
                        bg_color = '#FFE5E5'
                    else:
                        interpretation = "📊 Next month performing better than Current month"
                        bg_color = '#FFF3E0'
                else:
                    interpretation = "⚖️ Both months showing equal changes"
                    bg_color = 'light yellow'
                
                interpretation_label.config(text=interpretation, foreground=result_color)
                window.configure(bg=bg_color)
                
            except Exception as e:
                print(f"Error updating price difference popup: {e}")
            
            # Schedule next update
            if window.winfo_exists():
                window.after(2000, update_popup)
        
        # Start updates
        window.after(1000, update_popup)

    def on_price_diff_popup_close(self, window):
        """Handle price difference popup window close"""
        window.destroy()
        self.price_diff_popup = None

    def log_message(self, message):
        """Add message to log"""
        def update_log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.log_text.see(tk.END)
        
        self.root.after(0, update_log)

    def init_daily_performance_db(self):
        """Initialize SQLite database for daily performance tracking"""
        try:
            conn = sqlite3.connect(self.daily_performance_db)
            cursor = conn.cursor()
            
            # Create table for daily performance
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_performance (
                    date DATE,
                    commodity TEXT,
                    current_month_contract TEXT,
                    next_month_contract TEXT,
                    current_month_close REAL,
                    next_month_close REAL,
                    current_performance REAL,
                    next_performance REAL,
                    relative_performance REAL,
                    smiley_status TEXT,
                    total_sum REAL,
                    PRIMARY KEY (date, commodity)
                )
            ''')
            
            # Create table for previous day closes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS previous_day_closes (
                    date DATE,
                    contract_symbol TEXT,
                    close_price REAL,
                    volume INTEGER,
                    PRIMARY KEY (date, contract_symbol)
                )
            ''')
            
            conn.commit()
            conn.close()
            self.log_message("Daily performance database initialized")
        except Exception as e:
            self.log_message(f"Error initializing database: {e}")

    def generate_login_url(self):
        """Generate login URL for Zerodha"""
        try:
            self.api_key = self.api_key_entry.get()
            if not self.api_key:
                messagebox.showerror("Error", "Please enter API Key")
                return
                
            self.kite = KiteConnect(api_key=self.api_key)
            
            login_url = self.kite.login_url()
            webbrowser.open(login_url)
            messagebox.showinfo("Login URL", f"Login URL generated and opened in browser.\nIf not, copy this URL:\n{login_url}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate login URL: {e}")

    def manual_login(self):
        """Manual login with request token"""
        try:
            self.api_key = self.api_key_entry.get()
            api_secret = self.api_secret_entry.get()
            request_token = self.request_token_entry.get()
            
            if not all([self.api_key, api_secret, request_token]):
                messagebox.showerror("Error", "Please fill all fields")
                return
            
            self.kite = KiteConnect(api_key=self.api_key)
            data = self.kite.generate_session(request_token, api_secret=api_secret)
            self.access_token = data['access_token']
            self.kite.set_access_token(self.access_token)
            
            # Save credentials
            self.save_credentials()
            
            self.is_logged_in = True
            self.login_status.config(text="Logged In Successfully", foreground='green')
            
            # Load instruments
            self.load_instruments()
            
            messagebox.showinfo("Success", "Login successful!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Login failed: {e}")

    def auto_login(self):
        """Auto login with saved credentials"""
        try:
            if not hasattr(self, 'api_key') or not self.api_key or not hasattr(self, 'access_token') or not self.access_token:
                messagebox.showerror("Error", "No saved credentials found")
                return
            
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)
            
            # Test connection
            profile = self.kite.profile()
            
            self.is_logged_in = True
            self.login_status.config(text=f"Auto Login Successful - {profile['user_name']}", foreground='green')
            
            # Load instruments
            self.load_instruments()
            
            messagebox.showinfo("Success", f"Auto login successful! Welcome {profile['user_name']}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Auto login failed: {e}")

    def load_instruments(self):
        """Load MCX instruments"""
        try:
            if self.kite and self.is_logged_in:
                # Get all instruments
                all_instruments = self.kite.instruments("MCX")
                self.instruments_df = pd.DataFrame(all_instruments)
                
                # Convert expiry to datetime if it's string
                if 'expiry' in self.instruments_df.columns and self.instruments_df['expiry'].dtype == 'object':
                    self.instruments_df['expiry'] = pd.to_datetime(self.instruments_df['expiry']).dt.date
                
                self.log_message(f"Loaded {len(self.instruments_df)} MCX instruments")
                
        except Exception as e:
            self.log_message(f"Error loading instruments: {e}")

    def get_monthly_contracts(self, base_symbol):
        """Get current and next month contracts"""
        try:
            if self.instruments_df is None:
                self.load_instruments()
                if self.instruments_df is None:
                    return []
            
            # Filter instruments for the base symbol (futures)
            relevant_instruments = self.instruments_df[
                (self.instruments_df['tradingsymbol'].str.startswith(base_symbol)) &
                (self.instruments_df['instrument_type'] == 'FUT')
            ].copy()
            
            if relevant_instruments.empty:
                self.log_message(f"No FUT contracts found for {base_symbol}")
                return []
            
            # Sort by expiry
            relevant_instruments = relevant_instruments.sort_values('expiry')
            
            # Get current date
            current_date = datetime.now().date()
            
            # Filter out expired contracts
            relevant_instruments = relevant_instruments[relevant_instruments['expiry'] >= current_date]
            
            # Get nearest 2 contracts (current and next month)
            if len(relevant_instruments) >= 2:
                selected_contracts = relevant_instruments.head(2)['tradingsymbol'].tolist()
            else:
                selected_contracts = relevant_instruments['tradingsymbol'].tolist()
            
            self.log_message(f"Found {len(selected_contracts)} contracts for {base_symbol}")
            return selected_contracts
            
        except Exception as e:
            self.log_message(f"Error getting monthly contracts: {str(e)}")
            return []

    def load_month_contracts(self):
        """Load current and next month contracts"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        commodity = self.month_commodity.get()
        
        try:
            contracts = self.get_monthly_contracts(commodity)
            
            if len(contracts) < 2:
                messagebox.showerror("Error", f"Need at least 2 contracts for {commodity}")
                return
            
            # Store current and next month contracts
            self.current_month_contract = contracts[0]
            self.next_month_contract = contracts[1]
            
            # Clear existing display
            for widget in self.month_comparison_frame.winfo_children():
                widget.destroy()
            
            # Create comparison display with PREVIOUS DAY CLOSE
            # Current month frame
            current_frame = ttk.LabelFrame(self.month_comparison_frame, text="Current Month")
            current_frame.pack(side='left', fill='both', expand=True, padx=5, pady=5)
            
            ttk.Label(current_frame, text=self.current_month_contract, 
                     font=('Arial', 12, 'bold')).pack(pady=10)
            
            self.current_price_label = ttk.Label(current_frame, text="Current: ₹--", 
                                                font=('Arial', 14))
            self.current_price_label.pack(pady=5)
            
            self.current_prev_close_label = ttk.Label(current_frame, text="Prev Close: ₹--", 
                                                     font=('Arial', 10))
            self.current_prev_close_label.pack(pady=5)
            
            self.current_change_label = ttk.Label(current_frame, text="Change: --%", 
                                                 font=('Arial', 10))
            self.current_change_label.pack(pady=5)
            
            # VS separator
            vs_frame = ttk.Frame(self.month_comparison_frame)
            vs_frame.pack(side='left', fill='y', padx=10)
            
            ttk.Label(vs_frame, text="VS", font=('Arial', 16, 'bold')).pack(pady=50)
            
            # Next month frame
            next_frame = ttk.LabelFrame(self.month_comparison_frame, text="Next Month")
            next_frame.pack(side='left', fill='both', expand=True, padx=5, pady=5)
            
            ttk.Label(next_frame, text=self.next_month_contract, 
                     font=('Arial', 12, 'bold')).pack(pady=10)
            
            self.next_price_label = ttk.Label(next_frame, text="Current: ₹--", 
                                             font=('Arial', 14))
            self.next_price_label.pack(pady=5)
            
            self.next_prev_close_label = ttk.Label(next_frame, text="Prev Close: ₹--", 
                                                  font=('Arial', 10))
            self.next_prev_close_label.pack(pady=5)
            
            self.next_change_label = ttk.Label(next_frame, text="Change: --%", 
                                              font=('Arial', 10))
            self.next_change_label.pack(pady=5)
            
            # Smiley indicator
            smiley_frame = ttk.Frame(self.month_comparison_frame)
            smiley_frame.pack(side='left', fill='both', expand=True, padx=10)
            
            self.month_smiley_label = tk.Label(smiley_frame, text="😐", 
                                              font=('Arial', 72), bg='white')
            self.month_smiley_label.pack(pady=20)
            
            self.month_comparison_text = ttk.Label(smiley_frame, text="Comparison: --", 
                                                  font=('Arial', 12))
            self.month_comparison_text.pack()
            
            # Update history display
            self.update_history_display(commodity)
            
            self.log_message(f"Loaded month comparison: {self.current_month_contract} vs {self.next_month_contract}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load contracts: {e}")

    def fetch_previous_day_closes(self):
        """Fetch previous day closing prices for the contracts"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        if not hasattr(self, 'current_month_contract') or not hasattr(self, 'next_month_contract'):
            messagebox.showerror("Error", "Please load contracts first")
            return
        
        try:
            # Get today and previous trading day
            today = datetime.now().date()
            
            # Try to get data for last 5 days to find a trading day
            for days_back in range(1, 6):
                check_date = today - timedelta(days=days_back)
                
                # Try to fetch historical data for previous day
                self.fetch_contract_historical_data(self.current_month_contract, check_date)
                self.fetch_contract_historical_data(self.next_month_contract, check_date)
                
                # Check if we got data for both contracts
                if (self.current_month_contract in self.previous_day_close_prices and 
                    self.next_month_contract in self.previous_day_close_prices):
                    break
            
            # Update display
            self.update_prev_close_display()
            
            current_prev = self.previous_day_close_prices.get(self.current_month_contract, "Not found")
            next_prev = self.previous_day_close_prices.get(self.next_month_contract, "Not found")
            
            messagebox.showinfo("Previous Day Close Fetched", 
                              f"Previous day closing prices fetched:\n"
                              f"Current Month: ₹{current_prev if isinstance(current_prev, (int, float)) else current_prev}\n"
                              f"Next Month: ₹{next_prev if isinstance(next_prev, (int, float)) else next_prev}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch previous day closes: {e}")

    def fetch_contract_historical_data(self, contract_symbol, date_to_check):
        """Fetch historical data for a specific contract and date"""
        try:
            # Get instrument token
            instrument_token = self.get_instrument_token(contract_symbol)
            if not instrument_token:
                self.log_message(f"Cannot find instrument token for {contract_symbol}")
                return None
            
            # Convert date to string format for Zerodha API
            from_date = date_to_check.strftime("%Y-%m-%d")
            to_date = date_to_check.strftime("%Y-%m-%d")
            
            # Fetch historical data
            historical_data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval="day",
                continuous=False
            )
            
            if historical_data and len(historical_data) > 0:
                # Get the last day's closing price
                last_day_data = historical_data[-1]
                close_price = last_day_data['close']
                
                # Store in dictionary
                self.previous_day_close_prices[contract_symbol] = close_price
                
                # Also save to database
                self.save_previous_day_close_to_db(contract_symbol, date_to_check, close_price)
                
                return close_price
            
            return None
            
        except Exception as e:
            self.log_message(f"Error fetching historical data for {contract_symbol}: {e}")
            return None

    def get_instrument_token(self, tradingsymbol):
        """Get instrument token for a trading symbol"""
        try:
            if self.instruments_df is None:
                self.load_instruments()
            
            if self.instruments_df is not None:
                # Search for the contract
                contract = self.instruments_df[
                    (self.instruments_df['tradingsymbol'] == tradingsymbol)
                ]
                
                if not contract.empty:
                    return int(contract.iloc[0]['instrument_token'])
            
            # Fallback: try to fetch fresh data
            all_instruments = self.kite.instruments("MCX")
            for inst in all_instruments:
                if inst['tradingsymbol'] == tradingsymbol:
                    return int(inst['instrument_token'])
            
            self.log_message(f"Instrument token not found for {tradingsymbol}")
            return None
                
        except Exception as e:
            self.log_message(f"Error getting instrument token for {tradingsymbol}: {e}")
            return None

    def save_previous_day_close_to_db(self, contract_symbol, date_obj, close_price):
        """Save previous day close to database"""
        try:
            conn = sqlite3.connect(self.daily_performance_db)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO previous_day_closes 
                (date, contract_symbol, close_price)
                VALUES (?, ?, ?)
            ''', (date_obj, contract_symbol, close_price))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.log_message(f"Error saving previous day close to DB: {e}")

    def update_prev_close_display(self):
        """Update previous day close price display"""
        if hasattr(self, 'current_prev_close_label') and hasattr(self, 'next_prev_close_label'):
            current_prev = self.previous_day_close_prices.get(self.current_month_contract, 0)
            next_prev = self.previous_day_close_prices.get(self.next_month_contract, 0)
            
            if current_prev:
                self.current_prev_close_label.config(text=f"Prev Close: ₹{current_prev:.2f}")
            else:
                self.current_prev_close_label.config(text="Prev Close: Not set")
            
            if next_prev:
                self.next_prev_close_label.config(text=f"Prev Close: ₹{next_prev:.2f}")
            else:
                self.next_prev_close_label.config(text="Prev Close: Not set")

    def set_manual_previous_close(self):
        """Set previous day close prices manually"""
        if not hasattr(self, 'current_month_contract') or not hasattr(self, 'next_month_contract'):
            messagebox.showerror("Error", "Please load contracts first")
            return
        
        # Create dialog for manual entry
        dialog = tk.Toplevel(self.root)
        dialog.title("Set Manual Previous Day Close Prices")
        dialog.geometry("400x250")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text=f"Enter Previous Day Close Prices:", 
                 font=('Arial', 10, 'bold')).pack(pady=10)
        
        # Current month price
        current_frame = ttk.Frame(dialog)
        current_frame.pack(fill='x', padx=20, pady=5)
        ttk.Label(current_frame, text=f"{self.current_month_contract}:").pack(side='left')
        current_price_entry = ttk.Entry(current_frame, width=15)
        current_price_entry.pack(side='left', padx=10)
        current_price_entry.insert(0, str(self.previous_day_close_prices.get(self.current_month_contract, '')))
        
        # Next month price
        next_frame = ttk.Frame(dialog)
        next_frame.pack(fill='x', padx=20, pady=5)
        ttk.Label(next_frame, text=f"{self.next_month_contract}:").pack(side='left')
        next_price_entry = ttk.Entry(next_frame, width=15)
        next_price_entry.pack(side='left', padx=10)
        next_price_entry.insert(0, str(self.previous_day_close_prices.get(self.next_month_contract, '')))
        
        def save_manual_prices():
            try:
                current_price = float(current_price_entry.get())
                next_price = float(next_price_entry.get())
                
                self.previous_day_close_prices[self.current_month_contract] = current_price
                self.previous_day_close_prices[self.next_month_contract] = next_price
                
                self.update_prev_close_display()
                dialog.destroy()
                
                messagebox.showinfo("Success", "Manual previous day closes set successfully")
                
            except ValueError:
                messagebox.showerror("Error", "Please enter valid numbers")
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=20)
        ttk.Button(button_frame, text="Save", command=save_manual_prices).pack(side='left', padx=10)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side='left', padx=10)

    def start_month_comparison(self):
        """Start month comparison monitoring using PREVIOUS DAY CLOSE"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        if not hasattr(self, 'current_month_contract') or not hasattr(self, 'next_month_contract'):
            messagebox.showerror("Error", "Please load contracts first")
            return
        
        # Check if we have previous day closes
        if (self.current_month_contract not in self.previous_day_close_prices or 
            self.next_month_contract not in self.previous_day_close_prices):
            
            response = messagebox.askyesno("Previous Day Close Missing", 
                                         "Previous day closing prices not set. Would you like to fetch them now?")
            if response:
                self.fetch_previous_day_closes()
            else:
                response2 = messagebox.askyesno("Set Manual", 
                                              "Would you like to set them manually?")
                if response2:
                    self.set_manual_previous_close()
                else:
                    return
        
        self.month_comparison_running = True
        self.start_month_btn.config(state='disabled')
        self.stop_month_btn.config(state='normal')
        self.month_status_label.config(text="Status: Monitoring", foreground='green')
        self.trigger_status_label.config(text="Trigger Status: Ready", foreground='green')
        
        # Start monitoring thread
        threading.Thread(target=self.monitor_month_comparison, daemon=True).start()
        
        self.log_message(f"Started month comparison monitoring (vs Previous Day Close)")

    def stop_month_comparison(self):
        """Stop month comparison monitoring"""
        self.month_comparison_running = False
        self.start_month_btn.config(state='normal')
        self.stop_month_btn.config(state='disabled')
        self.month_status_label.config(text="Status: Stopped", foreground='red')
        
        self.log_message("Stopped month comparison monitoring")

    def monitor_month_comparison(self):
        """Monitor and compare current vs next month contracts vs PREVIOUS DAY CLOSE"""
        update_interval = 2  # seconds
        
        while self.month_comparison_running and self.is_logged_in:
            try:
                contracts = [self.current_month_contract, self.next_month_contract]
                instruments = [f"MCX:{contract}" for contract in contracts]
                
                quote_data = self.kite.quote(instruments)
                
                current_prices = {}
                for contract in contracts:
                    price = quote_data[f"MCX:{contract}"]['last_price']
                    current_prices[contract] = price
                
                # Update GUI with current prices and comparisons vs PREVIOUS DAY CLOSE
                self.update_month_comparison_display(current_prices)
                
                # Update popup window if it exists
                if self.comparison_popup and self.comparison_popup.winfo_exists():
                    self.update_comparison_popup_display(
                        self.comparison_popup,
                        current_prices[self.current_month_contract],
                        current_prices[self.next_month_contract],
                        self.previous_day_close_prices.get(self.current_month_contract, 0),
                        self.previous_day_close_prices.get(self.next_month_contract, 0)
                    )
                
                # Update price difference popup if it exists
                if self.price_diff_popup and self.price_diff_popup.winfo_exists():
                    # Trigger update through the main thread
                    self.root.after(0, lambda: self.update_price_diff_display())
                
                time.sleep(update_interval)
                
            except Exception as e:
                self.log_message(f"Error in month comparison monitoring: {e}")
                time.sleep(5)

    def update_price_diff_display(self):
        """Update price difference display in the main window"""
        try:
            if not hasattr(self, 'current_month_contract') or not hasattr(self, 'next_month_contract'):
                return
            
            # Get current prices
            contracts = [self.current_month_contract, self.next_month_contract]
            instruments = [f"MCX:{contract}" for contract in contracts]
            quote_data = self.kite.quote(instruments)
            
            current_price = quote_data[f"MCX:{self.current_month_contract}"]['last_price']
            next_price = quote_data[f"MCX:{self.next_month_contract}"]['last_price']
            
            # Get PREVIOUS DAY CLOSE prices
            current_prev = self.previous_day_close_prices.get(self.current_month_contract, current_price)
            next_prev = self.previous_day_close_prices.get(self.next_month_contract, next_price)
            
            # Calculate changes in rupees
            current_change_rupees = current_price - current_prev
            next_change_rupees = next_price - next_prev
            
            # Calculate price difference using the formula:
            # change difference in rs = current month (Current Price - Previous Close) - next month (Current Price - Previous Close)
            price_difference = current_change_rupees - next_change_rupees
            
            print("price_difference: ", price_difference)
            
            # # Extract the date part as a date object
            # current_date = current_datetime.date()

            # # Extract the time part as a time object
            # current_time = current_datetime.time()

            # # Print the results
            # print(f"Current Date: {current_date}")
            # print(f"Current Time: {current_time}")
            
            # next_row = sheet.range('A' + str(sheet.cells.last_cell.row)).end('up').row + 1
            # sheet.range(f'A{next_row}').value = datetime.now()
            # sheet.range(f'B{next_row}').value = price_difference

            
            #writer.writerows(new_row)
            #with open('New Microsoft Excel Worksheet.csv', 'a', newline='') as f: csv.writer(f).writerow(new_row)
            update_existing_file(price_difference)

            # if price_difference > -2.5:
            #     import winsound
            #     frequency = 3000  # Set Frequency To 2500 Hertz
            #     duration = 2000   # Set Duration To 1000 ms == 1 second
            #     winsound.Beep(frequency, duration)    
            # Update labels with colors
            current_color = 'green' if current_change_rupees >= 0 else 'red'
            next_color = 'green' if next_change_rupees >= 0 else 'red'
            diff_color = 'green' if price_difference > 0 else 'red' if price_difference < 0 else 'orange'
            
            self.price_diff_current.config(
                text=f"₹{current_change_rupees:+.2f}",
                foreground=current_color
            )
            self.price_diff_next.config(
                text=f"₹{next_change_rupees:+.2f}",
                foreground=next_color
            )
            self.price_diff_total.config(
                text=f"₹{price_difference:+.2f}",
                foreground=diff_color
            )
            
        except Exception as e:
            print(f"Error updating price difference display: {e}")

    def update_month_comparison_display(self, current_prices):
        """Update month comparison display vs PREVIOUS DAY CLOSE"""
        if not self.root.winfo_exists():
            return
        
        def update_gui():
            try:
                current_price = current_prices.get(self.current_month_contract, 0)
                next_price = current_prices.get(self.next_month_contract, 0)
                
                # Get PREVIOUS DAY CLOSE prices
                current_prev_close = self.previous_day_close_prices.get(self.current_month_contract, current_price)
                next_prev_close = self.previous_day_close_prices.get(self.next_month_contract, next_price)
                
                # Calculate changes from PREVIOUS DAY CLOSE
                if current_prev_close > 0:
                    current_change = ((current_price - current_prev_close) / current_prev_close) * 100
                else:
                    current_change = 0
                
                if next_prev_close > 0:
                    next_change = ((next_price - next_prev_close) / next_prev_close) * 100
                else:
                    next_change = 0
                
                # Calculate total sum of changes
                total_sum = current_change + next_change
                
                # Calculate price changes in rupees
                current_change_rupees = current_price - current_prev_close
                next_change_rupees = next_price - next_prev_close
                price_difference = current_change_rupees - next_change_rupees
                
                # Update price labels
                self.current_price_label.config(text=f"Current: ₹{current_price:.2f}")
                self.next_price_label.config(text=f"Current: ₹{next_price:.2f}")
                
                # Update change labels with colors
                current_color = 'green' if current_change >= 0 else 'red'
                next_color = 'green' if next_change >= 0 else 'red'
                
                self.current_change_label.config(
                    text=f"Change: {current_change:+.2f}%",
                    foreground=current_color
                )
                self.next_change_label.config(
                    text=f"Change: {next_change:+.2f}%",
                    foreground=next_color
                )
                
                # Update price difference display
                current_rupee_color = 'green' if current_change_rupees >= 0 else 'red'
                next_rupee_color = 'green' if next_change_rupees >= 0 else 'red'
                diff_color = 'green' if price_difference > 0 else 'red' if price_difference < 0 else 'orange'
                
                self.price_diff_current.config(
                    text=f"₹{current_change_rupees:+.2f}",
                    foreground=current_rupee_color
                )
                self.price_diff_next.config(
                    text=f"₹{next_change_rupees:+.2f}",
                    foreground=next_rupee_color
                )
                self.price_diff_total.config(
                    text=f"₹{price_difference:+.2f}",
                    foreground=diff_color
                )
                
                # Update price difference display in the main window
                # This ensures the price difference updates during live monitoring
                self.update_price_diff_display()
                
                # Check entry/exit condition
                should_trigger, signal_type, _ = self.check_entry_exit_condition(price_difference)
                
                if should_trigger:
                    self.show_entry_exit_popup(price_difference, signal_type)
                
                # Update total changes summary section
                self.update_total_changes_summary(current_change, next_change, total_sum)
                
                # Check trigger condition for special popup
                should_perf_trigger, difference = self.check_trigger_condition(current_change, next_change)
                
                if should_perf_trigger:
                    self.show_triggered_popup(current_change, next_change, difference)
                
                # Determine comparison logic
                next_increased = next_change > 0
                current_decreased = current_change < 0
                
                # Calculate relative performance
                relative_performance = next_change - current_change
                
                # Determine smiley
                smiley_status = "NEUTRAL"
                if next_increased and current_decreased:
                    # Best case: next month up, current month down
                    smiley = "😊"
                    smiley_color = 'green'
                    comparison_text = "📈 Next month UP, Current DOWN vs Prev Close"
                    result_color = 'green'
                    smiley_status = "POSITIVE"
                elif relative_performance > 0.5:  # Next month performing better by 0.5%
                    smiley = "😊"
                    smiley_color = 'green'
                    comparison_text = f"📈 Next month +{relative_performance:.2f}% better"
                    result_color = 'green'
                    smiley_status = "POSITIVE"
                elif relative_performance < -0.5:  # Current month performing better
                    smiley = "☹️"
                    smiley_color = 'red'
                    comparison_text = f"📉 Current month +{abs(relative_performance):.2f}% better"
                    result_color = 'red'
                    smiley_status = "NEGATIVE"
                else:
                    smiley = "😐"
                    smiley_color = 'orange'
                    comparison_text = "⚖️ Months similar performance vs Prev Close"
                    result_color = 'orange'
                    smiley_status = "NEUTRAL"
                
                # Update smiley and text
                self.month_smiley_label.config(text=smiley, fg=smiley_color)
                self.month_comparison_text.config(text=comparison_text, foreground=result_color)
                
                # Update result label
                self.month_result_label.config(
                    text=f"Comparison: Next month is {relative_performance:+.2f}% vs Current",
                    foreground=result_color
                )
                
                # Update trigger status
                if self.last_trigger_time:
                    time_since = int(time.time() - self.last_trigger_time)
                    cooldown_left = max(0, self.trigger_cooldown - time_since)
                    if cooldown_left > 0:
                        self.trigger_status_label.config(
                            text=f"Trigger Cooldown: {cooldown_left}s",
                            foreground='orange'
                        )
                    else:
                        self.trigger_status_label.config(
                            text="Trigger Status: Ready",
                            foreground='green'
                        )
                
                # Save daily performance to database (including total sum)
                commodity = self.month_commodity.get()
                self.save_daily_performance(
                    commodity, self.current_month_contract, self.next_month_contract,
                    current_price, next_price, current_change, next_change,
                    relative_performance, smiley_status, total_sum
                )
                
                # Update history display
                self.update_history_display(commodity)
                
            except Exception as e:
                print(f"Error updating month comparison display: {e}")
        
        self.root.after(0, update_gui)

    def update_total_changes_summary(self, current_change, next_change, total_sum):
        """Update the total changes summary section"""
        try:
            # Update individual changes
            current_color = 'green' if current_change >= 0 else 'red'
            next_color = 'green' if next_change >= 0 else 'red'
            
            self.total_current_change.config(
                text=f"{current_change:+.2f}%",
                foreground=current_color
            )
            self.total_next_change.config(
                text=f"{next_change:+.2f}%",
                foreground=next_color
            )
            
            # Update performance difference
            perf_diff = next_change - current_change
            perf_color = 'green' if perf_diff > 0 else 'red' if perf_diff < 0 else 'orange'
            self.total_perf_diff.config(
                text=f"{perf_diff:+.2f}%",
                foreground=perf_color
            )
            
            # Update total sum with color coding
            if total_sum > 2.0:
                total_color = 'dark green'
                total_emoji = "🚀"
            elif total_sum > 0.5:
                total_color = 'green'
                total_emoji = "📈"
            elif total_sum < -2.0:
                total_color = 'dark red'
                total_emoji = "⚠️"
            elif total_sum < -0.5:
                total_color = 'red'
                total_emoji = "📉"
            else:
                total_color = 'orange'
                total_emoji = "⚖️"
            
            self.total_sum_label.config(
                text=f"{total_emoji} {total_sum:+.2f}%",
                foreground=total_color,
                font=('Arial', 12, 'bold')
            )
            
        except Exception as e:
            print(f"Error updating total changes summary: {e}")

    def save_daily_performance(self, commodity, current_contract, next_contract, 
                              current_close, next_close, current_perf, next_perf, 
                              relative_perf, smiley_status, total_sum=None):
        """Save daily performance to database"""
        try:
            conn = sqlite3.connect(self.daily_performance_db)
            cursor = conn.cursor()
            
            today = date.today()
            
            cursor.execute('''
                INSERT OR REPLACE INTO daily_performance 
                (date, commodity, current_month_contract, next_month_contract,
                 current_month_close, next_month_close, current_performance,
                 next_performance, relative_performance, smiley_status, total_sum)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (today, commodity, current_contract, next_contract,
                  current_close, next_close, current_perf, next_perf,
                  relative_perf, smiley_status, total_sum))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.log_message(f"Error saving daily performance: {e}")

    def get_historical_performance(self, commodity, days=7):
        """Get historical performance data"""
        try:
            conn = sqlite3.connect(self.daily_performance_db)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT date, current_performance, next_performance, 
                       relative_performance, smiley_status, total_sum
                FROM daily_performance 
                WHERE commodity = ?
                ORDER BY date DESC
                LIMIT ?
            ''', (commodity, days))
            
            results = cursor.fetchall()
            conn.close()
            
            return results
            
        except Exception as e:
            self.log_message(f"Error getting historical performance: {e}")
            return []

    def update_history_display(self, commodity):
        """Update historical performance display"""
        try:
            history_data = self.get_historical_performance(commodity, days=7)
            
            self.history_text.delete(1.0, tk.END)
            
            if not history_data:
                self.history_text.insert(tk.END, "No historical data available")
                return
            
            self.history_text.insert(tk.END, "Date       | Curr%  | Next%  | Rel%   | Total%  | Status\n")
            self.history_text.insert(tk.END, "-" * 60 + "\n")
            
            for record in history_data:
                date_str, curr_perf, next_perf, rel_perf, smiley, total_sum = record
                
                # Format date
                if isinstance(date_str, str):
                    display_date = date_str[:10]  # Take first 10 chars
                else:
                    display_date = str(date_str)[:10]
                
                # Format percentages
                curr_str = f"{curr_perf:+.1f}" if curr_perf is not None else "N/A"
                next_str = f"{next_perf:+.1f}" if next_perf is not None else "N/A"
                rel_str = f"{rel_perf:+.1f}" if rel_perf is not None else "N/A"
                total_str = f"{total_sum:+.1f}" if total_sum is not None else "N/A"
                
                # Add color tags based on smiley status
                line = f"{display_date} | {curr_str:6s} | {next_str:6s} | {rel_str:6s} | {total_str:7s} | {smiley}\n"
                
                self.history_text.insert(tk.END, line)
                
                # Apply colors based on total sum
                if total_sum is not None:
                    if total_sum > 2.0:
                        self.history_text.tag_add("dark_green", f"end-2l", f"end-1l")
                    elif total_sum > 0.5:
                        self.history_text.tag_add("green", f"end-2l", f"end-1l")
                    elif total_sum < -2.0:
                        self.history_text.tag_add("dark_red", f"end-2l", f"end-1l")
                    elif total_sum < -0.5:
                        self.history_text.tag_add("red", f"end-2l", f"end-1l")
                    else:
                        self.history_text.tag_add("orange", f"end-2l", f"end-1l")
                else:
                    self.history_text.tag_add("gray", f"end-2l", f"end-1l")
            
            # Configure text colors
            self.history_text.tag_config("dark_green", foreground="dark green")
            self.history_text.tag_config("green", foreground="green")
            self.history_text.tag_config("dark_red", foreground="dark red")
            self.history_text.tag_config("red", foreground="red")
            self.history_text.tag_config("orange", foreground="orange")
            self.history_text.tag_config("gray", foreground="gray")
            
        except Exception as e:
            self.log_message(f"Error updating history display: {e}")

    def center_window(self, window):
        """Center a window on screen"""
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        x = (window.winfo_screenwidth() // 2) - (width // 2)
        y = (window.winfo_screenheight() // 2) - (height // 2)
        window.geometry(f'{width}x{height}+{x}+{y}')

    def test_connection(self):
        """Test connection to Zerodha"""
        if not self.is_logged_in:
            messagebox.showinfo("Not Logged In", "Please login first")
            return
        
        try:
            profile = self.kite.profile()
            self.log_message(f"Connection test successful! User: {profile['user_name']}")
            messagebox.showinfo("Success", f"Connected to Zerodha as {profile['user_name']}")
        except Exception as e:
            self.log_message(f"Connection test failed: {e}")
            messagebox.showerror("Error", f"Connection failed: {e}")

    # Missing methods from previous implementations that need to be included
    def check_trigger_condition(self, current_change, next_change):
        """
        Check if next month's performance is significantly better than current month's
        Returns: (bool, float difference)
        """
        try:
            # Update threshold from GUI
            self.trigger_threshold = float(self.trigger_threshold_var.get())
            self.trigger_cooldown = int(self.cooldown_var.get())
            
            # Calculate difference
            difference = next_change - current_change
            
            # Check if next month is performing significantly better
            if difference > self.trigger_threshold:
                # Check cooldown
                current_time = time.time()
                if self.last_trigger_time is None or (current_time - self.last_trigger_time) > self.trigger_cooldown:
                    return True, difference
            return False, difference
            
        except ValueError:
            # If invalid threshold, use defaults
            if next_change - current_change > 0.5:
                current_time = time.time()
                if self.last_trigger_time is None or (current_time - self.last_trigger_time) > 60:
                    return True, next_change - current_change
            return False, next_change - current_change

    def test_triggered_popup(self):
        """Test the triggered popup display"""
        if not hasattr(self, 'current_month_contract') or not hasattr(self, 'next_month_contract'):
            messagebox.showerror("Error", "Please load contracts first")
            return
        
        # Simulate trigger condition
        current_change = -0.5  # Current month down 0.5%
        next_change = 1.5      # Next month up 1.5%
        difference = 2.0       # 2% difference
        
        self.show_triggered_popup(current_change, next_change, difference)

    def show_triggered_popup(self, current_change, next_change, difference):
        """Show triggered popup when next month is performing significantly better"""
        # Close existing popup if open
        if self.triggered_popup and self.triggered_popup.winfo_exists():
            self.triggered_popup.destroy()
        
        # Calculate total sum of changes
        total_sum = current_change + next_change
        
        # Create new popup window
        window = tk.Toplevel(self.root)
        window.title("🚨 ALERT: Next Month Outperforming!")
        window.geometry("500x450")
        #window.resizable(False, False)
        
        # Make window stay on top and give it focus
        window.attributes('-topmost', True)
        window.focus_force()
        
        # Play system beep
        window.bell()
        
        # Store reference
        self.triggered_popup = window
        
        # Set urgent color
        window.configure(bg='#FFE5E5')  # Light red background
        
        # Center window
        self.center_window(window)
        
        # Main frame
        main_frame = ttk.Frame(window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Header with alert symbol
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill='x', pady=10)
        
        alert_label = tk.Label(header_frame, text="⚠️", font=('Arial', 48), bg='#FFE5E5')
        alert_label.pack(side='left', padx=10)
        
        title_frame = ttk.Frame(header_frame)
        title_frame.pack(side='left', fill='y', padx=10)
        
        title_label = ttk.Label(title_frame, 
                               text="NEXT MONTH OUTPERFORMING!",
                               font=('Arial', 16, 'bold'),
                               foreground='red')
        title_label.pack(pady=5)
        
        subtitle_label = ttk.Label(title_frame,
                                  text=f"{self.month_commodity.get()} - Month Performance Alert",
                                  font=('Arial', 12))
        subtitle_label.pack()
        
        # Details frame
        details_frame = ttk.LabelFrame(main_frame, text="Performance Details")
        details_frame.pack(fill='both', expand=True, pady=10, padx=5)
        
        # Create a grid for details
        details_grid = ttk.Frame(details_frame)
        details_grid.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Current month performance
        ttk.Label(details_grid, text="Current Month:", font=('Arial', 11)).grid(row=0, column=0, sticky='w', pady=5)
        current_perf_label = ttk.Label(details_grid, 
                                      text=f"{current_change:+.2f}%",
                                      font=('Arial', 11, 'bold'),
                                      foreground='green' if current_change >= 0 else 'red')
        current_perf_label.grid(row=0, column=1, sticky='w', pady=5, padx=10)
        
        # Next month performance
        ttk.Label(details_grid, text="Next Month:", font=('Arial', 11)).grid(row=1, column=0, sticky='w', pady=5)
        next_perf_label = ttk.Label(details_grid,
                                   text=f"{next_change:+.2f}%",
                                   font=('Arial', 11, 'bold'),
                                   foreground='green' if next_change >= 0 else 'red')
        next_perf_label.grid(row=1, column=1, sticky='w', pady=5, padx=10)
        
        # Performance difference (highlighted)
        ttk.Label(details_grid, text="Performance Gap:", font=('Arial', 12, 'bold')).grid(row=2, column=0, sticky='w', pady=10)
        diff_label = ttk.Label(details_grid,
                              text=f"{difference:+.2f}%",
                              font=('Arial', 14, 'bold'),
                              foreground='green')
        diff_label.grid(row=2, column=1, sticky='w', pady=10, padx=10)
        
        # NEW: TOTAL SUM of changes
        ttk.Label(details_grid, text="TOTAL SUM of Changes:", 
                 font=('Arial', 12, 'bold')).grid(row=3, column=0, sticky='w', pady=10)
        total_sum_label = ttk.Label(details_grid,
                                   text=f"{total_sum:+.2f}%",
                                   font=('Arial', 14, 'bold'),
                                   foreground='blue' if total_sum > 0 else 'red' if total_sum < 0 else 'orange')
        total_sum_label.grid(row=3, column=1, sticky='w', pady=10, padx=10)
        
        # Contract names
        ttk.Label(details_grid, text="Current Contract:", font=('Arial', 10)).grid(row=4, column=0, sticky='w', pady=5)
        ttk.Label(details_grid, text=self.current_month_contract, font=('Arial', 10)).grid(row=4, column=1, sticky='w', pady=5, padx=10)
        
        ttk.Label(details_grid, text="Next Contract:", font=('Arial', 10)).grid(row=5, column=0, sticky='w', pady=5)
        ttk.Label(details_grid, text=self.next_month_contract, font=('Arial', 10)).grid(row=5, column=1, sticky='w', pady=5, padx=10)
        
        # Time of trigger
        trigger_time = datetime.now().strftime("%H:%M:%S")
        ttk.Label(details_grid, text="Trigger Time:", font=('Arial', 9)).grid(row=6, column=0, sticky='w', pady=5)
        ttk.Label(details_grid, text=trigger_time, font=('Arial', 9)).grid(row=6, column=1, sticky='w', pady=5, padx=10)
        
        # Message frame
        message_frame = ttk.Frame(main_frame)
        message_frame.pack(fill='x', pady=10)
        
        # Determine message based on total sum
        if total_sum > 2.0:
            message_text = "🔥 STRONG POSITIVE MOMENTUM: Both months up significantly!"
            total_color = 'dark green'
        elif total_sum > 0.5:
            message_text = "📈 Positive momentum: Total changes are positive"
            total_color = 'green'
        elif total_sum < -2.0:
            message_text = "⚠️ STRONG NEGATIVE MOMENTUM: Both months down significantly!"
            total_color = 'dark red'
        elif total_sum < -0.5:
            message_text = "📉 Negative momentum: Total changes are negative"
            total_color = 'red'
        else:
            message_text = "⚖️ Mixed signals: Months moving in opposite directions"
            total_color = 'orange'
        
        total_message = ttk.Label(message_frame,
                                 text=f"Total Sum: {total_sum:+.2f}%",
                                 font=('Arial', 11, 'bold'),
                                 foreground=total_color)
        total_message.pack(pady=5)
        
        message_label = ttk.Label(message_frame,
                                 text=message_text,
                                 font=('Arial', 11, 'italic'),
                                 foreground=total_color,
                                 wraplength=400,
                                 justify='center')
        message_label.pack(pady=5)
        
        # Action buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        # Show detailed comparison button
        ttk.Button(button_frame, text="Show Detailed Comparison",
                  command=self.show_comparison_popup).pack(side='left', padx=5)
        
        # NEW: Show Price Difference button
        ttk.Button(button_frame, text="Show Price Difference",
                  command=self.show_price_difference_popup).pack(side='left', padx=5)
        
        # Acknowledge button
        ttk.Button(button_frame, text="Acknowledge",
                  command=lambda: self.acknowledge_trigger(window)).pack(side='right', padx=5)
        
        # Mute button
        ttk.Button(button_frame, text="Mute Alerts for 5 min",
                  command=lambda: self.mute_alerts(300, window)).pack(side='right', padx=5)
        
        # Log this trigger
        self.log_message(f"🚨 TRIGGER: Next month outperforming by {difference:.2f}% (Total: {total_sum:+.2f}%)")
        
        # Update trigger time
        self.last_trigger_time = time.time()
        
        # Handle window close
        window.protocol("WM_DELETE_WINDOW", lambda: self.acknowledge_trigger(window))

    def acknowledge_trigger(self, window):
        """Acknowledge and close triggered popup"""
        window.destroy()
        self.triggered_popup = None
        self.trigger_status_label.config(text="Trigger Status: Acknowledged", foreground='orange')
        
        # Reset status after 10 seconds
        self.root.after(10000, lambda: self.trigger_status_label.config(
            text="Trigger Status: Ready", 
            foreground='green'
        ))

    def mute_alerts(self, seconds, window):
        """Mute alerts for specified number of seconds"""
        self.trigger_cooldown = seconds
        self.last_trigger_time = time.time()
        
        # Close window
        window.destroy()
        self.triggered_popup = None
        
        # Update status
        minutes = seconds // 60
        self.trigger_status_label.config(
            text=f"Trigger Status: Muted for {minutes} min", 
            foreground='gray'
        )
        
        self.log_message(f"🔕 Alerts muted for {minutes} minutes")
        
        # Reset after cooldown
        self.root.after(seconds * 1000, lambda: self.reset_mute())

    def reset_mute(self):
        """Reset mute status"""
        try:
            self.trigger_cooldown = int(self.cooldown_var.get())
            self.trigger_status_label.config(text="Trigger Status: Ready", foreground='green')
            self.log_message("🔔 Alerts unmuted")
        except ValueError:
            self.trigger_cooldown = 60
            self.trigger_status_label.config(text="Trigger Status: Ready", foreground='green')

    def show_comparison_popup(self):
        """Show common popup with both Current and Next Month contract changes"""
        if not hasattr(self, 'current_month_contract') or not hasattr(self, 'next_month_contract'):
            messagebox.showerror("Error", "Please load contracts first")
            return
        
        # Close existing popup if open
        if self.comparison_popup and self.comparison_popup.winfo_exists():
            self.comparison_popup.destroy()
        
        # Create new window
        window = tk.Toplevel(self.root)
        window.title(f"📊 {self.month_commodity.get()} - Month Comparison")
        window.geometry("600x550")  # Increased height for total changes
        #window.resizable(False, False)
        
        # Make window stay on top
        window.attributes('-topmost', True)
        
        # Store reference
        self.comparison_popup = window
        
        # Center window
        self.center_window(window)
        
        # Main frame
        main_frame = ttk.Frame(window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Title
        title_label = ttk.Label(main_frame, 
                               text=f"{self.month_commodity.get()} - Month Comparison", 
                               font=('Arial', 16, 'bold'))
        title_label.pack(pady=5)
        
        subtitle_label = ttk.Label(main_frame, 
                                  text="Changes from Previous Day Close",
                                  font=('Arial', 12))
        subtitle_label.pack(pady=2)
        
        # Current date/time
        self.popup_timestamp = ttk.Label(main_frame, 
                                        text=f"Last update: {datetime.now().strftime('%H:%M:%S')}",
                                        font=('Arial', 9))
        self.popup_timestamp.pack(pady=5)
        
        # Create a container for both contracts
        contracts_frame = ttk.Frame(main_frame)
        contracts_frame.pack(fill='both', expand=True, pady=10)
        
        # Left side - Current Month
        current_frame = ttk.LabelFrame(contracts_frame, text="Current Month")
        current_frame.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        
        # Current Month header
        ttk.Label(current_frame, text=self.current_month_contract, 
                 font=('Arial', 12, 'bold')).pack(pady=10)
        
        # Current Price
        self.popup_current_price = ttk.Label(current_frame, text="₹--", 
                                            font=('Arial', 20, 'bold'))
        self.popup_current_price.pack(pady=5)
        
        # Previous Close
        prev_frame = ttk.Frame(current_frame)
        prev_frame.pack(fill='x', pady=5)
        ttk.Label(prev_frame, text="Prev Close:").pack(side='left')
        self.popup_current_prev = ttk.Label(prev_frame, text="₹--", 
                                           font=('Arial', 10))
        self.popup_current_prev.pack(side='left', padx=5)
        
        # Change in Rupees
        change_frame = ttk.LabelFrame(current_frame, text="Change (₹)")
        change_frame.pack(fill='x', pady=10, padx=10)
        
        self.popup_current_rupee_change = ttk.Label(change_frame, text="₹--", 
                                                   font=('Arial', 18, 'bold'))
        self.popup_current_rupee_change.pack(pady=10)
        
        # Percentage change
        self.popup_current_percent = ttk.Label(current_frame, text="(--%)", 
                                              font=('Arial', 14))
        self.popup_current_percent.pack(pady=5)
        
        # Status indicator
        self.popup_current_status = ttk.Label(current_frame, text="--", 
                                             font=('Arial', 12, 'bold'))
        self.popup_current_status.pack(pady=5)
        
        # Right side - Next Month
        next_frame = ttk.LabelFrame(contracts_frame, text="Next Month")
        next_frame.pack(side='right', fill='both', expand=True, padx=5, pady=5)
        
        # Next Month header
        ttk.Label(next_frame, text=self.next_month_contract, 
                 font=('Arial', 12, 'bold')).pack(pady=10)
        
        # Next Price
        self.popup_next_price = ttk.Label(next_frame, text="₹--", 
                                         font=('Arial', 20, 'bold'))
        self.popup_next_price.pack(pady=5)
        
        # Previous Close
        next_prev_frame = ttk.Frame(next_frame)
        next_prev_frame.pack(fill='x', pady=5)
        ttk.Label(next_prev_frame, text="Prev Close:").pack(side='left')
        self.popup_next_prev = ttk.Label(next_prev_frame, text="₹--", 
                                        font=('Arial', 10))
        self.popup_next_prev.pack(side='left', padx=5)
        
        # Change in Rupees
        next_change_frame = ttk.LabelFrame(next_frame, text="Change (₹)")
        next_change_frame.pack(fill='x', pady=10, padx=10)
        
        self.popup_next_rupee_change = ttk.Label(next_change_frame, text="₹--", 
                                                font=('Arial', 18, 'bold'))
        self.popup_next_rupee_change.pack(pady=10)
        
        # Percentage change
        self.popup_next_percent = ttk.Label(next_frame, text="(--%)", 
                                           font=('Arial', 14))
        self.popup_next_percent.pack(pady=5)
        
        # Status indicator
        self.popup_next_status = ttk.Label(next_frame, text="--", 
                                          font=('Arial', 12, 'bold'))
        self.popup_next_status.pack(pady=5)
        
        # Comparison Frame (Bottom)
        comparison_frame = ttk.LabelFrame(main_frame, text="Month Comparison")
        comparison_frame.pack(fill='x', pady=15, padx=10)
        
        # Price Difference
        self.popup_price_diff = ttk.Label(comparison_frame, 
                                         text="Next month is ₹-- higher",
                                         font=('Arial', 12, 'bold'))
        self.popup_price_diff.pack(pady=5)
        
        # Performance Difference
        self.popup_perf_diff = ttk.Label(comparison_frame, 
                                        text="Performance difference: --%",
                                        font=('Arial', 11))
        self.popup_perf_diff.pack(pady=2)
        
        # NEW: Price Difference in Rupees (Current Change - Next Change)
        self.popup_price_diff_rupees = ttk.Label(comparison_frame,
                                                text="Price Difference (₹): --",
                                                font=('Arial', 11))
        self.popup_price_diff_rupees.pack(pady=2)
        
        # TOTAL SUM of changes
        self.popup_total_sum = ttk.Label(comparison_frame,
                                        text="TOTAL SUM of Changes: --%",
                                        font=('Arial', 11, 'bold'))
        self.popup_total_sum.pack(pady=2)
        
        # Smiley indicator
        self.popup_smiley = tk.Label(comparison_frame, text="😐", 
                                    font=('Arial', 36))
        self.popup_smiley.pack(pady=5)
        
        # Status text
        self.popup_status_text = ttk.Label(comparison_frame, text="--", 
                                          font=('Arial', 11))
        self.popup_status_text.pack(pady=2)
        
        # Close button
        ttk.Button(main_frame, text="Close", 
                  command=lambda: self.on_comparison_popup_close(window)).pack(pady=10)
        
        # NEW: Price Difference button
        ttk.Button(main_frame, text="Show Price Difference Details",
                  command=self.show_price_difference_popup).pack(pady=5)
        
        # Handle window close
        window.protocol("WM_DELETE_WINDOW", lambda: self.on_comparison_popup_close(window))
        
        # Start updates
        self.start_comparison_popup_updates(window)

    def start_comparison_popup_updates(self, window):
        """Start updating comparison popup window"""
        def update_popup():
            if not window.winfo_exists():
                return
            
            try:
                # Get current prices
                contracts = [self.current_month_contract, self.next_month_contract]
                instruments = [f"MCX:{contract}" for contract in contracts]
                
                quote_data = self.kite.quote(instruments)
                
                current_price = quote_data[f"MCX:{self.current_month_contract}"]['last_price']
                next_price = quote_data[f"MCX:{self.next_month_contract}"]['last_price']
                
                # Get PREVIOUS DAY CLOSE prices
                current_prev = self.previous_day_close_prices.get(self.current_month_contract, current_price)
                next_prev = self.previous_day_close_prices.get(self.next_month_contract, next_price)
                
                # Update the popup display
                self.update_comparison_popup_display(window, current_price, next_price, current_prev, next_prev)
                
            except Exception as e:
                print(f"Error updating comparison popup: {e}")
            
            # Schedule next update
            if window.winfo_exists():
                window.after(2000, update_popup)
        
        # Start updates
        window.after(1000, update_popup)

    def update_comparison_popup_display(self, window, current_price, next_price, current_prev, next_prev):
        """Update comparison popup with all data"""
        try:
            # Calculate changes for Current Month
            current_change = current_price - current_prev
            current_percent = ((current_price - current_prev) / current_prev * 100) if current_prev > 0 else 0
            
            # Calculate changes for Next Month
            next_change = next_price - next_prev
            next_percent = ((next_price - next_prev) / next_prev * 100) if next_prev > 0 else 0
            
            # Calculate price difference between months
            price_diff = next_price - current_price
            perf_diff = next_percent - current_percent
            
            # NEW: Calculate price difference in rupees (Current Change - Next Change)
            price_diff_rupees = current_change - next_change
            
            # Calculate total sum of changes
            total_sum = current_percent + next_percent
            
            # Update timestamp
            self.popup_timestamp.config(text=f"Last update: {datetime.now().strftime('%H:%M:%S')}")
            
            # Update Current Month section
            self.update_contract_section(
                price=current_price,
                prev_price=current_prev,
                rupee_change=current_change,
                percent_change=current_percent,
                is_current=True
            )
            
            # Update Next Month section
            self.update_contract_section(
                price=next_price,
                prev_price=next_prev,
                rupee_change=next_change,
                percent_change=next_percent,
                is_current=False
            )
            
            # Update comparison section (including total sum and price difference)
            self.update_comparison_section(price_diff, perf_diff, current_percent, next_percent, 
                                         total_sum, current_change, next_change, price_diff_rupees)
            
        except Exception as e:
            print(f"Error updating comparison popup display: {e}")

    def update_contract_section(self, price, prev_price, rupee_change, percent_change, is_current=True):
        """Update a contract section in the popup"""
        try:
            # Determine colors and status
            if rupee_change > 0:
                price_color = 'green'
                status_text = "▲ UP"
                change_text = f"+₹{abs(rupee_change):.2f}"
            elif rupee_change < 0:
                price_color = 'red'
                status_text = "▼ DOWN"
                change_text = f"-₹{abs(rupee_change):.2f}"
            else:
                price_color = 'orange'
                status_text = "⏺ FLAT"
                change_text = "₹0.00"
            
            # Format percentage
            percent_text = f"({percent_change:+.2f}%)"
            
            if is_current:
                # Update Current Month widgets
                self.popup_current_price.config(
                    text=f"₹{price:,.2f}",
                    foreground=price_color
                )
                self.popup_current_prev.config(
                    text=f"₹{prev_price:,.2f}",
                    foreground='gray'
                )
                self.popup_current_rupee_change.config(
                    text=change_text,
                    foreground=price_color
                )
                self.popup_current_percent.config(
                    text=percent_text,
                    foreground=price_color
                )
                self.popup_current_status.config(
                    text=status_text,
                    foreground=price_color
                )
            else:
                # Update Next Month widgets
                self.popup_next_price.config(
                    text=f"₹{price:,.2f}",
                    foreground=price_color
                )
                self.popup_next_prev.config(
                    text=f"₹{prev_price:,.2f}",
                    foreground='gray'
                )
                self.popup_next_rupee_change.config(
                    text=change_text,
                    foreground=price_color
                )
                self.popup_next_percent.config(
                    text=percent_text,
                    foreground=price_color
                )
                self.popup_next_status.config(
                    text=status_text,
                    foreground=price_color
                )
                
        except Exception as e:
            print(f"Error updating contract section: {e}")

    def update_comparison_section(self, price_diff, perf_diff, current_percent, next_percent, 
                                total_sum, current_change_rupees, next_change_rupees, price_diff_rupees):
        """Update the comparison section in the popup"""
        try:
            # Determine colors for price difference
            if price_diff > 0:
                diff_color = 'green'
                diff_text = f"Next month is ₹{abs(price_diff):.2f} HIGHER"
            elif price_diff < 0:
                diff_color = 'red'
                diff_text = f"Next month is ₹{abs(price_diff):.2f} LOWER"
            else:
                diff_color = 'orange'
                diff_text = "Months are SAME PRICE"
            
            # Update price difference
            self.popup_price_diff.config(
                text=diff_text,
                foreground=diff_color
            )
            
            # Update performance difference
            perf_text = f"Performance difference: {perf_diff:+.2f}%"
            self.popup_perf_diff.config(
                text=perf_text,
                foreground=diff_color
            )
            
            # NEW: Update price difference in rupees
            price_diff_color = 'green' if price_diff_rupees > 0 else 'red' if price_diff_rupees < 0 else 'orange'
            price_diff_text = f"Price Difference (₹): {price_diff_rupees:+.2f}"
            self.popup_price_diff_rupees.config(
                text=price_diff_text,
                foreground=price_diff_color
            )
            
            # Update total sum of changes
            # Determine color for total sum
            if total_sum > 2.0:
                total_color = 'dark green'
                total_emoji = "🚀"
            elif total_sum > 0.5:
                total_color = 'green'
                total_emoji = "📈"
            elif total_sum < -2.0:
                total_color = 'dark red'
                total_emoji = "⚠️"
            elif total_sum < -0.5:
                total_color = 'red'
                total_emoji = "📉"
            else:
                total_color = 'orange'
                total_emoji = "⚖️"
            
            total_text = f"{total_emoji} TOTAL SUM of Changes: {total_sum:+.2f}%"
            self.popup_total_sum.config(
                text=total_text,
                foreground=total_color
            )
            
            # Determine smiley based on performance
            next_up = next_percent > 0
            current_down = current_percent < 0
            
            if next_up and current_down:
                # Best case: next month up, current month down
                smiley = "😊"
                smiley_color = 'green'
                status_text = "📈 Next UP, Current DOWN"
                bg_color = 'light green'
            elif perf_diff > 0.5:
                # Next month performing better by 0.5%
                smiley = "😊"
                smiley_color = 'green'
                status_text = f"📈 Next month +{perf_diff:.2f}% better"
                bg_color = 'light green'
            elif perf_diff < -0.5:
                # Current month performing better
                smiley = "☹️"
                smiley_color = 'red'
                status_text = f"📉 Current month +{abs(perf_diff):.2f}% better"
                bg_color = 'light coral'
            else:
                # Similar performance
                smiley = "😐"
                smiley_color = 'orange'
                status_text = "⚖️ Months similar performance"
                bg_color = 'light yellow'
            
            # Update smiley and status
            self.popup_smiley.config(
                text=smiley,
                fg=smiley_color
            )
            self.popup_status_text.config(
                text=status_text,
                foreground=smiley_color
            )
            
            # Update window background based on total sum
            if self.comparison_popup and self.comparison_popup.winfo_exists():
                if total_sum > 2.0:
                    self.comparison_popup.configure(bg='#E8F5E9')  # Very light green
                elif total_sum > 0.5:
                    self.comparison_popup.configure(bg='#F1F8E9')  # Light green
                elif total_sum < -2.0:
                    self.comparison_popup.configure(bg='#FFEBEE')  # Very light red
                elif total_sum < -0.5:
                    self.comparison_popup.configure(bg='#FFE5E5')  # Light red
                else:
                    self.comparison_popup.configure(bg='light yellow')
                
            # Visual effect for significant differences
            if abs(total_sum) > 3.0:
                current_bg = self.popup_smiley.cget('bg')
                self.popup_smiley.config(
                    bg='gold' if current_bg == 'SystemButtonFace' else 'SystemButtonFace'
                )
                if self.comparison_popup and self.comparison_popup.winfo_exists():
                    self.comparison_popup.after(500, 
                        lambda: self.popup_smiley.config(bg='SystemButtonFace'))
            
        except Exception as e:
            print(f"Error updating comparison section: {e}")

    def on_comparison_popup_close(self, window):
        """Handle comparison popup window close"""
        window.destroy()
        self.comparison_popup = None

def main():
    root = tk.Tk()
    app = ZerodhaTradingApp(root)
    create_initial_file()
    root.mainloop()
    

if __name__ == "__main__":
    main()

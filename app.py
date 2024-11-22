import os
import tkinter as tk
import json
import logging
import time
import ollama

from tkinter import ttk, filedialog, scrolledtext
from tkinterdnd2 import TkinterDnD, DND_FILES

from PyThreadKiller import PyThreadKiller
from datetime import datetime
from queue import Queue, Empty
from typing import Dict, Any

from utils import (
    process_chunks,
    parse_metadata,
    read_epub,
    save_api_keys_to_file,
    encrypt_api_key,
    decrypt_api_key,
    load_daily_requests,
    save_daily_requests,
    seconds_to_time,
    float_to_cost,
    convert_to_readable_time,
)


class LoadingWheel(tk.Canvas):
    def __init__(self, master, size=20, width=2, color="#4c525e"):
        try:
            bg_color = master.cget("bg")
        except tk.TclError:
            bg_color = "#282c34"

        super().__init__(
            master, width=size, height=size, bg=bg_color, highlightthickness=0
        )
        self.size = size
        self.center = size // 2
        self.arc_extent = 60
        self.arc = self.create_arc(
            2,
            2,
            size - 2,
            size - 2,
            start=0,
            extent=self.arc_extent,
            width=width,
            outline=color,
            style=tk.ARC,
        )
        self.angle = 0
        self.is_running = False

    def start(self):
        self.is_running = True
        self._animate()

    def stop(self):
        self.is_running = False

    def _animate(self):
        if self.is_running:
            self.angle = (self.angle + 10) % 360
            self.itemconfigure(self.arc, start=self.angle)
            self.after(50, self._animate)

    def set_color(self, color):
        self.itemconfigure(self.arc, outline=color)


class BookSummarizerGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("Book Summarizer")
        self.master.geometry("800x650")
        self.daily_requests = load_daily_requests()
        self.load_ai_config()
        self.encrypted_api_keys = {}
        self.load_api_keys()

        self.master.configure(background="#282c34")
        style = ttk.Style()
        style.theme_use("clam")

        self.animate_loading_wheel = False

        style.configure(
            ".",
            background="#282c34",
            foreground="#abb2bf",
            fieldbackground="#3e4451",
            selectbackground="#565c64",
            insertbackground="#abb2bf",
            selectforeground="#abb2bf",
        )
        style.configure(
            "TButton",
            background="#3e4451",
            foreground="#abb2bf",
            activebackground="#4c525e",
            activeforeground="#abb2bf",
            relief="flat",
            borderwidth=0,
        )

        style.configure(
            "TCheckbutton",
            background="#282c34",
            foreground="#abb2bf",
            indicatorcolor="#3e4451",
            selectcolor="#565c64",
        )
        style.map("TCheckbutton", background=[("active", "#282c34")])
        style.map(
            "TButton",
            background=[("active", "#4c525e")],
            foreground=[("disabled", "#6c757d")],
        )
        style.configure("TLabel", background="#282c34", foreground="#abb2bf")
        style.configure(
            "TCombobox",
            fieldbackground="#3e4451",
            selectbackground="#565c64",
            arrowcolor="#abb2bf",
            foreground="#abb2bf",
            lightcolor="#3e4451",
            darkcolor="#3e4451",
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#3e4451")],
            selectbackground=[("readonly", "#565c64")],
            arrowcolor=[("disabled", "#6c757d")],
        )
        style.configure(
            "Treeview.Heading",
            background="#282c34",
            foreground="#abb2bf",
            indicatorcolor="#3e4451",
            selectcolor="#565c64",
        )
        style.configure(
            "Horizontal.TScale", background="#282c34", troughcolor="#3e4451"
        )
        style.configure(
            "Borderless.TFrame", background="#3e4451", borderwidth=0, relief="flat"
        )

        style.map(
            "Treeview.Heading",
            background=[("active", "#4c525e")],
            foreground=[("active", "#abb2bf")],
            relief=[("active", "flat")],
        )

        style.map(
            "Treeview.Heading",
            background=[("pressed", "#4c525e")],
            foreground=[("pressed", "#abb2bf")],
            relief=[("pressed", "flat")],
        )
        style.configure("TProgressbar", background="#565c64", troughcolor="#3e4451")
        style.configure(
            "TScrollbar",
            background="#3e4451",
            troughcolor="#282c34",
            arrowcolor="#abb2bf",
            borderwidth=0,
        )
        style.map("TScrollbar", background=[("active", "#4c525e")])

        self.file_listbox_style = ttk.Style()
        self.file_listbox_style.configure(
            "My.TListbox",
            background="#3e4451",
            foreground="#abb2bf",
            selectbackground="#565c64",
            selectforeground="#abb2bf",
        )

        self.console_text_style = ttk.Style()
        self.console_text_style.configure(
            "My.TText",
            background="#3e4451",
            foreground="#abb2bf",
            insertbackground="#abb2bf",
            wrap=tk.WORD,
        )

        self.processed_basenames = {}

        self.processed_books = set()
        self.aborted_books = set()

        self.create_widgets()

        self.processing_queue = Queue()
        self.current_book = 0
        self.total_books = 0
        self.update_time_thread = None
        self.start_processing_thread = None

        self.master.after(100, self.check_queue)

        self.file_paths = {}

    def load_ai_config(self):
        config_path = os.path.join(
            os.path.dirname(__file__), "ai_providers_config.json"
        )
        with open(config_path, "r") as config_file:
            self.ai_config = json.load(config_file)

    def create_widgets(self):

        self.select_frame = ttk.Frame(self.master)
        self.select_frame.grid(
            row=0, column=0, columnspan=3, pady=10, padx=10, sticky="ew"
        )

        ttk.Button(
            self.select_frame, text="Select Files", command=self.select_files
        ).grid(row=0, column=0, padx=5, sticky="ew")
        ttk.Button(
            self.select_frame, text="Select Folder", command=self.select_folder
        ).grid(row=0, column=1, padx=5, sticky="ew")
        self.remove_selected_button = ttk.Button(
            self.select_frame,
            text="Remove Selected",
            command=self.remove_selected_files,
        )
        self.remove_selected_button.grid(row=0, column=2, padx=5, sticky="ew")
        self.clear_list_button = ttk.Button(
            self.select_frame, text="Clear List", command=self.clear_file_list
        )
        self.clear_list_button.grid(row=0, column=3, padx=5, sticky="ew")

        self.book_count_label = ttk.Label(self.select_frame, text="Books Added: 0")
        self.book_count_label.grid(row=0, column=4, padx=5, sticky="e")

        self.api_keys_button = ttk.Button(
            self.select_frame, text="Manage API Keys", command=self.manage_api_keys
        )
        self.api_keys_button.grid(row=0, column=5, padx=5, sticky="e")

        self.file_list_frame = ttk.Frame(self.master)
        self.file_list_frame.grid(
            row=1, column=0, columnspan=3, pady=10, padx=10, sticky="nsew"
        )

        self.file_listbox_style = ttk.Style()
        self.file_listbox_style.configure(
            "My.Treeview",
            background="#3e4451",
            foreground="#abb2bf",
            selectbackground="#565c64",
            selectforeground="#abb2bf",
            fieldbackground="#3e4451",
        )

        self.file_listbox = ttk.Treeview(
            self.file_list_frame,
            style="My.Treeview",
            show="headings",
            selectmode=tk.EXTENDED,
        )
        self.file_listbox["columns"] = (
            "file_path",
            "chunk_progress",
            "processing_time",
        )

        self.file_listbox.heading("file_path", text="File/s", command=lambda: None)
        self.file_listbox.heading(
            "chunk_progress", text="Progress", command=lambda: None
        )
        self.file_listbox.heading(
            "processing_time", text="Processing Time", command=lambda: None
        )

        self.file_listbox.column("file_path", width=300)
        self.file_listbox.column("chunk_progress", width=250)
        self.file_listbox.column("processing_time", width=50)

        self.file_listbox.grid(row=0, column=0, sticky="nsew")

        self.scrollbar = ttk.Scrollbar(
            self.file_list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_listbox.config(yscrollcommand=self.scrollbar.set)

        self.file_listbox.bind("<Double-1>", self.open_summary_file)

        self.file_listbox.drop_target_register(DND_FILES)
        self.file_listbox.dnd_bind("<<Drop>>", self.on_drop)

        self.drag_drop_frame = ttk.Frame(
            self.file_list_frame, style="Borderless.TFrame"
        )
        self.drag_drop_frame.place(relx=0.5, rely=0.5, anchor="center")

        self.drag_drop_label = ttk.Label(
            self.drag_drop_frame,
            text="Drag and drop files here",
            foreground="#abb2bf",
            background="#3e4451",
            font=("TkDefaultFont", 14, "bold"),
        )
        self.drag_drop_label.pack(pady=20, padx=20)

        self.update_drag_drop_label()

        self.provider_frame = ttk.Frame(self.master)
        self.provider_frame.grid(
            row=2, column=0, columnspan=3, pady=10, padx=10, sticky="ew"
        )

        ttk.Label(self.provider_frame, text="AI Provider:").grid(
            row=0, column=0, padx=5, sticky="w"
        )
        self.provider_var = tk.StringVar()
        self.provider_combobox = ttk.Combobox(
            self.provider_frame, textvariable=self.provider_var, state="readonly"
        )
        self.provider_combobox["values"] = [
            provider["name"] for provider in self.ai_config["providers"]
        ]
        self.provider_combobox.grid(row=0, column=1, padx=5, sticky="ew")
        self.provider_combobox.bind("<<ComboboxSelected>>", self.update_model_options)

        ttk.Label(self.provider_frame, text="Model:").grid(
            row=0, column=2, padx=5, sticky="w"
        )
        self.model_var = tk.StringVar()
        self.model_combobox = ttk.Combobox(
            self.provider_frame, textvariable=self.model_var, state="readonly"
        )
        self.model_combobox.grid(row=0, column=3, padx=5, sticky="ew")
        self.model_combobox.bind("<<ComboboxSelected>>", self.model_selected)

        ttk.Label(self.provider_frame, text="Temperature:").grid(
            row=0, column=4, padx=5, sticky="w"
        )
        self.temperature_var = tk.DoubleVar(value=0.2)
        self.temperature_slider = ttk.Scale(
            self.provider_frame,
            from_=0.0,
            to=1.0,
            style="Horizontal.TScale",
            orient=tk.HORIZONTAL,
            variable=self.temperature_var,
            length=200,
            command=self.update_temperature_label,
        )
        self.temperature_slider.grid(row=0, column=5, padx=5, sticky="ew")
        self.temperature_label = ttk.Label(
            self.provider_frame, textvariable=self.temperature_var
        )
        self.temperature_label.grid(row=0, column=6, padx=5, sticky="w")

        self.process_frame = ttk.Frame(self.master)
        self.process_frame.grid(
            row=3, column=0, columnspan=3, pady=10, padx=10, sticky="ew"
        )

        self.process_button = ttk.Button(
            self.process_frame,
            text="Process Books",
            command=self.start_processing,
        )
        self.process_button.grid(row=0, column=0, padx=10, sticky="ew")

        self.estimated_time_frame = ttk.Frame(
            self.process_frame, width=305, height=20
        )
        self.estimated_time_frame.grid(row=0, column=1, padx=10, sticky="ew")

        self.estimated_time_frame.grid_propagate(False)

        self.estimated_time_label = ttk.Label(
            self.estimated_time_frame, text="Estimated requests: N/A"
        )
        self.estimated_time_label.grid()

        self.loading_wheel = LoadingWheel(
            self.estimated_time_frame, size=20, width=2, color="#abb2bf"
        )
        
        ttk.Label(self.process_frame, text="Max tokens:").grid(
            row=0, column=2, padx=5, sticky="w"
        )
        
        self.max_tokens_var = tk.DoubleVar(value=32768)
        self.tokens_slider = ttk.Scale(
            self.process_frame,
            from_=8192,
            to=32768,
            style="Horizontal.TScale",
            orient=tk.HORIZONTAL,
            variable=self.max_tokens_var,
            length=200,
        )
        self.tokens_slider.grid(row=0, column=3, padx=5, sticky="ew")
        
        self.tokens_slider.bind("<ButtonRelease-1>", self.on_slider_release)
        
        self.tokens_label = ttk.Label(
            self.process_frame, textvariable=self.max_tokens_var
        )
        self.tokens_label.grid(row=0, column=4, padx=5, sticky="w")

        self.progress_frame = ttk.Frame(self.master)
        self.progress_frame.grid(
            row=4, column=0, columnspan=3, pady=10, padx=10, sticky="ew"
        )

        ttk.Label(self.progress_frame, text="Overall Progress:").grid(
            row=0, column=0, padx=5, sticky="w"
        )
        self.overall_progress_bar = ttk.Progressbar(
            self.progress_frame, orient=tk.HORIZONTAL, length=200, mode="determinate"
        )
        self.overall_progress_bar.grid(row=0, column=1, sticky="ew")
        self.progress_percentage_label = ttk.Label(self.progress_frame, text="0%")
        self.progress_percentage_label.grid(row=0, column=2, padx=5, sticky="w")

        self.stop_button = ttk.Button(
            self.progress_frame,
            text="Stop Processing",
            command=self.stop_processing,
            state=tk.DISABLED,
        )
        self.stop_button.grid(row=0, column=3, padx=10, sticky="ew")

        self.open_summaries_button = ttk.Button(
            self.progress_frame,
            text="Open Summaries Folder",
            command=self.open_summaries_folder,
        )
        self.open_summaries_button.grid(row=0, column=4, padx=10, sticky="ew")

        self.clear_console_button = ttk.Button(
            self.progress_frame,
            text="Clear console output",
            command=self.clear_console,
        )
        self.clear_console_button.grid(row=0, column=5, padx=10, sticky="ew")

        self.console_frame = ttk.Frame(self.master)
        self.console_frame.grid(
            row=5, column=0, columnspan=3, pady=10, padx=10, sticky="nsew"
        )

        self.console = scrolledtext.ScrolledText(
            self.console_frame,
            state=tk.DISABLED,
            wrap=tk.WORD,
            bg="#3e4451",
            fg="#abb2bf",
        )
        self.console.grid(row=0, column=0, sticky="nsew")

        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(1, weight=1, minsize=300)
        self.master.rowconfigure(5, weight=1, minsize=150)
        self.file_list_frame.columnconfigure(0, weight=1)
        self.file_list_frame.rowconfigure(0, weight=1)
        self.console_frame.columnconfigure(0, weight=1)
        self.console_frame.rowconfigure(0, weight=1)
        
    def on_slider_release(self, event):
        # pass the slider value to the update_tokens_label function
        self.update_tokens_label(self.tokens_slider.get())
        
    def model_selected(self, event):
        # update the max tokens slider max value based on the selected model max tokens setting
        provider_name = self.provider_var.get()
        model_name = self.model_var.get()
        model_info = self.get_model_info(model_name, provider_name)
        max_tokens = model_info.get("max_tokens", 32768) # default to 32k
        self.tokens_slider.configure(to=max_tokens)
        self.max_tokens_var.set(max_tokens)
        self.update_estimated_time()

    def open_summary_file(self, event):
        selected_item = self.file_listbox.selection()
        if selected_item:
            item_values = self.file_listbox.item(selected_item, "values")
            file_path = item_values[0]
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            summary_path = self.processed_basenames.get(base_name)
            if summary_path and os.path.exists(summary_path):
                try:
                    os.startfile(summary_path)
                except Exception as e:
                    self.console_print(f"Failed to open summary file: {e}")
            else:
                self.console_print(f"Summary file not found for {file_path}")

    def manage_api_keys(self):
        manage_window = tk.Toplevel(self.master)
        manage_window.title("Manage API Keys")
        manage_window.configure(background="#282c34")
        providers = [
            x for x in self.ai_config["providers"] if x["name"] not in ["ollama", "lmstudio"]
        ]

        for i, provider in enumerate(providers):
            label = ttk.Label(
                manage_window,
                text=f"API Key for {provider['name']}:",
                background="#282c34",
                foreground="#abb2bf",
            )
            label.grid(row=i, column=0, padx=5, pady=5)

            entry = ttk.Entry(manage_window, width=40)
            entry.grid(row=i, column=1, padx=5, pady=5)

            # Check if the provider has an API key
            if provider.get("api_key"):
                try:
                    decrypted_key = decrypt_api_key(provider["api_key"])
                    entry.insert(0, decrypted_key)
                except Exception as e:
                    print(f"Error decrypting key for {provider['name']}: {e}")

            show_hide_var = tk.BooleanVar(value=False)
            show_hide_check = ttk.Checkbutton(
                manage_window,
                text="Show",
                variable=show_hide_var,
                command=lambda e=entry, v=show_hide_var: self.toggle_show_hide(e, v),
            )
            show_hide_check.grid(row=i, column=2, padx=5, pady=5)
            self.toggle_show_hide(entry, show_hide_var)

            provider["entry"] = entry
            provider["show_hide_var"] = show_hide_var

        self.save_apis_keys_button = ttk.Button(manage_window, text="Save", command=self.save_api_keys_thread)
        self.save_apis_keys_button.grid(row=len(providers), column=0, columnspan=3, pady=10)

    def toggle_show_hide(self, entry, show_hide_var):
        entry.config(show="" if show_hide_var.get() else "*")

    def save_api_keys_thread(self):
        PyThreadKiller(target=self.save_api_keys).start()

    def save_api_keys(self):
        self.save_apis_keys_button.config(state=tk.DISABLED)
        for provider in [
            x for x in self.ai_config["providers"] if x["name"] not in ["ollama", "lmstudio"]
        ]:
            api_key = provider["entry"].get()
            if api_key:  # Only encrypt and save non-empty keys
                encrypted_key = encrypt_api_key(api_key)
                provider["api_key"] = encrypted_key
                self.encrypted_api_keys[provider["name"]] = encrypted_key

        save_api_keys_to_file(self.encrypted_api_keys)
        time.sleep(0.5)
        self.save_apis_keys_button.config(state=tk.NORMAL)

    def load_api_keys(self):
        if os.path.exists("api_keys.json"):
            with open("api_keys.json", "r") as file:
                self.encrypted_api_keys = json.load(file)
                for i, provider in enumerate(self.ai_config["providers"]):
                    if provider["name"] in self.encrypted_api_keys:
                        provider["api_key"] = self.encrypted_api_keys[provider["name"]]
                        self.ai_config["providers"][i] = provider
        else:
            print("No API keys file found. Starting with empty keys.")

    def clear_console(self):
        "delete contents from console scrolled text widget"
        self.console.config(state=tk.NORMAL)
        self.console.delete("1.0", tk.END)
        self.console.config(state=tk.DISABLED)

    def update_daily_requests(self, model, provider, requests):
        today = datetime.now().strftime("%Y-%m-%d")

        if today not in self.daily_requests:
            self.daily_requests[today] = {}

        if provider not in self.daily_requests[today]:
            self.daily_requests[today][provider] = {}

        if model not in self.daily_requests[today][provider]:
            self.daily_requests[today][provider][model] = 0

        self.daily_requests[today][provider][model] += requests
        save_daily_requests(self.daily_requests)

    def check_daily_limit(self, model, provider, additional_requests):
        today = datetime.now().strftime("%Y-%m-%d")
        model_info = self.get_model_info(model, provider)

        if not model_info or ("rpd" not in model_info and "tpd" not in model_info):
            self.console_print(
                f"{model} from {provider} does not have a daily requests limit set. This may cause interruptions and unfinished book summaries..."
            )
            return True

        if "rpd" in model_info:
            daily_limit = model_info["rpd"]
        else:
            daily_limit = model_info["tpd"] // model_info["tpm"]

        current_requests = (
            self.daily_requests.get(today, {}).get(provider, {}).get(model, 0)
        )

        if (current_requests + additional_requests) > daily_limit:
            self.console_print(
                f"Error: Processing these books would exceed your remaining daily requests limit for {model} from {provider} ({daily_limit-current_requests}). Aborting."
            )
            return False

        return True

    def update_drag_drop_label(self):
        if len(self.file_listbox.get_children()) == 0:
            self.drag_drop_frame.place(relx=0.5, rely=0.5, anchor="center")
            self.drag_drop_label.pack(pady=20, padx=20)
        else:
            self.drag_drop_frame.place_forget()

    def on_drop(self, event):
        items = self.master.tk.splitlist(event.data)
        for item in items:
            if os.path.isfile(item):
                self.process_dropped_file(item)
            elif os.path.isdir(item):
                self.process_dropped_folder(item)

        if self.model_combobox.get() != "None":
            self.update_estimated_time()
        self.update_drag_drop_label()

    def open_summaries_folder(self):
        summaries_folder = f".{os.sep}summaries"
        if not os.path.exists(summaries_folder):
            try:
                os.makedirs(summaries_folder)
                self.console_print("Summaries folder created.")
            except Exception as e:
                self.console_print(f"Failed to create summaries folder: {str(e)}")
                return
        try:
            os.startfile(summaries_folder)
        except Exception as e:
            self.console_print(f"Failed to open summaries folder: {str(e)}")

    def select_files(self):
        filetypes = (("eBook files", "*.mobi;*.azw3;*.epub"), ("All files", "*.*"))
        files = filedialog.askopenfilenames(filetypes=filetypes)
        for file in files:
            if not self.file_listbox_contains(file):
                base_name = os.path.basename(file)
                self.file_listbox.insert("", tk.END, values=(base_name, "", ""))
                self.file_paths[base_name] = file
                self.update_book_count()
        if self.model_combobox.get() != "None":
            self.update_estimated_time()

    def select_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if file.endswith((".mobi", ".azw3", ".epub")):
                        file_path = os.path.join(root, file)
                        if not self.file_listbox_contains(file_path):
                            base_name = os.path.basename(file_path)
                            self.file_listbox.insert(
                                "", tk.END, values=(base_name, "", "")
                            )
                            self.file_paths[base_name] = file_path
                            self.update_book_count()  # Update the book count label
        if self.model_combobox.get() != "None":
            self.update_estimated_time()

    def update_book_count(self):
        book_count = len(self.file_listbox.get_children())
        self.book_count_label.config(text=f"Books Added: {book_count}")
        self.update_drag_drop_label()

    def process_dropped_file(self, file_path):
        if file_path.lower().endswith((".mobi", ".azw3", ".epub")):
            base_name = os.path.basename(file_path)
            if not self.file_listbox_contains(file_path):
                self.file_listbox.insert("", tk.END, values=(base_name, "", ""))
                self.file_paths[base_name] = file_path
                self.update_book_count()

    def process_dropped_folder(self, folder_path):
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                self.process_dropped_file(file_path)
        self.update_book_count()

    def remove_selected_files(self):
        selected_items = self.file_listbox.selection()
        if selected_items:
            for item in selected_items:
                self.file_listbox.delete(item)
        self.update_book_count()
        self.update_estimated_time()

    def clear_file_list(self):
        self.file_listbox.delete(*self.file_listbox.get_children())
        self.update_book_count()
        self.update_estimated_time()

    def file_listbox_contains(self, file_path: str) -> bool:
        book_dir = os.path.dirname(file_path)
        opf_file = next(
            (
                os.path.join(book_dir, file)
                for file in os.listdir(book_dir)
                if file.endswith(".opf")
            ),
            None,
        )
        if not opf_file:
            return False

        try:
            title, author, _, _ = parse_metadata(opf_file)
        except Exception as e:
            self.console_print(f"Failed to parse metadata from {opf_file}: {str(e)}")
            return False

        for item in self.file_listbox.get_children():
            item_base_name = self.file_listbox.item(item)["values"][0]
            item_file_path = self.file_paths.get(item_base_name)
            if not item_file_path:
                continue

            item_book_dir = os.path.dirname(item_file_path)
            item_opf_file = next(
                (
                    os.path.join(item_book_dir, file)
                    for file in os.listdir(item_book_dir)
                    if file.endswith(".opf")
                ),
                None,
            )
            if not item_opf_file:
                continue

            item_title, item_author, _, _ = parse_metadata(item_opf_file)
            if (
                item_title == title
                and item_author == author
                and os.path.samefile(item_book_dir, book_dir)
            ):
                return True
        return False

    def update_model_options(self, event):
        selected_provider = self.provider_var.get()
        for provider in self.ai_config["providers"]:
            if provider["name"] == selected_provider:
                self.model_combobox["values"] = [
                    model["name"] for model in provider["models"]
                ]
                self.model_combobox.set("")

    def get_selected_model_info(self) -> Dict[str, Any]:
        selected_provider = self.provider_var.get()
        selected_model = self.model_var.get()
        temperature = self.temperature_var.get()
        max_tokens = self.max_tokens_var.get()

        for provider in self.ai_config["providers"]:
            if provider["name"] == selected_provider:
                for model in provider["models"]:
                    if model["name"] == selected_model:
                        model = (
                            model
                            | {"provider": provider["name"]}
                            | {"temperature": temperature}
                            | {"max_tokens": max_tokens}
                        )
                        return model
        return {}

    def _load_model_if_needed(self, model):
        """Load the model if it is not already present locally."""
        if model not in [x["name"] for x in ollama.list()["models"]]:
            self.console_print(
                f"{model} not found locally. Pulling from Hugging Face... Please wait some minutes..."
            )
            ollama.pull(model)
            self.console_print(f"{model} pulled successfully.")

    def preprocess_books(self, max_tokens, tpm):
        preprocessed_books = {}
        book_chunk_info = {}

        # Load existing processed books cache if it exists
        processed_books_cache = {}
        cache_file = 'processed_books_cache.json'
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                processed_books_cache = json.load(f)

        for item in self.file_listbox.get_children():
            if self.file_listbox.item(item)["values"][1] != "Aborted" and self.file_listbox.item(item)["values"][2] == "":
                base_name = self.file_listbox.item(item)["values"][0]
                book_path = self.file_paths.get(base_name)
                
                content = read_epub(book_path)
                if content:
                    total_tokens = int(len(content.split()) * 1.3)

                    # Start with initial values
                    initial_chunk_size = min(int(max_tokens * 0.8), tpm)
                    reduction_factor = 1
                    max_allowed_tokens = int(max_tokens * 0.90)

                    for _ in range(200):
                        chunks = []
                        current_token_count = 0
                        content_words = content.split()
                        previous_summary_tokens = 0
                        theoretical_max_tokens = 0
                        chunk_info = []

                        while current_token_count < total_tokens:
                            chunk_size = max(
                                int((initial_chunk_size * reduction_factor) - previous_summary_tokens),
                                max_tokens // 10,
                            )

                            # Convert chunk size to word count and ensure it's an integer
                            chunk_word_count = int(chunk_size / 1.3)

                            # Update theoretical maximum possible token count
                            theoretical_max_tokens += chunk_size

                            # Check if we're exceeding the max allowed tokens
                            if chunk_size + previous_summary_tokens > max_allowed_tokens:
                                break

                            chunk_content = " ".join(
                                content_words[current_token_count : current_token_count + int(chunk_word_count)]
                            )
                            chunks.append(chunk_content)
                            chunk_info.append(
                                {
                                    "chunk_size": chunk_size,
                                    "summary_tokens": previous_summary_tokens,
                                }
                            )
                            current_token_count += chunk_word_count

                            # Estimate summary tokens for next iteration
                            summary_tokens = 1000
                            previous_summary_tokens += summary_tokens

                        if current_token_count >= total_tokens or (
                            chunk_size + previous_summary_tokens <= max_allowed_tokens
                        ):
                            break

                        reduction_factor -= 0.01

                    # Adjust the console message to reflect theoretical max tokens, not current token count
                    if current_token_count < total_tokens:
                        self.console_print(
                            f"Failed to preprocess {os.path.splitext(os.path.basename(book_path))[0]} ({total_tokens} tokens of length), as it's too large to process (maximum of ∼{int(theoretical_max_tokens)} tokens possible with this model current settings)."
                        )
                        continue
                    else:
                        self.console_print(
                            f"Preprocessed {os.path.splitext(os.path.basename(book_path))[0]} ({total_tokens} tokens of length)."
                        )

                    preprocessed_books[book_path] = chunks
                    book_chunk_info[book_path] = chunk_info

        self.book_chunk_info = book_chunk_info
        return preprocessed_books

    def calculate_estimated_cost(self, tokens: int, model: str, provider: str) -> str:
        model_info = self.get_model_info(model, provider)
        if not model_info or "cost_per_million" not in model_info:
            return None

        cost_per_million = model_info["cost_per_million"]

        estimated_cost = (tokens / 1000000) * cost_per_million

        return estimated_cost

    def estimate_processing_time(self, tokens: int, model: str, provider: str) -> str:
        model_info = self.get_model_info(model, provider)
        if not model_info or "output_speed" not in model_info:
            return None

        input_latency_per_10k = model_info.get("latency_per_10k", 0.6)
        output_speed = model_info["output_speed"]

        # Calculate input and output time for a single chunk
        chunk_total_tokens = tokens
        input_time = (chunk_total_tokens / 10000) * input_latency_per_10k
        output_time = 1000 / output_speed  # estimated at an upper limit of 1000 tokens

        # Calculate delays due to RPM and TPM
        # sometimes model info does not have rpm or tpm, handle this
        rpm = model_info.get("rpm", float("inf"))
        tpm = model_info.get("tpm", float("inf"))
        rpm_delay = max(0, (1 / rpm - 1) * 60) if rpm < float("inf") else 0
        tpm_delay = (
            max(0, (chunk_total_tokens / tpm - 1) * 60) if tpm < float("inf") else 0
        )

        total_input_time = input_time
        total_output_time = output_time

        total_seconds = total_input_time + total_output_time + rpm_delay + tpm_delay

        return total_seconds

    def estimate_process(self):
        selected_model_info = self.get_selected_model_info()

        if not selected_model_info:
            self.estimated_time_label.grid()
            self.estimated_time_label.config(text="Estimated requests: N/A")
            return

        max_tokens = selected_model_info["max_tokens"]
        provider = selected_model_info["provider"]
        model = selected_model_info["name"]
        if "tpm" not in selected_model_info:
            tpm = selected_model_info.get("tpm", float("inf"))
        else:
            tpm = selected_model_info["tpm"]

        # Preprocess the books and store chunks and summaries
        self.preprocessed_books = self.preprocess_books(max_tokens, tpm)

        # Retrieve pre-calculated chunk and summary data
        chunk_summary_info = {
            "total_chunks": 0,
            "total_tokens": 0,
            "final_summaries": 0,
        }

        total_estimated_time_seconds = 0
        total_estimated_cost_value = 0

        # Iterate through each preprocessed book and calculate estimates
        for book_path, chunks in self.preprocessed_books.items():
            num_chunks = len(chunks)
            chunk_summary_info["total_chunks"] += num_chunks
            chunk_summary_info["total_tokens"] += int(
                sum(len(chunk.split()) for chunk in chunks) * 1.3
            )
            
            # Only count as a final summary if there is more than one chunk
            if num_chunks > 1:
                chunk_summary_info["final_summaries"] += 1

            # Calculate time and cost per chunk using max_tokens
            for i in range(num_chunks):
                chunk_tokens = int(len(chunks[i].split()) * 1.3)
                estimated_time_chunk = self.estimate_processing_time(
                    chunk_tokens, model, provider
                )
                estimated_cost_chunk = self.calculate_estimated_cost(
                    chunk_tokens, model, provider
                )

                total_estimated_time_seconds += estimated_time_chunk
                total_estimated_cost_value += estimated_cost_chunk

        # Add the final summaries time and cost (tokens estimated at 1250)
        final_summaries = chunk_summary_info["final_summaries"]
        if final_summaries > 0:
            estimated_time_final_summaries = self.estimate_processing_time(
                1250, model, provider
            )
            estimated_cost_final_summaries = self.calculate_estimated_cost(
                1250, model, provider
            )

            total_estimated_time_seconds += estimated_time_final_summaries
            total_estimated_cost_value += estimated_cost_final_summaries

        # Convert seconds to readable time and cost to readable format
        total_estimated_time = seconds_to_time(total_estimated_time_seconds)
        total_estimated_cost = float_to_cost(total_estimated_cost_value)

        # Calculate available requests
        available_requests = self.calculate_available_requests(selected_model_info)

        # Update the UI with estimated values
        self.estimated_time_label.grid()
        estimated_requests = chunk_summary_info["total_chunks"] + final_summaries
        self.estimated_time_label.config(
            text=f"Estimated requests: {estimated_requests} / {available_requests} | {total_estimated_time if estimated_requests > 0 else 'N/A'} | {total_estimated_cost if estimated_requests > 0 else 'N/A'}"
        )


    def start_processing(self):

        self.process_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.disable_widgets()

        self.console_print("Verifying provider and model...")

        if not self.file_listbox.get_children():
            self.console_print(
                "No books loaded for processing. Please select files or a folder first."
            )
            self.enable_widgets()
            return False

        selected_model_info = self.get_selected_model_info()
        if not selected_model_info:
            self.console_print("Error: Please select an AI provider and model.")
            self.enable_widgets()
            return False

        if len(self.preprocessed_books) == 0:
            self.console_print(
                "No books loaded for processing. Please select files or a folder first, or make sure no books were bypassed or previously processed."
            )
            self.enable_widgets()
            return False

        provider = selected_model_info["provider"]
        model = selected_model_info["name"]

        total_chunks = sum(len(chunks) for chunks in self.preprocessed_books.values())
        final_summaries = len(
            [1 for chunks in self.preprocessed_books.values() if len(chunks) > 1]
        )
        total_requests = total_chunks + final_summaries

        if not self.check_daily_limit(model, provider, total_requests):
            self.overall_progress_bar["value"] = 0
            self.process_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.enable_widgets()
            return False

        self.start_processing_thread = PyThreadKiller(
            target=self._start_processing_thread,
            args=(
                self.preprocessed_books,
                selected_model_info,
            ),
            daemon=True,
        )
        self.start_processing_thread.start()

    def _start_processing_thread(self, preprocessed_books, selected_model_info):
        model = selected_model_info["name"]
        max_tokens = selected_model_info["max_tokens"]
        provider = selected_model_info["provider"]
        temperature = selected_model_info["temperature"]

        if provider not in ["ollama", "lmstudio"]:
            if not self.encrypted_api_keys.get(provider):
                self.console_print(
                    f"Error: No API key found for {provider}. Aborting..."
                )
                self.enable_widgets()
                return
            api_key = decrypt_api_key(self.encrypted_api_keys.get(provider))

        if provider == "ollama":
            from ai_models import OllamaManager

            self._load_model_if_needed(model)

            manager = OllamaManager(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif provider == "alibaba":
            from ai_models import AlibabaManager

            manager = AlibabaManager(
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif provider == "GLHF":
            from ai_models import GLHFManager

            manager = GLHFManager(
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif provider == "openai":
            from ai_models import OpenAIManager

            manager = OpenAIManager(
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif provider == "openrouter":
            from ai_models import OpenRouterManager

            manager = OpenRouterManager(
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif provider == "lmstudio":
            from ai_models import LMStudioManager

            manager = LMStudioManager(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif provider == "google":
            from ai_models import GeminiManager

            manager = GeminiManager(
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif provider == "hyperbolic":
            from ai_models import HyperbolicManager

            manager = HyperbolicManager(
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif provider == "deepinfra":
            from ai_models import DeepInfraManager

            manager = DeepInfraManager(
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif provider == "mistral":
            from ai_models import MistralManager

            manager = MistralManager(
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif provider == "anthropic":
            from ai_models import AnthropicManager

            manager = AnthropicManager(
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif provider == "huggingface":
            from ai_models import HuggingFaceManager

            manager = HuggingFaceManager(
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif provider == "arliai":
            from ai_models import ArliAiManager

            manager = ArliAiManager(
                api_key=api_key,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        else:
            self.console_print(f"Error: Unknown provider: {provider}. Aborting...")
            self.enable_widgets()
            return

        self.total_books = len(preprocessed_books)
        self.current_book = 0

        self.console_print("Starting processing...")

        self.process_books(manager, provider, preprocessed_books)

    def process_books(self, manager, provider, preprocessed_books):
        for book_path, chunks in preprocessed_books.items():
            self.console_print(f"Starting to process: {book_path}")
            item = self.get_item_from_book_path(book_path)
            self.process_single_book(book_path, manager, provider, item, chunks)
            self.current_book += 1
            self.processing_queue.put(("update_progress", self.current_book))

        self.processing_queue.put(("processing_complete", None))

    def process_single_book(self, book_path: str, manager, provider, item, chunks):
        start_time = time.time()
        try:
            self.processing_queue.put(("update_chunk_progress", (item, 0)))

            title, author, series, series_index = parse_metadata(book_path)
            if not title or not author:
                raise ValueError(
                    f"Failed to extract any metadata from {book_path}. Skipping..."
                )

            self.processing_queue.put(
                ("console_print", f"Processing: {title} by {author}")
            )

            book_dir = os.path.join(f".{os.sep}summaries", f"{title} - {author}")
            os.makedirs(book_dir, exist_ok=True)

            def progress_callback(step_number, total_steps):
                percent_complete = (step_number / total_steps) * 100
                self.processing_queue.put(
                    ("update_chunk_progress", (item, percent_complete))
                )
                self.processing_queue.put(
                    (
                        "update_processing_time",
                        (item, round(time.time() - start_time, 2)),
                    )
                )
                if step_number <= len(chunks):
                    self.processing_queue.put(
                        (
                            "console_print",
                            f"Processed chunk {step_number}/{len(chunks)} of {title}...",
                        )
                    )
                else:
                    self.processing_queue.put(
                        (
                            "console_print",
                            f"Creating final summary for {title}...",
                        )
                    )
                self.update_daily_requests(manager.model, provider, 1)

            summary = process_chunks(
                chunks, title, author, book_dir, manager, progress_callback
            )

            if not summary:
                raise ValueError("Failed to generate summary")

            if len(chunks) > 1:
                self.update_daily_requests(
                    manager.model, provider, 1
                )  # +1 for final summary

            summary_path = os.path.join(
                book_dir, f"{title} - {author} - Full Summary.txt"
            )
            with open(summary_path, "w", encoding="utf-8") as summary_file:
                summary_file.write(f"Title: {title}\n")
                summary_file.write(f"Author: {author}\n")
                summary_file.write(f"Series: {series}\n")
                summary_file.write(f"Series Index: {series_index}\n\n")
                summary_file.write(summary)

            self.processed_books.add(book_path)
            base_name = os.path.splitext(os.path.basename(book_path))[0]
            self.processed_basenames[base_name] = summary_path
            self.processing_queue.put(
                (
                    "console_print",
                    f"Finished processing {title}. Summary saved to {summary_path}.",
                )
            )

        except Exception as e:
            logging.error(f"Error processing {book_path}: {e}")
            self.aborted_books.add(book_path)
            self.console_print(f"Failed to process {book_path}: {str(e)}")
            # add "Aborted" in place of the chunk progress bar
            self.processing_queue.put(("update_chunk_progress", (item, "Aborted")))

        finally:
            time.sleep(0.5) # to account for queue delay
            self.update_estimated_time()

    def get_item_from_book_path(self, book_path):
        for item in self.file_listbox.get_children():
            base_name = self.file_listbox.item(item)["values"][0]
            if self.file_paths.get(base_name) == book_path:
                return item
        return None

    def update_estimated_time(self, event=None):
        # don't run if treeview has no items
        selected_model_info = self.get_selected_model_info()
        if selected_model_info:
            self.estimated_time_label.grid_forget()
            self.animate_loading_wheel = True
            self.loading_wheel.grid()
            self.loading_wheel.start()
            self.process_button.config(state=tk.DISABLED)
            self.update_time_thread = PyThreadKiller(
                target=self._update_estimated_time_thread, daemon=True
            )
            self.update_time_thread.start()
        else:
            self.animate_loading_wheel = False
            self.loading_wheel.stop()
            self.loading_wheel.grid_forget()
            self.estimated_time_label.grid()
            self.estimated_time_label.config(text="Estimated requests: N/A")

    def _update_estimated_time_thread(self):
        self.estimate_process()
        if self.animate_loading_wheel:
            self.master.after(0, self.loading_wheel.stop)
            self.loading_wheel.grid_forget()
            self.process_button.config(state=tk.NORMAL)

    def calculate_available_requests(self, selected_model_info):
        # Assuming `selected_model_info` contains limits like "rpd" or "tpd"
        if "rpd" in selected_model_info:
            available_requests = selected_model_info["rpd"]
        else:
            if "tpd" in selected_model_info and "tpm" in selected_model_info:
                available_requests = (
                    selected_model_info["tpd"] // selected_model_info["tpm"]
                )
            else:
                # add infinite symbol
                available_requests = float("inf")

        model = selected_model_info["name"]
        provider = selected_model_info["provider"]

        today = datetime.now().strftime("%Y-%m-%d")

        if today not in self.daily_requests:
            return available_requests

        if provider not in self.daily_requests[today]:
            return available_requests

        if model not in self.daily_requests[today][provider]:
            return available_requests

        return available_requests - self.daily_requests[today][provider].get(model, 0)

    def get_model_info(self, model: str, provider: str) -> Dict[str, Any]:
        for provider_data in self.ai_config["providers"]:
            if provider == provider_data["name"]:
                for model_info in provider_data["models"]:
                    if model_info["name"] == model:
                        return model_info
        return None

    def update_progress(self, current_book):
        self.overall_progress_bar["value"] = (current_book / self.total_books) * 100
        self.progress_percentage_label.config(
            text=f"{self.overall_progress_bar['value']:.0f}%"
        )

    def check_queue(self):
        try:
            while True:
                message, data = self.processing_queue.get_nowait()
                if message == "update_progress":
                    self.update_progress(data)
                elif message == "update_chunk_progress":
                    self.update_chunk_progress(data)
                elif message == "update_processing_time":
                    self.update_processing_time(data)
                elif message == "processing_complete":
                    self.processing_complete()
                elif message == "console_print":
                    self.console_print(data)
        except Empty:
            pass
        finally:
            self.master.after(100, self.check_queue)

    def update_processing_time(self, data):
        item, processing_time = data
        processing_time = convert_to_readable_time(processing_time)
        self.file_listbox.set(item, "processing_time", processing_time)

    def update_chunk_progress(self, data):
        item, progress = data
        if progress == "Aborted":
            self.file_listbox.set(item, "chunk_progress", "Aborted")
        else:
            progress_int = int(progress)
            filled_length = round(progress_int / 5)
            bar = "█" * filled_length + "▒" * (20 - filled_length)
            progress_text = f"{bar} {progress_int:3d}%"
            self.file_listbox.set(item, "chunk_progress", progress_text)

    def processing_complete(self):
        self.update_drag_drop_label()
        self.overall_progress_bar["value"] = 0
        self.process_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.enable_widgets()
        self.console_print("All books have been processed.")
        self.loading_wheel.stop()

    def console_print(self, message):
        self.console.config(state=tk.NORMAL)
        self.console.insert(tk.END, message + "\n")
        self.console.see(tk.END)
        self.console.config(state=tk.DISABLED)

    def on_closing(self):
        self.master.destroy()

    def update_temperature_label(self, value):
        rounded_value = round(float(value), 2)
        self.temperature_var.set(rounded_value)
        
    def update_tokens_label(self, value):
        value = int(float(value))
        self.max_tokens_var.set(value)
        self.update_estimated_time()

    def stop_processing(self):
        if self.start_processing_thread and self.start_processing_thread.is_alive():
            self.start_processing_thread.kill()

        if self.update_time_thread and self.update_time_thread.is_alive():
            self.update_time_thread.kill()

        self.console_print("Processing stopped.")

        self.process_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.enable_widgets()

    def disable_widgets(self):
        self.provider_combobox.config(state=tk.DISABLED)
        self.model_combobox.config(state=tk.DISABLED)
        self.process_button.config(state=tk.DISABLED)
        self.temperature_slider.config(state=tk.DISABLED)
        self.tokens_slider.config(state=tk.DISABLED)
        self.remove_selected_button.config(state=tk.DISABLED)
        self.clear_console_button.config(state=tk.DISABLED)

    def enable_widgets(self):
        self.provider_combobox.config(state=tk.NORMAL)
        self.model_combobox.config(state=tk.NORMAL)
        self.temperature_slider.config(state=tk.NORMAL)
        self.tokens_slider.config(state=tk.NORMAL)
        self.process_button.config(state=tk.NORMAL)
        self.remove_selected_button.config(state=tk.NORMAL)
        self.clear_console_button.config(state=tk.NORMAL)


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = BookSummarizerGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

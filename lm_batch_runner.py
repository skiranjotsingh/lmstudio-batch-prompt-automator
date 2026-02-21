import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
import threading
import os
import time
import subprocess
import sys


# ─────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────
LM_BASE      = "http://127.0.0.1:1234/v1"
LM_ADMIN     = "http://127.0.0.1:1234/api/v1"
LOAD_TIMEOUT      = 600   # seconds – loading a model can be slow
GENERATE_TIMEOUT  = 3600  # seconds – generation can be very long (1 hour)
UNLOAD_TIMEOUT    = 30


# ─────────────────────────────────────────────────────────────
#  Main Application
# ─────────────────────────────────────────────────────────────
class LMStudioBatchApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("LM Studio Batch Prompt Automator")
        self.root.geometry("720x820")
        self.root.resizable(True, True)

        # Threading/pause state
        self._pause_event  = threading.Event()   # set   → running freely
        self._pause_event.set()                   # start unpaused
        self._stop_flag    = False               # hard stop (not exposed in UI yet, placeholder)

        # Track the output folder for the "open folder" button
        self._last_output_folder: str = ""

        # Track which model we explicitly loaded so we can reliably unload it
        self._currently_loaded_model: str | None = None

        self._build_ui()

    # ──────────────────────────────────────────────
    #  UI construction
    # ──────────────────────────────────────────────
    def _build_ui(self):
        pad = dict(padx=10, pady=4)

        # ── Prompt ─────────────────────────────────
        ttk.Label(self.root, text="Prompt:", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", **pad)
        self.prompt_text = tk.Text(self.root, height=8, width=80, wrap="word",
                                   font=("Segoe UI", 9))
        self.prompt_text.pack(fill="x", **pad)

        # ── Output folder ──────────────────────────
        folder_frame = ttk.Frame(self.root)
        folder_frame.pack(fill="x", **pad)
        ttk.Label(folder_frame, text="Output Folder:").pack(side="left")
        self.folder_var = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.folder_var).pack(
            side="left", fill="x", expand=True, padx=5)
        ttk.Button(folder_frame, text="Browse…",
                   command=self._browse_folder).pack(side="left")

        # ── Filename format ────────────────────────
        fmt_frame = ttk.Frame(self.root)
        fmt_frame.pack(fill="x", **pad)
        ttk.Label(fmt_frame, text="Filename format (use {model}):").pack(side="left")
        self.filename_fmt_var = tk.StringVar(value="{session}_{model}_response.txt")
        ttk.Entry(fmt_frame, textvariable=self.filename_fmt_var).pack(
            side="left", fill="x", expand=True, padx=5)

        # ── Delay ──────────────────────────────────
        delay_frame = ttk.Frame(self.root)
        delay_frame.pack(fill="x", **pad)
        ttk.Label(delay_frame, text="Wait after unload (sec):").pack(side="left")
        self.delay_var = tk.IntVar(value=5)
        ttk.Spinbox(delay_frame, from_=0, to=120, textvariable=self.delay_var,
                    width=5).pack(side="left", padx=5)

        # ── Model list ─────────────────────────────
        model_header = ttk.Frame(self.root)
        model_header.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Label(model_header, text="Available Models:",
                  font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Button(model_header, text="↻ Refresh Models",
                   command=self._refresh_models).pack(side="right")
        ttk.Button(model_header, text="Select All",
                   command=self._select_all).pack(side="right", padx=4)
        ttk.Button(model_header, text="Deselect All",
                   command=self._deselect_all).pack(side="right")

        # Scrollable checkbox list
        list_outer = ttk.Frame(self.root, relief="sunken", borderwidth=1)
        list_outer.pack(fill="both", expand=True, padx=10, pady=4)

        self._canvas = tk.Canvas(list_outer, height=160,
                                 highlightthickness=0, background="white")
        scrollbar = ttk.Scrollbar(list_outer, orient="vertical",
                                  command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._check_frame = ttk.Frame(self._canvas, style="White.TFrame")
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._check_frame, anchor="nw")
        self._check_frame.bind("<Configure>", lambda e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(
            self._canvas_window, width=e.width))

        # dict: model_id → tk.BooleanVar
        self._model_vars: dict[str, tk.BooleanVar] = {}
        self._model_labels: dict[str, ttk.Label] = {}

        # ── Progress / Status ──────────────────────
        prog_frame = ttk.Frame(self.root)
        prog_frame.pack(fill="x", padx=10, pady=(8, 0))

        self.counter_var = tk.StringVar(value="Models: –")
        ttk.Label(prog_frame, textvariable=self.counter_var,
                  font=("Segoe UI", 9, "bold")).pack(side="right")

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.root, variable=self.progress_var,
                                            maximum=100)
        self.progress_bar.pack(fill="x", padx=10, pady=4)

        self.status_var = tk.StringVar(value="Status: Ready")
        self.status_label = ttk.Label(self.root, textvariable=self.status_var,
                                      foreground="steelblue",
                                      font=("Segoe UI", 9, "italic"))
        self.status_label.pack(pady=(0, 4))

        # ── Action buttons ─────────────────────────
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=6)

        self.start_btn = ttk.Button(btn_frame, text="▶ Start Batch",
                                    command=self._start_batch)
        self.start_btn.pack(side="left", padx=6)

        self.pause_btn = ttk.Button(btn_frame, text="⏸ Pause",
                                    command=self._toggle_pause, state="disabled")
        self.pause_btn.pack(side="left", padx=6)

        self.stop_btn = ttk.Button(btn_frame, text="⏹ Stop",
                                   command=self._stop_batch, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        self.open_folder_btn = ttk.Button(btn_frame, text="📂 Open Output Folder",
                                          command=self._open_output_folder,
                                          state="disabled")
        self.open_folder_btn.pack(side="left", padx=6)

        # Load model list on startup
        self._refresh_models()

    # ──────────────────────────────────────────────
    #  Model list helpers
    # ──────────────────────────────────────────────
    def _refresh_models(self):
        """Fetch models from LM Studio and rebuild the checkbox list."""
        for widget in self._check_frame.winfo_children():
            widget.destroy()
        self._model_vars.clear()
        self._model_labels.clear()

        self._set_status("Fetching models…")
        models = self._fetch_models()
        if not models:
            ttk.Label(self._check_frame,
                      text="No models found. Is LM Studio running?",
                      foreground="gray").pack(anchor="w", padx=6, pady=4)
            return

        for m in models:
            model_id = m["id"]
            size_str = m["size_str"]
            display_text = f"{model_id} ({size_str})" if size_str else model_id
            
            var = tk.BooleanVar(value=True)
            row = ttk.Frame(self._check_frame)
            row.pack(fill="x", padx=4, pady=1)
            cb = ttk.Checkbutton(row, text=display_text, variable=var)
            cb.pack(side="left")
            # Status indicator label per model
            lbl = ttk.Label(row, text="", width=16, foreground="gray")
            lbl.pack(side="right", padx=6)
            self._model_vars[model_id] = var
            self._model_labels[model_id] = lbl

        self.counter_var.set(f"Models: {len(models)} total, 0 done")
        self._set_status(f"Found {len(models)} model(s). Ready.")

    def _select_all(self):
        for var in self._model_vars.values():
            var.set(True)

    def _deselect_all(self):
        for var in self._model_vars.values():
            var.set(False)

    # ──────────────────────────────────────────────
    #  LM Studio API  (no openai package)
    # ──────────────────────────────────────────────
    def _fetch_models(self) -> list[dict]:
        """Return all model IDs available in LM Studio, plus their sizes.
        Tries multiple endpoints & response shapes to maximise compatibility."""
        endpoints = [
            f"{LM_BASE}/models",      # /v1/models   – OpenAI compat
            f"{LM_ADMIN}/models",     # /api/v1/models – LM Studio native
        ]
        for url in endpoints:
            try:
                self._set_status(f"Trying {url}…")
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                body = r.json()

                # Most LM Studio versions: {"data": [{"id": "..."}]}
                if isinstance(body, dict) and "data" in body:
                    items = body["data"]
                    if isinstance(items, list) and items:
                        results = []
                        for m in items:
                            mid = m.get("id") or m.get("model") or m.get("path") or ""
                            if mid:
                                size = m.get("size") or m.get("size_bytes")
                                size_str = ""
                                if size:
                                    try:
                                        size_gb = float(size) / (1024**3)
                                        size_str = f"{size_gb:.2f} GB"
                                    except ValueError:
                                        pass
                                results.append({"id": mid, "size_str": size_str})
                        if results:
                            return results

                # Some builds return a flat list of strings
                if isinstance(body, list) and body and isinstance(body[0], str):
                    return [{"id": m, "size_str": ""} for m in body]

                self._set_status(
                    f"{url} responded but returned unexpected shape: "
                    f"{str(body)[:200]}", error=True)
            except requests.ConnectionError:
                self._set_status(f"Cannot reach {url}", error=True)
            except Exception as e:
                self._set_status(f"{url} error: {e}", error=True)

        self._set_status("Could not fetch models from any endpoint.", error=True)
        return []

    def _get_loaded_models(self) -> list[dict]:
        """Return a list of dicts with 'id' and 'instance_id' for models
        currently loaded in memory.
        /v1/models (OpenAI compat) returns only loaded models."""
        try:
            r = requests.get(f"{LM_BASE}/models", timeout=5)
            r.raise_for_status()
            loaded = []
            for m in r.json().get("data", []):
                # The ID is usually the model name, but LM Studio also provides
                # a specific instance_id which is often required for unloading.
                # Fall back to using the 'id' if 'instance_id' is missing.
                loaded.append({
                    "id": m["id"],
                    "instance_id": m.get("instance_id", m["id"])
                })
            return loaded
        except Exception:
            return []

    def _do_unload_request(self, model_id: str, instance_id: str) -> bool:
        """Attempt to unload using different JSON payloads for API compatibility."""
        payloads = [
            {"instance_id": instance_id},  # Strict requirement in newer LM Studio
            {"model": model_id},           # Older requirement
            {"model": model_id, "instance_id": instance_id}
        ]
        for payload in payloads:
            try:
                r = requests.post(f"{LM_ADMIN}/models/unload", 
                                  json=payload, timeout=UNLOAD_TIMEOUT)
                if r.ok:
                    return True
            except Exception:
                pass
        return False

    def _force_unload_all(self) -> bool:
        """Unload every model currently in memory. Retries up to 3 times
        and polls to verify nothing is left loaded."""
        for attempt in range(1, 4):
            loaded = self._get_loaded_models()
            if not loaded:
                return True  # nothing loaded – success

            self._set_status(
                f"Unloading {len(loaded)} resident model(s) "
                f"(attempt {attempt}/3)…")

            for m in loaded:
                self._do_unload_request(m["id"], m["instance_id"])

            # Give the runtime a moment to release VRAM/RAM
            time.sleep(3)

            # Verify
            still_loaded = self._get_loaded_models()
            if not still_loaded:
                return True

        # If we get here, something is still loaded after 3 tries
        still = self._get_loaded_models()
        if still:
            names = [m["id"] for m in still]
            self._set_status(
                f"Warning: could not unload: {', '.join(names)}", error=True)
            return False
        return True

    def _load_model(self, model_id: str) -> bool:
        """Ensure no other model is in memory, then load the target model."""
        # ── 1. Unload everything currently in memory ──
        self._set_status(f"Clearing memory before loading {model_id}…")
        self._force_unload_all()
        time.sleep(2)  # extra settle time for VRAM release

        # ── 2. Load the target ──
        self._set_status(f"Loading: {model_id}…")
        try:
            r = requests.post(f"{LM_ADMIN}/models/load",
                              json={"model": model_id},
                              timeout=LOAD_TIMEOUT)
            r.raise_for_status()
            self._currently_loaded_model = model_id
            return True
        except Exception as e:
            self._set_status(f"Load failed for {model_id}: {e}", error=True)
            return False

    def _unload_model(self, model_id: str) -> bool:
        """Unload a specific model and verify it is actually gone."""
        self._set_status(f"Unloading: {model_id}…")
        
        # Need to find the specific instance_id of this model
        loaded = self._get_loaded_models()
        target_instance = None
        for m in loaded:
            if m["id"] == model_id:
                target_instance = m["instance_id"]
                break
                
        if not target_instance:
            # Maybe it's already unloaded? Check again to be sure
            time.sleep(1)
            loaded_ids = [m["id"] for m in self._get_loaded_models()]
            if model_id not in loaded_ids:
                return True
            target_instance = model_id # fallback
            
        for attempt in range(1, 4):
            success = self._do_unload_request(model_id, target_instance)
            if not success:
                self._set_status(
                    f"Unload API returned error for {model_id} (Attempt {attempt})",
                    error=True)

            time.sleep(2)  # let the runtime release resources

            # Verify model is gone
            loaded_ids = [m["id"] for m in self._get_loaded_models()]
            if model_id not in loaded_ids:
                self._currently_loaded_model = None
                return True

        self._set_status(f"Could not verify unload of {model_id}!", error=True)
        return False

    def _generate(self, model_id: str, prompt: str) -> tuple[str, str, str]:
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        }
        try:
            self._set_status(f"Generating → {model_id}…")
            start_time = time.time()
            r = requests.post(f"{LM_BASE}/chat/completions",
                              json=payload, timeout=GENERATE_TIMEOUT)
            r.raise_for_status()
            end_time = time.time()
            
            data = r.json()
            choices = data.get("choices", [])
            content = choices[0]["message"].get("content", "") if choices else "(No content returned)"
            
            usage = data.get("usage", {})
            tokens = usage.get("completion_tokens", 0)
            time_taken = end_time - start_time
            tps = (tokens / time_taken) if time_taken > 0 else 0
            
            return content, f"{tps:.2f}", f"{time_taken:.2f}s"
        except Exception as e:
            return f"[Generation error: {e}]", "0.00", "0.0s"

    # ──────────────────────────────────────────────
    #  Batch worker thread
    # ──────────────────────────────────────────────
    def _run_batch(self, prompt: str, output_folder: str, filename_fmt: str):
        selected = [mid for mid, var in self._model_vars.items() if var.get()]
        total    = len(selected)
        done     = 0

        if total == 0:
            self._set_status("No models selected.", error=True)
            self._restore_ui()
            return

        self.counter_var.set(f"Models: {total} total, 0 done")
        session_id = time.strftime("%Y%m%d_%H%M%S")

        for i, model_id in enumerate(selected):
            # ── Pause checkpoint ──
            # Waits here if user pressed Pause; resumes when they press Resume.
            self._set_label(model_id, "⏳ waiting…", "gray")
            self._pause_event.wait()   # blocks until event is set (i.e. not paused)

            if self._stop_flag:
                self._set_status("Batch aborted by user.")
                break

            # ── Mark as active ──
            self._highlight_model(model_id, active=True)
            self._set_label(model_id, "⟳ loading…", "orange")

            # ── Load (with guaranteed unload-all-first) ──
            ok = self._load_model(model_id)
            if not ok:
                self._set_label(model_id, "✗ load fail", "red")
                self._highlight_model(model_id, active=False)
                done += 1
                self._update_counter(done, total, i + 1)
                continue

            self._set_label(model_id, "⟳ generating…", "steelblue")

            # ── Generate ──
            content, tps, time_taken = self._generate(model_id, prompt)

            # ── Save ──
            safe_name = self._sanitize(model_id)
            filename  = filename_fmt.replace("{model}", safe_name).replace("{session}", session_id)
            filepath  = os.path.join(output_folder, filename)
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"Model: {model_id}\n")
                    f.write(f"Session: {session_id}\n")
                    f.write("=" * 60 + "\n")
                    f.write(content)
                    f.write("\n\n" + "-" * 60 + "\n")
                    f.write(f"Generation Time: {time_taken}\n")
                    f.write(f"Tokens Per Second (TPS): {tps}\n")
                self._set_label(model_id, "✓ done", "green")
            except Exception as e:
                self._set_label(model_id, "✗ save fail", "red")
                self._set_status(f"Save failed for {model_id}: {e}", error=True)

            self._highlight_model(model_id, active=False)

            # ── Unload (with verification) ──
            unload_ok = self._unload_model(model_id)
            if not unload_ok:
                # Force-unload everything as a safety net
                self._force_unload_all()

            done += 1
            self._update_counter(done, total, i + 1)

            # ── Delay for RAM/VRAM clearance ──
            delay = self.delay_var.get()
            if delay > 0 and i < total - 1:   # no need to wait after the last model
                self._set_status(f"Waiting {delay}s for RAM/VRAM to clear…")
                time.sleep(delay)

        self.progress_var.set(100)
        self._set_status(f"Batch complete! {done}/{total} models processed.")
        self._last_output_folder = output_folder
        self.root.after(0, lambda: self.open_folder_btn.config(state="normal"))
        self.root.after(0, lambda: messagebox.showinfo(
            "Done", f"Batch complete!\n{done}/{total} models processed.\n\nOutput: {output_folder}"))
        self._restore_ui()

    # ──────────────────────────────────────────────
    #  UI thread-safe helpers
    # ──────────────────────────────────────────────
    def _set_status(self, msg: str, error: bool = False):
        color = "red" if error else "steelblue"
        self.root.after(0, lambda: self.status_var.set(f"Status: {msg}"))
        self.root.after(0, lambda: self.status_label.config(foreground=color))

    def _set_label(self, model_id: str, text: str, color: str):
        lbl = self._model_labels.get(model_id)
        if lbl:
            self.root.after(0, lambda l=lbl, t=text, c=color: (
                l.config(text=t, foreground=c)))

    def _highlight_model(self, model_id: str, active: bool):
        lbl = self._model_labels.get(model_id)
        if lbl:
            bg = "lightyellow" if active else ""
            # We re-configure the parent row frame background
            parent = lbl.master
            try:
                self.root.after(0, lambda p=parent, b=bg: p.config(style=""))
            except Exception:
                pass

    def _update_counter(self, done: int, total: int, processed: int):
        pct = (processed / total) * 100
        self.root.after(0, lambda: self.progress_var.set(pct))
        self.root.after(0, lambda: self.counter_var.set(
            f"Models: {total} total, {done} done"))

    def _restore_ui(self):
        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.pause_btn.config(
            state="disabled", text="⏸ Pause"))
        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
        self._pause_event.set()   # ensure not stuck paused

    # ──────────────────────────────────────────────
    #  Button callbacks
    # ──────────────────────────────────────────────
    def _browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_var.set(folder)

    def _stop_batch(self):
        self._set_status("Aborting sequence soon…")
        self._stop_flag = True
        self._pause_event.set()  # Unpause so thread can loop and break

    def _start_batch(self):
        prompt        = self.prompt_text.get("1.0", tk.END).strip()
        output_folder = self.folder_var.get().strip()
        filename_fmt  = self.filename_fmt_var.get().strip()

        if not prompt:
            messagebox.showerror("Error", "Prompt cannot be empty.")
            return
        if not output_folder:
            messagebox.showerror("Error", "Output folder cannot be empty.")
            return
        if not os.path.isdir(output_folder):
            messagebox.showerror("Error", "Output folder does not exist.")
            return
        if "{model}" not in filename_fmt:
            if not messagebox.askyesno(
                    "Warning",
                    "Filename format has no {model} placeholder.\n"
                    "Responses will overwrite each other.\nContinue anyway?"):
                return

        selected_count = sum(1 for v in self._model_vars.values() if v.get())
        if selected_count == 0:
            messagebox.showerror("Error", "No models selected.")
            return

        # Reset state
        self._stop_flag = False
        self._pause_event.set()
        self.progress_var.set(0)
        self.open_folder_btn.config(state="disabled")
        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal", text="⏸ Pause")
        self.stop_btn.config(state="normal")

        # Reset per-model labels
        for mid, lbl in self._model_labels.items():
            if self._model_vars[mid].get():
                lbl.config(text="⬤ queued", foreground="gray")
            else:
                lbl.config(text="", foreground="gray")

        threading.Thread(
            target=self._run_batch,
            args=(prompt, output_folder, filename_fmt),
            daemon=True
        ).start()

    def _toggle_pause(self):
        if self._pause_event.is_set():
            # Currently running → pause
            self._pause_event.clear()
            self.pause_btn.config(text="▶ Resume")
            self._set_status("Paused – will stop after current generation finishes.")
        else:
            # Currently paused → resume
            self._pause_event.set()
            self.pause_btn.config(text="⏸ Pause")
            self._set_status("Resumed.")

    def _open_output_folder(self):
        folder = self._last_output_folder or self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Error", "Output folder not found.")
            return
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    # ──────────────────────────────────────────────
    #  Utility
    # ──────────────────────────────────────────────
    @staticmethod
    def _sanitize(name: str) -> str:
        for ch in r'<>:"/\|?*':
            name = name.replace(ch, "_")
        return name


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = LMStudioBatchApp(root)
    root.mainloop()

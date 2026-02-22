import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import requests
import threading
import os
import time
import subprocess
import sys
import re
import webbrowser

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

LOAD_TIMEOUT = 600
UNLOAD_TIMEOUT = 30

class LMStudioBatchApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("LM Studio Batch Prompt Automator")
        self.root.geometry("860x900")
        
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_flag = False
        
        self._last_output_folder = ""
        self._currently_loaded_model = None

        self._build_ui()
        self.root.after(100, self._refresh_models)

    def _build_ui(self):
        # We use a scrollable frame for main content
        self.main_container = ctk.CTkScrollableFrame(self.root)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # ── System Prompt ───────────────────────────
        ctk.CTkLabel(self.main_container, text="System Prompt (Optional):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=5)
        self.sys_prompt_text = ctk.CTkTextbox(self.main_container, height=60)
        self.sys_prompt_text.pack(fill="x", padx=5, pady=(0, 10))

        # ── User Prompt ─────────────────────────────
        ctk.CTkLabel(self.main_container, text="User Prompt:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=5)
        self.prompt_text = ctk.CTkTextbox(self.main_container, height=120)
        self.prompt_text.pack(fill="x", padx=5, pady=(0, 10))

        # ── Output Options ──────────────────────────
        opts_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        opts_frame.pack(fill="x", padx=5, pady=(0, 10))
        
        ctk.CTkLabel(opts_frame, text="Output Format:").pack(side="left", padx=(0, 5))
        self.format_var = ctk.StringVar(value=".md")
        self.format_menu = ctk.CTkOptionMenu(opts_frame, variable=self.format_var, values=[".md", ".txt"], width=80)
        self.format_menu.pack(side="left", padx=(0, 20))

        self.skip_thinking_var = ctk.BooleanVar(value=False)
        self.skip_thinking_cb = ctk.CTkCheckBox(opts_frame, text="Skip Thinking Part (<think>...)", variable=self.skip_thinking_var)
        self.skip_thinking_cb.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(opts_frame, text="Filename format:").pack(side="left", padx=(0, 5))
        self.filename_fmt_var = ctk.StringVar(value="{session}_{model}_response")
        ctk.CTkEntry(opts_frame, textvariable=self.filename_fmt_var, width=180).pack(side="left", padx=(0, 5))
        ctk.CTkLabel(opts_frame, text="({model}, {session})", text_color="gray", font=("", 10)).pack(side="left")

        # ── Output folder ───────────────────────────
        folder_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        folder_frame.pack(fill="x", padx=5, pady=(0, 10))
        ctk.CTkLabel(folder_frame, text="Output Folder:").pack(side="left", padx=(0, 5))
        self.folder_var = ctk.StringVar()
        ctk.CTkEntry(folder_frame, textvariable=self.folder_var).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(folder_frame, text="Browse…", command=self._browse_folder, width=80).pack(side="left")

        # ── Advanced Settings Toggle & Theme ─────────
        opts_bar = ctk.CTkFrame(self.main_container, fg_color="transparent")
        opts_bar.pack(fill="x", padx=5, pady=(0, 5))
        
        self.adv_toggle_btn = ctk.CTkButton(opts_bar, text="⚙ Advanced Settings ▼", command=self._toggle_advanced, fg_color="transparent", text_color=("black", "white"), border_width=1)
        self.adv_toggle_btn.pack(side="left")
        
        self.theme_var = ctk.StringVar(value="dark")
        self.theme_switch = ctk.CTkSwitch(opts_bar, text="Dark Mode", command=self._toggle_theme, variable=self.theme_var, onvalue="dark", offvalue="light")
        self.theme_switch.pack(side="right")

        self.adv_frame = ctk.CTkFrame(self.main_container, fg_color=("gray90", "gray13"))
        
        # Row 1 (Server & Wait)
        adv_row1 = ctk.CTkFrame(self.adv_frame, fg_color="transparent")
        adv_row1.pack(fill="x", pady=5)
        
        ctk.CTkLabel(adv_row1, text="Server URL:").pack(side="left", padx=(0,5))
        self.server_url_var = ctk.StringVar(value="http://localhost:1234")
        ctk.CTkEntry(adv_row1, textvariable=self.server_url_var, width=160).pack(side="left", padx=(0,20))
        
        ctk.CTkLabel(adv_row1, text="Wait after unload (sec):").pack(side="left", padx=(0,5))
        self.delay_var = ctk.StringVar(value="5")
        ctk.CTkEntry(adv_row1, textvariable=self.delay_var, width=50).pack(side="left", padx=(0,20))

        ctk.CTkLabel(adv_row1, text="Max Wait Time (sec):").pack(side="left", padx=(0,5))
        self.max_wait_var = ctk.StringVar(value="3600")
        ctk.CTkEntry(adv_row1, textvariable=self.max_wait_var, width=50).pack(side="left", padx=(0,5))
        ctk.CTkLabel(adv_row1, text="(Leave blank or 0 for infinite)", text_color="gray", font=("", 10)).pack(side="left")

        # Row 2 (Temp & Tokens)
        adv_row2 = ctk.CTkFrame(self.adv_frame, fg_color="transparent")
        adv_row2.pack(fill="x", pady=5)

        ctk.CTkLabel(adv_row2, text="Temperature:").pack(side="left", padx=(0,5))
        self.temp_var = ctk.DoubleVar(value=0.7)
        self.temp_slider = ctk.CTkSlider(adv_row2, from_=0.1, to=1.0, variable=self.temp_var, width=120)
        self.temp_slider.pack(side="left", padx=(0,10))
        self.temp_label = ctk.CTkLabel(adv_row2, text="0.70")
        self.temp_label.pack(side="left", padx=(0,10))
        self.temp_slider.configure(command=lambda v: self.temp_label.configure(text=f"{v:.2f}"))

        self.use_default_temp_var = ctk.BooleanVar(value=True)
        self.use_default_temp_cb = ctk.CTkCheckBox(adv_row2, text="Use Model Default", variable=self.use_default_temp_var, command=self._toggle_temp_slider)
        self.use_default_temp_cb.pack(side="left", padx=(0,30))
        self.temp_slider.configure(state="disabled")

        ctk.CTkLabel(adv_row2, text="Max Tokens:").pack(side="left", padx=(0,5))
        self.tokens_var = ctk.DoubleVar(value=-1)
        self.tokens_slider = ctk.CTkSlider(adv_row2, from_=-1, to=16384, variable=self.tokens_var, width=150)
        self.tokens_slider.pack(side="left", padx=(0,10))
        self.tokens_label = ctk.CTkLabel(adv_row2, text="-1")
        self.tokens_label.pack(side="left")
        self.tokens_slider.configure(command=lambda v: self.tokens_label.configure(text=f"{int(v)}"))

        # ── Model list ──────────────────────────────
        model_header = ctk.CTkFrame(self.main_container, fg_color="transparent")
        model_header.pack(fill="x", padx=5, pady=(10, 5))
        ctk.CTkLabel(model_header, text="Available Models:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkButton(model_header, text="↻ Refresh Models", command=self._refresh_models, width=110).pack(side="right")
        ctk.CTkButton(model_header, text="Select All", command=self._select_all, width=80).pack(side="right", padx=5)
        ctk.CTkButton(model_header, text="Deselect All", command=self._deselect_all, width=80).pack(side="right")

        self.list_frame = ctk.CTkScrollableFrame(self.main_container, height=200, fg_color=("#F9F9F9", "#1E1E1E"), border_width=1, border_color=("#CCCCCC", "#333333"))
        self.list_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self._model_vars: dict[str, ctk.BooleanVar] = {}
        self._model_labels: dict[str, ctk.CTkLabel] = {}
        self._model_rows: dict[str, ctk.CTkFrame] = {}

        # ── Progress / Status ───────────────────────
        prog_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        prog_frame.pack(fill="x", padx=5, pady=(10, 5))

        self.counter_var = ctk.StringVar(value="Models: –")
        ctk.CTkLabel(prog_frame, textvariable=self.counter_var, font=ctk.CTkFont(weight="bold")).pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(self.main_container)
        self.progress_bar.pack(fill="x", padx=5, pady=5)
        self.progress_bar.set(0)

        self.status_var = ctk.StringVar(value="Status: Ready")
        self.status_label = ctk.CTkLabel(self.main_container, textvariable=self.status_var, text_color="#3498DB", font=ctk.CTkFont(slant="italic"))
        self.status_label.pack(pady=5)

        # ── Action buttons ──────────────────────────
        btn_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        btn_frame.pack(pady=10)

        self.start_btn = ctk.CTkButton(btn_frame, text="▶ Start Batch", command=self._start_batch)
        self.start_btn.pack(side="left", padx=5)

        self.pause_btn = ctk.CTkButton(btn_frame, text="⏸ Pause", command=self._toggle_pause, state="disabled")
        self.pause_btn.pack(side="left", padx=5)

        self.stop_btn = ctk.CTkButton(btn_frame, text="⏹ Stop", command=self._stop_batch, state="disabled", fg_color="#E74C3C", hover_color="#C0392B")
        self.stop_btn.pack(side="left", padx=5)

        self.open_folder_btn = ctk.CTkButton(btn_frame, text="📂 Open Output Folder", command=self._open_output_folder, state="disabled")
        self.open_folder_btn.pack(side="left", padx=5)

        # ── Developer Footer ────────────────────────
        dev_label = ctk.CTkLabel(
            self.main_container, 
            text="Developed by Kiranjot Singh Malhotra",
            text_color=("gray60", "gray40"), 
            font=ctk.CTkFont(size=11, slant="italic"),
            cursor="hand2"
        )
        dev_label.pack(side="bottom", pady=(10, 0))
        dev_label.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/skiranjotsingh"))

    def _toggle_advanced(self):
        if self.adv_frame.winfo_ismapped():
            self.adv_frame.pack_forget()
            self.adv_toggle_btn.configure(text="⚙ Advanced Settings ▼")
        else:
            self.adv_frame.pack(fill="x", padx=5, pady=(0, 10), after=self.adv_toggle_btn.master)
            self.adv_toggle_btn.configure(text="⚙ Advanced Settings ▲")

    def _toggle_temp_slider(self):
        if self.use_default_temp_var.get():
            self.temp_slider.configure(state="disabled")
        else:
            self.temp_slider.configure(state="normal")

    def _toggle_theme(self):
        new_mode = self.theme_var.get()
        ctk.set_appearance_mode(new_mode)
        if new_mode == "dark":
            self.theme_switch.configure(text="Dark Mode")
        else:
            self.theme_switch.configure(text="Light Mode")

    def _get_lm_urls(self):
        base = self.server_url_var.get().strip().rstrip("/")
        return f"{base}/v1", f"{base}/api/v1"

    # ──────────────────────────────────────────────
    #  Model list helpers
    # ──────────────────────────────────────────────
    def _refresh_models(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self._model_vars.clear()
        self._model_labels.clear()
        self._model_rows.clear()

        self._set_status("Fetching models…")
        base = self.server_url_var.get().strip().rstrip("/")
        
        try:
            # Secondary fetch to get size_bytes (api/v0 doesn't include sizes, but api/v1 does)
            sizes_map = {}
            try:
                r1 = requests.get(f"{base}/api/v1/models", timeout=5)
                if r1.ok:
                    for m1 in r1.json().get("models", []):
                        key = m1.get("key", "")
                        sb = m1.get("size_bytes")
                        if key and sb:
                            sizes_map[key] = sb
                            # v0 ids may have @quantization suffix (e.g. "model@iq3_m")
                            qname = ""
                            q = m1.get("quantization")
                            if isinstance(q, dict):
                                qname = q.get("name", "")
                            elif isinstance(q, str):
                                qname = q
                            if qname:
                                sizes_map[f"{key}@{qname.lower()}"] = sb
            except Exception:
                pass

            r = requests.get(f"{base}/api/v0/models", timeout=10)
            r.raise_for_status()
            data = r.json()
            models = []
            if isinstance(data, dict) and "data" in data:
                for m in data["data"]:
                    mid = m.get("id") or m.get("name")
                    display_name = m.get("name") or mid
                    if mid:
                        size_bytes = sizes_map.get(mid)
                        size_str = ""
                        if size_bytes:
                            size_gb = size_bytes / (1024**3)
                            if size_gb >= 1:
                                size_str = f"{size_gb:.2f} GB"
                            else:
                                size_mb = size_bytes / (1024**2)
                                size_str = f"{size_mb:.2f} MB"
                        models.append({"id": mid, "display_name": display_name, "size_str": size_str})
            
            if not models:
                ctk.CTkLabel(self.list_frame, text="No models found. Check Server URL and LM Studio.", text_color="gray").pack(anchor="w", padx=6, pady=4)
                self.counter_var.set("Models: 0 total, 0 done")
                self._set_status("No models found.")
                return

            for m in models:
                model_id = m["id"]
                display_name = m["display_name"]
                size_str = m["size_str"]
                display_text = f"{display_name} ({size_str})" if size_str else display_name
                
                var = ctk.BooleanVar(value=True)
                row = ctk.CTkFrame(self.list_frame, fg_color="transparent", corner_radius=0)
                row.pack(fill="x", padx=4, pady=2)
                
                cb = ctk.CTkCheckBox(row, text=display_text, variable=var)
                cb.pack(side="left", padx=5)
                
                lbl = ctk.CTkLabel(row, text="", width=100, text_color="gray", anchor="e")
                lbl.pack(side="right", padx=5)
                
                self._model_vars[model_id] = var
                self._model_labels[model_id] = lbl
                self._model_rows[model_id] = row

            self.counter_var.set(f"Models: {len(models)} total, 0 done")
            self._set_status(f"Found {len(models)} model(s). Ready.")

        except Exception as e:
            ctk.CTkLabel(self.list_frame, text=f"Error connecting to LM Studio: {e}", text_color="#E74C3C").pack(anchor="w", padx=6, pady=4)
            self._set_status("Error fetching models.", error=True)

    def _select_all(self):
        for var in self._model_vars.values():
            var.set(True)

    def _deselect_all(self):
        for var in self._model_vars.values():
            var.set(False)

    # ──────────────────────────────────────────────
    #  LM Studio API
    # ──────────────────────────────────────────────
    def _get_loaded_models(self) -> list[dict]:
        """Return a list of dicts with 'id' and 'instance_id' for models
        currently loaded in memory. Uses /api/v0/models which includes
        a 'state' field to distinguish loaded vs not-loaded models."""
        base = self.server_url_var.get().strip().rstrip("/")
        try:
            r = requests.get(f"{base}/api/v0/models", timeout=5)
            r.raise_for_status()
            loaded = []
            for m in r.json().get("data", []):
                if m.get("state") == "loaded":
                    loaded.append({
                        "id": m["id"],
                        "instance_id": m.get("instance_id", m["id"])
                    })
            return loaded
        except Exception:
            return []

    def _do_unload_request(self, model_id: str, instance_id: str) -> bool:
        _, lm_admin = self._get_lm_urls()
        for payload in [
            {"model": model_id},
            {"identifier": model_id},
            {"instance_id": instance_id},
            {"model": model_id, "instance_id": instance_id}
        ]:
            try:
                r = requests.post(f"{lm_admin}/models/unload", 
                                  json=payload, timeout=UNLOAD_TIMEOUT)
                if r.ok:
                    return True
            except Exception:
                pass
        return False

    def _force_unload_all(self) -> bool:
        for attempt in range(1, 4):
            loaded = self._get_loaded_models()
            if not loaded:
                return True

            self._set_status(f"Unloading {len(loaded)} resident model(s) (attempt {attempt}/3)…")
            for m in loaded:
                self._do_unload_request(m["id"], m["instance_id"])

            time.sleep(3)
            if not self._get_loaded_models():
                return True

        self._set_status("Failed to unload all models.", error=True)
        return False

    def _poll_loading(self, target_model_id: str, timeout=120) -> bool:
        """Poll the /v1/models endpoint to confirm the model is perfectly active before we generate."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._stop_flag:
                return False
            loaded_ids = [m["id"] for m in self._get_loaded_models()]
            if target_model_id in loaded_ids:
                return True
            time.sleep(2)
        return False

    def _load_model(self, model_id: str) -> bool:
        _, lm_admin = self._get_lm_urls()
        self._set_status(f"Clearing memory before loading {model_id}…")
        self._force_unload_all()
        time.sleep(2)

        if self._stop_flag: return False

        self._set_status(f"Loading: {model_id}…")
        try:
            r = requests.post(f"{lm_admin}/models/load",
                              json={"model": model_id},
                              timeout=LOAD_TIMEOUT)
            r.raise_for_status()
            self._currently_loaded_model = model_id
            
            self._set_status(f"Confirming {model_id} is active...")
            return self._poll_loading(model_id)

        except Exception as e:
            self._set_status(f"Load failed for {model_id}: {e}", error=True)
            return False

    def _unload_model(self, model_id: str) -> bool:
        self._set_status(f"Unloading: {model_id}…")
        loaded = self._get_loaded_models()
        target_instance = None
        for m in loaded:
            if m["id"] == model_id:
                target_instance = m["instance_id"]
                break
                
        if not target_instance:
            return True
            
        for attempt in range(1, 4):
            success = self._do_unload_request(model_id, target_instance)
            time.sleep(2)
            loaded_ids = [m["id"] for m in self._get_loaded_models()]
            if model_id not in loaded_ids:
                self._currently_loaded_model = None
                return True

        self._set_status(f"Could not verify unload of {model_id}!", error=True)
        return False

    def _generate(self, model_id: str, sys_prompt: str, user_prompt: str, max_wait: float | None) -> tuple[str, str, str]:
        lm_base, _ = self._get_lm_urls()
        
        messages = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
            
        # Payload Safety: format exact text message as a dictionary block for multimodal backends
        messages.append({
            "role": "user", 
            "content": [{"type": "text", "text": user_prompt}]
        })

        tokens_val = int(self.tokens_var.get())
        if tokens_val < 1: tokens_val = -1
        
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": tokens_val,
        }
        if not self.use_default_temp_var.get():
            payload["temperature"] = self.temp_var.get()

        try:
            self._set_status(f"Generating → {model_id}…")
            start_time = time.time()
            r = requests.post(f"{lm_base}/chat/completions",
                              json=payload, timeout=max_wait)
            
            if not r.ok:
                try:
                    err_details = r.json()
                except Exception:
                    err_details = r.text
                return f"[Generation error: HTTP {r.status_code} {r.reason}\nDetails: {err_details}]", "0.00", "0.0s"
                
            end_time = time.time()
            
            data = r.json()
            choices = data.get("choices", [])
            content = choices[0]["message"].get("content", "") if choices else "(No content returned)"
            
            usage = data.get("usage", {})
            tokens = usage.get("completion_tokens", 0)
            time_taken = end_time - start_time
            tps = (tokens / time_taken) if time_taken > 0 else 0
            
            return content, f"{tps:.2f}", f"{time_taken:.2f}s"

        except requests.exceptions.Timeout:
            return f"[Generation error: Request timed out after {max_wait}s]", "0.00", "0.0s"
        except Exception as e:
            return f"[Generation error: {e}]", "0.00", "0.0s"

    # ──────────────────────────────────────────────
    #  Batch worker thread
    # ──────────────────────────────────────────────
    def _run_batch(self, sys_prompt: str, prompt: str, output_folder: str, filename_fmt: str, max_wait: float | None):
        selected = [mid for mid, var in self._model_vars.items() if var.get()]
        total    = len(selected)
        done     = 0

        if total == 0:
            self._set_status("No models selected.", error=True)
            self._restore_ui()
            return

        self.counter_var.set(f"Models: {total} total, 0 done")
        session_id = time.strftime("%Y%m%d_%H%M%S")
        file_ext = self.format_var.get()

        for i, model_id in enumerate(selected):
            self._set_label(model_id, "⏳ waiting…", "gray")
            self._pause_event.wait()
            
            if self._stop_flag:
                self._set_status("Batch aborted by user.")
                break

            self._highlight_model(model_id, active=True)
            self._set_label(model_id, "⟳ loading…", "#E67E22")  # Orange
            
            ok = self._load_model(model_id)
            if not ok or self._stop_flag:
                if not self._stop_flag:
                    self._set_label(model_id, "✗ load fail", "#E74C3C")
                self._highlight_model(model_id, active=False)
                done += 1
                self._update_counter(done, total, i + 1)
                continue

            self._set_label(model_id, "⟳ generating…", "#3498DB")

            content, tps, time_taken = self._generate(model_id, sys_prompt, prompt, max_wait)

            if self._stop_flag:
                self._set_status("Batch aborted by user.")
                break

            # Filter thinking tags if requested
            if self.skip_thinking_var.get():
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

            safe_name = self._sanitize(model_id)
            # Ensure extension isn't duplicated
            base_filename = filename_fmt.replace("{model}", safe_name).replace("{session}", session_id)
            if not base_filename.endswith(file_ext):
                base_filename += file_ext
            
            filepath = os.path.join(output_folder, base_filename)
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    # Write markdown headers if format is markdown
                    if file_ext == ".md":
                        f.write(f"# Model: {model_id}\n")
                        f.write(f"**Session:** {session_id}\n\n")
                        f.write("---\n\n")
                        f.write(content)
                        f.write("\n\n---\n\n")
                        f.write(f"*Generation Time:* {time_taken}\n\n")
                        f.write(f"*Tokens Per Second (TPS):* {tps}\n")
                    else:
                        f.write(f"Model: {model_id}\n")
                        f.write(f"Session: {session_id}\n")
                        f.write("=" * 60 + "\n")
                        f.write(content)
                        f.write("\n\n" + "-" * 60 + "\n")
                        f.write(f"Generation Time: {time_taken}\n")
                        f.write(f"Tokens Per Second (TPS): {tps}\n")
                        
                self._set_label(model_id, "✓ done", "#2ECC71")
            except Exception as e:
                self._set_label(model_id, "✗ save fail", "#E74C3C")
                self._set_status(f"Save failed for {model_id}: {e}", error=True)

            self._highlight_model(model_id, active=False)

            unload_ok = self._unload_model(model_id)
            if not unload_ok:
                self._force_unload_all()

            done += 1
            self._update_counter(done, total, i + 1)

            if self._stop_flag:
                break

            try:
                delay = int(self.delay_var.get())
            except ValueError:
                delay = 0

            if delay > 0 and i < total - 1:
                self._set_status(f"Waiting {delay}s…")
                for _ in range(delay):
                    if self._stop_flag: break
                    time.sleep(1)

        self.progress_bar.set(1.0 if not self._stop_flag else done/total)
        if not self._stop_flag:
            self._set_status(f"Batch complete! {done}/{total} models processed.")
            self.root.after(0, lambda: messagebox.showinfo("Done", f"Batch complete!\n{done}/{total} models processed.\n\nOutput: {output_folder}"))
            
        self._last_output_folder = output_folder
        self._restore_ui()

    # ──────────────────────────────────────────────
    #  UI thread-safe helpers
    # ──────────────────────────────────────────────
    def _set_status(self, msg: str, error: bool = False):
        color = "#E74C3C" if error else "#3498DB"
        self.root.after(0, lambda: self.status_var.set(f"Status: {msg}"))
        self.root.after(0, lambda: self.status_label.configure(text_color=color))

    def _set_label(self, model_id: str, text: str, color: str):
        lbl = self._model_labels.get(model_id)
        if lbl:
            self.root.after(0, lambda: lbl.configure(text=text, text_color=color))

    def _highlight_model(self, model_id: str, active: bool):
        row = self._model_rows.get(model_id)
        if row:
            bg = ("#D6EAF8", "#2C3E50") if active else "transparent"
            try:
                self.root.after(0, lambda: row.configure(fg_color=bg))
            except Exception:
                pass

    def _update_counter(self, done: int, total: int, processed: int):
        pct = processed / total
        self.root.after(0, lambda: self.progress_bar.set(pct))
        self.root.after(0, lambda: self.counter_var.set(f"Models: {total} total, {done} done"))

    def _restore_ui(self):
        self.root.after(0, lambda: self.start_btn.configure(state="normal"))
        self.root.after(0, lambda: self.pause_btn.configure(state="disabled", text="⏸ Pause"))
        self.root.after(0, lambda: self.stop_btn.configure(state="disabled"))
        self.root.after(0, lambda: self.open_folder_btn.configure(state="normal"))
        self._pause_event.set()

    # ──────────────────────────────────────────────
    #  Button callbacks
    # ──────────────────────────────────────────────
    def _browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_var.set(folder)

    def _stop_batch(self):
        # Override behavior: Break the batch instantly, force unload everything to kill current generation
        self._set_status("Abort requested! Killing generation and clearing memory...")
        self._stop_flag = True
        self._pause_event.set()
        
        # Fire off an asynchronous force-unload to break the current generation block
        threading.Thread(target=self._force_unload_all, daemon=True).start()

    def _start_batch(self):
        sys_prompt    = self.sys_prompt_text.get("1.0", tk.END).strip()
        prompt        = self.prompt_text.get("1.0", tk.END).strip()
        output_folder = self.folder_var.get().strip()
        filename_fmt  = self.filename_fmt_var.get().strip()
        
        raw_max_wait  = self.max_wait_var.get().strip()
        max_wait = None
        if raw_max_wait and raw_max_wait != "0":
            try:
                max_wait = float(raw_max_wait)
            except ValueError:
                messagebox.showerror("Error", "Invalid Max Wait Time.")
                return

        if not prompt:
            messagebox.showerror("Error", "User Prompt cannot be empty.")
            return
        if not output_folder:
            messagebox.showerror("Error", "Output folder cannot be empty.")
            return
        if not os.path.isdir(output_folder):
            messagebox.showerror("Error", "Output folder does not exist.")
            return
        if "{model}" not in filename_fmt:
            if not messagebox.askyesno("Warning", "Filename format lacks {model} placeholder.\nOverwrites may occur.\nContinue?"):
                return

        selected_count = sum(1 for v in self._model_vars.values() if v.get())
        if selected_count == 0:
            messagebox.showerror("Error", "No models selected.")
            return

        self._stop_flag = False
        self._pause_event.set()
        self.progress_bar.set(0)
        self.open_folder_btn.configure(state="disabled")
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal", text="⏸ Pause")
        self.stop_btn.configure(state="normal")

        for mid, lbl in self._model_labels.items():
            if self._model_vars[mid].get():
                lbl.configure(text="⬤ queued", text_color="gray")
            else:
                lbl.configure(text="", text_color="gray")

        threading.Thread(
            target=self._run_batch,
            args=(sys_prompt, prompt, output_folder, filename_fmt, max_wait),
            daemon=True
        ).start()

    def _toggle_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            self.pause_btn.configure(text="▶ Resume")
            self._set_status("Paused (will wait after current operation).")
        else:
            self._pause_event.set()
            self.pause_btn.configure(text="⏸ Pause")
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

    @staticmethod
    def _sanitize(name: str) -> str:
        for ch in r'<>:"/\|?*':
            name = name.replace(ch, "_")
        return name


if __name__ == "__main__":
    root = ctk.CTk()
    app  = LMStudioBatchApp(root)
    root.mainloop()

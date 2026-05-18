"""
Tab Reader - a modern PDF + audio scroller for guitar / piano / sheet-music tabs.

Features
  * Open a PDF (your tab) and an MP3 or WAV (the song).
  * Play / Pause / Stop transport (Spacebar = play/pause).
  * Adjustable start delay, scroll speed, zoom, volume.
  * Per-song settings auto-saved and restored, keyed by audio filename.

Dependencies (install once):
    pip install pymupdf pillow pygame customtkinter

Run:
    python tab_reader.py
"""

import json
import os
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

try:
    import pygame
except ImportError:
    pygame = None


SETTINGS_FILE = Path.home() / ".tab_reader_settings.json"
PLAYLIST_FILE = Path.home() / ".tab_reader_playlist.json"

# ---------- Modern flat palette (no glass, just soft surfaces) ----------
BG          = "#18181b"   # window background
SURFACE     = "#27272a"   # cards / panels
SURFACE_2   = "#3f3f46"   # secondary buttons
ACCENT      = "#6366f1"   # indigo - primary action
ACCENT_HOV  = "#818cf8"
DANGER      = "#ef4444"
DANGER_HOV  = "#f87171"
TEXT        = "#e4e4e7"
TEXT_MUTED  = "#a1a1aa"
TEXT_DIM    = "#71717a"
CANVAS_BG   = "#1f1f23"

CORNER_LG   = 16
CORNER_MD   = 12
CORNER_SM   = 10

FONT_FAMILY = "Segoe UI"


class TabReader:
    def __init__(self, root) -> None:
        self.root = root
        self.root.title("Tab Reader")
        self.root.geometry("1000x900")
        self.root.configure(fg_color=BG)
        self.root.minsize(720, 520)

        # -------- state --------
        self.pdf_path: str | None = None
        self.audio_path: str | None = None
        self.pdf_doc = None
        self.page_images: list = []
        self.total_height: int = 0
        self.render_width: int = 0

        self.is_playing = False
        self.play_start_time: float | None = None
        self.elapsed_offset: float = 0.0
        self.scroll_pos: float = 0.0
        self._last_tick: float | None = None
        self._zoom_after_id: str | None = None

        # playlist state
        self.playlist: list[dict] = self._load_playlist_file()  # [{name, pdf, audio}]
        self.selected_idx: int | None = None
        self.entry_buttons: list = []  # CTkButton refs for highlighting

        self.settings = self._load_settings_file()

        self._build_ui()

        if pygame is not None:
            try:
                pygame.mixer.init()
            except Exception as e:
                messagebox.showwarning("Audio init", f"pygame.mixer couldn't start: {e}")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(33, self._tick)

    # ----------------------------------------------------------- UI ---------
    def _build_ui(self) -> None:
        # top transport "card" - explicit height so it hugs the buttons
        BTN_H   = 34          # button height
        BAR_PAD = 8           # vertical padding inside the bar
        BAR_H   = BTN_H + BAR_PAD * 2

        top = ctk.CTkFrame(self.root, fg_color=SURFACE, corner_radius=CORNER_LG, height=BAR_H)
        top.pack(fill="x", padx=14, pady=(12, 6))
        top.pack_propagate(False)  # keep our explicit height

        # file buttons (secondary)
        file_btn = dict(
            corner_radius=CORNER_SM, height=BTN_H, width=110,
            font=(FONT_FAMILY, 13),
            fg_color=SURFACE_2, hover_color="#52525b",
            text_color=TEXT, border_width=0,
        )
        ctk.CTkButton(top, text="Open PDF",  command=self.open_pdf,   **file_btn).pack(side="left", padx=(12, 6), pady=BAR_PAD)
        ctk.CTkButton(top, text="Open Audio", command=self.open_audio, **file_btn).pack(side="left", padx=6, pady=BAR_PAD)

        # divider (vertical thin line)
        ctk.CTkFrame(top, width=1, fg_color="#3f3f46").pack(side="left", fill="y", padx=10, pady=BAR_PAD + 2)

        # play (primary accent)
        primary_btn = dict(
            corner_radius=CORNER_SM, height=BTN_H, width=110,
            font=(FONT_FAMILY, 13, "bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOV,
            text_color="white", border_width=0,
        )
        self.play_btn = ctk.CTkButton(top, text="\u25B6  Play", command=self.toggle_play, **primary_btn)
        self.play_btn.pack(side="left", padx=6, pady=BAR_PAD)

        # stop / reset (secondary)
        secondary_btn = dict(
            corner_radius=CORNER_SM, height=BTN_H, width=100,
            font=(FONT_FAMILY, 13),
            fg_color=SURFACE_2, hover_color="#52525b",
            text_color=TEXT, border_width=0,
        )
        ctk.CTkButton(top, text="\u23F9  Stop",  command=self.stop,         **secondary_btn).pack(side="left", padx=6, pady=BAR_PAD)
        ctk.CTkButton(top, text="\u21BA  Reset", command=self.reset_scroll, **secondary_btn).pack(side="left", padx=6, pady=BAR_PAD)

        # save (right side, accent-tinted)
        save_btn = dict(
            corner_radius=CORNER_SM, height=BTN_H, width=170,
            font=(FONT_FAMILY, 13),
            fg_color="#3730a3", hover_color="#4338ca",
            text_color="white", border_width=0,
        )
        ctk.CTkButton(top, text="Save settings for song", command=self.save_current_settings,
                      **save_btn).pack(side="right", padx=(6, 12), pady=BAR_PAD)

        # ---------- body: sidebar (playlist) + main column ----------
        body_split = ctk.CTkFrame(self.root, fg_color="transparent")
        body_split.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        # sidebar (left)
        sidebar = ctk.CTkFrame(body_split, fg_color=SURFACE, corner_radius=CORNER_LG, width=240)
        sidebar.pack(side="left", fill="y", padx=(0, 10))
        sidebar.pack_propagate(False)
        self._build_playlist_sidebar(sidebar)

        # main column (right) - holds settings, status, canvas
        main_col = ctk.CTkFrame(body_split, fg_color="transparent")
        main_col.pack(side="left", fill="both", expand=True)

        # ---------- settings card ----------
        mid = ctk.CTkFrame(main_col, fg_color=SURFACE, corner_radius=CORNER_LG)
        mid.pack(fill="x", pady=(0, 7))

        grid = ctk.CTkFrame(mid, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=12)
        for c in range(4):
            grid.grid_columnconfigure(c, weight=1, uniform="col")

        # column 0: Start delay (entry)
        col0 = ctk.CTkFrame(grid, fg_color="transparent")
        col0.grid(row=0, column=0, sticky="ew", padx=8)
        ctk.CTkLabel(col0, text="Start delay", text_color=TEXT_MUTED,
                     font=(FONT_FAMILY, 11)).pack(anchor="w")
        delay_row = ctk.CTkFrame(col0, fg_color="transparent")
        delay_row.pack(fill="x", pady=(4, 0))
        self.start_var = tk.DoubleVar(value=0.0)
        self.delay_entry = ctk.CTkEntry(
            delay_row, textvariable=self.start_var,
            corner_radius=CORNER_SM, height=34, width=80,
            fg_color=BG, border_color=SURFACE_2, border_width=1,
            text_color=TEXT, font=(FONT_FAMILY, 13),
            justify="center",
        )
        self.delay_entry.pack(side="left")
        ctk.CTkLabel(delay_row, text="seconds", text_color=TEXT_DIM,
                     font=(FONT_FAMILY, 11)).pack(side="left", padx=(8, 0))

        # column 1: Scroll speed
        col1 = ctk.CTkFrame(grid, fg_color="transparent")
        col1.grid(row=0, column=1, sticky="ew", padx=8)
        speed_head = ctk.CTkFrame(col1, fg_color="transparent")
        speed_head.pack(fill="x")
        ctk.CTkLabel(speed_head, text="Scroll speed", text_color=TEXT_MUTED,
                     font=(FONT_FAMILY, 11)).pack(side="left")
        self.speed_value_lbl = ctk.CTkLabel(
            speed_head, text="30 px/s", text_color=TEXT,
            font=(FONT_FAMILY, 11, "bold"))
        self.speed_value_lbl.pack(side="right")
        self.speed_var = tk.DoubleVar(value=30.0)
        ctk.CTkSlider(
            col1, from_=1, to=300, number_of_steps=299,
            variable=self.speed_var, height=18,
            fg_color=SURFACE_2, progress_color=ACCENT,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            corner_radius=CORNER_SM,
            command=lambda v: self.speed_value_lbl.configure(text=f"{float(v):.0f} px/s"),
        ).pack(fill="x", pady=(8, 0))

        # column 2: Zoom
        col2 = ctk.CTkFrame(grid, fg_color="transparent")
        col2.grid(row=0, column=2, sticky="ew", padx=8)
        zoom_head = ctk.CTkFrame(col2, fg_color="transparent")
        zoom_head.pack(fill="x")
        ctk.CTkLabel(zoom_head, text="Zoom", text_color=TEXT_MUTED,
                     font=(FONT_FAMILY, 11)).pack(side="left")
        self.zoom_value_lbl = ctk.CTkLabel(
            zoom_head, text="100%", text_color=TEXT,
            font=(FONT_FAMILY, 11, "bold"))
        self.zoom_value_lbl.pack(side="right")
        self.zoom_var = tk.DoubleVar(value=100.0)
        ctk.CTkSlider(
            col2, from_=40, to=300, number_of_steps=52,
            variable=self.zoom_var, height=18,
            fg_color=SURFACE_2, progress_color=ACCENT,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            corner_radius=CORNER_SM,
            command=self._on_zoom_change,
        ).pack(fill="x", pady=(8, 0))

        # column 3: Volume
        col3 = ctk.CTkFrame(grid, fg_color="transparent")
        col3.grid(row=0, column=3, sticky="ew", padx=8)
        vol_head = ctk.CTkFrame(col3, fg_color="transparent")
        vol_head.pack(fill="x")
        ctk.CTkLabel(vol_head, text="Volume", text_color=TEXT_MUTED,
                     font=(FONT_FAMILY, 11)).pack(side="left")
        self.vol_value_lbl = ctk.CTkLabel(
            vol_head, text="80%", text_color=TEXT,
            font=(FONT_FAMILY, 11, "bold"))
        self.vol_value_lbl.pack(side="right")
        self.vol_var = tk.DoubleVar(value=0.8)
        ctk.CTkSlider(
            col3, from_=0.0, to=1.0, number_of_steps=20,
            variable=self.vol_var, height=18,
            fg_color=SURFACE_2, progress_color=ACCENT,
            button_color=ACCENT, button_hover_color=ACCENT_HOV,
            corner_radius=CORNER_SM,
            command=self._on_volume,
        ).pack(fill="x", pady=(8, 0))

        # ---------- status pill ----------
        self.status_var = tk.StringVar(value="Open a PDF and an audio file to begin.")
        status_card = ctk.CTkFrame(main_col, fg_color=SURFACE, corner_radius=CORNER_MD)
        status_card.pack(fill="x", pady=(0, 7))
        ctk.CTkLabel(status_card, textvariable=self.status_var,
                     text_color=TEXT_MUTED, font=(FONT_FAMILY, 11),
                     anchor="w").pack(fill="x", padx=14, pady=8)

        # ---------- PDF canvas card ----------
        canvas_card = ctk.CTkFrame(main_col, fg_color=SURFACE, corner_radius=CORNER_LG)
        canvas_card.pack(fill="both", expand=True)

        # inner frame to hold canvas + scrollbars (use plain tk widgets here; the
        # rounded card around it gives the modern look).
        body = tk.Frame(canvas_card, bg=SURFACE, highlightthickness=0)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        self.canvas = tk.Canvas(body, bg=CANVAS_BG, highlightthickness=0, bd=0)
        sb_y = ctk.CTkScrollbar(body, orientation="vertical",   command=self.canvas.yview,
                                fg_color="transparent", button_color=SURFACE_2,
                                button_hover_color="#52525b", corner_radius=CORNER_SM)
        sb_x = ctk.CTkScrollbar(body, orientation="horizontal", command=self.canvas.xview,
                                fg_color="transparent", button_color=SURFACE_2,
                                button_hover_color="#52525b", corner_radius=CORNER_SM)
        self.canvas.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

        sb_y.pack(side="right", fill="y")
        sb_x.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        # mouse-wheel scrolling
        self.canvas.bind("<MouseWheel>", lambda e: self._wheel(e.delta))
        self.canvas.bind("<Button-4>",   lambda e: self._wheel(120))
        self.canvas.bind("<Button-5>",   lambda e: self._wheel(-120))

        # space-bar = play/pause (but not when typing in the delay entry)
        def _space(event):
            if event.widget is not self.delay_entry:
                self.toggle_play()
                return "break"
        self.root.bind("<space>", _space)

    def _wheel(self, delta: int) -> None:
        self.canvas.yview_scroll(-1 * int(delta / 120) * 3, "units")
        self._sync_scroll_pos_from_canvas()

    def _sync_scroll_pos_from_canvas(self) -> None:
        if self.total_height <= 0:
            return
        top_frac = self.canvas.yview()[0]
        visible = max(1, self.canvas.winfo_height())
        max_scroll = max(1, self.total_height - visible)
        self.scroll_pos = top_frac * max_scroll

    # --------------------------------------------------------- PDF ---------
    def open_pdf(self) -> None:
        if fitz is None or Image is None:
            messagebox.showerror(
                "Missing dependency",
                "PyMuPDF and Pillow are required.\n\nInstall:\n    pip install pymupdf pillow pygame customtkinter"
            )
            return
        path = filedialog.askopenfilename(
            title="Select PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        self._load_pdf(path)

    def _load_pdf(self, path: str) -> bool:
        if fitz is None or Image is None:
            return False
        try:
            self.pdf_path = path
            self.pdf_doc = None  # force reopen
            self._render_pdf()
            self.status_var.set(f"Loaded PDF: {os.path.basename(path)}")
            return True
        except Exception as e:
            messagebox.showerror("PDF load error", str(e))
            return False

    def _render_pdf(self, preserve_position: bool = False) -> None:
        if not self.pdf_path:
            return

        old_total = self.total_height
        old_pos = self.scroll_pos
        rel_pos = (old_pos / old_total) if (preserve_position and old_total > 0) else 0.0

        self.canvas.delete("all")
        self.page_images.clear()

        self.root.update_idletasks()
        canvas_w = self.canvas.winfo_width() or 900

        zoom_pct = max(10.0, float(self.zoom_var.get())) / 100.0

        if self.pdf_doc is None:
            self.pdf_doc = fitz.open(self.pdf_path)
        doc = self.pdf_doc

        first_page = doc[0]
        base_zoom = canvas_w / first_page.rect.width
        effective_zoom = base_zoom * zoom_pct
        page_render_w = int(first_page.rect.width * effective_zoom)
        self.render_width = page_render_w

        scroll_w = max(canvas_w, page_render_w)

        y = 0
        for page in doc:
            mat = fitz.Matrix(effective_zoom, effective_zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            photo = ImageTk.PhotoImage(img)
            self.page_images.append(photo)
            self.canvas.create_image(scroll_w // 2, y, anchor="n", image=photo)
            y += pix.height + 14  # slightly more breathing room between pages

        self.total_height = y
        self.canvas.configure(scrollregion=(0, 0, scroll_w, y))

        if preserve_position:
            self.scroll_pos = rel_pos * y
            visible = max(1, self.canvas.winfo_height())
            max_scroll = max(1, y - visible)
            self.canvas.yview_moveto(max(0.0, min(1.0, self.scroll_pos / max_scroll)))
        else:
            self.canvas.yview_moveto(0)
            self.scroll_pos = 0.0

    def _on_zoom_change(self, val) -> None:
        try:
            self.zoom_value_lbl.configure(text=f"{float(val):.0f}%")
        except Exception:
            pass
        if self._zoom_after_id is not None:
            try:
                self.root.after_cancel(self._zoom_after_id)
            except Exception:
                pass
        self._zoom_after_id = self.root.after(150, self._zoom_apply)

    def _zoom_apply(self) -> None:
        self._zoom_after_id = None
        if self.pdf_path:
            self._render_pdf(preserve_position=True)
            self.status_var.set(f"Zoom: {float(self.zoom_var.get()):.0f}%")

    # -------------------------------------------------------- AUDIO --------
    def open_audio(self) -> None:
        if pygame is None:
            messagebox.showerror(
                "Missing dependency",
                "pygame is required for audio.\n\nInstall:\n    pip install pygame"
            )
            return
        path = filedialog.askopenfilename(
            title="Select audio file",
            filetypes=[("Audio", "*.mp3 *.wav"), ("MP3", "*.mp3"), ("WAV", "*.wav"), ("All files", "*.*")],
        )
        if not path:
            return
        self._load_audio(path)

    def _load_audio(self, path: str) -> bool:
        if pygame is None:
            return False
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(path)
        except Exception as e:
            messagebox.showerror("Audio load error", str(e))
            return False

        self.audio_path = path
        self.is_playing = False
        self.elapsed_offset = 0.0
        self.play_start_time = None
        self.play_btn.configure(text="\u25B6  Play")

        s = self.settings.get(self._song_key(), {})
        if "start_delay" in s:
            self.start_var.set(float(s["start_delay"]))
        if "scroll_speed" in s:
            self.speed_var.set(float(s["scroll_speed"]))
            self.speed_value_lbl.configure(text=f"{float(s['scroll_speed']):.0f} px/s")
        if "zoom" in s:
            self.zoom_var.set(float(s["zoom"]))
            self.zoom_value_lbl.configure(text=f"{float(s['zoom']):.0f}%")
            if self.pdf_path:
                self._render_pdf(preserve_position=False)

        pygame.mixer.music.set_volume(float(self.vol_var.get()))

        loaded_msg = "  -  saved settings restored" if s else ""
        self.status_var.set(f"Loaded audio: {os.path.basename(path)}{loaded_msg}")
        return True

    def _on_volume(self, val) -> None:
        try:
            self.vol_value_lbl.configure(text=f"{float(val) * 100:.0f}%")
        except Exception:
            pass
        if pygame is not None:
            try:
                pygame.mixer.music.set_volume(float(self.vol_var.get()))
            except Exception:
                pass

    # ---------------------------------------------------- TRANSPORT --------
    def toggle_play(self) -> None:
        if not self.audio_path or pygame is None:
            self.status_var.set("Load an audio file first.")
            return

        if not self.is_playing:
            try:
                if self.elapsed_offset > 0:
                    pygame.mixer.music.unpause()
                else:
                    pygame.mixer.music.play()
            except Exception as e:
                messagebox.showerror("Playback error", str(e))
                return
            self.play_start_time = time.time() - self.elapsed_offset
            self.is_playing = True
            self._last_tick = time.time()
            self.play_btn.configure(text="\u23F8  Pause")
        else:
            try:
                pygame.mixer.music.pause()
            except Exception:
                pass
            if self.play_start_time is not None:
                self.elapsed_offset = time.time() - self.play_start_time
            self.is_playing = False
            self.play_btn.configure(text="\u25B6  Play")

    def stop(self) -> None:
        if pygame is not None:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self.is_playing = False
        self.elapsed_offset = 0.0
        self.play_start_time = None
        self._last_tick = None
        self.play_btn.configure(text="\u25B6  Play")
        self.status_var.set("Stopped.")

    def reset_scroll(self) -> None:
        self.scroll_pos = 0.0
        self.canvas.yview_moveto(0)

    # ---------------------------------------------------- SETTINGS ---------
    def _song_key(self) -> str:
        return os.path.basename(self.audio_path) if self.audio_path else ""

    def save_current_settings(self) -> None:
        if not self.audio_path:
            self.status_var.set("Load an audio file first to save its settings.")
            return
        try:
            delay = float(self.start_var.get())
        except Exception:
            delay = 0.0
        self.settings[self._song_key()] = {
            "start_delay":  delay,
            "scroll_speed": float(self.speed_var.get()),
            "zoom":         float(self.zoom_var.get()),
        }
        self._write_settings_file()
        self.status_var.set(
            f"Saved '{self._song_key()}'  -  "
            f"delay {delay:.2f}s | speed {self.speed_var.get():.0f} px/s | "
            f"zoom {self.zoom_var.get():.0f}%"
        )

    def _load_settings_file(self) -> dict:
        if SETTINGS_FILE.exists():
            try:
                return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _write_settings_file(self) -> None:
        try:
            SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        except Exception as e:
            messagebox.showerror("Couldn't save", str(e))

    # ------------------------------------------------------- TICK ----------
    def _tick(self) -> None:
        try:
            if self.is_playing and self.total_height > 0 and self.play_start_time is not None:
                now = time.time()
                elapsed = now - self.play_start_time
                try:
                    start_delay = float(self.start_var.get())
                except Exception:
                    start_delay = 0.0

                if elapsed >= start_delay:
                    speed = float(self.speed_var.get())
                    if self._last_tick is None:
                        self._last_tick = now
                    dt = now - self._last_tick
                    self._last_tick = now
                    self.scroll_pos += speed * dt

                    visible = max(1, self.canvas.winfo_height())
                    max_scroll = max(1, self.total_height - visible)
                    frac = max(0.0, min(1.0, self.scroll_pos / max_scroll))
                    self.canvas.yview_moveto(frac)

                    self.status_var.set(
                        f"Playing  -  t={elapsed:6.2f}s  -  scroll {self.scroll_pos:6.0f} px  -  {speed:.0f} px/s"
                    )
                else:
                    self._last_tick = now
                    remaining = start_delay - elapsed
                    self.status_var.set(
                        f"Playing  -  t={elapsed:6.2f}s  -  scroll begins in {remaining:5.2f}s"
                    )
            else:
                self._last_tick = None
        finally:
            self.root.after(33, self._tick)

    # ---------------------------------------------------- PLAYLIST ---------
    def _build_playlist_sidebar(self, parent) -> None:
        # header
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(12, 6))
        ctk.CTkLabel(head, text="Playlist", text_color=TEXT,
                     font=(FONT_FAMILY, 14, "bold")).pack(side="left")

        # add / remove row
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkButton(
            btn_row, text="+ Add", command=self.add_to_playlist,
            corner_radius=CORNER_SM, height=30, width=82,
            font=(FONT_FAMILY, 12),
            fg_color=ACCENT, hover_color=ACCENT_HOV,
            text_color="white", border_width=0,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            btn_row, text="â Remove", command=self.remove_from_playlist,
            corner_radius=CORNER_SM, height=30, width=92,
            font=(FONT_FAMILY, 12),
            fg_color=SURFACE_2, hover_color="#52525b",
            text_color=TEXT, border_width=0,
        ).pack(side="left", padx=4)

        # scrollable list of entries
        self.entry_list = ctk.CTkScrollableFrame(
            parent, fg_color=BG, corner_radius=CORNER_SM,
            scrollbar_button_color=SURFACE_2,
            scrollbar_button_hover_color="#52525b",
        )
        self.entry_list.pack(fill="both", expand=True, padx=10, pady=(0, 12))

        self._refresh_playlist_ui()

    def _refresh_playlist_ui(self) -> None:
        # rebuild the entry buttons in the scrollable list
        for child in self.entry_list.winfo_children():
            child.destroy()
        self.entry_buttons = []

        if not self.playlist:
            ctk.CTkLabel(
                self.entry_list, text="No songs yet.\nClick + Add to start.",
                text_color=TEXT_DIM, font=(FONT_FAMILY, 11), justify="center"
            ).pack(pady=16)
            return

        for i, entry in enumerate(self.playlist):
            name = entry.get("name") or os.path.basename(entry.get("audio", "")) or f"Entry {i+1}"
            is_active = (i == self.selected_idx)
            btn = ctk.CTkButton(
                self.entry_list, text=name, anchor="w",
                command=lambda idx=i: self.load_playlist_entry(idx),
                corner_radius=CORNER_SM, height=32,
                font=(FONT_FAMILY, 12),
                fg_color=(ACCENT if is_active else "transparent"),
                hover_color=(ACCENT_HOV if is_active else SURFACE_2),
                text_color=("white" if is_active else TEXT),
                border_width=0,
            )
            btn.pack(fill="x", padx=4, pady=2)
            self.entry_buttons.append(btn)

    def add_to_playlist(self) -> None:
        # pick PDF
        pdf = filedialog.askopenfilename(
            title="Select PDF for new playlist entry",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not pdf:
            return
        # pick audio
        audio = filedialog.askopenfilename(
            title="Select audio file (MP3 / WAV) for new playlist entry",
            filetypes=[("Audio", "*.mp3 *.wav"), ("MP3", "*.mp3"), ("WAV", "*.wav"), ("All files", "*.*")],
        )
        if not audio:
            return
        name = os.path.splitext(os.path.basename(audio))[0]
        self.playlist.append({"name": name, "pdf": pdf, "audio": audio})
        self._write_playlist_file()
        self._refresh_playlist_ui()
        self.status_var.set(f"Added '{name}' to playlist.")

    def remove_from_playlist(self) -> None:
        if self.selected_idx is None or not (0 <= self.selected_idx < len(self.playlist)):
            self.status_var.set("Select a playlist entry first (click it once).")
            return
        removed = self.playlist.pop(self.selected_idx)
        self.selected_idx = None
        self._write_playlist_file()
        self._refresh_playlist_ui()
        self.status_var.set(f"Removed '{removed.get('name', '?')}' from playlist.")

    def load_playlist_entry(self, idx: int) -> None:
        if not (0 <= idx < len(self.playlist)):
            return
        entry = self.playlist[idx]
        self.selected_idx = idx
        # stop any currently playing audio cleanly
        self.stop()
        ok_pdf = self._load_pdf(entry["pdf"])
        ok_aud = self._load_audio(entry["audio"])
        self._refresh_playlist_ui()
        if ok_pdf and ok_aud:
            self.status_var.set(f"Loaded '{entry.get('name', os.path.basename(entry['audio']))}' from playlist.")

    def _load_playlist_file(self) -> list:
        if PLAYLIST_FILE.exists():
            try:
                data = json.loads(PLAYLIST_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception:
                return []
        return []

    def _write_playlist_file(self) -> None:
        try:
            PLAYLIST_FILE.write_text(json.dumps(self.playlist, indent=2), encoding="utf-8")
        except Exception as e:
            messagebox.showerror("Couldn't save playlist", str(e))

    # ------------------------------------------------------- CLOSE ---------
    def _on_close(self) -> None:
        try:
            if pygame is not None:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except Exception:
            pass
        self.root.destroy()


def main() -> None:
    if ctk is None:
        # Friendly fallback dialog if customtkinter isn't installed.
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Missing dependency",
            "customtkinter is required for the modern UI.\n\n"
            "Install with:\n    pip install customtkinter\n\n"
            "(also: pymupdf pillow pygame)"
        )
        return

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    TabReader(root)
    root.mainloop()


if __name__ == "__main__":
    main()

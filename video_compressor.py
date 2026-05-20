import sys
import subprocess
import os
import re

# ── Automatically install imageio-ffmpeg on startup ───────────────────
try:
    import imageio_ffmpeg
except ImportError:
    print("imageio-ffmpeg not found. Installing automatically...")
    try:
        # Attempt installation with a flag for modern Linux distributions
        subprocess.run([sys.executable, "-m", "pip", "install", "imageio-ffmpeg", "--break-system-packages"], check=True)
    except subprocess.CalledProcessError:
        # Fallback to the standard installation method (for Windows/macOS)
        subprocess.run([sys.executable, "-m", "pip", "install", "imageio-ffmpeg"], check=True)
    import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading

# ── Function to retrieve video info without using ffprobe ─────────────
def get_video_info(path):
    """Returns (duration_seconds, has_audio) using only ffmpeg"""
    result = subprocess.run(
        [FFMPEG, "-nostdin", "-i", path],
        capture_output=True, text=True, errors="ignore"
    )
    stderr = result.stderr

    # Parse duration regex pattern: Duration: 00:02:30.45
    duration = 0.0
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+)[\.,](\d+)", stderr)
    if match:
        h, m, s, ms = match.groups()
        duration = int(h) * 3600 + int(m) * 60 + int(s) + float(f"0.{ms}")

    # Check for the presence of an audio stream
    has_audio = bool(re.search(r"Stream #.*Audio:", stderr))
    
    return duration, has_audio

# ── Main compression function ─────────────────────────────────────────
def compress_video(input_path, output_path, target_mb, crf,
                   audio_bitrate_k, progress_cb, done_cb, cancel_ev):
    try:
        duration, has_audio = get_video_info(input_path)
        
        if duration == 0.0:
            done_cb(False, "Could not determine video duration. File might be corrupted.")
            return

        target_bits = target_mb * 8 * 1024 * 1024
        audio_bits = (audio_bitrate_k * 1024 * duration) if has_audio else 0
        video_bitrate = int((target_bits - audio_bits) / duration)

        if video_bitrate < 10_000:
            done_cb(False, "Target size is too small for this video's duration.")
            return

        vbr = f"{video_bitrate // 1000}k"

        # ── Pass 1 (Analysis) ──────────────────────────────────────────
        progress_cb(0, "Pass 1: analyzing…")
        
        # Omit the conflicting -crf parameter for 2-pass bitrate encoding.
        # Use a universal "-" output instead of system NUL//dev/null for optimal stability.
        p1 = subprocess.run(
            [FFMPEG, "-nostdin", "-y", "-i", input_path,
             "-c:v", "libx264", "-b:v", vbr,
             "-pass", "1", "-an", "-f", "null", "-"],
            capture_output=True, text=True
        )
        
        if cancel_ev.is_set():
            done_cb(False, "Cancelled.")
            return
        if p1.returncode != 0:
            done_cb(False, "Pass 1 failed:\n" + p1.stderr[-400:])
            return

        # ── Pass 2 (Encoding) ──────────────────────────────────────────
        progress_cb(2, "Pass 2: Encoding starting…")
        audio_args = (["-c:a", "aac", "-b:a", f"{audio_bitrate_k}k"]
                      if has_audio else ["-an"])

        # Redirect stderr to DEVNULL to prevent log buffer overflows from causing a deadlock
        proc = subprocess.Popen(
            [FFMPEG, "-nostdin", "-y", "-i", input_path,
             "-c:v", "libx264", "-b:v", vbr,
             "-pass", "2",
             *audio_args,
             "-progress", "pipe:1",
             output_path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
        )

        for line in proc.stdout:
            if cancel_ev.is_set():
                proc.terminate()
                done_cb(False, "Cancelled.")
                return
            if line.startswith("out_time_ms="):
                try:
                    ms = int(line.strip().split("=")[1])
                    # Calculate progress scaling from 2% to 99%
                    pct = min(99, max(2, int(ms / 1e6 / duration * 100)))
                    progress_cb(pct, f"Encoding… {pct}%")
                except ValueError:
                    pass

        proc.wait()
        if proc.returncode != 0:
            done_cb(False, "Pass 2 failed. Verify your output path or permissions.")
            return

        # Clean up temporary FFmpeg log files generated during 2-pass compression
        for log_file in ["ffmpeg2pass-0.log", "ffmpeg2pass-0.log.mbtree"]:
            if os.path.exists(log_file):
                try: os.remove(log_file)
                except: pass

        actual = os.path.getsize(output_path) / (1024 * 1024)
        done_cb(True, f"Done!  Actual size: {actual:.2f} MB")

    except Exception as e:
        done_cb(False, str(e))

# ════════════════════════════════════════════════════════════
#  UI (Interface configurations and styling colors)
# ════════════════════════════════════════════════════════════
BG      = "#16161e"
CARD    = "#1f1f2e"
BORDER  = "#2e2e42"
ACCENT  = "#7c3aed"
HOVER   = "#6d28d9"
FG      = "#e2e8f0"
MUTED   = "#8b8fa8"
ENTRY   = "#0d0d1a"
SUCCESS = "#16a34a"
DANGER  = "#dc2626"

def mk_label(parent, text, size=10, color=FG, bold=False):
    return tk.Label(parent, text=text, bg=parent["bg"], fg=color,
                    font=("Segoe UI", size, "bold" if bold else "normal"))

def mk_btn(parent, text, cmd, color=ACCENT, hover=HOVER, state="normal"):
    b = tk.Button(parent, text=text, command=cmd,
                  bg=color, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  activebackground=hover, activeforeground="white",
                  state=state, bd=0)
    b.bind("<Enter>", lambda _: b.config(bg=hover) if b["state"] == "normal" else None)
    b.bind("<Leave>", lambda _: b.config(bg=color) if b["state"] == "normal" else None)
    return b

def mk_card(parent, pady=(0, 10)):
    f = tk.Frame(parent, bg=CARD, padx=16, pady=12,
                 highlightbackground=BORDER, highlightthickness=1)
    f.pack(fill="x", padx=20, pady=pady)
    return f

class App:
    def __init__(self, root):
        self.root = root
        root.title("Video Compressor")
        root.geometry("600x580")
        root.resizable(False, False)
        root.configure(bg=BG)

        self._cancel = threading.Event()
        self._build()

    def _build(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Green.Horizontal.TProgressbar",
                        troughcolor=ENTRY, background=ACCENT,
                        thickness=8, bordercolor=CARD,
                        lightcolor=ACCENT, darkcolor=ACCENT)

        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(18, 8))
        mk_label(hdr, "🎬  Video Compressor", 15, FG, bold=True).pack(side="left")

        c = mk_card(self.root)
        mk_label(c, "Input video", color=MUTED).pack(anchor="w")
        self.inp = tk.StringVar()
        self._path_row(c, self.inp, self._pick_input)

        c = mk_card(self.root)
        mk_label(c, "Output file", color=MUTED).pack(anchor="w")
        self.out = tk.StringVar()
        self._path_row(c, self.out, self._pick_output)

        c = mk_card(self.root)
        mk_label(c, "Settings", color=MUTED).pack(anchor="w", pady=(0, 8))

        row = tk.Frame(c, bg=CARD)
        row.pack(fill="x")

        left = tk.Frame(row, bg=CARD)
        left.pack(side="left", fill="x", expand=True, padx=(0, 16))
        mk_label(left, "Target size (MB)", color=MUTED).pack(anchor="w")
        self.size_var = tk.IntVar(value=50)
        sb = tk.Spinbox(left, from_=1, to=100000, textvariable=self.size_var,
                        width=9, bg=ENTRY, fg=FG, buttonbackground=BORDER,
                        relief="flat", font=("Segoe UI", 11),
                        insertbackground=FG, bd=0)
        sb.pack(anchor="w", ipady=5, ipadx=6, pady=(4, 0))

        right = tk.Frame(row, bg=CARD)
        right.pack(side="left", fill="x", expand=True)
        self.crf_var = tk.IntVar(value=23)
        self._crf_lbl = mk_label(right, self._crf_text(23), color=MUTED)
        self._crf_lbl.pack(anchor="w")
        tk.Scale(right, from_=0, to=51, orient="horizontal",
                 variable=self.crf_var, command=self._on_crf,
                 bg=CARD, fg=FG, troughcolor=ENTRY,
                 highlightthickness=0, sliderrelief="flat",
                 activebackground=ACCENT, length=200,
                 showvalue=False).pack(anchor="w", pady=(4, 0))

        arow = tk.Frame(c, bg=CARD)
        arow.pack(fill="x", pady=(10, 0))
        mk_label(arow, "Audio bitrate:", color=MUTED).pack(side="left")
        self.audio_var = tk.StringVar(value="128")
        for v in ["64", "96", "128", "192", "320"]:
            tk.Radiobutton(arow, text=f"{v}k", variable=self.audio_var, value=v,
                           bg=CARD, fg=FG, selectcolor=ACCENT,
                           activebackground=CARD, activeforeground=FG,
                           font=("Segoe UI", 10), cursor="hand2").pack(side="left", padx=5)

        c = mk_card(self.root, pady=(0, 8))
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(c, textvariable=self.status_var, bg=CARD, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 6))
        
        self.pvar = tk.IntVar()
        self.pbar = ttk.Progressbar(c, variable=self.pvar, maximum=100, style="Green.Horizontal.TProgressbar", length=530)
        self.pbar.pack(fill="x")

        brow = tk.Frame(self.root, bg=BG)
        brow.pack(pady=(4, 16))
        self.go_btn = mk_btn(brow, "▶️  Compress", self._start)
        self.go_btn.pack(side="left", ipady=9, ipadx=10, padx=(0, 10))
        self.cancel_btn = mk_btn(brow, "✕  Cancel", self._do_cancel, color=DANGER, hover="#b91c1c", state="disabled")
        self.cancel_btn.pack(side="left", ipady=9, ipadx=10)

    def _path_row(self, parent, var, cmd):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=(4, 0))
        tk.Entry(row, textvariable=var, bg=ENTRY, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 10), bd=0).pack(side="left", fill="x", expand=True, ipady=6, ipadx=8)
        mk_btn(row, "Browse", cmd).pack(side="left", padx=(6, 0), ipady=6, ipadx=8)

    @staticmethod
    def _crf_text(v):
        v = int(v)
        q = ("Visually lossless" if v <= 18 else "High quality" if v <= 23 else "Medium quality" if v <= 28 else "Low quality")
        return f"CRF {v}  —  {q}"

    def _on_crf(self, v):
        self._crf_lbl.config(text=self._crf_text(v))

    def _pick_input(self):
        p = filedialog.askopenfilename(title="Select video", filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv"), ("All files", "*.*")])
        if p:
            self.inp.set(p)
            if not self.out.get():
                base, ext = os.path.splitext(p)
                self.out.set(base + "_compressed.mp4")

    def _pick_output(self):
        p = filedialog.asksaveasfilename(title="Save as", defaultextension=".mp4", filetypes=[("MP4", "*.mp4"), ("MKV", "*.mkv"), ("All files", "*.*")])
        if p:
            self.out.set(p)

    def _start(self):
        inp = self.inp.get().strip()
        out = self.out.get().strip()
        if not inp or not os.path.exists(inp):
            messagebox.showerror("Error", "Select a valid input file.")
            return
        if not out:
            messagebox.showerror("Error", "Specify an output path.")
            return

        self._cancel.clear()
        self.go_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.pvar.set(0)
        self.status_var.set("Starting…")

        threading.Thread(
            target=compress_video,
            args=(inp, out, self.size_var.get(), self.crf_var.get(), int(self.audio_var.get()), self._on_progress, self._on_done, self._cancel),
            daemon=True
        ).start()

    def _do_cancel(self):
        self._cancel.set()
        self.status_var.set("Cancelling…")

    def _on_progress(self, pct, msg):
        self.root.after(0, lambda: (self.pvar.set(pct), self.status_var.set(msg)))

    def _on_done(self, ok, msg):
        def _update():
            self.go_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")
            self.pvar.set(100 if ok else 0)
            self.status_var.set(msg)
            (messagebox.showinfo if ok else messagebox.showerror)("Done" if ok else "Error", msg)
        self.root.after(0, _update)

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
    

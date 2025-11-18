import argparse
import sys
import time
import os
import json
import yt_dlp

CONFIG_FILE = "downloader_config.json"


def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_config(config: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f)
    except Exception:
        pass


def default_download_dir(config: dict) -> str:
    return config.get("download_location", os.path.join(os.path.expanduser("~"), "Downloads"))


def quality_to_format(quality: str) -> str:
    if quality.lower() in ("best", "best available", "auto"):
        return "best"
    try:
        height = int("".join(ch for ch in quality if ch.isdigit()))
    except Exception:
        height = 1080
    return f"best[height<={height}]/bestvideo[height<={height}]+bestaudio/best"


class ConsoleProgress:
    def __init__(self):
        self._last_shown = -1
        self._finished_line_printed = False

    def hook(self, d: dict):
        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            speed = d.get("speed")
            eta = d.get("eta")
            percent = None
            if total and total > 0:
                percent = int(max(0.0, min(100.0, (downloaded / total) * 100.0)))
            self._print_progress(percent, speed, eta)
        elif status == "finished":
            self._print_progress(100, None, None)
            self._println("Processing file...")

    def _human_speed(self, bps):
        if not bps:
            return "?"
        units = ["B/s", "KB/s", "MB/s", "GB/s"]
        i = 0
        while bps >= 1024 and i < len(units) - 1:
            bps /= 1024.0
            i += 1
        return f"{bps:.2f} {units[i]}"

    def _format_eta(self, seconds):
        if seconds is None:
            return "?"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _print_progress(self, percent, speed, eta):
        if percent is None:
            line = f"Downloading... (unknown size) | {self._human_speed(speed)} | ETA {self._format_eta(eta)}"
            print(f"\r{line}", end="", flush=True)
            self._finished_line_printed = False
            return
        if percent == self._last_shown:
            return
        self._last_shown = percent
        line = f"Downloading: {percent:3d}% | {self._human_speed(speed)} | ETA {self._format_eta(eta)}"
        print(f"\r{line}", end="", flush=True)
        self._finished_line_printed = False

    def _println(self, text: str):
        if not self._finished_line_printed:
            print()
            self._finished_line_printed = True
        print(text)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="YouTube Video Downloader (CLI)")
    parser.add_argument("url", nargs="?", help="YouTube video URL")
    parser.add_argument(
        "-o", "--output-dir",
        help="Download directory (defaults to last used or ~/Downloads)")
    parser.add_argument(
        "-q", "--quality",
        choices=["2160p", "1440p", "1080p", "720p", "480p", "360p", "best"],
        default=None,
        help="Preferred video quality (default 1080p; 'best' for best available)")
    parser.add_argument(
        "--filename-template",
        default="%(title)s.%(ext)s",
        help="Output filename template (yt-dlp template)")
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Run in interactive prompt mode (useful when double-clicking)")
    return parser.parse_args(argv)


def normalize_url(url: str):
    if not url:
        return None
    u = url.strip()
    if os.path.exists(u):
        return None
    if u.lower().startswith("http://") or u.lower().startswith("https://"):
        return u
    prefixes = ("www.", "youtube.com", "m.youtube.com", "youtu.be")
    if u.lower().startswith(prefixes):
        return f"https://{u}"
    return None


def _interactive_prompt(config):
    print("YouTube Video Downloader (interactive)")
    print("\nPress Enter to accept defaults shown in [brackets].\n")
    url = ""
    while True:
        url = input("Video URL: ").strip()
        url_norm = normalize_url(url)
        if url_norm:
            url = url_norm
            break
        print("Please enter a valid URL starting with http:// or https:// (e.g., https://youtu.be/...).")
    default_dir = default_download_dir(config)
    out_dir = input(f"Download directory [{default_dir}]: ").strip() or default_dir
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        print(f"Invalid directory '{out_dir}': {e}")
        return None
    default_quality = config.get("quality", "1080p")
    print("Available qualities: 2160p, 1440p, 1080p, 720p, 480p, 360p, best")
    quality = input(f"Quality [{default_quality}]: ").strip() or default_quality
    quality = quality.lower()
    if quality not in ("2160p", "1440p", "1080p", "720p", "480p", "360p", "best"):
        try:
            height = int("".join(ch for ch in quality if ch.isdigit()))
            if height in (2160, 1440, 1080, 720, 480, 360):
                quality = f"{height}p"
            else:
                quality = "1080p"
        except Exception:
            quality = "1080p"
    return {"url": url, "out_dir": out_dir, "quality": quality}


def main(argv=None) -> int:
    args = parse_args(argv)
    config = load_config()
    if args.interactive or not args.url:
        info = _interactive_prompt(config)
        if not info:
            return 2
        url = info["url"]
        out_dir = info["out_dir"]
        quality = info["quality"]
    else:
        url = normalize_url(args.url)
        if not url:
            print("Error: invalid URL. Provide a URL starting with http(s) or run with --interactive.", file=sys.stderr)
            return 2
        out_dir = args.output_dir or default_download_dir(config)
        quality = args.quality or config.get("quality", "1080p")

    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        print(f"Error: invalid output directory: {e}", file=sys.stderr)
        return 2

    format_string = quality_to_format(quality)

    progress = ConsoleProgress()
    ydl_opts = {
        "format": format_string,
        "outtmpl": os.path.join(out_dir, args.filename_template),
        "quiet": True,
        "no_warnings": False,
        "noprogress": True,
        "progress_hooks": [progress.hook],
    }

    print(f"Saving to: {out_dir}")
    print(f"Quality: {quality}  (format: {format_string})")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        progress._println("Download completed successfully.")
        config["download_location"] = out_dir
        config["quality"] = quality
        save_config(config)
        return 0
    except Exception as e:
        err = str(e)
        if "ffmpeg" in err.lower():
            err += ("\nNote: Some quality options require ffmpeg. "
                    "Try --quality best, or install ffmpeg: https://ffmpeg.org/download.html")
        print(f"Download failed: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

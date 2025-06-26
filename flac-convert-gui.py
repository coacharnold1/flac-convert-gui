#!/usr/bin/env python3
# version 1.9
# Threading issue fixed, stop button fix, default to flac16 on start - grey out mp3 spin wheel
# CLI versions - convert-audio.fish and flac-py-convert
# v1.4 added ripper log,    fixed issues with conversion identification
# v1.5 changed metadata line to correct mtadata copy issue - new copied line below
#----------"-map_metadata", "0",  # Map all metadata (including embedded artwork as a picture tag)
# v1.6 Added "Delete .cue Files" option and Output Subdirectory feature
# v1.7 (Fix for 24-bit detection using ffprobe, improved error handling)
# v1.8 (Log file path fixed for /usr/bin execution)
# v1.9 - fixed issue to delete  cue file and fault identifying bit depth in conversions 
VERSION = "1.9" # Updated version number
DATE = "June 20, 2025" # Current date

import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, scrolledtext
import os
import subprocess
from pathlib import Path
import shutil
import threading
from mutagen import File
import logging
from logging.handlers import RotatingFileHandler

class AudioConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Audio Converter")
        self.root.geometry("650x650") 

        # Default directory to user's Music/Downloads or just home if those don't exist
        default_dir = Path.home() / "Music"
        if not default_dir.exists():
            default_dir = Path.home() / "Downloads"
            if not default_dir.exists():
                default_dir = Path.home()
        self.directory = tk.StringVar(value=str(default_dir))
        
        self.format = tk.StringVar(value="flac")
        self.recursive = tk.BooleanVar(value=False)
        self.delete_source = tk.BooleanVar(value=False)
        self.delete_cue = tk.BooleanVar(value=False)
        self.bitrate = tk.IntVar(value=320)
        self.output_subdir = tk.StringVar(value="")

        self.running = False
        self.conversion_thread = None
        self.process = None

        # --- MODIFICATION HERE: Set log file to a user-writable path ---
        # Create a hidden directory for logs within the user's home directory
        self.log_dir = Path.home() / ".audio_converter_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True) # Ensure the directory exists
        self.log_filename = self.log_dir / "audio_converter.log"
        # --- END MODIFICATION ---

        self.setup_logging()

        self.create_widgets()
        self.root.grid_rowconfigure(6, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

    def setup_logging(self):
        log_handler = RotatingFileHandler(
            str(self.log_filename), # Use str() as RotatingFileHandler might not accept Path objects
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        log_handler.setFormatter(log_format)

        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        logging.basicConfig(level=logging.DEBUG, handlers=[log_handler])

    def create_widgets(self):
        ttk.Label(self.root, text="Source Directory:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(self.root, textvariable=self.directory, width=60).grid(row=0, column=1, padx=5, pady=5, columnspan=3, sticky="ew")
        ttk.Button(self.root, text="Browse", command=self.browse_directory).grid(row=0, column=4, padx=5, pady=5)

        ttk.Label(self.root, text="Output Subdir:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.output_subdir_entry = ttk.Entry(self.root, textvariable=self.output_subdir, width=60)
        self.output_subdir_entry.grid(row=1, column=1, padx=5, pady=5, columnspan=3, sticky="ew")
        self.output_subdir_browse_button = ttk.Button(self.root, text="Browse", command=self.browse_output_subdir)
        self.output_subdir_browse_button.grid(row=1, column=4, padx=5, pady=5)

        ttk.Label(self.root, text="Output Format:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        ttk.Radiobutton(self.root, text="FLAC (16-bit)", variable=self.format, value="flac").grid(row=2, column=1, sticky="w")
        ttk.Radiobutton(self.root, text="MP3", variable=self.format, value="mp3").grid(row=2, column=2, sticky="w")

        ttk.Label(self.root, text="MP3 Bitrate (kbps):").grid(row=2, column=3, padx=5, pady=5, sticky="w")
        self.bitrate_spinbox = ttk.Spinbox(self.root, from_=128, to_=320, increment=16, textvariable=self.bitrate, width=5)
        self.bitrate_spinbox.grid(row=2, column=4, padx=5, pady=5, sticky="w")
        self.format.trace("w", self.update_bitrate_state)
        self.update_bitrate_state()

        ttk.Checkbutton(self.root, text="Recursive", variable=self.recursive).grid(row=3, column=1, pady=5, sticky="w")
        self.delete_source_checkbox = ttk.Checkbutton(self.root, text="Delete Source Files", variable=self.delete_source)
        self.delete_source_checkbox.grid(row=3, column=2, pady=5, sticky="w")
        self.delete_source.trace("w", self.update_output_subdir_state)

        ttk.Checkbutton(self.root, text="Delete .cue Files", variable=self.delete_cue).grid(row=3, column=3, pady=5, sticky="w")
        self.update_output_subdir_state()

        self.start_button = ttk.Button(self.root, text="Start Conversion", command=self.start_conversion)
        self.start_button.grid(row=4, column=1, pady=10)

        self.stop_button = ttk.Button(self.root, text="Stop", command=self.stop_conversion, state="disabled")
        self.stop_button.grid(row=4, column=2, pady=10)

        self.progress = ttk.Progressbar(self.root, length=500, mode="determinate")
        self.progress.grid(row=5, column=0, columnspan=5, padx=5, pady=5, sticky="ew")

        self.status_text = scrolledtext.ScrolledText(self.root, width=70, height=15)
        self.status_text.grid(row=6, column=0, columnspan=5, padx=5, pady=5, sticky="nsew")

        self.close_button = ttk.Button(self.root, text="Close", command=self.close_app)
        self.close_button.grid(row=7, column=1, pady=10)

        self.clear_log_button = ttk.Button(self.root, text="Clear Log", command=self.clear_log)
        self.clear_log_button.grid(row=7, column=2, pady=10)

        # Log file path label now points to the user's home directory log file
        self.log_path_label = ttk.Label(self.root, text=f"Log File: {self.log_filename.resolve()}")
        self.log_path_label.grid(row=8, column=0, columnspan=5, pady=5, sticky="w")

        version_info = f"Version: {VERSION} ({DATE})"
        ttk.Label(self.root, text=version_info).grid(row=9, column=0, columnspan=5, pady=5, sticky="ew")

    def browse_directory(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.directory.set(folder_selected)

    def browse_output_subdir(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.output_subdir.set(folder_selected)

    def update_output_subdir_state(self, *args):
        if self.delete_source.get():
            self.output_subdir_entry["state"] = "disabled"
            self.output_subdir_browse_button["state"] = "disabled"
        else:
            self.output_subdir_entry["state"] = "normal"
            self.output_subdir_browse_button["state"] = "normal"

    def start_conversion(self):
        if self.running:
            self.log("Conversion already in progress.")
            return
        self.running = True
        self.start_button["state"] = "disabled"
        self.stop_button["state"] = "normal"
        self.conversion_thread = threading.Thread(target=self.run_conversion, daemon=True)
        self.conversion_thread.start()

    def run_conversion(self):
        self.log("Starting conversion...")
        directory = Path(self.directory.get())
        output_format = self.format.get()
        delete_source = self.delete_source.get()
        delete_cue = self.delete_cue.get()
        recursive = self.recursive.get()

        if not directory.exists():
            self.log("Invalid directory.")
            self.cleanup()
            return

        files_to_convert = []
        if recursive:
            for root, _, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith((".flac", ".mp3")):
                        files_to_convert.append(Path(root) / file)
        else:
            for file in directory.iterdir():
                if file.suffix.lower() in [".flac", ".mp3"]:
                    files_to_convert.append(file)

        if not files_to_convert:
            self.log("No audio files found.")
            self.cleanup()
            return

        total_files = len(files_to_convert)
        logging.debug(f"Total files to convert: {total_files}")
        for i, file_path in enumerate(files_to_convert):
            logging.debug(f"Processing file {i + 1} of {total_files}: {file_path}")
            if not self.running:
                self.log("Conversion stopped by user.")
                break
            self.progress['value'] = (i + 1) / total_files * 100
            self.root.update_idletasks()
            
            self.convert_audio(file_path, output_format, delete_source, directory)

            if delete_cue:
                cue_file_path = file_path.with_suffix('.cue')
                if cue_file_path.exists():
                    try:
                        os.remove(cue_file_path)
                        self.log(f"Deleted CUE file: {cue_file_path.name}")
                        logging.info(f"Deleted CUE file: {cue_file_path}")
                    except OSError as e:
                        self.log(f"Error deleting CUE file {cue_file_path.name}: {e}")
                        logging.error(f"Error deleting CUE file {cue_file_path}: {e}")
                else:
                    logging.debug(f"No .cue file found for {file_path.name} in the same directory.")

        if self.running:
            self.log("Conversion completed.")
        self.cleanup()

    def convert_audio(self, file_path, output_format, delete_source, target_dir):
        if not self.running:
            return

        if output_format == "flac":
            source_bit_depth = self.get_bit_depth(file_path)
            if source_bit_depth == 16:
                self.log(f"Skipping {file_path.name} (already 16-bit FLAC)")
                return

        artist, album = self.get_metadata(file_path)
        if delete_source:
            output_dir = file_path.parent
        else:
            base_output_path = Path(self.output_subdir.get()) if self.output_subdir.get() else target_dir
            sanitized_artist = "".join(c for c in artist if c.isalnum() or c in (' ', '.', '_', '-')).strip()
            sanitized_album = "".join(c for c in album if c.isalnum() or c in (' ', '.', '_', '-')).strip()
            
            suffix = "MP3" if output_format == "mp3" else "16bit"
            output_dir = base_output_path / f"{sanitized_artist} - {sanitized_album} {suffix}"
            output_dir.mkdir(parents=True, exist_ok=True)

        output_file_name = file_path.stem + f".{output_format}"
        output_file = output_dir / output_file_name

        try:
            if output_format == "flac":
                cmd = [
                    "ffmpeg", "-i", str(file_path),
                    "-map", "0:a",
                    "-map_metadata", "0",
                    "-c:a", "flac",
                    "-sample_fmt", "s16", "-ar", "44100",
                    str(output_file)
                ]
                self.log(f"Converting {file_path.name} to 16-bit FLAC...")
                logging.debug(f"FFmpeg command: {' '.join(cmd)}")
                self.process = subprocess.run(cmd, capture_output=True, text=True)
                logging.debug(f"FFmpeg return code: {self.process.returncode}")
                if self.process.returncode != 0:
                    logging.error(f"FFmpeg error: {self.process.stderr}")
                    self.log(f"Failed to convert {file_path.name}:")
                    self.log(self.process.stderr)
                    return

            elif output_format == "mp3":
                selected_bitrate = f"{self.bitrate.get()}k"
                artwork_filename = "cover.jpg"
                artwork = output_dir / artwork_filename
                has_artwork = False

                artwork_cmd = ["ffmpeg", "-i", str(file_path), "-an", "-vcodec", "mjpeg",
                                 "-vf", "format=yuv420p", "-f", "image2", str(artwork)]
                logging.debug(f"Artwork extraction command: {' '.join(artwork_cmd)}")
                artwork_result = subprocess.run(artwork_cmd, capture_output=True, text=True)
                logging.debug(f"Artwork extraction return code: {artwork_result.returncode}")
                logging.debug(f"Artwork extraction stderr: {artwork_result.stderr}")

                if artwork_result.returncode == 0 and artwork.exists() and artwork.stat().st_size > 0:
                    has_artwork = True
                    logging.debug(f"Artwork extracted successfully: {artwork}")
                else:
                    self.log(f"No artwork or failed to extract artwork for {file_path.name}. Output: {artwork_result.stderr.strip()}")
                    logging.warning(f"No artwork or failed to extract artwork for {file_path.name}. Output: {artwork_result.stderr.strip()}")

                cmd = ["ffmpeg", "-i", str(file_path)]
                if has_artwork:
                    cmd.extend(["-i", str(artwork)])
                cmd.extend(["-map", "0:a"])
                if has_artwork:
                    cmd.extend(["-map", "1:v"])
                cmd.extend([
                    "-b:a", selected_bitrate, "-ar", "44100", "-ac", "2",
                    "-map_metadata", "0", "-id3v2_version", "3", "-write_id3v1", "1",
                    str(output_file)
                ])

                self.log(f"Converting {file_path.name} to MP3 ({selected_bitrate})...")
                logging.debug(f"MP3 conversion command: {' '.join(cmd)}")
                self.process = subprocess.run(cmd, capture_output=True, text=True)
                logging.debug(f"MP3 conversion return code: {self.process.returncode}")
                logging.debug(f"MP3 conversion stderr: {self.process.stderr}")

                if self.process.returncode != 0:
                    logging.error(f"FFmpeg error: {self.process.stderr}")
                    self.log(f"Failed to convert {file_path.name} to MP3:")
                    self.log(self.process.stderr)
                    return
                if has_artwork and artwork.exists():
                    try:
                        os.remove(artwork)
                        logging.debug(f"Deleted temporary artwork file: {artwork}")
                    except OSError as e:
                        logging.error(f"Error deleting temporary artwork file {artwork}: {e}")

            if delete_source:
                try:
                    os.remove(file_path)
                    self.log(f"Deleted source file: {file_path.name}")
                    logging.info(f"Deleted source file: {file_path}")
                except OSError as e:
                    self.log(f"Error deleting source file {file_path.name}: {e}")
                    logging.error(f"Error deleting source file {file_path}: {e}")

        except Exception as e:
            self.log(f"Unexpected error converting {file_path.name}: {e}")
            logging.error(f"Unexpected error converting {file_path.name}: {e}", exc_info=True)

    def stop_conversion(self):
        if self.running:
            self.running = False
            self.log("Stopping conversion...")
            if self.process and self.process.poll() is None:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                    self.log("Terminated current process.")
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.log("Forced kill of process.")
            if self.conversion_thread and self.conversion_thread.is_alive():
                self.conversion_thread.join(timeout=5)
                if self.conversion_thread.is_alive():
                    self.log("Warning: Conversion thread did not terminate cleanly.")
            self.cleanup()

    def cleanup(self):
        self.progress['value'] = 0
        self.start_button["state"] = "normal"
        self.stop_button["state"] = "disabled"
        self.running = False
        self.process = None
        self.root.update()

    def log(self, message):
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.yview(tk.END)
        logging.info(message)

    def get_metadata(self, file_path):
        try:
            audio = File(file_path)
            if audio is None:
                return "Unknown Artist", "Unknown Album"

            artist = audio.get("TPE1") or audio.get("artist")
            artist = str(artist[0]) if artist and artist[0] else "Unknown Artist"

            album = audio.get("TALB") or audio.get("album")
            album = str(album[0]) if album and album[0] else "Unknown Album"

            invalid_chars = '<>:"/\\|?*'
            for char in invalid_chars:
                artist = artist.replace(char, "")
                album = album.replace(char, "")

            return artist.strip(), album.strip()
        except Exception as e:
            self.log(f"Error reading metadata for {file_path.name}: {e}")
            logging.error(f"Error reading metadata for {file_path.name}: {e}", exc_info=True)
            return "Unknown Artist", "Unknown Album"

    def get_bit_depth(self, file_path):
        try:
            try:
                subprocess.run(["ffprobe", "-version"], check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                self.log("Error: 'ffprobe' command not found. Please ensure FFmpeg (which includes ffprobe) is installed and in your system's PATH.")
                logging.error("Error: 'ffprobe' command not found. FFmpeg might not be installed or in PATH.", exc_info=True)
                return 16

            cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=bits_per_raw_sample",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path)
            ]
            
            logging.debug(f"FFprobe command for bit depth: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            bit_depth_str = result.stdout.strip()
            logging.debug(f"FFprobe raw output for bit depth: '{bit_depth_str}'")

            if bit_depth_str.isdigit():
                bit_depth = int(bit_depth_str)
                self.log(f"Debug: {file_path.name} - Detected bit depth: {bit_depth}-bit")
                if bit_depth > 16:
                    return 24
                else:
                    return 16
            else:
                self.log(f"Could not parse numeric bit depth from FFprobe output for {file_path.name}: '{bit_depth_str}'. Assuming 16-bit.")
                logging.warning(f"Could not parse numeric bit depth from FFprobe output for {file_path.name}: '{bit_depth_str}'. Assuming 16-bit.")
                return 16

        except subprocess.CalledProcessError as e:
            self.log(f"FFprobe failed for {file_path.name}. Stderr: {e.stderr.strip()}")
            logging.error(f"FFprobe failed for {file_path.name}. Stderr: {e.stderr.strip()}", exc_info=True)
            return 16
        except Exception as e:
            self.log(f"Unexpected error checking bit depth with FFprobe for {file_path.name}: {e}")
            logging.error(f"Unexpected error checking bit depth with FFprobe for {file_path.name}: {e}", exc_info=True)
            return 16

    def update_bitrate_state(self, *args):
        if self.format.get() == "flac":
            self.bitrate_spinbox["state"] = "disabled"
        else:
            self.bitrate_spinbox["state"] = "normal"

    def clear_log(self):
        try:
            self.status_text.delete(1.0, tk.END)
            logging.info("GUI log cleared by user.") 

            with open(self.log_filename, 'w'):
                pass
            logging.info("Log file truncated by user.")
        except Exception as e:
            self.log(f"Error clearing log: {e}")
            logging.error(f"Error clearing log: {e}", exc_info=True)

    def close_app(self):
        self.stop_conversion()
        self.root.quit()

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioConverterApp(root)
    root.mainloop()

# AutoSub: Local AI Subtitle Generator

AutoSub is a local, fault-tolerant automation pipeline that generates translated `.srt` subtitles and preserves original `.orig.srt` raw subtitles for video files. It leverages `mpv` and `ffmpeg` for robust audio extraction and chunking, and interfaces with a local instance of **ComfyUI** to perform heavy ASR (Qwen3) and Translation (Google Translate) tasks.

This toolset is designed for long-form content, utilizing a 10-minute sliding window with a 10-second overlap to prevent word truncation across audio chunks.

## Architecture

- **`autosub_single`**: The core processor. It handles audio chunking, calculates timestamp offsets, and intelligently routes tasks. It outputs two files: `<video>.srt` (Translated) and `<video>.orig.srt` (Raw ASR).
- **`autosub`**: The batch wrapper. It scans a directory, skips videos that already have a `.srt` file, queues the rest through `autosub_single`, and provides a final error summary.
- **`autosub_workflow.json`**: The **"Happy Path"** workflow. It routes audio through the Qwen3-ASR node, saves the raw text, pushes it through a Translate node, and saves the translated text.
- **`autosub_workflow_translate.json`**: The **"Rescue"** workflow. If the network drops during translation but the heavy GPU ASR is already done, the script uses this lightweight workflow to resume from the cached raw text and re-attempt the translation.

---

## 🛠 Prerequisites & Dependencies

Before deploying the scripts, ensure your Ubuntu system has the required dependencies installed.

### 1. System Packages

The scripts rely on `mpv` for robust audio extraction (bypassing corrupted headers) and `ffmpeg`/`ffprobe` for precise compression and chunking.

```bash
sudo apt update
sudo apt install mpv ffmpeg
```

### 2. ComfyUI & Custom Nodes

You must have a working installation of ComfyUI.

- **AILab Qwen3 ASR Node**: Ensure you have the `AILab_Qwen3ASRSubtitle` custom node installed and working in your ComfyUI environment.
- **Model Weights**: Ensure the Qwen3-ASR models (`Qwen/Qwen3-ASR-0.6B` and the forced aligner) are downloaded and accessible to your ComfyUI instance.
- **Translation Node**: Ensure you have the translation node (e.g., GoogleTranslateTextNode) used in your workflows installed.

---

## 🚀 Installation & Deployment

Follow these steps to make the commands globally accessible from anywhere in your terminal.

### Step 1: Configure the Workflows

The scripts expect both ComfyUI workflow JSONs to be located in your `~/.config` directory.

```bash
mkdir -p ~/.config
cp path/to/your/autosub_workflow.json ~/.config/
cp path/to/your/autosub_workflow_translate.json ~/.config/
```

### Step 2: Update Script Configurations

Open `autosub_single` and ensure your paths and **Node IDs** match your specific ComfyUI setup.

1. **Directories**: Set `COMFY_INPUT_DIR` to your actual ComfyUI input folder (e.g., `/home/username/dev/ComfyUI/input`).
2. **Node Mapping**: Look at the `NODE CONFIGURATION` block in the Python script. You must open your two `.json` workflow files in a text editor and update the Python variables to match the exact ID numbers of your Load Audio, Save Text, and String Input nodes.

### Step 3: Make Scripts Executable

Navigate to the directory where you saved the Python scripts and make them executable.

```bash
chmod +x autosub_single autosub
```

### Step 4: Move to Local Bin

Move the scripts to your local binaries folder so they are included in your system's PATH.

```bash
mkdir -p ~/.local/bin
mv autosub_single ~/.local/bin/
mv autosub ~/.local/bin/
```

_(Note: If you get a "command not found" error later, run `source ~/.bashrc` or restart your terminal)._

---

## 💻 Usage

**CRITICAL:** ComfyUI **must** be running in the background (accessible at `http://127.0.0.1:8188`) before initiating these scripts.

### Processing a Single Video

To generate subtitles for a single video, use `autosub_single`:

```bash
autosub_single /path/to/your/video.mp4
```

### Batch Processing a Directory

To scan an entire folder and process all missing subtitles automatically, use `autosub`:

```bash
# Process the current directory
autosub .

# Process a specific directory
autosub /path/to/your/videos/
```

**Supported File Types:** `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`

---

## 🛑 The Caching & Failsafe System

This pipeline is designed to survive crashes, network timeouts, and system reboots.

**1. Persistent Caching (`~/.cache/autosub/`)**
Unlike previous versions that used volatile `/tmp` directories, this system writes all intermediate files (`_raw.txt` and `_trans.txt`) to a persistent hidden folder. If your computer shuts down halfway through a 3-hour video, your progress is saved.

**2. The "Smart Resume" Feature**
If a network timeout causes the Translation node to fail, the script will crash safely. When you rerun the command, `autosub_single` will see that the `_raw.txt` for that chunk already exists. Instead of re-running the expensive GPU transcription, it will instantly switch to the `autosub_workflow_translate.json` rescue workflow, skipping straight to translation.

**3. Atomic Commits**
The final `.srt` and `.orig.srt` files are only moved to your video's directory upon **100% successful completion** of all chunks. If you cancel the script mid-way (`Ctrl+C`), no broken `.srt` files will be left behind next to your video, ensuring batch operations won't accidentally skip incomplete files on the next run.

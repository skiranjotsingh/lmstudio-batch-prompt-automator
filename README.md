# LM Studio Batch Prompt Automator

A lightweight, memory-safe GUI tool to automate prompt testing across multiple local LLMs sequentially. Designed for developers and local AI enthusiasts running constrained hardware.

## Why this exists
Loading multiple billion-parameter models simultaneously is impossible on standard consumer hardware. This tool allows you to queue a single prompt against multiple models in LM Studio. It strictly polls the API to ensure one model is fully loaded, tested, and aggressively unloaded from RAM/VRAM before initiating the next model in the queue.

## Features
* **Reasoning Model Support:** Built-in regex filter to automatically strip `<think>` tags and inner monologues from output logs (ideal for DeepSeek-R1).
* **System Prompts & Formatting:** Define custom system instructions and export directly to `.md` or `.txt`.
* **Memory Safe:** Instantly unloads models from system memory after generation or via an asynchronous "Stop" button override.
* **Multimodal Ready:** Dynamically formats API payloads (`max_tokens: -1`, rich-media text arrays) to ensure vision-language models do not reject standard prompts.
* **Advanced API Handling:** Cross-references LM Studio's v0 and v1 endpoints to accurately report active RAM states and model weights.
* **CustomTkinter GUI:** Modern interface with dynamic Dark/Light mode toggling and collapsible advanced hardware settings.

## LM Studio Setup (Required)
Before running this tool, you must configure LM Studio to accept external API requests:
1. Open LM Studio and navigate to the **Developer** tab (the `< >` icon on the left sidebar).
2. Look at the right-side configuration panel. 
3. Ensure the **Server Port** is set to `1234`.
4. **Important:** Ensure **CORS** (Cross-Origin Resource Sharing) is enabled if you are running the app from a different network interface.
5. Click the green **Start Server** button at the top. 

## Installation & Usage

### Option 1: The Executable (Windows & Linux)
1. Go to the [Releases](https://github.com/skiranjotsingh/lmstudio-batch-prompt-automator/releases) tab.
2. Download `lm_batch_runner.exe` (Windows) or the Linux binary.
3. Run the executable. No installation required.

> **Note on Windows SmartScreen:** > Because this is an independently compiled open-source tool, Windows Defender SmartScreen will flag it as an "Unknown Publisher". To run the executable, click **More info** -> **Run anyway**. If you have security concerns, you are highly encouraged to review the open-source Python code in this repository and run it via Option 2.

### Option 2: Run from Source
1. Clone the repository: `git clone https://github.com/skiranjotsingh/lmstudio-batch-prompt-automator.git`
2. Install dependencies: `pip install -r requirements.txt`
3. Run the script: `python lm_batch_runner.py`

---
### About the Developer
Developed and maintained by [Kiranjot Singh](https://github.com/skiranjotsingh).

![ASMARA](https://github.com/A-c0rN/ASMARA/blob/main/assets/asmara-white-text.png)

### Automated System for Monitoring And Relaying Alerts
The comprehensive software EAS solution.

![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/A-c0rN/ASMARA/main_runner.yml?style=flat-square) ![GitHub language count](https://img.shields.io/github/languages/count/A-c0rN/ASMARA?style=flat-square) ![GitHub](https://img.shields.io/github/license/A-c0rN/ASMARA?style=flat-square)

## Features
> - [x] EAS Generation and Translation using stable and tested systems
> - [x] Live and buffered audio flow systems
> - [x] Audio file and log generation systems
> - [x] Easy to use
> - [x] Built-In Discord and Email logging
> - [x] Comprehensive audio quality
> - [x] AutoDJ for Playout, with a Tone Only mode.
> - [x] InfiniteMonitor System for unlimited monitoring
> - [x] Back-to-back Alert Detection on all monitors
> - [x] MultiATTN Attention Detection on all Monitors
> - [x] ENDEC Header Style Emulation
> - [x] The Fastest and most reliable system on the market for over 6 monitors
> - [x] Built-in Icecast Playout with Metadata
> - [x] Direct stream monitoring
> - [x] SDR monitoring


## Installation
This system currently only runs on MacOS and Linux.

If you are running the Compiled ASMARA Binary, skip to step 2.

### Step 1
Install Python dependencies
```
sudo apt update
sudo apt install python3 python3-pip python3-pyaudio
pip3 install -r requirements.txt
```

### Step 2
Install other dependencies.
#### FFmpeg:
```
sudo apt update
sudo apt install ffmpeg
```
#### Samedec:
```
sudo apt update
sudo apt install curl git
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
git clone https://github.com/cbs228/sameold.git
cd sameold
cargo install --path crates/samedec
```
> NOTE: Add RUST to path with `source $HOME/.cargo/env` after CURL, otherwise restart your terminal or log out/in before installing sameold, otherwise cargo will not work.

### Step 3
Test ASMARA's config generation by running
`python3 asmara.py -d` if using Python, or
`./asmara -d` if using compiled binaries.
> Configs will by default be stored in `.config` if not specified.
> To specify a config, add it after the ASMARA executable, and all flags.
> E.G. `./asmara -d CONFIGFILE.CFG` for a file named `CONFIGFILE.CFG`

## Configuration
DO LATER

## Usage
To run ASMARA, use the executable or the raw Python script.

For the Python executable:
```
python3 asmara.py
```
For the Compiled Binary:
```
./asmara
```

### Verbosity

If you would like more info in the terminal, you can increase the `verbosity` flag.
For a higher verbosity, run `-v`. The more `v`s you add increase the verbosity. (E.G. `-vvvv` is higher than `-vv`)

For debug info, run `-d` for debug.

For the lowest verbosity, run `-q` for quiet mode.

### Extra Flags:
`-A` gives data about ASMARA.

`-V` gives the current version of ASMARA.

`-u` updates the current version of ASMARA if there is a newer version available in the internal updater system. use `-n` to disable the internal updater for this session. (NOT IMPLEMENTED YET.)

`-U` sets your config file to always update if available. `-N` disables this feature, and update notifications. (NOT IMPLEMENTED YET.)

### Config Files:
Adding a file on to the end of the executable after all flags will set that file as a config file.
> Note: Must be a valid ASMARA config file for that version. Using an incompatible file may cause problems, and-or corruption of the said file.

Example:
```
python3 asmara.py -vvvv .config2
```
to use `.config2` as the selected config file. If the file does not exist, it will be created.
> Note: The config file *must* always come after the flags. Adding a flag after the config file may result in unexpected behavior.

## Changelog
DO LATER

###### Copyright © 2024 MissingTextures Software

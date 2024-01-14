# WACN TECH - ASMARA
### Automated System for Monitoring And Relaying Alerts

<IMG HERE WHEN AVAILABLE>

<STATS HERE WHEN AVAILABLE>

The comprehensive software EAS solution.

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

## License
This software is licensed under `GWES-ERN LIDS` for ERN Network Development Partners (`ERN-ND`). This license applies to any and all user(s) of this software.

Please read the license carefully.

```
Global Weather and EAS Society EAS Relay Network License for Internally Developed Software

Internally developed software developed by the Network Development team ("ERN-ND") is granted to those who have access as a privilege, not a right.

As such, ERN-ND can take away access to said software under this license agreement. Usage of the software means that you, the end user, agree to all provisions within this agreement.

Alright, now that the legal stuff is out of the way, here is what you can do under this license agreement:

- Use the software
- Make changes to the configuration of the software
- If access was granted by ERN-ND, modifications to the source code are allowed, however the changes are limited to:
        - Quality of Life
        - Extended functionality in specific applications
        - Aesthetic modifications
        - Porting to unsupported platforms
  These changes are allowed under the condition that:
        - Source code modifications are made available to ERN-ND
        - They are not designed to bypass security regarding Software Licensing or gaining access to IPAWS.
        - You declare to ERN-ND that by modifying the software, you are relinquishing any further support for software issues regarding the modifications unless the modifications make it into the main source tree using a pull request that is approved.
        - This license is retained within the software in a unmodified state.

Here is what you can't do:

        - Make unauthorized changes to the software
        - Reverse engineer the software
        - Bypass the activation of the software
        - Redistribute the software
        - Run the software on any electronic device that is owned (or hosted) by an individual not bound under this license agreement
        - Attempt to retrieve the GWES-ERN IPAWS Access Key without express authorization by the Network Operations team.


Violations of this agreement will result in removal of access to any software that is developed under this agreement and may prevent you from being eligible for further software access indefinitely.

TL;DR- You can use the software, change the software config, and make modifications as long as they are not extensive and code is made available to network devs. Just know we won't help you if you break it.
Any violations will make you look like a jackass and access will be revoked as needed. You wouldn't download a car so why steal shit you don't own.
```

###### Copyright © 2023 WACN Technologes and GWES ERN

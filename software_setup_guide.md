# Raspberry Pi Setup Guide: Coherence Emulator (TFT Edition)

This guide covers setting up a Raspberry Pi 3 B+ (or Zero 2 W) from scratch to run the Partial Coherence Emulator on a **2.8" SPI TFT Display** (ILI9341 or ST7789).

## Phase 1: Flashing the OS

**Goal:** Install the operating system and configure Wi-Fi/SSH.

1.  **Download Raspberry Pi Imager**: [Download here](https://www.raspberrypi.com/software/)
2.  **Insert MicroSD Card**.
3.  **Open Raspberry Pi Imager**:
    *   **Device**: Select "Raspberry Pi 3".
    *   **OS**: Select "Raspberry Pi OS (other)" -> **"Raspberry Pi OS Lite (64-bit)"**.
    *   **Storage**: Select your SD card.
4.  **OS Customisation (Required)**:
    *   Click **Next**. Select **EDIT SETTINGS**.
    *   **General Tab**:
        *   Hostname: `coherence-pi`
        *   Username: `coherence-pi`
        *   Password: Set a strong password.
        *   **Wireless LAN**: Enter your Wi-Fi SSID and Password.
    *   **Services Tab**:
        *   **Enable SSH**: Select "Use password authentication".
    *   **Save** and click **YES** to write.

## Phase 2: Connecting & Updating

1.  **Connect via SSH**:
    ```bash
    ssh coherence-pi@coherence-pi.local
    ```
2.  **Update System**:
    ```bash
    sudo apt-get update
    sudo apt-get upgrade -y
    ```

## Phase 3: Dependencies

Install Python libraries for math, GPIO, and the SPI display:

```bash
sudo apt-get install -y python3-pip python3-numpy python3-scipy python3-gpiozero python3-pil python3-dev git
sudo pip3 install adafruit-circuitpython-rgb-display adafruit-circuitpython-mcp3xxx --break-system-packages
```

## Phase 4: Hardware Config (Enable SPI)

1.  **Enable SPI Interface**:
    ```bash
    sudo raspi-config nonint do_spi 0
    ```
    *(Or add `dtparam=spi=on` to `/boot/firmware/config.txt`)*

2.  **Disable Audio** (Recommended to free up timers/pins):
    ```bash
    sudo nano /boot/firmware/config.txt
    ```
    Change `dtparam=audio=on` to `dtparam=audio=off`.

3.  **Reboot**:
    ```bash
    sudo reboot
    ```

## Phase 5: Deploying Code

From your computer (project folder):

```bash
# 1. Sync code to Pi
scp -r . coherence-pi@coherence-pi.local:rpi_photonics_sim/

# 2. SSH in
ssh coherence-pi@coherence-pi.local
```

On the Pi:

```bash
# Move to /opt
sudo rm -rf /opt/rpi_photonics_sim
sudo mv /home/coherence-pi/rpi_photonics_sim /opt/rpi_photonics_sim
sudo chown -R root:root /opt/rpi_photonics_sim
```

## Phase 6: Running

### A. Hardware Test
Run this to verify your wiring (screen colors + knob values):
```bash
sudo python3 /opt/rpi_photonics_sim/hardware_test.py
```

### B. Run Emulator
```bash
sudo python3 /opt/rpi_photonics_sim/tft_emulator.py --driver ili9341
```
*(Use `--driver st7789` if using that chipset)*

### C. Enable Autostart
```bash
sudo cp /opt/rpi_photonics_sim/coherence-tft.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now coherence-tft.service
```

### D. Web Mockup Mode (No hardware)
If waiting for parts, run the web server:
```bash
sudo cp /opt/rpi_photonics_sim/coherence-web.service /etc/systemd/system/
sudo systemctl enable --now coherence-web.service
```
Visit `http://coherence-pi.local:8000`

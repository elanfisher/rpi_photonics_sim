# Build Guide: Coherence Emulator (Web Controller Edition)

## Bill of Materials (BOM)

| Item | Description | Notes |
| :--- | :--- | :--- |
| **Brain** | Raspberry Pi 3 B+ (or Zero 2 W) | Headers required |
| **Display** | 2.8" SPI TFT (240x320) | ILI9341 or ST7789 driver |
| **Power** | 5V 2.5A+ MicroUSB | Good quality supply |
| **Controller** | None (Web Interface) | Controlled via Phone/Laptop |

## Wiring Diagram (Golden Pinout)

This is the standard configuration using **CE0** and **5V Power**.

### 1. Visual Wiring Diagram
*(Open `wiring_diagram.svg` in a browser for a color visual)*

```
       Raspberry Pi GPIO Header (Top View)
       -----------------------------------
       3.3V  [01] [02]  5V (LED)
   SDA (I2C) [03] [04]  5V (VCC)
   SCL (I2C) [05] [06]  GND  <-- Common Ground
       GPIO4 [07] [08]  TXD
         GND [09] [10]  RXD
      GPIO17 [11] [12]  GPIO18
      GPIO27 [13] [14]  GND
      GPIO22 [15] [16]  GPIO23
      3.3V   [17] [18]  GPIO24 -> TFT D/C
TFT MOSI <-- [19] [20]  GND
      MISO   [21] [22]  GPIO25 -> TFT RST
TFT SCLK <-- [23] [24]  CE0    -> TFT CS
         GND [25] [26]  CE1
```

### 2. Wiring Table

| Signal | Pi Pin | Pi GPIO | Target Device | Target Pin |
| :--- | :--- | :--- | :--- | :--- |
| **VCC** | 4 | - | **TFT Display** | VCC (5V) |
| **GND** | 6 | - | **TFT Display** | GND |
| **CS** | 24 | GPIO 8 | **TFT Display** | CS |
| **RESET** | 22 | GPIO 25 | **TFT Display** | RESET |
| **D/C** | 18 | GPIO 24 | **TFT Display** | DC / A0 |
| **MOSI** | 19 | GPIO 10 | **TFT Display** | SDA / MOSI |
| **SCLK** | 23 | GPIO 11 | **TFT Display** | SCK / CLK |
| **LED** | 2 | - | **TFT Display** | LED / Backlight (5V) |

### 3. Usage

1.  **Power on the Pi**.
2.  **Open Browser**: Go to `http://coherence-pi.local:8000`.
3.  **Control**: Use the web knobs to control the simulation on the Pi screen.

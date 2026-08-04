# Breadboard Wiring Guide for Coherence Simulation

This guide details how to wire your Raspberry Pi 3B+ to the TFT Display, MCP3008 ADC, Buttons, LEDs, and Piezo buzzer to interact with the simulation.

## ⚠️ Important Safety Notes
- **Power Off** your Raspberry Pi before wiring components.
- **Double Check** all connections, especially Power (3.3V/5V) and Ground (GND).
- The Raspberry Pi GPIO pins use **3.3V logic**. Do not connect 5V directly to GPIO pins (except 5V power pins).

---

## ⚠️ Important Note: Missing MCP3008?
If you do not have the **MCP3008** chip (common in some starter kits), you **cannot** connect the analog Joystick or Potentiometer directly to the Raspberry Pi. The Pi does not have built-in analog inputs.

**If you don't have an MCP3008 (Digital-Only Mode):**
1.  **Skip Section 4 and 5** (ADC and Sensors).
2.  Wire up the **TFT Display** (Section 3).
3.  Wire up the **5 Buttons** (Section 6).
4.  Wire up the **LEDs and Piezo** (Section 7).

---

## 1. Component Overview
- **TFT Display**: 2.8" SPI Display (ILI9341 Driver)
- **Inputs**: 5x Push Buttons (Mode, Source, View, Speed, Size).
- **Outputs**: 2x LEDs, 1x Piezo Buzzer.

---

## 2. Shared SPI Bus
(Only for TFT if no MCP3008 is used)

| Signal | Pi Pin (Physical) | Pi GPIO | Connects To |
| :--- | :---: | :---: | :--- |
| **SCLK** | 23 | GPIO 11 | TFT `SCK` |
| **MOSI** | 19 | GPIO 10 | TFT `MOSI` |
| **MISO** | 21 | GPIO 9 | TFT `MISO` |

---

## 3. TFT Display Wiring
(Same as before)
| TFT Pin | Pi Pin | Description |
| :--- | :---: | :--- |
| **CS** | **26** | **GPIO 7 (CE1)** |
| **RESET** | 22 | GPIO 25 |
| **DC** | 18 | GPIO 24 |
| **VCC/LED**| 2/4 | 5V |
| **GND** | 6 | GND |

---

## 4 & 5. Analog Inputs (SKIPPED if no MCP3008)
*Ignore if you are using the 5-button setup.*

---

## 6. Digital Buttons (Active Low)
Wire one side of each button to the GPIO pin, and the other side to **GND**.

| Function | Pi Pin | Pi GPIO | Description |
| :--- | :---: | :---: | :--- |
| **Mode Toggle** | 29 | GPIO 5 | Toggles Gaussian / Rational |
| **Source Toggle** | 31 | GPIO 6 | Toggles Auto / EMF |
| **View Toggle** | 33 | GPIO 13 | Cycles Phase / Kernel / Beam Monitor |
| **Speed Cycle** | 11 | GPIO 17 | Cycles Speed (Slow -> Fast) |
| **Size Cycle** | 13 | GPIO 27 | Cycles Size/Rho (Small -> Large) |

---

## 7. Digital Outputs (LEDs & Piezo)

### LEDs
Long Leg (+) to GPIO, Short Leg (-) to GND via Resistor (220Ω).

| Function | Pi Pin | Pi GPIO |
| :--- | :---: | :---: |
| **LED Mode** (Rational) | 35 | GPIO 19 |
| **LED Source** (EMF) | 36 | GPIO 16 |

### Piezo Buzzer
(+) to GPIO, (-) to GND.

| Function | Pi Pin | Pi GPIO |
| :--- | :---: | :---: |
| **Piezo Beep** | 32 | GPIO 12 |

---

## Summary Pinout Table (Digital Setup)

| Left Side (Odd) | Function | | Right Side (Even) | Function |
| :--- | :--- | :---: | :--- | :--- |
| **1** 3.3V | | | **2** 5V | TFT Power |
| **3** GPIO 2 | | | **4** 5V | |
| **5** GPIO 3 | | | **6** GND | GND |
| **7** GPIO 4 | | | **8** GPIO 14 | |
| **9** GND | | | **10** GPIO 15 | |
| **11** GPIO 17 | **Btn Speed** | | **12** GPIO 18 | TFT DC |
| **13** GPIO 27 | **Btn Size** | | **14** GND | |
| **15** GPIO 22 | | | **16** GPIO 23 | |
| **17** 3.3V | | | **18** GPIO 24 | |
| **19** GPIO 10 | TFT MOSI | | **20** GND | |
| **21** GPIO 9 | TFT MISO | | **22** GPIO 25 | TFT RESET |
| **23** GPIO 11 | TFT SCLK | | **24** GPIO 8 | |
| **25** GND | | | **26** GPIO 7 | **TFT CS (CE1)** |
| **27** GPIO 0 | | | **28** GPIO 1 | |
| **29** GPIO 5 | **Btn Mode** | | **30** GND | |
| **31** GPIO 6 | **Btn Source** | | **32** GPIO 12 | **Piezo** |
| **33** GPIO 13 | **Btn View** | | **34** GND | |
| **35** GPIO 19 | **LED Mode** | | **36** GPIO 16 | **LED Source** |
| **37** GPIO 26 | | | **38** GPIO 20 | |
| **39** GND | | | **40** GPIO 21 | |


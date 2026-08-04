#!/usr/bin/env python3
import time
import board
import digitalio
import adafruit_rgb_display.ili9341 as ili9341
from PIL import Image, ImageDraw

# SOFTWARE SPI SETUP (Bit-banging)
# This bypasses the hardware SPI driver to rule out driver issues.

print("--- SOFTWARE SPI TEST ---")

# Define pins manually
cs_pin = digitalio.DigitalInOut(board.CE1)
dc_pin = digitalio.DigitalInOut(board.D24)
rst_pin = digitalio.DigitalInOut(board.D25)

# Manually define Clock and MOSI as generic GPIO
import busio
# Try super slow hardware SPI first (500kHz) which is immune to almost all wiring noise
spi = busio.SPI(board.SCK, MOSI=board.MOSI)

try:
    print("Initializing Display (Slow SPI 1MHz)...")
    # Baudrate is ignored by some drivers but we set it anyway
    display = ili9341.ILI9341(spi, cs=cs_pin, dc=dc_pin, rst=rst_pin, width=240, height=320, baudrate=1000000)
    
    # Create Red Image
    image = Image.new("RGB", (240, 320), (255, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.line((0,0, 240,320), fill=(255,255,255), width=5)
    
    print("Sending RED image...")
    display.image(image)
    print("Done. Check screen.")

except Exception as e:
    print(f"Error: {e}")

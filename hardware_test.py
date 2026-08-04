#!/usr/bin/env python3
"""
Hardware Test Script for Coherence Emulator
Verifies:
1. SPI Connection to TFT Display (Draws a test pattern)
"""

import time
import board
import busio
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789
import adafruit_rgb_display.ili9341 as ili9341

# --- CONFIG ---
# Try lowering this if you see glitching/artifacts
BAUDRATE = 1000000 

def test_display(spi):
    print(f"Testing Display (ILI9341)... Baud: {BAUDRATE}")
    
    # Pin Definitions for Display (CE1)
    cs = digitalio.DigitalInOut(board.CE1)
    dc = digitalio.DigitalInOut(board.D24)
    rst = digitalio.DigitalInOut(board.D25)

    display = ili9341.ILI9341(spi, cs=cs, dc=dc, rst=rst, baudrate=BAUDRATE,
                              width=240, height=320)

    # Draw Test Pattern
    image = Image.new("RGB", (display.width, display.height))
    draw = ImageDraw.Draw(image)

    # Red, Green, Blue Bars
    w = display.width
    h = display.height
    draw.rectangle((0, 0, w, h//3), fill=(255, 0, 0))
    draw.rectangle((0, h//3, w, 2*h//3), fill=(0, 255, 0))
    draw.rectangle((0, 2*h//3, w, h), fill=(0, 0, 255))
    
    # Text
    try:
        font = ImageFont.load_default()
    except:
        font = None
    
    draw.text((20, h//2 - 10), "DISPLAY OK", fill=(255, 255, 255), font=font)
    draw.text((20, h//2 + 10), "If this is stable,", fill=(255, 255, 255), font=font)
    draw.text((20, h//2 + 30), "Hardware is Good!", fill=(255, 255, 255), font=font)
    
    display.image(image)
    print("Display should show Red/Green/Blue bars.")
    time.sleep(3) # Give user time to see the bars
    
    # Flash loop to test update speed
    print("Flashing test (White/Black) for 5 seconds...")
    for _ in range(5):
        draw.rectangle((0, 0, w, h), fill=(255, 255, 255))
        display.image(image)
        time.sleep(0.5)
        draw.rectangle((0, 0, w, h), fill=(0, 0, 0))
        display.image(image)
        time.sleep(0.5)
        
    # Restore bars
    draw.rectangle((0, 0, w, h//3), fill=(255, 0, 0))
    draw.rectangle((0, h//3, w, 2*h//3), fill=(0, 255, 0))
    draw.rectangle((0, 2*h//3, w, h), fill=(0, 0, 255))
    display.image(image)

def main():
    print("Initializing SPI Bus (SCK=23, MOSI=19)...")
    spi = busio.SPI(board.SCK, MOSI=board.MOSI)
    
    try:
        test_display(spi)
    except Exception as e:
        print(f"Display Error: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTest stopped.")

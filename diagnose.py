#!/usr/bin/env python3
import time
import board
import busio
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789
import adafruit_rgb_display.ili9341 as ili9341

BAUDRATE = 8000000

def get_cs(pin_name):
    if pin_name == "CE0": return digitalio.DigitalInOut(board.CE0)
    if pin_name == "CE1": return digitalio.DigitalInOut(board.CE1)
    return None

def test_config(driver_name, cs_pin_name, spi):
    print(f"\n--- TESTING: {driver_name} on {cs_pin_name} ---")
    
    cs = get_cs(cs_pin_name)
    dc = digitalio.DigitalInOut(board.D24)
    rst = digitalio.DigitalInOut(board.D25)

    try:
        if driver_name == "ILI9341":
            display = ili9341.ILI9341(spi, cs=cs, dc=dc, rst=rst, baudrate=BAUDRATE, width=240, height=320)
        else:
            display = st7789.ST7789(spi, cs=cs, dc=dc, rst=rst, baudrate=BAUDRATE, width=240, height=320)
            
        image = Image.new("RGB", (240, 320), (0, 0, 255)) # Blue Background
        draw = ImageDraw.Draw(image)
        
        # Draw a huge X
        draw.line((0, 0, 240, 320), fill=(255, 255, 255), width=5)
        draw.line((0, 320, 240, 0), fill=(255, 255, 255), width=5)
        
        # Text
        try:
            draw.rectangle((10, 100, 230, 220), fill=(255, 255, 255))
        except:
            pass
            
        display.image(image)
        print(f"Sent image. Watch screen for 5 seconds...")
        time.sleep(5)
        
    except Exception as e:
        print(f"Failed: {e}")

def main():
    spi = busio.SPI(board.SCK, MOSI=board.MOSI)
    
    # 1. Standard ILI9341 on CE1 (My Wiring Guide)
    test_config("ILI9341", "CE1", spi)
    
    # 2. Common ILI9341 on CE0 (Alternate Wiring)
    test_config("ILI9341", "CE0", spi)
    
    # 3. ST7789 on CE1
    test_config("ST7789", "CE1", spi)
    
    # 4. ST7789 on CE0
    test_config("ST7789", "CE0", spi)

if __name__ == "__main__":
    main()

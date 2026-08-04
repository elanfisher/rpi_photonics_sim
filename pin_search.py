#!/usr/bin/env python3
import time
import board
import busio
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.ili9341 as ili9341

# Low speed for maximum compatibility during search
BAUDRATE = 1000000

def get_pin(pin_name):
    """Safe pin retrieval"""
    try:
        return getattr(board, pin_name)
    except AttributeError:
        return None

def test_config(config_id, cs_name, dc_name, rst_name, spi):
    print(f"\n[ID: {config_id}] Testing: CS={cs_name}, DC={dc_name}, RST={rst_name}")
    
    try:
        # Release pins if they were used
        # (This is tricky in CircuitPython, we just create new objects and hope for garbage collection 
        # or just rely on the try/except to catch busy pins if we didn't clean up perfectly, 
        # but re-instantiating usually works for these tests)
        
        cs_pin = digitalio.DigitalInOut(get_pin(cs_name))
        dc_pin = digitalio.DigitalInOut(get_pin(dc_name))
        rst_pin = digitalio.DigitalInOut(get_pin(rst_name))
        
        display = ili9341.ILI9341(spi, cs=cs_pin, dc=dc_pin, rst=rst_pin, baudrate=BAUDRATE, width=240, height=320)
        
        # Create a distinct color for this config
        # Cycle colors: Red, Green, Blue, Yellow, Magenta, Cyan
        colors = [(255,0,0), (0,255,0), (0,0,255), (255,255,0), (255,0,255), (0,255,255)]
        color = colors[config_id % len(colors)]
        
        image = Image.new("RGB", (240, 320), color)
        draw = ImageDraw.Draw(image)
        
        # Draw ID on screen
        draw.rectangle((20, 20, 220, 100), fill=(0,0,0))
        draw.line((0,0, 240,320), fill=(255,255,255), width=5)
        
        # Attempt to draw text, fallback to blocks if font fails
        try:
            # We don't load a fancy font, just default
            # Drawing a block pattern representing the ID number might be safer if fonts are tiny
            for i in range(config_id):
                x = 20 + (i * 30)
                draw.rectangle((x, 120, x+20, 140), fill=(255,255,255))
        except:
            pass
            
        display.image(image)
        print(f"   -> SENT IMAGE. CHECK SCREEN FOR CONFIG ID: {config_id}")
        print(f"   -> (Color: {color})")
        time.sleep(4)
        
    except Exception as e:
        print(f"   -> Failed: {e}")

def main():
    print("Initializing SPI...")
    spi = busio.SPI(board.SCK, MOSI=board.MOSI)
    
    # Define pin candidates
    # Common mistakes:
    # 1. Swapping CE0 (Pin 24) and CE1 (Pin 26)
    # 2. Swapping DC (Pin 18) and RST (Pin 22)
    # 3. Using Pin 22 (GPIO 25) vs Pin 18 (GPIO 24)
    
    configs = [
        # (CS, DC, RST)
        ("CE0", "D24", "D25"), # 1. Golden Standard (Pin 24, 18, 22)
        ("CE1", "D24", "D25"), # 2. Old Standard (Pin 26, 18, 22)
        ("CE0", "D25", "D24"), # 3. Golden SWAPPED DC/RST
        ("CE1", "D25", "D24"), # 4. Old SWAPPED DC/RST
        ("CE0", "D23", "D25"), # 5. Maybe DC is on Pin 16?
        ("CE0", "D25", "D23"), # 6. Maybe RST is on Pin 16?
    ]
    
    print(f"Starting search through {len(configs)} configurations...")
    print("Watch the screen. If you see a colored screen with a number/white blocks, note the ID.")
    
    for i, (cs, dc, rst) in enumerate(configs):
        test_config(i+1, cs, dc, rst, spi)

    print("\nSearch complete.")

if __name__ == "__main__":
    main()

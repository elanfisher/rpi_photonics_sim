#!/usr/bin/env python3
import time
import board
import busio
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789
import adafruit_rgb_display.ili9341 as ili9341

# Ultra conservative speed
BAUDRATE = 1000000 

def get_cs(pin_name):
    if pin_name == "CE0": return digitalio.DigitalInOut(board.CE0)
    if pin_name == "CE1": return digitalio.DigitalInOut(board.CE1)
    return None

def test_config(driver_name, cs_pin_name, spi, test_num):
    print(f"\n[{test_num}] TESTING: {driver_name} on {cs_pin_name} (1MHz)")
    
    cs = get_cs(cs_pin_name)
    dc = digitalio.DigitalInOut(board.D24)
    rst = digitalio.DigitalInOut(board.D25)

    try:
        # Re-initialize display for this test
        if driver_name == "ILI9341":
            display = ili9341.ILI9341(spi, cs=cs, dc=dc, rst=rst, baudrate=BAUDRATE, width=240, height=320)
        else:
            # ST7789 often needs different offsets or modes, but basic init should show something
            display = st7789.ST7789(spi, cs=cs, dc=dc, rst=rst, baudrate=BAUDRATE, width=240, height=320)
            
        # Create distinctive image for this test
        # Test 1 = Red, Test 2 = Green, Test 3 = Blue, Test 4 = Yellow
        colors = [(255,0,0), (0,255,0), (0,0,255), (255,255,0)]
        bg_color = colors[test_num-1]
        
        image = Image.new("RGB", (240, 320), bg_color) 
        draw = ImageDraw.Draw(image)
        
        # Giant Number
        draw.line((0,0, 240,320), fill=(255,255,255), width=10)
        draw.line((0,320, 240,0), fill=(255,255,255), width=10)
        
        try:
             # Draw a black box for text
            draw.rectangle((20, 100, 220, 220), fill=(0,0,0))
            # Just drawn shapes are enough to identify
        except:
            pass
            
        display.image(image)
        print(f"   -> Sending {bg_color} screen...")
        print("   -> Watch for image for 5 seconds...")
        time.sleep(5)
        
    except Exception as e:
        print(f"   -> Setup Failed: {e}")

def main():
    print("Initializing SPI...")
    spi = busio.SPI(board.SCK, MOSI=board.MOSI)
    
    # Sequence
    test_config("ILI9341", "CE1", spi, 1) # Expect RED
    test_config("ILI9341", "CE0", spi, 2) # Expect GREEN
    test_config("ST7789",  "CE1", spi, 3) # Expect BLUE
    test_config("ST7789",  "CE0", spi, 4) # Expect YELLOW

if __name__ == "__main__":
    main()

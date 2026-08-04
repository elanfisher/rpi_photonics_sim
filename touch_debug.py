import time
import argparse
import board
import busio
import digitalio
from xpt2046_circuitpython import Touch

def get_pin(pin_name):
    if hasattr(board, pin_name):
        return getattr(board, pin_name)
    try:
        # Try raw int if passed as string "8" -> D8
        return getattr(board, f"D{pin_name}")
    except AttributeError:
        pass
    raise ValueError(f"Pin {pin_name} not found on board")

def main():
    parser = argparse.ArgumentParser(description="XPT2046 Touch Debugger")
    parser.add_argument("--cs", default="D6", help="Chip Select Pin (default: D6)")
    parser.add_argument("--irq", default="D22", help="IRQ Pin (default: D22)")
    parser.add_argument("--speed", type=int, default=1000000, help="SPI Speed")
    args = parser.parse_args()

    print(f"Testing XPT2046 on CS={args.cs}, IRQ={args.irq}")

    # SPI Setup
    # Note: XPT2046 often supports up to 2MHz. 1MHz is safe.
    try:
        spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
    except Exception as e:
        print(f"Failed to init SPI: {e}")
        return

    # IMPORTANT: Disable other SPI devices to avoid bus contention/glitches
    # TFT is on CE1, ADC is on CE0. Pull them HIGH to disable.
    try:
        tft_cs = digitalio.DigitalInOut(board.CE1)
        tft_cs.direction = digitalio.Direction.OUTPUT
        tft_cs.value = True # Disable TFT
        
        adc_cs = digitalio.DigitalInOut(board.CE0)
        adc_cs.direction = digitalio.Direction.OUTPUT
        adc_cs.value = True # Disable ADC
        print("Disabled TFT (CE1) and ADC (CE0) to prevent conflicts.")
    except Exception as e:
        print(f"Warning: Could not disable other SPI devices: {e}")

    # Pin Config
    try:
        cs_pin = get_pin(args.cs)
        irq_pin = get_pin(args.irq)
        
        cs = digitalio.DigitalInOut(cs_pin)
        irq = digitalio.DigitalInOut(irq_pin)
    except Exception as e:
        print(f"Failed to setup pins: {e}")
        return

    print("Initializing Touch Controller...")
    try:
        touch = Touch(spi, cs=cs, interrupt=irq, width=240, height=320)
        print("Touch object created.")
    except Exception as e:
        print(f"Failed to initialize touch: {e}")
        return

    print("Attempting to read. Touch the screen! (Ctrl+C to exit)")
    print("-----------------------------------------------------")

    success_count = 0
    fail_count = 0

    while True:
        try:
            # We can check is_pressed() or just try to get coordinates
            # is_pressed() checks the IRQ pin if provided.
            if touch.is_pressed():
                print("IRQ Active! Reading...", end=" ")
                coords = touch.get_coordinates()
                if coords:
                    x, y = coords
                    print(f"OK! ({x}, {y})")
                    success_count += 1
                else:
                    print("No coords returned.")
                    fail_count += 1
            else:
                # print(".", end="", flush=True)
                pass
                
            time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            # print(f"\nError: {e}")
            fail_count += 1
            time.sleep(0.5)

if __name__ == "__main__":
    main()

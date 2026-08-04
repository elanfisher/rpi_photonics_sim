#!/usr/bin/env python3
import argparse
import math
import time
import serial

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import fftconvolve

# Pre-compute Phase-to-RGB Lookup Table (256 entries)
_PHASE_LUT = np.zeros((256, 3), dtype=np.uint8)
for _i in range(256):
    _hue = _i / 255.0
    _h6 = _hue * 6.0
    _sector = int(_h6) % 6
    _f = _h6 - int(_h6)
    _q = 1.0 - _f
    if _sector == 0:
        _PHASE_LUT[_i] = [255, int(_f * 255), 0]
    elif _sector == 1:
        _PHASE_LUT[_i] = [int(_q * 255), 255, 0]
    elif _sector == 2:
        _PHASE_LUT[_i] = [0, 255, int(_f * 255)]
    elif _sector == 3:
        _PHASE_LUT[_i] = [0, int(_q * 255), 255]
    elif _sector == 4:
        _PHASE_LUT[_i] = [int(_f * 255), 0, 255]
    else:
        _PHASE_LUT[_i] = [255, 0, int(_q * 255)]

# Hardware Imports
try:
    import board
    import busio
    import digitalio
    import adafruit_mcp3xxx.mcp3008 as MCP
    from adafruit_mcp3xxx.analog_in import AnalogIn
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False
    print("Warning: Hardware libraries not found. Running in simulation-only mode.")


def _phase_to_rgb(phase: np.ndarray) -> np.ndarray:
    # Fast LUT-based conversion
    hue = (phase + np.pi) / (2 * np.pi)
    hue = np.mod(hue, 1.0)
    idx = (hue * 255).astype(np.uint8)
    return _PHASE_LUT[idx]


def _magnitude_to_rgb(mag: np.ndarray) -> np.ndarray:
    """Render magnitude as grayscale/intensity map for Beam Monitor"""
    # Normalize
    m_max = np.max(mag)
    if m_max > 0:
        norm = mag / m_max
    else:
        norm = mag
    
    # Simple green phosphor look
    r = np.zeros_like(norm)
    g = norm
    b = norm * 0.2
    
    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255.0).astype(np.uint8)


def _kernel_to_rgb(kernel: np.ndarray) -> np.ndarray:
    """Render kernel as heat map"""
    k_max = np.max(kernel)
    if k_max > 0:
        norm = kernel / k_max
    else:
        norm = kernel
        
    # Heatmap: Blue -> Red
    r = norm
    g = np.zeros_like(norm)
    b = 1.0 - norm
    
    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255.0).astype(np.uint8)


# Serial Input Handler
class SerialInput:
    def __init__(self, port='/dev/ttyACM0', baud=9600):
        self.port = port
        self.baud = baud
        self.ser = None
        self.last_connect_attempt = 0
        self._connect()

    def _connect(self):
        now = time.time()
        if now - self.last_connect_attempt < 2.0: # Limit reconnect rate
            return
            
        self.last_connect_attempt = now
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
            self.ser.flush()
            print(f"Connected to Arduino on {self.port}")
        except Exception:
            self.ser = None

    def read(self):
        """
        Reads one line from serial and parses it.
        Expected format: j1_x,j1_y,j1_sw,pot,j2_x,j2_y,j2_sw (7 values)
        Returns: dict with normalized values or None
        """
        if not self.ser:
            self._connect()
            if not self.ser:
                return None
            
        try:
            if self.ser.in_waiting == 0:
                return None

            # Read all available lines, keep only the last one to be up-to-date
            lines = self.ser.read_all().decode('utf-8').strip().split('\n')
            if not lines:
                return None
                
            last_line = lines[-1].strip()
            data = last_line.split(',')
            
            # Support both old 4-value and new 7-value formats
            if len(data) == 7:
                # New format: j1_x, j1_y, j1_sw, pot, j2_x, j2_y, j2_sw
                j1_x = int(data[0])
                j1_y = int(data[1])
                j1_sw = int(data[2])
                pot = int(data[3])
                j2_x = int(data[4])
                j2_y = int(data[5])
                j2_sw = int(data[6])
                
                # Normalize joysticks with deadzone and reduced sensitivity
                def normalize_joy(val, center=512, deadzone=50):
                    offset = val - center
                    if abs(offset) < deadzone:
                        return 0.0
                    # Remove deadzone from calculation and scale
                    sign = 1 if offset > 0 else -1
                    adjusted = abs(offset) - deadzone
                    max_range = center - deadzone
                    norm = (adjusted / max_range) * 0.5  # 0.5 = reduced sensitivity
                    return max(-1.0, min(1.0, sign * norm))
                
                dx1 = normalize_joy(j1_x)
                dy1 = normalize_joy(j1_y)
                dx2 = normalize_joy(j2_x)
                dy2 = normalize_joy(j2_y)
                
                # Buttons: 0 = pressed (INPUT_PULLUP)
                btn1 = (j1_sw == 0)
                btn2 = (j2_sw == 0)
                
                # Potentiometer: 0..1023 -> Rho 1.0..8.0
                rho = 1.0 + (pot / 1023.0) * 7.0
                
                return {
                    "dx1": dx1, "dy1": dy1, "btn1": btn1,
                    "dx2": dx2, "dy2": dy2, "btn2": btn2,
                    "rho": rho
                }
            elif len(data) == 4:
                # Legacy format: X, Y, Switch, Pot (single joystick)
                raw_x = int(data[0])
                raw_y = int(data[1])
                sw = int(data[2])
                pot = int(data[3])
                
                dx = max(-1.0, min(1.0, (raw_x - 512) / 512.0))
                dy = max(-1.0, min(1.0, (raw_y - 512) / 512.0))
                btn_pressed = (sw == 0)
                rho = 1.0 + (pot / 1023.0) * 7.0
                
                return {
                    "dx1": dx, "dy1": dy, "btn1": btn_pressed,
                    "dx2": 0.0, "dy2": 0.0, "btn2": False,
                    "rho": rho
                }
                
        except Exception as e:
            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
            return None
            
        return None


class HardwareInterface:
    def __init__(self, spi, use_adc=True):
        self.state = {
            "rho": 2.0,
            "speed": 0.2,
            "mode": "gaussian",   # gaussian, rational
            "source": "uniform",  # uniform, beam
            "noise_type": "interp", # interp, perlin
            "resolution": 240,    # Physics grid size: 8, 16, 24, 100, 240
            "view": "PHA",        # PHA, KER, BM
            "p_0": 0.5,           # Potentiometer value
            "dx1": 0.0,           # Beam 1 X
            "dy1": 0.0,           # Beam 1 Y
            "dx2": 0.0,           # Beam 2 X
            "dy2": 0.0,           # Beam 2 Y
            "btn1_last": False,   # Joystick 1 button debounce
            "btn2_last": False,   # Joystick 2 button debounce
        }
        
        self.mcp = None
        if not HARDWARE_AVAILABLE:
            return

        # --- ADC Setup (MCP3008) ---
        if use_adc:
            try:
                # MCP3008 on CE0 (Device 0)
                # Note: TFT is on CE1. We share the SPI bus.
                self.cs_adc = digitalio.DigitalInOut(board.CE0)
                self.mcp = MCP.MCP3008(spi, self.cs_adc)
                
                # Channels
                self.chan_pot = AnalogIn(self.mcp, MCP.P0)   # Potentiometer -> p_0 (Speed/Param)
                self.chan_joy_x = AnalogIn(self.mcp, MCP.P1) # Joystick X
                self.chan_joy_y = AnalogIn(self.mcp, MCP.P2) # Joystick Y -> Size (Rho)
            except Exception as e:
                print(f"ADC Init Failed: {e}")
                self.mcp = None

        # --- GPIO Buttons ---
        # Btn 1: Mode (Gauss/Rat) - GPIO 5
        self.btn_mode = digitalio.DigitalInOut(board.D5)
        self.btn_mode.direction = digitalio.Direction.INPUT
        self.btn_mode.pull = digitalio.Pull.UP
        
        # Btn 2: Resolution Cycle - GPIO 6
        self.btn_res = digitalio.DigitalInOut(board.D6)
        self.btn_res.direction = digitalio.Direction.INPUT
        self.btn_res.pull = digitalio.Pull.UP
        
        # Btn 3: View (KER/PHA/BM) - GPIO 13
        self.btn_view = digitalio.DigitalInOut(board.D13)
        self.btn_view.direction = digitalio.Direction.INPUT
        self.btn_view.pull = digitalio.Pull.UP
        
        # Btn 4: Speed UP - GPIO 17
        self.btn_speed_up = digitalio.DigitalInOut(board.D17)
        self.btn_speed_up.direction = digitalio.Direction.INPUT
        self.btn_speed_up.pull = digitalio.Pull.UP

        # Btn 5: Speed DOWN - GPIO 27
        self.btn_speed_down = digitalio.DigitalInOut(board.D27)
        self.btn_speed_down.direction = digitalio.Direction.INPUT
        self.btn_speed_down.pull = digitalio.Pull.UP
        
        # --- Outputs (LEDs/Piezo) ---
        # LED Mode - GPIO 19
        self.led_mode = digitalio.DigitalInOut(board.D19)
        self.led_mode.direction = digitalio.Direction.OUTPUT
        
        # LED Source (Beam) - GPIO 16
        self.led_source = digitalio.DigitalInOut(board.D16)
        self.led_source.direction = digitalio.Direction.OUTPUT

        # Piezo - GPIO 12
        self.piezo = digitalio.DigitalInOut(board.D12)
        self.piezo.direction = digitalio.Direction.OUTPUT
        
        # Button State tracking
        self.last_btn_mode = True
        self.last_btn_res = True
        self.last_btn_view = True
        self.last_btn_speed_up = True
        self.last_btn_speed_down = True
        
    def update(self, serial_inputs=None):
        # Priority: Serial > Default
        if serial_inputs:  # dict with dx1, dy1, btn1, dx2, dy2, btn2, rho
            self.state["dx1"] = serial_inputs["dx1"]
            self.state["dy1"] = serial_inputs["dy1"]
            self.state["dx2"] = serial_inputs["dx2"]
            self.state["dy2"] = serial_inputs["dy2"]
            self.state["rho"] = serial_inputs["rho"]
            
            # Joystick 1 Button: Toggle Source Mode (Uniform/Beam)
            btn1 = serial_inputs["btn1"]
            if btn1 and not self.state["btn1_last"]:
                self.state["source"] = "beam" if self.state["source"] == "uniform" else "uniform"
                self._beep()
            self.state["btn1_last"] = btn1
            
            # Joystick 2 Button: Toggle Noise Type (Interp/Perlin)
            btn2 = serial_inputs["btn2"]
            if btn2 and not self.state["btn2_last"]:
                self.state["noise_type"] = "perlin" if self.state["noise_type"] == "interp" else "interp"
                self._beep()
            self.state["btn2_last"] = btn2
        
        if not HARDWARE_AVAILABLE:
            return self.state

        # 1. Read Analog Inputs (If ADC exists)
        if self.mcp:
            pass

        # 2. Read Buttons (Active Low)
        try:
            # Mode Toggle
            curr_mode = self.btn_mode.value
            if not curr_mode and self.last_btn_mode:
                self.state["mode"] = "rational" if self.state["mode"] == "gaussian" else "gaussian"
                self._beep()
            self.last_btn_mode = curr_mode
            
            # Resolution Cycle (8 -> 16 -> 24 -> 100 -> 240 -> 8)
            curr_res = self.btn_res.value
            if not curr_res and self.last_btn_res:
                res_options = [8, 16, 24, 100, 240]
                curr_idx = res_options.index(self.state["resolution"]) if self.state["resolution"] in res_options else 0
                self.state["resolution"] = res_options[(curr_idx + 1) % len(res_options)]
                self._beep()
            self.last_btn_res = curr_res
            
            # View Toggle
            curr_view = self.btn_view.value
            if not curr_view and self.last_btn_view:
                modes = ["PHA", "KER", "BM"]
                idx = modes.index(self.state["view"])
                self.state["view"] = modes[(idx + 1) % len(modes)]
                self._beep()
            self.last_btn_view = curr_view

            # Speed UP (adaptive: small steps at low speeds)
            curr_speed_up = self.btn_speed_up.value
            if not curr_speed_up and self.last_btn_speed_up:
                curr_spd = self.state["speed"]
                if curr_spd < 0.1:
                    step = 0.01
                else:
                    step = 0.1
                new_speed = min(1.0, curr_spd + step)
                self.state["speed"] = round(new_speed, 3)
                self._beep()
            self.last_btn_speed_up = curr_speed_up

            # Speed DOWN (adaptive: small steps at low speeds, min 0 = stop)
            curr_speed_down = self.btn_speed_down.value
            if not curr_speed_down and self.last_btn_speed_down:
                curr_spd = self.state["speed"]
                if curr_spd <= 0.1:
                    step = 0.01
                else:
                    step = 0.1
                new_speed = max(0.0, curr_spd - step)
                self.state["speed"] = round(new_speed, 3)
                self._beep()
            self.last_btn_speed_down = curr_speed_down

        except Exception as e:
            print(f"Error reading Buttons: {e}")
        
        # 3. Update LEDs
        try:
            self.led_mode.value = (self.state["mode"] == "rational")
            self.led_source.value = (self.state["source"] == "beam")
        except Exception:
            pass
        
        return self.state

    def _beep(self):
        # Simple click. The serial branch of update() runs before the
        # HARDWARE_AVAILABLE guard, so off-Pi this is reached with no piezo.
        if not HARDWARE_AVAILABLE or getattr(self, "piezo", None) is None:
            return
        self.piezo.value = True
        time.sleep(0.005)
        self.piezo.value = False


class CoherencePhysics:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.noiseA = np.random.uniform(-np.pi, np.pi, (height, width))
        self.noiseB = np.random.uniform(-np.pi, np.pi, (height, width))
        self.time_t = 0.0
        
        # Caching
        self.last_rho = -1.0
        self.last_mode = ""
        self.kernel_fft = None
        self.kernel_small = None
        
        # Cache last output for speed=0 (complete stop)
        self.cached_phase = None
        self.cached_magnitude = None
        
        # Pre-compute coordinate grids for beam mask
        self.y_grid, self.x_grid = np.mgrid[0:self.height, 0:self.width]
        self.emf_val = 0.0
        
        # Perlin noise state (continuous evolution)
        self.perlin_time = 0.0
        self._init_perlin_gradients()
    
    def _init_perlin_gradients(self):
        # Simple Perlin-like noise using multiple octaves of sin waves
        # Pre-compute random frequencies and phases for smooth noise
        np.random.seed(42)  # Reproducible but can be changed
        self.n_octaves = 4
        self.freqs_x = np.random.uniform(0.5, 2.0, self.n_octaves)
        self.freqs_y = np.random.uniform(0.5, 2.0, self.n_octaves)
        self.freqs_t = np.random.uniform(0.1, 0.5, self.n_octaves)
        self.phases_x = np.random.uniform(0, 2*np.pi, self.n_octaves)
        self.phases_y = np.random.uniform(0, 2*np.pi, self.n_octaves)
        self.phases_t = np.random.uniform(0, 2*np.pi, self.n_octaves)
        self.amplitudes = np.array([1.0, 0.5, 0.25, 0.125])
        np.random.seed(None)  # Re-randomize
    
    def _generate_perlin_noise(self, t: float) -> np.ndarray:
        # Generate smooth continuous noise using sum of sinusoids
        # Normalized coords
        x_norm = self.x_grid / self.width * 2 * np.pi
        y_norm = self.y_grid / self.height * 2 * np.pi
        
        noise = np.zeros((self.height, self.width))
        for i in range(self.n_octaves):
            wave = np.sin(x_norm * self.freqs_x[i] + self.phases_x[i] + t * self.freqs_t[i])
            wave += np.sin(y_norm * self.freqs_y[i] + self.phases_y[i] + t * self.freqs_t[i] * 1.3)
            wave += np.sin((x_norm + y_norm) * self.freqs_x[i] * 0.7 + self.phases_t[i] + t * self.freqs_t[i] * 0.8)
            noise += wave * self.amplitudes[i]
        
        # Normalize to -pi to pi
        noise = noise / np.max(np.abs(noise)) * np.pi
        return noise

    def _generate_beam_mask(self, dx: float, dy: float) -> np.ndarray:
        # Gaussian Beam Profile at (dx, dy) position
        # dx, dy are in range -1.0 to 1.0 (relative to screen center)
        cy = self.height / 2.0 + (dy * self.height / 2.0)
        cx = self.width / 2.0 + (dx * self.width / 2.0)
        
        # Small sigma for focused beam spot
        sigma = min(self.width, self.height) / 6.0
        dist_sq = (self.x_grid - cx)**2 + (self.y_grid - cy)**2
        return np.exp(-dist_sq / (2 * sigma**2))

    def _update_kernel_cache(self, rho: float, mode: str):
        if rho == self.last_rho and mode == self.last_mode:
            return

        # Kernel radius must be smaller than half the grid size
        k_rad = min(16, (min(self.height, self.width) - 1) // 2)
        y, x = np.mgrid[-k_rad : k_rad + 1, -k_rad : k_rad + 1]
        r = np.sqrt(x**2 + y**2)
        rho = max(0.25, float(rho))
        
        if mode == 'gaussian':
            kernel = np.exp(-(r**2) / (rho**2))
        else:
            kernel = 1.0 / (1.0 + np.power(r / rho, 1.5))
            
        s = float(np.sum(kernel))
        if s > 0:
            kernel /= s
            
        self.kernel_small = kernel
        
        # Prepare for FFT Convolution (Circular)
        k_full = np.zeros((self.height, self.width))
        h, w = kernel.shape
        k_full[:h, :w] = kernel
        # Parenthesised deliberately. -h//2 parses as (-h)//2, which for odd h
        # (always, since h = 2*k_rad+1) rounds the wrong way and translates every
        # convolved frame by one pixel.
        k_full = np.roll(k_full, -(h // 2), axis=0)
        k_full = np.roll(k_full, -(w // 2), axis=1)
        
        self.kernel_fft = np.fft.fft2(k_full)
        self.last_rho = rho
        self.last_mode = mode

    def update(self, speed: float, dx1: float, dy1: float, dx2: float, dy2: float, 
               rho: float, mode: str, source: str, noise_type: str = "interp") -> tuple:
        self._update_kernel_cache(rho, mode)
        
        # Speed 0 = complete stop - return cached output
        if speed == 0 and self.cached_phase is not None:
            return self.cached_phase, self.cached_magnitude, self.kernel_small
        
        # Generate noise based on noise_type
        if noise_type == "perlin":
            # Perlin mode: smooth continuous evolution
            self.perlin_time += speed * 0.5
            base_noise = self._generate_perlin_noise(self.perlin_time)
        else:
            # Interp mode: interpolate between random noise frames
            self.time_t += speed * 0.1
            if self.time_t >= 1.0:
                self.time_t = 0.0
                self.noiseA = self.noiseB
                self.noiseB = np.random.uniform(-np.pi, np.pi, (self.height, self.width))
            base_noise = self.noiseA * (1 - self.time_t) + self.noiseB * self.time_t
        
        if source == "beam":
            # BEAM MODE: Two beams that interfere
            beam_mask1 = self._generate_beam_mask(dx1, dy1)
            beam_mask2 = self._generate_beam_mask(dx2, dy2)
            # Combine masks - where beams overlap, they interfere
            combined_mask = np.clip(beam_mask1 + beam_mask2, 0, 1)
            mixed_noise = base_noise * combined_mask
            self.emf_val = 1.0
        else:
            # UNIFORM MODE: Full-screen noise
            mixed_noise = base_noise
            self.emf_val = 0.0
        
        # FFT Convolution
        complex_field = np.exp(1j * mixed_noise)
        field_fft = np.fft.fft2(complex_field)
        conv_fft = field_fft * self.kernel_fft
        conv_field = np.fft.ifft2(conv_fft)
        
        phase = np.angle(conv_field)
        magnitude = np.abs(conv_field)
        
        # Cache for speed=0
        self.cached_phase = phase
        self.cached_magnitude = magnitude

        return phase, magnitude, self.kernel_small


def _init_display(spi, driver: str, rotation: int, baudrate: int, width: int, height: int, cs_pin: str, dc_pin: str, rst_pin: str):
    import digitalio
    import board

    # Dynamic Pin Mapping
    def get_pin(name):
        return getattr(board, name)

    cs = digitalio.DigitalInOut(get_pin(cs_pin))
    dc = digitalio.DigitalInOut(get_pin(dc_pin))
    rst = digitalio.DigitalInOut(get_pin(rst_pin))

    if driver == "st7789":
        import adafruit_rgb_display.st7789 as st7789

        return st7789.ST7789(
            spi,
            cs=cs,
            dc=dc,
            rst=rst,
            baudrate=baudrate,
            width=width,
            height=height,
            rotation=rotation,
        )

    if driver == "ili9341":
        import adafruit_rgb_display.ili9341 as ili9341

        return ili9341.ILI9341(
            spi,
            cs=cs,
            dc=dc,
            rst=rst,
            baudrate=baudrate,
            width=width,
            height=height,
            rotation=rotation,
        )

    raise ValueError(f"Unsupported driver: {driver}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", choices=["st7789", "ili9341"], default="ili9341")
    parser.add_argument("--rotation", type=int, default=0)
    parser.add_argument("--width", type=int, default=240)
    parser.add_argument("--height", type=int, default=320)
    parser.add_argument("--baudrate", type=int, default=64000000)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--physics", type=int, default=24)
    
    # Pin Config
    parser.add_argument("--cs", type=str, default="CE1", help="Chip Select Pin (e.g. CE0 or CE1)")
    parser.add_argument("--dc", type=str, default="D24", help="Data/Command Pin (e.g. D24)")
    parser.add_argument("--rst", type=str, default="D25", help="Reset Pin (e.g. D25)")
    parser.add_argument("--no-adc", action="store_true", help="Disable ADC (MCP3008) initialization")
    
    # Touch Config (XPT2046) - REMOVED
    # Serial Config
    parser.add_argument("--serial-port", type=str, default="/dev/ttyUSB0", help="Arduino Serial Port")
    
    args = parser.parse_args()

    # --- Hardware Init ---
    if HARDWARE_AVAILABLE:
        spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
    else:
        spi = None

    # Init Display
    if HARDWARE_AVAILABLE and spi:
        display = _init_display(
            spi,
            driver=args.driver,
            rotation=args.rotation,
            baudrate=args.baudrate,
            width=args.width,
            height=args.height,
            cs_pin=args.cs,
            dc_pin=args.dc,
            rst_pin=args.rst
        )
    else:
        display = None
        print("Display not initialized (Hardware unavailable)")

    # Init Controls
    controls = HardwareInterface(spi, use_adc=not args.no_adc)
    
    # Init Serial
    serial_input = SerialInput(port=args.serial_port)

    # Init Physics (default to max resolution)
    current_resolution = 240
    physics = CoherencePhysics(current_resolution, current_resolution)
    font = ImageFont.load_default()
    target_frame_time = 1.0 / max(1, args.fps)
    
    # FPS Tracking
    frame_count = 0
    last_fps_time = time.time()
    current_fps = 0.0
    
    # Pre-allocate canvas (avoid creating new Image every frame)
    canvas = Image.new("RGB", (args.width, args.height), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    info_area_top = args.width  # Where the text info starts

    while True:
        start = time.time()

        # 1. Read Serial Input
        ser_data = serial_input.read()
        
        # 2. Update Controls
        inputs = controls.update(ser_data)
        
        rho = inputs["rho"]
        speed = inputs["speed"]
        mode = inputs["mode"]
        source = inputs["source"]
        noise_type = inputs["noise_type"]
        resolution = inputs["resolution"]
        view_mode = inputs["view"]
        dx1 = inputs.get("dx1", 0.0)
        dy1 = inputs.get("dy1", 0.0)
        dx2 = inputs.get("dx2", 0.0)
        dy2 = inputs.get("dy2", 0.0)
        
        # 3. Check if resolution changed - recreate physics if needed
        if resolution != current_resolution:
            current_resolution = resolution
            physics = CoherencePhysics(current_resolution, current_resolution)
        
        # 4. Update Physics
        phase, magnitude, kernel = physics.update(
            speed=speed, dx1=dx1, dy1=dy1, dx2=dx2, dy2=dy2,
            rho=rho, mode=mode, source=source, noise_type=noise_type
        )
        
        # 5. Render based on View Mode
        if view_mode == "PHA":
            rgb = _phase_to_rgb(phase)
        elif view_mode == "KER":
            rgb = _kernel_to_rgb(kernel)
        elif view_mode == "BM":
            rgb = _magnitude_to_rgb(magnitude)
        else:
            rgb = _phase_to_rgb(phase)

        # 6. Display
        image = Image.fromarray(rgb, mode="RGB")
        image = image.resize((args.width, args.width), resample=Image.NEAREST)

        # Paste simulation into pre-allocated canvas
        canvas.paste(image, (0, 0))
        
        # Clear info area (below simulation)
        draw.rectangle([(0, info_area_top), (args.width, args.height)], fill=(0, 0, 0))
        
        # Top Info - show noise type
        noise_str = "PRL" if noise_type == "perlin" else "INT"
        draw.text((8, args.width + 4), f"RHO {rho:.1f}  SPD {speed:.3f}  {noise_str}", fill=(0, 255, 0), font=font)
        
        # Middle Info
        src_str = "BM" if source == "beam" else "UNI"
        draw.text((8, args.width + 18), f"MOD {mode[:3].upper()}  SRC {src_str}  RES {resolution}", fill=(0, 255, 255), font=font)
        
        # Bottom Info
        ser_str = "SER" if ser_data else "---"
        draw.text((8, args.width + 32), f"VIEW {view_mode}  {ser_str}", fill=(255, 255, 0), font=font)
        draw.text((8, args.width + 46), f"FPS {current_fps:.1f}", fill=(100, 100, 100), font=font)

        if display:
            display.image(canvas)

        # FPS Calculation
        frame_count += 1
        now = time.time()
        if now - last_fps_time >= 1.0:
            current_fps = frame_count / (now - last_fps_time)
            frame_count = 0
            last_fps_time = now

        elapsed = time.time() - start
        if elapsed < target_frame_time:
            time.sleep(target_frame_time - elapsed)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Mirror Simulation - Raspberry Pi Hardware Version
Uses two joysticks via Arduino serial:
  - Left joystick: beam position, click = cycle views
  - Right joystick: menu nav (up/down), value adjust (left/right), click = toggle menu
"""
import argparse
import time
import serial
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Import shared physics module
from mirror_physics import (
    compute_interference, compute_Qp_matrix, setup_grids,
    WAVELENGTH, K, W0, ZR, L,
    ROUGHNESS_OPTIONS, ROUGHNESS_LABELS, MIRROR_MODES, QP_MODES,
    DEFAULT_PARAMS
)

# Hardware imports (optional for testing without Pi)
try:
    import board
    import busio
    import digitalio
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False
    print("Warning: Hardware libraries not found. Display output disabled.")

# -----------------------------
# Display Configuration
# -----------------------------
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
SIM_SIZE = 240  # Square simulation area
MENU_WIDTH = 80  # Right sidebar
FPS_TARGET = 30

# Resolution options
RESOLUTION_OPTIONS = [8, 16, 24, 64, 100, 240]

# Fidelity levels: (name, resolution, qp_grid_size)
FIDELITY_LEVELS = [
    ("Low", 8, 4),
    ("Med", 16, 6),
    ("High", 64, 12),
    ("Max", 240, 24),
]

# View names
VIEW_NAMES = [
    "Roughness",
    "Surface", 
    "Interference",
    "Phase",
    "Amplitude",
    "Q_p Matrix"
]

# -----------------------------
# Colormap Generation (PIL compatible)
# -----------------------------
def generate_colormap(name):
    """Generate a 256-color lookup table"""
    colors = []
    
    if name == "viridis":
        for i in range(256):
            t = i / 255
            colors.append((int(68 + t*120), int(1 + t*180), int(84 + t*100)))
    elif name == "inferno":
        for i in range(256):
            t = i / 255
            if t < 0.25:
                r = int(t * 4 * 80)
                g = int(t * 4 * 10)
                b = int(t * 4 * 60)
            elif t < 0.5:
                t2 = (t - 0.25) * 4
                r = int(80 + t2 * 175)
                g = int(10 + t2 * 30)
                b = int(60 - t2 * 60)
            elif t < 0.75:
                t2 = (t - 0.5) * 4
                r = 255
                g = int(40 + t2 * 140)
                b = 0
            else:
                t2 = (t - 0.75) * 4
                r = 255
                g = int(180 + t2 * 75)
                b = int(t2 * 120)
            colors.append((min(255, r), min(255, g), min(255, b)))
    elif name == "twilight":
        for i in range(256):
            t = i / 255
            angle = t * 2 * np.pi
            colors.append((
                int(127 + 127 * np.sin(angle)),
                int(127 + 127 * np.sin(angle + 2*np.pi/3)),
                int(127 + 127 * np.sin(angle + 4*np.pi/3))
            ))
    elif name == "hot":
        for i in range(256):
            t = i / 255
            r = int(min(255, max(0, t * 3 * 255)))
            g = int(min(255, max(0, (t - 0.33) * 3 * 255)))
            b = int(min(255, max(0, (t - 0.66) * 3 * 255)))
            colors.append((r, g, b))
    else:  # grayscale
        for i in range(256):
            colors.append((i, i, i))
            
    return colors

# Pre-generate colormaps as numpy arrays for fast indexing
CMAP_VIRIDIS = np.array(generate_colormap("viridis"), dtype=np.uint8)
CMAP_INFERNO = np.array(generate_colormap("inferno"), dtype=np.uint8)
CMAP_TWILIGHT = np.array(generate_colormap("twilight"), dtype=np.uint8)
CMAP_HOT = np.array(generate_colormap("hot"), dtype=np.uint8)


# -----------------------------
# Serial Input Handler
# -----------------------------
class SerialInput:
    """Reads joystick data from Arduino via serial"""
    
    def __init__(self, port='/dev/ttyUSB0', baud=9600):
        self.port = port
        self.baud = baud
        self.ser = None
        self.last_connect_attempt = 0
        self._connect()
        
        # State
        self.left_joy = [0.0, 0.0]
        self.right_joy = [0.0, 0.0]
        self.left_click = False
        self.right_click = False
        self.left_btn_state = False  # Current button state (for hold detection)
        self.right_btn_state = False
        
        # Button edge detection
        self._prev_btn1 = False
        self._prev_btn2 = False

    def _connect(self):
        now = time.time()
        if now - self.last_connect_attempt < 2.0:
            return
            
        self.last_connect_attempt = now
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
            self.ser.flush()
            print(f"Connected to Arduino on {self.port}")
        except Exception as e:
            self.ser = None
            print(f"Serial connection failed: {e}")

    def update(self):
        """Read serial data and update state. Returns True if successful."""
        self.left_click = False
        self.right_click = False
        
        if not self.ser:
            self._connect()
            if not self.ser:
                return False
            
        try:
            if self.ser.in_waiting == 0:
                return True  # No new data, keep previous state
                
            # Read all available lines, keep only the last one
            lines = self.ser.read_all().decode('utf-8').strip().split('\n')
            if not lines:
                return True
                
            last_line = lines[-1].strip()
            data = last_line.split(',')
            
            # Expected format: j1_x, j1_y, j1_sw, pot, j2_x, j2_y, j2_sw (7 values)
            # We ignore pot (index 3)
            if len(data) >= 7:
                j1_x = int(data[0])
                j1_y = int(data[1])
                j1_sw = int(data[2])
                # pot = int(data[3])  # Ignored
                j2_x = int(data[4])
                j2_y = int(data[5])
                j2_sw = int(data[6])
                
                # Normalize joysticks with deadzone
                def normalize_joy(val, center=512, deadzone=50):
                    offset = val - center
                    if abs(offset) < deadzone:
                        return 0.0
                    sign = 1 if offset > 0 else -1
                    adjusted = abs(offset) - deadzone
                    max_range = center - deadzone
                    norm = adjusted / max_range
                    return max(-1.0, min(1.0, sign * norm))
                
                # Swap & Remap: 
                # Left Joystick gets J2 input (Physical Right Stick)
                # Remapping J2 axes: Down(+Y) -> Left(-X), Up(-Y) -> Right(+X)
                #                    Right(+X) -> Up(+Y), Left(-X) -> Down(-Y)
                self.left_joy[0] = -normalize_joy(j2_y)
                self.left_joy[1] = normalize_joy(j2_x)
                
                # Right Joystick gets J1 input (Physical Left Stick) - Standard mapping
                self.right_joy[0] = -normalize_joy(j1_y)
                self.right_joy[1] = normalize_joy(j1_x)
                
                # Buttons: 0 = pressed (INPUT_PULLUP), detect edges
                # Swap buttons: btn2 -> Left, btn1 -> Right
                btn1 = (j1_sw == 0)
                btn2 = (j2_sw == 0)
                
                # Store current button state for hold detection
                self.left_btn_state = btn2
                self.right_btn_state = btn1
                
                if btn2 and not self._prev_btn2:
                    self.left_click = True
                if btn1 and not self._prev_btn1:
                    self.right_click = True
                    
                self._prev_btn1 = btn1
                self._prev_btn2 = btn2
                
            return True
            
        except Exception as e:
            if self.ser:
                try:
                    self.ser.close()
                except:
                    pass
            self.ser = None
            return False


# -----------------------------
# Physics Engine
# -----------------------------
class MirrorPhysics:
    """Wrapper for mirror physics calculations"""
    
    def __init__(self, resolution=240):
        self.resolution = resolution
        
        # Default parameters (matching lens_test.py)
        self.mirror_mode = DEFAULT_PARAMS["mirror_mode"]
        self.qp_mode = DEFAULT_PARAMS["qp_mode"]
        self.beam_x = DEFAULT_PARAMS["beam_x"]
        self.beam_y = DEFAULT_PARAMS["beam_y"]
        self.z_m = DEFAULT_PARAMS["z_m"]
        self.R_m = DEFAULT_PARAMS["R_m"]
        self.roughness_idx = DEFAULT_PARAMS["roughness_idx"]
        self.corr_len = DEFAULT_PARAMS["corr_len"]
        self.show_beam_markers = True  # Enabled by default
        self.fidelity_idx = 2  # Default to "High"
        
        # Cached results
        self.rough = None
        self.surface = None
        self.interference = None
        self.phase = None
        self.amplitude = None
        self.qp_matrix = None
        self.ref_x = 0
        self.ref_y = 0
        
        # Setup grids
        self._setup_grids()
        
    def _setup_grids(self):
        """Initialize computation grids"""
        self.x, self.y, self.X, self.Y, self.FX, self.FY, self.base_noise = setup_grids(self.resolution)
        
    def set_resolution(self, new_res):
        """Change resolution and reinitialize grids"""
        if new_res != self.resolution:
            self.resolution = new_res
            self._setup_grids()
            
    def compute(self, compute_qp=False):
        """Compute physics outputs. Only compute Q_p if needed (slow)."""
        sigma_h = ROUGHNESS_OPTIONS[self.roughness_idx] * WAVELENGTH
        
        self.rough, self.surface, self.interference, self.amplitude, self.phase, self.ref_x, self.ref_y = \
            compute_interference(
                self.X, self.Y, self.FX, self.FY, self.base_noise,
                self.z_m, self.R_m, sigma_h, self.corr_len,
                self.beam_x, self.beam_y, self.mirror_mode
            )
        
        # Only compute Q_p matrix when viewing it (expensive O(n^4) operation)
        if compute_qp:
            qp_grid = FIDELITY_LEVELS[self.fidelity_idx][2]
            self.qp_matrix = compute_Qp_matrix(
                self.resolution, self.corr_len, self.surface, self.qp_mode, grid_size=qp_grid
            )
    
    def reset_to_defaults(self):
        """Reset all parameters to defaults"""
        self.mirror_mode = DEFAULT_PARAMS["mirror_mode"]
        self.qp_mode = DEFAULT_PARAMS["qp_mode"]
        self.beam_x = DEFAULT_PARAMS["beam_x"]
        self.beam_y = DEFAULT_PARAMS["beam_y"]
        self.z_m = DEFAULT_PARAMS["z_m"]
        self.R_m = DEFAULT_PARAMS["R_m"]
        self.roughness_idx = DEFAULT_PARAMS["roughness_idx"]
        self.corr_len = DEFAULT_PARAMS["corr_len"]
        self.fidelity_idx = 2  # High
        new_res = FIDELITY_LEVELS[self.fidelity_idx][1]
        if new_res != self.resolution:
            self.resolution = new_res
            self._setup_grids()
        
    def get_view_data(self, view_idx):
        """Get normalized data for a specific view"""
        if view_idx == 0:  # Roughness
            data = self.rough
        elif view_idx == 1:  # Surface
            data = self.surface
        elif view_idx == 2:  # Interference
            return self.interference  # Already 0-1
        elif view_idx == 3:  # Phase
            data = (self.phase + np.pi) / (2 * np.pi)
            return data
        elif view_idx == 4:  # Amplitude
            data = self.amplitude
        elif view_idx == 5:  # Q_p Matrix
            return self.qp_matrix  # Already 0-1
        else:
            data = self.interference
            
        # Normalize to 0-1
        dmin, dmax = data.min(), data.max()
        if dmax > dmin:
            return (data - dmin) / (dmax - dmin)
        return np.zeros_like(data)
        
    def get_beam_positions_normalized(self):
        """Get beam positions in 0-1 range"""
        inc_x = (self.beam_x / L + 0.5)
        inc_y = (self.beam_y / L + 0.5)
        ref_x = (self.ref_x / L + 0.5)
        ref_y = (self.ref_y / L + 0.5)
        return (inc_x, inc_y), (ref_x, ref_y)


# -----------------------------
# Menu System
# -----------------------------
class MenuSystem:
    """Sidebar menu for parameter adjustment"""
    
    def __init__(self):
        self.visible = False
        self.selected_idx = 0
        self.nav_cooldown = 0
        self.adj_cooldown = 0
        
        # Menu items: (name, param_key, type, options_or_range)
        self.items = [
            ("Fidelity", "fidelity", "fidelity", FIDELITY_LEVELS),
            ("Mirror", "mirror_mode", "cycle", MIRROR_MODES),
            ("Q_p", "qp_mode", "cycle", QP_MODES),
            ("Rough", "roughness_idx", "cycle_idx", ROUGHNESS_LABELS),
            ("Z", "z_m", "range", (0.05, 1.0, 0.05)),
            ("R", "R_m", "range", (0.1, 2.0, 0.1)),
            ("Corr", "corr_len_um", "range", (10, 500, 10)),
            ("Mark", "show_beam_markers", "toggle", None),
        ]
        
    def toggle(self):
        self.visible = not self.visible
        
    def navigate(self, direction):
        if not self.visible or self.nav_cooldown > 0:
            return
        self.selected_idx = (self.selected_idx + direction) % len(self.items)
        self.nav_cooldown = 8
        
    def update_cooldowns(self):
        if self.nav_cooldown > 0:
            self.nav_cooldown -= 1
        if self.adj_cooldown > 0:
            self.adj_cooldown -= 1
        
    def adjust(self, direction, physics):
        """Adjust current value"""
        if not self.visible or self.adj_cooldown > 0:
            return False
            
        item = self.items[self.selected_idx]
        param_key = item[1]
        item_type = item[2]
        changed = False
        
        if item_type == "range":
            min_val, max_val, step = item[3]
            if param_key == "corr_len_um":
                current = physics.corr_len * 1e6
                new_val = np.clip(current + direction * step, min_val, max_val)
                physics.corr_len = new_val * 1e-6
                changed = True
            elif param_key == "z_m":
                physics.z_m = np.clip(physics.z_m + direction * step, min_val, max_val)
                changed = True
            elif param_key == "R_m":
                physics.R_m = np.clip(physics.R_m + direction * step, min_val, max_val)
                changed = True
        elif item_type == "cycle":
            if param_key == "mirror_mode":
                idx = MIRROR_MODES.index(physics.mirror_mode)
                physics.mirror_mode = MIRROR_MODES[(idx + direction) % len(MIRROR_MODES)]
                changed = True
            elif param_key == "qp_mode":
                idx = QP_MODES.index(physics.qp_mode)
                physics.qp_mode = QP_MODES[(idx + direction) % len(QP_MODES)]
                changed = True
        elif item_type == "fidelity":
            physics.fidelity_idx = (physics.fidelity_idx + direction) % len(FIDELITY_LEVELS)
            new_res = FIDELITY_LEVELS[physics.fidelity_idx][1]
            physics.set_resolution(new_res)
            changed = True
        elif item_type == "cycle_idx":
            if param_key == "roughness_idx":
                physics.roughness_idx = (physics.roughness_idx + direction) % len(ROUGHNESS_OPTIONS)
                changed = True
        elif item_type == "toggle":
            if param_key == "show_beam_markers":
                physics.show_beam_markers = not physics.show_beam_markers
                changed = True
        
        if changed:
            self.adj_cooldown = 5
        return changed
                
    def get_value_str(self, physics, idx):
        """Get string representation of a parameter value"""
        item = self.items[idx]
        param_key = item[1]
        
        if param_key == "mirror_mode":
            return physics.mirror_mode.capitalize()
        elif param_key == "qp_mode":
            return physics.qp_mode.capitalize()
        elif param_key == "roughness_idx":
            return ROUGHNESS_LABELS[physics.roughness_idx]
        elif param_key == "z_m":
            return f"{physics.z_m:.2f}"
        elif param_key == "R_m":
            return f"{physics.R_m:.1f}"
        elif param_key == "corr_len_um":
            return f"{int(physics.corr_len * 1e6)}"
        elif param_key == "fidelity":
            return FIDELITY_LEVELS[physics.fidelity_idx][0]
        elif param_key == "show_beam_markers":
            return "On" if physics.show_beam_markers else "Off"
        return "?"


# -----------------------------
# Display Renderer
# -----------------------------
class DisplayRenderer:
    """Renders simulation to PIL Image for hardware display"""
    
    def __init__(self, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, sim_size=SIM_SIZE):
        self.width = width
        self.height = height
        self.sim_size = sim_size
        self.menu_width = width - sim_size
        
        # Spinner animation state
        self.spinner_chars = ['|', '/', '-', '\\']
        
        try:
            self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
            self.font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 8)
        except:
            self.font = ImageFont.load_default()
            self.font_small = self.font
            
    def array_to_image(self, data, colormap, target_size, matrix_mode=False):
        """Convert numpy array to PIL Image using colormap - OPTIMIZED"""
        # Resize if needed
        if data.shape[0] != target_size or data.shape[1] != target_size:
            scale_y = data.shape[0] / target_size
            scale_x = data.shape[1] / target_size
            indices_y = (np.arange(target_size) * scale_y).astype(int)
            indices_x = (np.arange(target_size) * scale_x).astype(int)
            indices_y = np.clip(indices_y, 0, data.shape[0]-1)
            indices_x = np.clip(indices_x, 0, data.shape[1]-1)
            data = data[np.ix_(indices_y, indices_x)]
        
        # Normalize and convert to indices
        data = np.clip(data, 0, 1)
        indices = (data * 255).astype(np.uint8)
        
        # Apply colormap using vectorized numpy indexing (FAST)
        rgb = colormap[indices]
        
        # Handle orientation
        if not matrix_mode:
            rgb = np.flip(rgb, axis=0)
            
        return Image.fromarray(rgb, mode='RGB')
        
    def render(self, physics, view_idx, menu, input_state=None, is_processing=False):
        """Render full display as PIL Image
        
        Args:
            input_state: dict with 'left_active', 'right_active' booleans
            is_processing: True if physics is being computed (show spinner)
        """
        # Create base image
        img = Image.new('RGB', (self.width, self.height), (20, 20, 30))
        draw = ImageDraw.Draw(img)
        
        # Get view data
        data = physics.get_view_data(view_idx)
        
        # Select colormap
        if view_idx == 2:  # Interference
            cmap = CMAP_INFERNO
        elif view_idx == 3:  # Phase
            cmap = CMAP_TWILIGHT
        elif view_idx == 4:  # Amplitude
            cmap = CMAP_HOT
        else:
            cmap = CMAP_VIRIDIS
            
        # Render simulation
        is_matrix = (view_idx == 5)
        sim_img = self.array_to_image(data, cmap, self.sim_size, matrix_mode=is_matrix)
        img.paste(sim_img, (0, 0))
        
        # Draw beam markers if enabled
        if physics.show_beam_markers and view_idx != 5:
            (inc_x, inc_y), (ref_x, ref_y) = physics.get_beam_positions_normalized()
            
            inc_px = int(inc_x * self.sim_size)
            inc_py = int((1 - inc_y) * self.sim_size)
            ref_px = int(ref_x * self.sim_size)
            ref_py = int((1 - ref_y) * self.sim_size)
            
            # Incident beam (red)
            r = 4
            draw.ellipse([inc_px-r, inc_py-r, inc_px+r, inc_py+r], outline=(255, 0, 0), width=2)
            # Reflected beam (cyan)
            draw.ellipse([ref_px-r, ref_py-r, ref_px+r, ref_py+r], outline=(0, 255, 255), width=2)
        
        # Draw view name
        draw.text((5, self.height - 15), VIEW_NAMES[view_idx], fill=(200, 200, 200), font=self.font_small)
        
        # Draw sidebar
        self._render_sidebar(draw, menu, physics, input_state, is_processing)
        
        return img
        
    def _render_sidebar(self, draw, menu, physics, input_state=None, is_processing=False):
        """Render right sidebar menu"""
        x_start = self.sim_size
        
        # Background
        draw.rectangle([x_start, 0, self.width, self.height], fill=(30, 30, 40))
        
        # Menu items
        y = 5
        line_height = 28
        
        for idx, item in enumerate(menu.items):
            name = item[0]
            value = menu.get_value_str(physics, idx)
            
            # Highlight selected item when menu is active
            if menu.visible and idx == menu.selected_idx:
                draw.rectangle([x_start+2, y-2, self.width-2, y+line_height-4], 
                             fill=(60, 60, 100))
            
            # Draw name and value
            text_color = (200, 200, 200) if not menu.visible else (255, 255, 255)
            draw.text((x_start + 4, y), name, fill=text_color, font=self.font_small)
            draw.text((x_start + 4, y + 12), value, fill=(150, 200, 255), font=self.font_small)
            
            y += line_height
            
        # Menu status indicator
        status = "MENU" if menu.visible else "view"
        draw.text((x_start + 4, self.height - 15), status, 
                 fill=(100, 255, 100) if menu.visible else (100, 100, 100), 
                 font=self.font_small)
        
        # Input indicator dots (bottom right corner)
        if input_state:
            dot_y = self.height - 10
            dot_r = 4
            
            # Left joystick indicator (L)
            left_x = self.width - 28
            left_color = (0, 255, 0) if input_state.get('left_active') else (60, 60, 60)
            draw.ellipse([left_x - dot_r, dot_y - dot_r, left_x + dot_r, dot_y + dot_r], 
                        fill=left_color)
            draw.text((left_x - 3, dot_y - 18), "L", fill=(150, 150, 150), font=self.font_small)
            
            # Right joystick indicator (R)
            right_x = self.width - 12
            right_color = (0, 255, 0) if input_state.get('right_active') else (60, 60, 60)
            draw.ellipse([right_x - dot_r, dot_y - dot_r, right_x + dot_r, dot_y + dot_r], 
                        fill=right_color)
            draw.text((right_x - 3, dot_y - 18), "R", fill=(150, 150, 150), font=self.font_small)
        
        # Processing spinner (shows activity)
        if is_processing:
            spinner_idx = int(time.time() * 8) % 4  # 8 Hz rotation
            spinner_char = self.spinner_chars[spinner_idx]
            draw.text((self.width - 15, 5), spinner_char, fill=(255, 200, 0), font=self.font)


# -----------------------------
# Display Driver Init
# -----------------------------
def init_display(spi, driver, rotation, baudrate, width, height, cs_pin, dc_pin, rst_pin):
    """Initialize hardware display"""
    def get_pin(name):
        return getattr(board, name)
    
    cs = digitalio.DigitalInOut(get_pin(cs_pin))
    dc = digitalio.DigitalInOut(get_pin(dc_pin))
    rst = digitalio.DigitalInOut(get_pin(rst_pin))
    
    if driver == "st7789":
        import adafruit_rgb_display.st7789 as st7789
        return st7789.ST7789(spi, cs=cs, dc=dc, rst=rst, baudrate=baudrate,
                            width=width, height=height, rotation=rotation)
    elif driver == "ili9341":
        import adafruit_rgb_display.ili9341 as ili9341
        return ili9341.ILI9341(spi, cs=cs, dc=dc, rst=rst, baudrate=baudrate,
                              width=width, height=height, rotation=rotation)
    else:
        raise ValueError(f"Unsupported driver: {driver}")


# -----------------------------
# Main
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Mirror Simulation for Raspberry Pi")
    parser.add_argument("--driver", choices=["st7789", "ili9341"], default="ili9341")
    parser.add_argument("--rotation", type=int, default=90, help="Display rotation (0, 90, 180, 270)")
    parser.add_argument("--width", type=int, default=240, help="Physical display width")
    parser.add_argument("--height", type=int, default=320, help="Physical display height")
    parser.add_argument("--baudrate", type=int, default=64000000)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--cs", type=str, default="CE1")
    parser.add_argument("--dc", type=str, default="D24")
    parser.add_argument("--rst", type=str, default="D25")
    parser.add_argument("--serial-port", type=str, default="/dev/ttyUSB0")
    args = parser.parse_args()
    
    # Calculate logical dimensions based on rotation
    if args.rotation % 180 == 90:
        logical_width = args.height
        logical_height = args.width
    else:
        logical_width = args.width
        logical_height = args.height
        
    print("Mirror Simulation - Raspberry Pi")
    print(f"Physical: {args.width}x{args.height}, Rotation: {args.rotation}")
    print(f"Logical: {logical_width}x{logical_height}")
    print("Controls:")
    print("  Left joystick: Move beam")
    print("  Left click: Cycle views")
    print("  Right joystick up/down: Navigate menu")
    print("  Right joystick left/right: Adjust value")
    print("  Right click: Toggle menu active")
    print("")
    
    # Initialize hardware
    display = None
    if HARDWARE_AVAILABLE:
        try:
            spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
            display = init_display(
                spi, args.driver, args.rotation, args.baudrate,
                args.width, args.height, args.cs, args.dc, args.rst
            )
            print(f"Display initialized: {args.driver}")
        except Exception as e:
            print(f"Display init failed: {e}")
            display = None
    
    # Initialize components
    serial_input = SerialInput(port=args.serial_port)
    # Use logical dimensions for renderer
    sim_size = min(logical_width, logical_height)
    # For 320x240, we want sim_size 240.
    # For 240x320, we want sim_size 240.
    
    physics = MirrorPhysics(resolution=64)  # Start with High fidelity
    renderer = DisplayRenderer(width=logical_width, height=logical_height, sim_size=sim_size)
    menu = MenuSystem()
    
    # State
    current_view = 2  # Start with Interference
    target_frame_time = 1.0 / args.fps
    left_hold_start = None  # Track when left button started being held
    
    # Optimization: Throttle Q_p updates (expensive O(n^4) operation)
    last_qp_update = 0
    QP_UPDATE_INTERVAL = 0.5  # Update Q_p matrix at most 2x per second
    
    # Initial compute
    physics.compute()
    
    print("Starting main loop...")
    print("Hold left joystick button 3 sec to reset all settings")
    
    while True:
        start_time = time.time()
        
        # 1. Read inputs
        serial_input.update()
        
        # 2. Update cooldowns
        menu.update_cooldowns()
        
        # 3. Process controls
        
        # Track left button hold for 3-second reset
        if serial_input.left_btn_state:  # Button currently pressed
            if left_hold_start is None:
                left_hold_start = time.time()
            else:
                hold_duration = time.time() - left_hold_start
                if hold_duration >= 3.0:
                    print("RESET: All settings restored to defaults")
                    physics.reset_to_defaults()
                    physics.compute()  # Recompute with new defaults
                    current_view = 2  # Reset to Interference view
                    menu.visible = False  # Close menu
                    left_hold_start = None  # Reset tracker
        else:
            left_hold_start = None
        
        # Left click: Cycle views (only on release, not during hold)
        if serial_input.left_click and (left_hold_start is None or time.time() - left_hold_start < 0.3):
            current_view = (current_view + 1) % len(VIEW_NAMES)
            print(f"View: {VIEW_NAMES[current_view]}")
            
        # Right click: Toggle menu
        if serial_input.right_click:
            menu.toggle()
            print(f"Menu: {'active' if menu.visible else 'inactive'}")
            
        # Left joystick: ALWAYS move beam
        beam_speed = 0.0002
        physics.beam_x += serial_input.left_joy[0] * beam_speed
        physics.beam_y -= serial_input.left_joy[1] * beam_speed
        physics.beam_x = np.clip(physics.beam_x, -L/2 + 0.001, L/2 - 0.001)
        physics.beam_y = np.clip(physics.beam_y, -L/2 + 0.001, L/2 - 0.001)
        
        # Right joystick: Menu nav/adjust (when active)
        if menu.visible:
            if serial_input.right_joy[1] < -0.5:
                menu.navigate(-1)
            elif serial_input.right_joy[1] > 0.5:
                menu.navigate(1)
                
            if serial_input.right_joy[0] < -0.5:
                menu.adjust(-1, physics)
            elif serial_input.right_joy[0] > 0.5:
                menu.adjust(1, physics)
        
        # 4. Build input state for visual feedback
        input_state = {
            'left_active': serial_input.left_btn_state or abs(serial_input.left_joy[0]) > 0.1 or abs(serial_input.left_joy[1]) > 0.1,
            'right_active': serial_input.right_btn_state or abs(serial_input.right_joy[0]) > 0.1 or abs(serial_input.right_joy[1]) > 0.1,
        }
        
        # 5. Update physics
        # Always compute base physics (fast)
        physics.compute(compute_qp=False)
        
        # Throttle Q_p updates: expensive O(n^4), limit to 2 FPS
        if current_view == 5:
            now = time.time()
            if now - last_qp_update > QP_UPDATE_INTERVAL:
                physics.compute(compute_qp=True)
                last_qp_update = now
        
        # 6. Render (show spinner only when user is providing input)
        has_input = input_state['left_active'] or input_state['right_active']
        frame = renderer.render(physics, current_view, menu, input_state=input_state, is_processing=has_input)
        
        # 6. Display
        if display:
            display.image(frame)
        
        # 7. Frame timing
        elapsed = time.time() - start_time
        sleep_time = max(0, target_frame_time - elapsed)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()

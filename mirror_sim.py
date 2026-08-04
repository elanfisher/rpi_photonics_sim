#!/usr/bin/env python3
"""
Mirror Simulation - Pi-Ready Interface

Gaussian Beam + Rough Mirror Interference Simulation with hardware-ready controls.
Designed to run in emulation mode (pygame) for development, then trivially port to Pi.

Controls:
- Left Joystick: Move beam X/Y position
- Left Joystick Click: Cycle through 6 views
- Right Joystick: Navigate menu (when open) / Adjust selected parameter
- Right Joystick Click: Select menu item
- Button: Open/close menu overlay

Views (cycle with left click):
0. Mirror Roughness
1. Total Mirror Surface  
2. Interference Pattern
3. Reflected Beam Phase
4. Beam Amplitude Profile
5. Q_p Correlation Matrix
"""

import numpy as np
import time
import pygame

# Import shared physics module
from mirror_physics import (
    compute_interference, compute_Qp_matrix, setup_grids,
    WAVELENGTH, K, W0, ZR, L,
    ROUGHNESS_OPTIONS, ROUGHNESS_LABELS, MIRROR_MODES, QP_MODES,
    DEFAULT_PARAMS
)

# -----------------------------
# Display Configuration
# -----------------------------
# Full 320x240 landscape (LCD on its side)
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
SIM_SIZE = 240  # Square simulation area (240x240)
MENU_WIDTH = 80  # Right sidebar (320 - 240 = 80)
EMULATION_SCALE = 2  # Scale factor for pygame window
FPS_TARGET = 30

# Resolution options (matching tft_emulator.py)
RESOLUTION_OPTIONS = [8, 16, 24, 64, 100, 240]

# Fidelity levels: (name, resolution, qp_grid_size)
FIDELITY_LEVELS = [
    ("Low", 8, 4),
    ("Med", 16, 6),
    ("High", 64, 12),
    ("Max", 240, 24),
]

# -----------------------------
# View Names
# -----------------------------
VIEW_NAMES = [
    "Roughness",
    "Surface",
    "Interference",
    "Phase",
    "Amplitude",
    "Q_p Matrix"
]


class MirrorPhysics:
    """Physics engine for mirror simulation - uses shared mirror_physics module"""
    
    def __init__(self, resolution=240):
        self.resolution = resolution
        self.N = resolution
        self._setup_grids()
        
        # State - initialize from DEFAULT_PARAMS
        self.beam_x = DEFAULT_PARAMS['beam_x']
        self.beam_y = DEFAULT_PARAMS['beam_y']
        self.z_m = DEFAULT_PARAMS['z_m']
        self.R_m = DEFAULT_PARAMS['R_m']
        self.roughness_idx = DEFAULT_PARAMS['roughness_idx']
        self.corr_len = DEFAULT_PARAMS['corr_len']
        self.mirror_mode = DEFAULT_PARAMS['mirror_mode']
        self.qp_mode = DEFAULT_PARAMS['qp_mode']
        
        # Display options
        self.show_beam_markers = True  # Enabled by default
        self.fidelity_idx = 2  # Default to "High"
        
        # Cached outputs
        self.rough = None
        self.h = None
        self.I = None
        self.A = None
        self.phi_ref = None
        self.Qp = None
        self.ref_x = 0.0
        self.ref_y = 0.0
        
    def _setup_grids(self):
        """Setup spatial grids using shared function"""
        self.x, self.y, self.X, self.Y, self.FX, self.FY, self.base_noise = setup_grids(self.N)
        
    def set_resolution(self, resolution):
        """Change simulation resolution"""
        if resolution != self.resolution:
            self.resolution = resolution
            self.N = resolution
            self._setup_grids()
            
    def get_sigma_h(self):
        """Get current roughness in meters"""
        return ROUGHNESS_OPTIONS[self.roughness_idx] * WAVELENGTH
    
    def compute(self, compute_qp=False):
        """Compute simulation outputs. Only compute Q_p if needed (slow)."""
        sigma_h = self.get_sigma_h()
        
        # Use shared compute_interference function
        self.rough, self.h, self.I, self.A, self.phi_ref, self.ref_x, self.ref_y = compute_interference(
            self.X, self.Y, self.FX, self.FY, self.base_noise,
            self.z_m, self.R_m, sigma_h, self.corr_len,
            self.beam_x, self.beam_y, self.mirror_mode
        )
        
        # Only compute Q_p matrix when viewing it (expensive O(n^4) operation)
        if compute_qp:
            qp_grid = FIDELITY_LEVELS[self.fidelity_idx][2]
            self.Qp = compute_Qp_matrix(
                self.N, self.corr_len, self.h, self.qp_mode, grid_size=qp_grid
            )
    
    def reset_to_defaults(self):
        """Reset all parameters to defaults"""
        self.beam_x = DEFAULT_PARAMS['beam_x']
        self.beam_y = DEFAULT_PARAMS['beam_y']
        self.z_m = DEFAULT_PARAMS['z_m']
        self.R_m = DEFAULT_PARAMS['R_m']
        self.roughness_idx = DEFAULT_PARAMS['roughness_idx']
        self.corr_len = DEFAULT_PARAMS['corr_len']
        self.mirror_mode = DEFAULT_PARAMS['mirror_mode']
        self.qp_mode = DEFAULT_PARAMS['qp_mode']
        self.fidelity_idx = 2  # High
        new_res = FIDELITY_LEVELS[self.fidelity_idx][1]
        if new_res != self.resolution:
            self.resolution = new_res
            self.N = new_res
            self._setup_grids()
        
    def get_view_data(self, view_idx):
        """Get normalized data for a specific view (0-1 range for display)"""
        if view_idx == 0:  # Roughness
            data = self.rough
        elif view_idx == 1:  # Surface
            data = self.h
        elif view_idx == 2:  # Interference
            return self.I  # Already 0-1
        elif view_idx == 3:  # Phase
            data = (self.phi_ref + np.pi) / (2 * np.pi)  # Map to 0-1
            return data
        elif view_idx == 4:  # Amplitude
            return self.A  # Already 0-1ish
        elif view_idx == 5:  # Q_p
            return self.Qp
        else:
            return np.zeros((self.N, self.N))
        
        # Normalize to 0-1
        if data.max() != data.min():
            return (data - data.min()) / (data.max() - data.min())
        return np.zeros_like(data)
    
    def get_beam_positions_normalized(self):
        """Get beam positions normalized to 0-1 for display"""
        inc_x = (self.beam_x / L + 0.5)
        inc_y = (self.beam_y / L + 0.5)
        ref_x = (self.ref_x / L + 0.5)
        ref_y = (self.ref_y / L + 0.5)
        return (inc_x, inc_y), (ref_x, ref_y)


class MenuSystem:
    """Sidebar menu system for parameter adjustment - always visible on right side"""
    
    def __init__(self):
        self.visible = False  # When True, menu is active for navigation/adjustment
        self.selected_idx = 0
        self.nav_cooldown = 0  # Prevent rapid navigation
        self.adj_cooldown = 0  # Prevent rapid adjustment
        
        # Menu items: (name, param_key, type, options_or_range)
        self.items = [
            ("Fidelity", "fidelity", "fidelity", FIDELITY_LEVELS),
            ("Mirror", "mirror_mode", "cycle", MIRROR_MODES),
            ("Q_p Mode", "qp_mode", "cycle", QP_MODES),
            ("Roughness", "roughness_idx", "cycle_idx", ROUGHNESS_LABELS),
            ("Z Pos", "z_m", "range", (0.05, 1.0, 0.05)),
            ("Mirror R", "R_m", "range", (0.1, 2.0, 0.1)),
            ("Corr Len", "corr_len_um", "range", (10, 500, 10)),
            ("Markers", "show_beam_markers", "toggle", None),
        ]
        
    def toggle(self):
        """Toggle menu active state"""
        self.visible = not self.visible
        
    def navigate(self, direction):
        """Navigate menu (direction: -1 up, +1 down)"""
        if not self.visible:
            return
        if self.nav_cooldown > 0:
            self.nav_cooldown -= 1
            return
        self.selected_idx = (self.selected_idx + direction) % len(self.items)
        self.nav_cooldown = 8  # Frames to wait before next nav
        
    def update_cooldowns(self):
        """Decrement cooldowns each frame"""
        if self.nav_cooldown > 0:
            self.nav_cooldown -= 1
        if self.adj_cooldown > 0:
            self.adj_cooldown -= 1
        
    def adjust(self, direction, physics):
        """Adjust current value live (direction: -1 decrease, +1 increase)"""
        if not self.visible:
            return False
        if self.adj_cooldown > 0:
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
            options = item[3]
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
            self.adj_cooldown = 5  # Frames to wait before next adjust
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
            return f"{physics.z_m:.2f} m"
        elif param_key == "R_m":
            return f"{physics.R_m:.2f} m"
        elif param_key == "corr_len_um":
            return f"{physics.corr_len*1e6:.0f} µm"
        elif param_key == "fidelity":
            return FIDELITY_LEVELS[physics.fidelity_idx][0]
        elif param_key == "show_beam_markers":
            return "ON" if physics.show_beam_markers else "OFF"
        return "?"


class SimulationDisplay:
    """Pygame-based display for emulation - 320x240 landscape with right sidebar"""
    
    def __init__(self, width=320, height=240, sim_size=240, scale=2):
        pygame.init()
        self.width = width
        self.height = height
        self.sim_size = sim_size
        self.menu_width = width - sim_size  # Right sidebar
        self.scale = scale
        self.screen = pygame.display.set_mode((width * scale, height * scale))
        pygame.display.set_caption("Mirror Simulation")
        
        # Fonts
        self.font_small = pygame.font.Font(None, 18 * scale // 2 + 8)
        self.font_medium = pygame.font.Font(None, 22 * scale // 2 + 10)
        self.font_tiny = pygame.font.Font(None, 14 * scale // 2 + 6)
        
        # Colormaps (simple implementations)
        self.cmap_viridis = self._generate_colormap("viridis")
        self.cmap_inferno = self._generate_colormap("inferno")
        self.cmap_twilight = self._generate_colormap("twilight")
        self.cmap_hot = self._generate_colormap("hot")
        
    def _generate_colormap(self, name):
        """Generate a 256-color lookup table"""
        colors = np.zeros((256, 3), dtype=np.uint8)
        
        if name == "viridis":
            for i in range(256):
                t = i / 255
                colors[i] = [int(68 + t*120), int(1 + t*180), int(84 + t*100)]
        elif name == "inferno":
            # Proper inferno: black → purple → red → orange → yellow (no blue)
            for i in range(256):
                t = i / 255
                if t < 0.25:
                    # Black to dark purple
                    r = int(t * 4 * 80)
                    g = int(t * 4 * 10)
                    b = int(t * 4 * 60)
                elif t < 0.5:
                    # Dark purple to red
                    t2 = (t - 0.25) * 4
                    r = int(80 + t2 * 175)
                    g = int(10 + t2 * 30)
                    b = int(60 - t2 * 60)
                elif t < 0.75:
                    # Red to orange
                    t2 = (t - 0.5) * 4
                    r = 255
                    g = int(40 + t2 * 140)
                    b = 0
                else:
                    # Orange to yellow
                    t2 = (t - 0.75) * 4
                    r = 255
                    g = int(180 + t2 * 75)
                    b = int(t2 * 120)
                colors[i] = [min(255, r), min(255, g), min(255, b)]
        elif name == "twilight":
            for i in range(256):
                t = i / 255
                # Circular colormap
                angle = t * 2 * np.pi
                colors[i] = [
                    int(127 + 127 * np.sin(angle)),
                    int(127 + 127 * np.sin(angle + 2*np.pi/3)),
                    int(127 + 127 * np.sin(angle + 4*np.pi/3))
                ]
        elif name == "hot":
            for i in range(256):
                t = i / 255
                r = int(min(255, max(0, t * 3 * 255)))
                g = int(min(255, max(0, (t - 0.33) * 3 * 255)))
                b = int(min(255, max(0, (t - 0.66) * 3 * 255)))
                colors[i] = [r, g, b]
        else:  # grayscale
            for i in range(256):
                colors[i] = [i, i, i]
                
        return colors
        
    def array_to_surface(self, data, colormap, target_size, matrix_mode=False):
        """Convert numpy array to pygame surface using colormap
        
        Args:
            matrix_mode: If True, display as matrix (0,0 at top-left, no flip)
                        If False, display as physics image (Y=0 at bottom)
        """
        # Resize to target size if needed
        if data.shape[0] != target_size or data.shape[1] != target_size:
            # Simple nearest-neighbor resize
            scale_y = data.shape[0] / target_size
            scale_x = data.shape[1] / target_size
            indices_y = (np.arange(target_size) * scale_y).astype(int)
            indices_x = (np.arange(target_size) * scale_x).astype(int)
            indices_y = np.clip(indices_y, 0, data.shape[0]-1)
            indices_x = np.clip(indices_x, 0, data.shape[1]-1)
            data = data[np.ix_(indices_y, indices_x)]
        
        # Normalize and convert to color indices
        data = np.clip(data, 0, 1)
        indices = (data * 255).astype(np.uint8)
        
        # Apply colormap
        rgb = colormap[indices]
        
        # Create surface - transpose for pygame coordinate system
        if matrix_mode:
            # Matrix display: 0,0 at top-left (standard matrix convention)
            surface = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
        else:
            # Physics display: Y=0 at bottom (flip vertically)
            rgb_flipped = np.flip(rgb, axis=0)
            surface = pygame.surfarray.make_surface(rgb_flipped.swapaxes(0, 1))
        return pygame.transform.scale(surface, (target_size * self.scale, target_size * self.scale))
        
    def render(self, physics, view_idx, menu):
        """Render the current view with right sidebar menu"""
        # Clear screen
        self.screen.fill((20, 20, 30))
        
        # Get view data
        data = physics.get_view_data(view_idx)
        
        # Select colormap based on view
        if view_idx == 2:  # Interference
            cmap = self.cmap_inferno
        elif view_idx == 3:  # Phase
            cmap = self.cmap_twilight
        elif view_idx == 4:  # Amplitude
            cmap = self.cmap_hot
        else:
            cmap = self.cmap_viridis
            
        # Render main simulation image (left side, square)
        # Use matrix_mode for Q_p matrix (view 5) so 0,0 is at top-left
        is_matrix = (view_idx == 5)
        surface = self.array_to_surface(data, cmap, self.sim_size, matrix_mode=is_matrix)
        self.screen.blit(surface, (0, 0))
        
        # Draw beam markers if enabled
        if physics.show_beam_markers and view_idx != 5:  # Not on Q_p matrix
            (inc_x, inc_y), (ref_x, ref_y) = physics.get_beam_positions_normalized()
            screen_size = self.sim_size * self.scale
            
            # Marker positions - X maps directly, Y is already flipped by array rendering
            inc_px = int(inc_x * screen_size)
            inc_py = int((1 - inc_y) * screen_size)  # Flip Y for screen coords
            ref_px = int(ref_x * screen_size)
            ref_py = int((1 - ref_y) * screen_size)
            
            # Incident beam (red)
            pygame.draw.circle(self.screen, (255, 50, 50), (inc_px, inc_py), 6 * self.scale // 2, 2)
            pygame.draw.circle(self.screen, (255, 255, 255), (inc_px, inc_py), 4 * self.scale // 2, 1)
            
            # Reflected beam (cyan)
            pygame.draw.circle(self.screen, (50, 255, 255), (ref_px, ref_py), 8 * self.scale // 2, 2)
            pygame.draw.circle(self.screen, (255, 255, 255), (ref_px, ref_py), 6 * self.scale // 2, 1)
        
        # Draw view name (top-left corner of sim area)
        view_text = self.font_medium.render(VIEW_NAMES[view_idx], True, (255, 255, 255))
        text_bg = pygame.Surface((view_text.get_width() + 6, view_text.get_height() + 2))
        text_bg.set_alpha(180)
        text_bg.fill((0, 0, 0))
        self.screen.blit(text_bg, (3, 3))
        self.screen.blit(view_text, (6, 4))
        
        # Always render right sidebar menu
        self._render_sidebar(menu, physics)
            
        pygame.display.flip()
        
    def _render_sidebar(self, menu, physics):
        """Render right sidebar with menu"""
        sidebar_x = self.sim_size * self.scale
        sidebar_w = self.menu_width * self.scale
        sidebar_h = self.height * self.scale
        
        # Sidebar background
        sidebar_bg = pygame.Surface((sidebar_w, sidebar_h))
        sidebar_bg.fill((25, 25, 40))
        self.screen.blit(sidebar_bg, (sidebar_x, 0))
        
        # Draw vertical separator line
        pygame.draw.line(self.screen, (60, 60, 80), 
                        (sidebar_x, 0), (sidebar_x, sidebar_h), 2)
        
        # Menu title
        if menu.visible:
            title_color = (100, 255, 100)
            title_text = "MENU"
        else:
            title_color = (150, 150, 150)
            title_text = "[SPACE]"
        title = self.font_medium.render(title_text, True, title_color)
        self.screen.blit(title, (sidebar_x + 8, 5))
        
        # Draw menu items
        y_pos = 30
        line_height = (sidebar_h - 35) // len(menu.items)
        
        for i, item in enumerate(menu.items):
            name = item[0]
            value = menu.get_value_str(physics, i)
            
            # Highlight selected when menu is active
            if menu.visible and i == menu.selected_idx:
                # Draw selection background
                sel_bg = pygame.Surface((sidebar_w - 4, line_height - 2))
                sel_bg.fill((50, 50, 80))
                self.screen.blit(sel_bg, (sidebar_x + 2, y_pos))
                name_color = (100, 255, 100)
                val_color = (255, 255, 100)
            else:
                name_color = (180, 180, 180)
                val_color = (220, 220, 220)
            
            # Render name (abbreviated to fit)
            short_name = name[:8] if len(name) > 8 else name
            name_surf = self.font_tiny.render(short_name, True, name_color)
            self.screen.blit(name_surf, (sidebar_x + 5, y_pos + 2))
            
            # Render value
            val_surf = self.font_tiny.render(str(value), True, val_color)
            self.screen.blit(val_surf, (sidebar_x + 5, y_pos + line_height // 2))
            
            y_pos += line_height


class InputHandler:
    """Handle keyboard input (emulating joysticks for development)"""
    
    def __init__(self):
        # Keyboard state
        self.keys_pressed = set()
        self.keys_just_pressed = set()
        
        # Joystick emulation state
        self.left_joy = [0.0, 0.0]
        self.right_joy = [0.0, 0.0]
        self.left_click = False
        self.right_click = False
        self.button = False
        
    def update(self):
        """Update input state from pygame events"""
        self.keys_just_pressed.clear()
        self.left_click = False
        self.right_click = False
        self.button = False
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                self.keys_pressed.add(event.key)
                self.keys_just_pressed.add(event.key)
            elif event.type == pygame.KEYUP:
                self.keys_pressed.discard(event.key)
                
        # Left joystick: WASD
        self.left_joy = [0.0, 0.0]
        if pygame.K_a in self.keys_pressed:
            self.left_joy[0] = -1.0
        if pygame.K_d in self.keys_pressed:
            self.left_joy[0] = 1.0
        if pygame.K_w in self.keys_pressed:
            self.left_joy[1] = -1.0
        if pygame.K_s in self.keys_pressed:
            self.left_joy[1] = 1.0
            
        # Right joystick: Arrow keys
        self.right_joy = [0.0, 0.0]
        if pygame.K_LEFT in self.keys_pressed:
            self.right_joy[0] = -1.0
        if pygame.K_RIGHT in self.keys_pressed:
            self.right_joy[0] = 1.0
        if pygame.K_UP in self.keys_pressed:
            self.right_joy[1] = -1.0
        if pygame.K_DOWN in self.keys_pressed:
            self.right_joy[1] = 1.0
            
        # Left click: Q
        if pygame.K_q in self.keys_just_pressed:
            self.left_click = True
            
        # Right click: E  
        if pygame.K_e in self.keys_just_pressed:
            self.right_click = True
            
        # Button: SPACE
        if pygame.K_SPACE in self.keys_just_pressed:
            self.button = True
            
        return True


def main():
    """Main simulation loop"""
    print("Mirror Simulation - Emulation Mode (320x240 landscape)")
    print("Controls:")
    print("  WASD: Move beam (always active)")
    print("  Q: Cycle views")
    print("  SPACE: Toggle menu active")
    print("  Arrow Up/Down: Navigate menu (when active)")
    print("  Arrow Left/Right: Adjust selected value (when active)")
    print("  Hold Q for 3 seconds: Reset all settings to defaults")
    print("")
    
    # Initialize components
    physics = MirrorPhysics(resolution=64)  # Start with High fidelity
    display = SimulationDisplay(
        width=DISPLAY_WIDTH, 
        height=DISPLAY_HEIGHT, 
        sim_size=SIM_SIZE, 
        scale=EMULATION_SCALE
    )
    menu = MenuSystem()
    inputs = InputHandler()
    
    # State - start with Interference view (index 2)
    current_view = 2
    left_hold_start = None  # Track when Q key started being held
    
    # Initial compute
    physics.compute()
    
    while True:
        start_time = time.time()
        
        # 1. Handle input
        if not inputs.update():
            break
            
        # 2. Update cooldowns
        menu.update_cooldowns()
            
        # 3. Process controls
        
        # Button (SPACE): Toggle menu active state
        if inputs.button:
            menu.toggle()
        
        # Track Q key hold for 3-second reset
        if pygame.K_q in inputs.keys_pressed:
            if left_hold_start is None:
                left_hold_start = time.time()
            elif time.time() - left_hold_start >= 3.0:
                print("RESET: All settings restored to defaults")
                physics.reset_to_defaults()
                left_hold_start = None
        else:
            left_hold_start = None
            
        # Left click (Q): Cycle views (only on press, not during hold)
        if inputs.left_click and (left_hold_start is None or time.time() - left_hold_start < 0.3):
            current_view = (current_view + 1) % len(VIEW_NAMES)
            
        # Left joystick (WASD): ALWAYS move beam
        beam_speed = 0.0002  # meters per frame
        physics.beam_x += inputs.left_joy[0] * beam_speed
        physics.beam_y -= inputs.left_joy[1] * beam_speed  # Invert Y for intuitive control
        physics.beam_x = np.clip(physics.beam_x, -L/2 + 0.001, L/2 - 0.001)
        physics.beam_y = np.clip(physics.beam_y, -L/2 + 0.001, L/2 - 0.001)
            
        # Right joystick: Menu navigation and adjustment (when menu active)
        if menu.visible:
            # Up/Down: Navigate menu items
            if inputs.right_joy[1] < -0.5:  # Up
                menu.navigate(-1)
            elif inputs.right_joy[1] > 0.5:  # Down
                menu.navigate(1)
                
            # Left/Right: Adjust current value directly
            if inputs.right_joy[0] < -0.5:
                menu.adjust(-1, physics)
            elif inputs.right_joy[0] > 0.5:
                menu.adjust(1, physics)
                        
        # 4. Update physics (only compute Q_p when viewing it - view 5)
        physics.compute(compute_qp=(current_view == 5))
        
        # 5. Render
        display.render(physics, current_view, menu)
        
        # 6. Cap framerate
        elapsed = time.time() - start_time
        sleep_time = max(0, 1.0/FPS_TARGET - elapsed)
        time.sleep(sleep_time)
        
    pygame.quit()
    print("Simulation ended.")


if __name__ == "__main__":
    main()

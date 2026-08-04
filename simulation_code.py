#!/usr/bin/env python3
import time
import sys
import math
import numpy as np
from scipy.signal import fftconvolve

# --- CONFIGURATION ---
MATRIX_WIDTH = 32
MATRIX_HEIGHT = 32
FPS_TARGET = 30

# --- HARDWARE DETECTION ---
EMULATION_MODE = False
try:
    # Try to import the RGB Matrix library (requires root/hardware)
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    print("Hardware: LED Matrix detected.")
except ImportError:
    # Fallback to Pygame for Emulation
    print("Hardware: LED Matrix NOT detected. Switching to Emulation Mode.")
    EMULATION_MODE = True
    import pygame
    # Pygame Config
    SCALE = 15  # Scale 32x32 up to 480x480 on screen
    pygame.init()
    screen = pygame.display.set_mode((MATRIX_WIDTH * SCALE, MATRIX_HEIGHT * SCALE))
    pygame.display.set_caption("Partial Coherence Emulator")

# Try to import GPIO Zero for ADC (MCP3008)
try:
    from gpiozero import MCP3008
    HAS_SENSORS = True
    print("Hardware: Sensors (MCP3008) detected.")
except ImportError:
    HAS_SENSORS = False
    print("Hardware: GPIO Zero not found. Using Mock Inputs.")


# --- PHYSICS ENGINE ---
class CoherencePhysics:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.noiseA = np.random.uniform(-np.pi, np.pi, (height, width))
        self.noiseB = np.random.uniform(-np.pi, np.pi, (height, width))
        self.time_t = 0.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        
    def generate_kernel(self, rho, mode='gaussian'):
        # Create a kernel grid
        k_rad = 16
        k_size = k_rad * 2 + 1
        y, x = np.mgrid[-k_rad:k_rad+1, -k_rad:k_rad+1]
        r = np.sqrt(x**2 + y**2)
        
        if mode == 'gaussian':
            kernel = np.exp(-(r**2) / (rho**2))
        else: # Rational
            kernel = 1.0 / (1.0 + np.power(r / rho, 1.5))
            
        return kernel / np.sum(kernel)

    def update(self, speed, dx, dy, rho, mode):
        # 1. Scroll Noise (Flow Control)
        # We use rolling to simulate movement
        if abs(dx) > 0.1 or abs(dy) > 0.1:
            shift_x = int(dx * 2) # Speed multiplier
            shift_y = int(dy * 2)
            self.noiseA = np.roll(self.noiseA, shift_x, axis=1)
            self.noiseA = np.roll(self.noiseA, shift_y, axis=0)
            self.noiseB = np.roll(self.noiseB, shift_x, axis=1)
            self.noiseB = np.roll(self.noiseB, shift_y, axis=0)
            # In a real infinite scroller, we'd inject new noise at edges
            # For this simple ver, wrapping (roll) looks okay like a lava lamp

        # 2. Temporal Evolution
        self.time_t += speed * 0.1
        if self.time_t >= 1.0:
            self.time_t = 0
            self.noiseA = self.noiseB
            self.noiseB = np.random.uniform(-np.pi, np.pi, (self.height, self.width))
            
        # 3. Interpolate Noise
        mixed_noise = self.noiseA * (1 - self.time_t) + self.noiseB * self.time_t
        
        # 4. Convolution (The Coherence)
        kernel = self.generate_kernel(rho, mode)
        
        # We use cosine/sine components to handle phase wrapping correctly
        real_part = np.cos(mixed_noise)
        imag_part = np.sin(mixed_noise)
        
        conv_real = fftconvolve(real_part, kernel, mode='same')
        conv_imag = fftconvolve(imag_part, kernel, mode='same')
        
        # 5. Extract Final Phase
        phase_screen = np.arctan2(conv_imag, conv_real)
        return phase_screen

# --- MAIN LOOP ---
def main():
    # Setup Inputs
    if HAS_SENSORS:
        # Check Wiring! CH0=Rho, CH1=Speed, CH2=JoyX, CH3=JoyY
        pot_rho = MCP3008(channel=0)
        pot_speed = MCP3008(channel=1)
        joy_x = MCP3008(channel=2)
        joy_y = MCP3008(channel=3)
    
    # Setup Display
    matrix = None
    offscreen_canvas = None
    if not EMULATION_MODE:
        options = RGBMatrixOptions()
        options.rows = MATRIX_HEIGHT
        options.cols = MATRIX_WIDTH
        options.chain_length = 1
        options.parallel = 1
        options.hardware_mapping = 'adafruit-hat'
        matrix = RGBMatrix(options = options)
        offscreen_canvas = matrix.CreateFrameCanvas()

    physics = CoherencePhysics(MATRIX_WIDTH, MATRIX_HEIGHT)
    
    running = True
    while running:
        start_time = time.time()
        
        # 1. Read Inputs
        rho = 2.0 # Default
        speed = 0.2
        dx = 0
        dy = 0
        mode = 'gaussian'
        
        if HAS_SENSORS:
            # Map Pot 0.0-1.0 to Rho 1.0-8.0
            rho = 1.0 + (pot_rho.value * 7.0)
            # Map Pot to Speed
            speed = pot_speed.value
            # Map Joystick 0.0-1.0 to -1.0 to 1.0
            dx = (joy_x.value - 0.5) * 2.0
            dy = (joy_y.value - 0.5) * 2.0
        elif EMULATION_MODE:
            # Mouse/Keyboard fallback for testing without sensors
            m_x, m_y = pygame.mouse.get_pos()
            rho = 1.0 + (m_x / (MATRIX_WIDTH * 15)) * 7.0
            
            keys = pygame.key.get_pressed()
            if keys[pygame.K_LEFT]: dx = -1
            if keys[pygame.K_RIGHT]: dx = 1
            if keys[pygame.K_UP]: dy = -1
            if keys[pygame.K_DOWN]: dy = 1

        # 2. Run Physics
        phase_map = physics.update(speed, dx, dy, rho, mode)
        
        # 3. Render
        if EMULATION_MODE:
            # Handle Pygame Events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
            
            # Draw to Screen
            for y in range(MATRIX_HEIGHT):
                for x in range(MATRIX_WIDTH):
                    # Map Phase (-PI to PI) to Hue (0-1) -> RGB
                    val = phase_map[y, x]
                    hue = (val + np.pi) / (2 * np.pi)
                    
                    # Simple HSV to RGB (Hue only)
                    # Use pygame's color conversion
                    color = pygame.Color(0)
                    color.hsva = ((hue * 360) % 360, 100, 100, 100)
                    
                    pygame.draw.rect(screen, color, 
                                   (x * SCALE, y * SCALE, SCALE, SCALE))
            pygame.display.flip()
            
        else:
            # Draw to LED Matrix
            for y in range(MATRIX_HEIGHT):
                for x in range(MATRIX_WIDTH):
                    val = phase_map[y, x]
                    hue = (val + np.pi) / (2 * np.pi)
                    # Convert to RGB (manual approximate for speed or use library)
                    # Here is a quick rainbow map
                    r, g, b = 0, 0, 0
                    h = hue * 6
                    x_c = (1 - abs(h % 2 - 1))
                    if 0 <= h < 1: r, g, b = 1, x_c, 0
                    elif 1 <= h < 2: r, g, b = x_c, 1, 0
                    elif 2 <= h < 3: r, g, b = 0, 1, x_c
                    elif 3 <= h < 4: r, g, b = 0, x_c, 1
                    elif 4 <= h < 5: r, g, b = x_c, 0, 1
                    elif 5 <= h < 6: r, g, b = 1, 0, x_c
                    
                    offscreen_canvas.SetPixel(x, y, int(r*255), int(g*255), int(b*255))
            
            offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

        # Cap FPS
        time.sleep(max(0, 1.0/FPS_TARGET - (time.time() - start_time)))

if __name__ == "__main__":
    main()
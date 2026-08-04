#!/usr/bin/env python3
"""
Gaussian Beam + Rough Mirror Interference Simulation

This is a physically accurate model that shows:
1. A Gaussian laser beam incident on a curved mirror with surface roughness
2. The reflected beam interfering with the incident beam
3. The resulting intensity pattern (what a camera would see)

Physics model:
- Incident beam: Gaussian amplitude with quadratic phase (spherical wavefront)
- Mirror: Quadratic curvature (focusing) + correlated random roughness
- Reflected beam: Phase shifted by 2*k*h where h is mirror height
- Interference: |E_inc + E_ref|^2

Interactive controls:
- Beam X/Y: Move the Gaussian beam across the mirror surface (like joystick)
- Mirror Mode: Toggle between Quadratic only, Rough only, or Both
- Z position: Distance from beam waist
- Mirror R: Radius of curvature
- Roughness: RMS surface roughness
- Corr. length: Roughness correlation length (paper's ρ₀)
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, RadioButtons

# -----------------------------
# Physical parameters (fixed)
# -----------------------------
wavelength = 1.0e-6  # 1 micron (IR laser)
k = 2 * np.pi / wavelength  # wavenumber

w0 = 1.0e-3  # beam waist: 1 mm
zR = np.pi * w0**2 / wavelength  # Rayleigh range

# -----------------------------
# Spatial grid
# -----------------------------
N = 400  # grid points
L = 6e-3  # 6 mm field of view
dx = L / N

x = np.linspace(-L/2, L/2, N)
y = np.linspace(-L/2, L/2, N)
X, Y = np.meshgrid(x, y)

# Frequency grid for roughness generation
fx = np.fft.fftfreq(N, dx)
fy = np.fft.fftfreq(N, dx)
FX, FY = np.meshgrid(fx, fy)

# Pre-generate roughness (fixed pattern, beam moves over it)
np.random.seed(42)
base_noise = np.random.randn(N, N)


def compute_interference(z_m, R_m, sigma_h, corr_len, beam_x, beam_y, mirror_mode='both'):
    """
    Compute the interference pattern for given parameters.
    
    Args:
        z_m: Distance from beam waist to mirror (meters)
        R_m: Mirror radius of curvature (meters), inf = flat
        sigma_h: RMS surface roughness height (meters)
        corr_len: Roughness correlation length (meters)
        beam_x: Beam center X offset (meters, from -L/2 to L/2)
        beam_y: Beam center Y offset (meters, from -L/2 to L/2)
        mirror_mode: 'quadratic', 'rough', or 'both'
    
    Returns:
        rough: Mirror roughness map
        h: Total mirror surface height
        I: Interference intensity pattern
    """
    # Beam parameters at mirror location
    Rz = z_m * (1 + (zR / z_m)**2) if z_m != 0 else np.inf
    gouy = np.arctan(z_m / zR) if z_m != 0 else 0
    wz = w0 * np.sqrt(1 + (z_m / zR)**2) if z_m != 0 else w0
    
    # Shifted coordinates for beam position
    X_shifted = X - beam_x
    Y_shifted = Y - beam_y
    
    # Gaussian amplitude envelope (centered at beam_x, beam_y)
    A = np.exp(-(X_shifted**2 + Y_shifted**2) / wz**2)
    
    # Incident beam phase (spherical wavefront + Gouy phase)
    if np.isfinite(Rz):
        phi_inc = (k / (2 * Rz)) * (X_shifted**2 + Y_shifted**2) - gouy
    else:
        phi_inc = -gouy * np.ones_like(X)
    
    # Mirror quadratic surface (focusing curvature) - fixed at center
    if np.isfinite(R_m) and R_m != 0:
        h_quad = (X**2 + Y**2) / (2 * R_m)
    else:
        h_quad = np.zeros_like(X)
    
    # Bump mirror: flat top/bottom, quadratic stripe in middle (horizontal bump)
    # Creates a cylindrical lens-like bump running left-to-right
    bump_width = L / 4  # Width of the curved region
    bump_mask = np.abs(Y) < bump_width  # Middle stripe where Y is near zero
    h_bump = np.zeros_like(X)
    h_bump[bump_mask] = (X[bump_mask]**2) / (2 * R_m) if np.isfinite(R_m) and R_m != 0 else 0
    
    # Generate correlated roughness via FFT filtering (fixed pattern)
    H = np.exp(-(FX**2 + FY**2) * (2 * np.pi * corr_len)**2)
    rough = np.fft.ifft2(np.fft.fft2(base_noise) * H).real
    
    # Normalize to desired RMS roughness
    if np.std(rough) > 0:
        rough *= sigma_h / np.std(rough)
    
    # Total mirror surface based on mode
    if mirror_mode == 'quadratic':
        h = h_quad
        rough_display = np.zeros_like(rough)
    elif mirror_mode == 'rough':
        h = rough
        rough_display = rough
    elif mirror_mode == 'bump':
        h = h_bump
        rough_display = np.zeros_like(rough)
    else:  # 'both'
        h = h_quad + rough
        rough_display = rough
    
    # Incident and reflected fields
    E_inc = A * np.exp(1j * phi_inc)
    E_ref = A * np.exp(-1j * phi_inc) * np.exp(1j * 2 * k * h)
    
    # Reflected beam phase (the key insight - shows mirror surface effect on beam)
    phi_ref = np.angle(E_ref)
    
    # Interference intensity
    E_tot = E_inc + E_ref
    I = np.abs(E_tot)**2
    I /= I.max() if I.max() > 0 else 1
    
    # Calculate reflected beam center position (geometric optics)
    # For curved mirror, beam gets angular deflection from surface slope
    # Slope at beam center: dh/dx = beam_x/R_m, dh/dy = beam_y/R_m
    # After propagating back distance z_m, displacement = 2 * z_m * slope
    if mirror_mode != 'rough' and np.isfinite(R_m) and R_m != 0:
        # Reflected beam shifts due to mirror curvature
        ref_x = beam_x * (1 - 2 * z_m / R_m)
        ref_y = beam_y * (1 - 2 * z_m / R_m)
    else:
        # Flat or rough-only mirror: reflected beam returns to same position
        ref_x = beam_x
        ref_y = beam_y
    
    return rough_display, h, I, A, phi_ref, ref_x, ref_y


# Initial parameter values
init_z_m = 0.2        # 20 cm from waist
init_R_m = 0.3        # 30 cm radius of curvature
init_sigma_h_lambda = 1/32  # Roughness as fraction of λ (e.g., λ/32)
init_sigma_h = init_sigma_h_lambda * wavelength  # Convert to meters
init_corr_len = 100e-6  # 100 micron correlation length
init_beam_x = 0.0     # Beam at center
init_beam_y = 0.0     # Beam at center
current_mode = 'both'

# Compute initial state
rough, h, I, A, phi_ref, ref_x, ref_y = compute_interference(init_z_m, init_R_m, init_sigma_h, init_corr_len, 
                                                              init_beam_x, init_beam_y, current_mode)


def compute_Qp_matrix(corr_len, mirror_mode, R_m, h_surface=None, qp_mode='statistical', grid_size=12):
    """
    Compute the Q_p correlation matrix.
    
    qp_mode='statistical': Gaussian spatial correlation Q(r1, r2) = exp(-|r1 - r2|² / ρ₀²)
                           This is the theoretical prediction for correlation decay with distance.
    
    qp_mode='empirical': Phase correlation from actual mirror surface cos(φ_i - φ_j)
                         This samples the real surface and computes actual phase coherence.
                         As roughness → 0, this → all 1s (perfect correlation).
                         With proper correlated roughness, this should statistically match statistical mode.
    """
    # Create a small spatial grid scaled appropriately for the correlation length
    # This ensures the checkerboard pattern is visible
    L_small = L * (grid_size / N)  # Scale to same physical size ratio
    coords = np.linspace(-L_small/2, L_small/2, grid_size)
    X_small, Y_small = np.meshgrid(coords, coords)
    
    # Flatten to 1D arrays of positions
    r1_x = X_small.flatten()
    r1_y = Y_small.flatten()
    n_pts = len(r1_x)
    
    # Build the correlation matrix Q(r1, r2)
    Qp = np.zeros((n_pts, n_pts))
    
    # For empirical mode, sample the actual mirror surface
    if qp_mode == 'empirical' and h_surface is not None:
        # Sample from a SMALL CENTRAL REGION of the surface matching L_small scale
        # The small grid coords range from -L_small/2 to +L_small/2
        # Map these to the central region of the full N×N surface
        phi_sample = np.zeros(n_pts)
        for idx in range(n_pts):
            # Convert small grid position to full surface index
            # r1_x ranges from -L_small/2 to +L_small/2
            # Map to full surface: position in full coords = r1_x (same physical position)
            # Full surface x ranges from -L/2 to +L/2, indices 0 to N-1
            full_ix = int((r1_x[idx] / L + 0.5) * N)
            full_iy = int((r1_y[idx] / L + 0.5) * N)
            full_ix = np.clip(full_ix, 0, N - 1)
            full_iy = np.clip(full_iy, 0, N - 1)
            # Phase from mirror height: φ = 2*k*h
            phi_sample[idx] = 2 * k * h_surface[full_iy, full_ix]
        
        # Empirical phase correlation: cos(φ_i - φ_j) mapped to [0, 1]
        for i in range(n_pts):
            for j in range(n_pts):
                phase_diff = phi_sample[i] - phi_sample[j]
                Qp[i, j] = (np.cos(phase_diff) + 1) / 2  # Map [-1,1] to [0,1]
        return Qp
    
    # Statistical mode: Pure Gaussian spatial correlation (no special cases)
    for i in range(n_pts):
        for j in range(n_pts):
            dist_sq = (r1_x[i] - r1_x[j])**2 + (r1_y[i] - r1_y[j])**2
            Qp[i, j] = np.exp(-dist_sq / corr_len**2)
    
    return Qp


# Q_p mode state
current_qp_mode = 'statistical'

# Compute initial Q_p matrix
Qp = compute_Qp_matrix(init_corr_len, current_mode, init_R_m, h, current_qp_mode)

# Create figure with 2x3 layout
fig, ax = plt.subplots(2, 3, figsize=(15, 9))
plt.subplots_adjust(bottom=0.28, right=0.88, hspace=0.3, wspace=0.3)

# Extent for proper axis labels (in mm)
extent_mm = [x[0]*1e3, x[-1]*1e3, y[0]*1e3, y[-1]*1e3]

# Row 1: Mirror properties and interference
# Plot roughness (in nm)
im0 = ax[0, 0].imshow(rough * 1e9, extent=extent_mm, cmap="viridis", origin='lower')
ax[0, 0].set_title("Mirror Roughness (nm)")
ax[0, 0].set_xlabel("x (mm)")
ax[0, 0].set_ylabel("y (mm)")
cb0 = plt.colorbar(im0, ax=ax[0, 0])
beam_marker0, = ax[0, 0].plot([init_beam_x*1e3], [init_beam_y*1e3], 'ro', markersize=8, label='Beam')

# Plot total surface (in µm)
im1 = ax[0, 1].imshow(h * 1e6, extent=extent_mm, cmap="viridis", origin='lower')
ax[0, 1].set_title("Total Mirror Surface (µm)")
ax[0, 1].set_xlabel("x (mm)")
ax[0, 1].set_ylabel("y (mm)")
cb1 = plt.colorbar(im1, ax=ax[0, 1])
beam_marker1, = ax[0, 1].plot([init_beam_x*1e3], [init_beam_y*1e3], 'ro', markersize=8)

# Plot interference pattern
im2 = ax[0, 2].imshow(I, extent=extent_mm, cmap="inferno", origin='lower')
ax[0, 2].set_title("Interference Pattern (Intensity)")
ax[0, 2].set_xlabel("x (mm)")
ax[0, 2].set_ylabel("y (mm)")
cb2 = plt.colorbar(im2, ax=ax[0, 2])
beam_marker2_inc, = ax[0, 2].plot([init_beam_x*1e3], [init_beam_y*1e3], 'ro', markersize=8, markeredgecolor='white', label='Incident')
beam_marker2_ref, = ax[0, 2].plot([ref_x*1e3], [ref_y*1e3], 'co', markersize=10, markeredgecolor='white', label='Reflected')
ax[0, 2].legend(loc='upper right', fontsize=8)

# Row 2: Beam analysis and correlation
# Plot reflected beam phase
im3 = ax[1, 0].imshow(phi_ref, extent=extent_mm, cmap="twilight", origin='lower', vmin=-np.pi, vmax=np.pi)
ax[1, 0].set_title("Reflected Beam Phase (rad)")
ax[1, 0].set_xlabel("x (mm)")
ax[1, 0].set_ylabel("y (mm)")
cb3 = plt.colorbar(im3, ax=ax[1, 0])
beam_marker3, = ax[1, 0].plot([init_beam_x*1e3], [init_beam_y*1e3], 'wo', markersize=8, markeredgecolor='black')

# Plot reflected beam amplitude (shows beam position clearly)
im4 = ax[1, 1].imshow(A, extent=extent_mm, cmap="hot", origin='lower')
ax[1, 1].set_title("Beam Amplitude Profile")
ax[1, 1].set_xlabel("x (mm)")
ax[1, 1].set_ylabel("y (mm)")
cb4 = plt.colorbar(im4, ax=ax[1, 1])
beam_marker4_inc, = ax[1, 1].plot([init_beam_x*1e3], [init_beam_y*1e3], 'ro', markersize=8, markeredgecolor='white')
beam_marker4_ref, = ax[1, 1].plot([ref_x*1e3], [ref_y*1e3], 'co', markersize=10, markeredgecolor='white')

# Plot Q_p correlation matrix (paper's Figure 3a)
im5 = ax[1, 2].imshow(Qp, cmap="viridis", origin='upper', vmin=0, vmax=1)
ax[1, 2].set_title(r"$\bar{Q}_p$ Gaussian Correlation Matrix")
ax[1, 2].set_xlabel(r"Running index for $\mathbf{r}_1$")
ax[1, 2].set_ylabel(r"Running index for $\mathbf{r}_2$")
cb5 = plt.colorbar(im5, ax=ax[1, 2], label="Degree of correlation")

# Sliders - rearranged for more controls
ax_beam_x = plt.axes([0.12, 0.20, 0.50, 0.02])
ax_beam_y = plt.axes([0.12, 0.17, 0.50, 0.02])
ax_z = plt.axes([0.12, 0.12, 0.50, 0.02])
ax_R = plt.axes([0.12, 0.09, 0.50, 0.02])
ax_sigma = plt.axes([0.12, 0.04, 0.50, 0.02])
ax_corr = plt.axes([0.12, 0.01, 0.50, 0.02])

slider_beam_x = Slider(ax_beam_x, 'Beam X (mm)', -2.5, 2.5, valinit=init_beam_x*1e3, valstep=0.1)
slider_beam_y = Slider(ax_beam_y, 'Beam Y (mm)', -2.5, 2.5, valinit=init_beam_y*1e3, valstep=0.1)
slider_z = Slider(ax_z, 'Z pos (m)', 0.05, 1.0, valinit=init_z_m, valstep=0.01)
slider_R = Slider(ax_R, 'Mirror R (m)', 0.1, 2.0, valinit=init_R_m, valstep=0.05)
# Roughness slider in λ fractions (0 to λ/2)
# Common values: λ/64, λ/32, λ/16, λ/8, λ/4, λ/2
roughness_fractions = [0, 1/64, 1/32, 1/16, 1/8, 1/4, 1/2]
slider_sigma = Slider(ax_sigma, r'Roughness (×λ)', 0, 0.5, valinit=init_sigma_h_lambda, valstep=1/64)
ax_sigma.set_xlabel(r'0=flat, λ/64, λ/32, λ/16, λ/8, λ/4, λ/2', fontsize=7)
slider_corr = Slider(ax_corr, 'Corr len (µm)', 10, 500, valinit=init_corr_len*1e6, valstep=10)

# Radio buttons for mirror mode
ax_radio = plt.axes([0.70, 0.12, 0.13, 0.16])
radio = RadioButtons(ax_radio, ('Both', 'Quadratic', 'Rough', 'Bump'), active=0)
ax_radio.set_title('Mirror Mode', fontsize=9)

# Radio buttons for Q_p mode
ax_radio_qp = plt.axes([0.84, 0.12, 0.13, 0.10])
radio_qp = RadioButtons(ax_radio_qp, ('Statistical', 'Empirical'), active=0)
ax_radio_qp.set_title('Q_p Mode', fontsize=9)

def update(val):
    global current_mode, current_qp_mode
    z_m = slider_z.val
    R_m = slider_R.val
    sigma_h = slider_sigma.val * wavelength  # Convert λ fraction to meters
    corr_len = slider_corr.val * 1e-6  # Convert µm to m
    beam_x = slider_beam_x.val * 1e-3  # Convert mm to m
    beam_y = slider_beam_y.val * 1e-3  # Convert mm to m
    
    rough, h, I, A, phi_ref, ref_x, ref_y = compute_interference(z_m, R_m, sigma_h, corr_len, beam_x, beam_y, current_mode)
    
    # Update Row 1 images
    im0.set_data(rough * 1e9)
    if rough.max() != rough.min():
        im0.set_clim(rough.min()*1e9, rough.max()*1e9)
    
    im1.set_data(h * 1e6)
    if h.max() != h.min():
        im1.set_clim(h.min()*1e6, h.max()*1e6)
    
    im2.set_data(I)
    im2.set_clim(0, 1)
    
    # Update Row 2 images
    im3.set_data(phi_ref)
    im4.set_data(A)
    
    # Update Q_p matrix (depends on corr_len, mode, R_m, and qp_mode)
    Qp_new = compute_Qp_matrix(corr_len, current_mode, R_m, h, current_qp_mode)
    im5.set_data(Qp_new)
    
    # Update Q_p title based on mode
    if current_qp_mode == 'empirical':
        ax[1, 2].set_title(r"$\bar{Q}_p$ Empirical Phase Correlation")
    else:
        ax[1, 2].set_title(r"$\bar{Q}_p$ Gaussian Correlation Matrix")
    
    # Update beam markers (red = incident, cyan = reflected)
    beam_marker0.set_data([beam_x*1e3], [beam_y*1e3])
    beam_marker1.set_data([beam_x*1e3], [beam_y*1e3])
    beam_marker2_inc.set_data([beam_x*1e3], [beam_y*1e3])
    beam_marker2_ref.set_data([ref_x*1e3], [ref_y*1e3])
    beam_marker3.set_data([beam_x*1e3], [beam_y*1e3])
    beam_marker4_inc.set_data([beam_x*1e3], [beam_y*1e3])
    beam_marker4_ref.set_data([ref_x*1e3], [ref_y*1e3])
    
    fig.canvas.draw_idle()

def mode_changed(label):
    global current_mode
    current_mode = label.lower()
    update(None)

def qp_mode_changed(label):
    global current_qp_mode
    current_qp_mode = label.lower()
    update(None)

slider_beam_x.on_changed(update)
slider_beam_y.on_changed(update)
slider_z.on_changed(update)
slider_R.on_changed(update)
slider_sigma.on_changed(update)
slider_corr.on_changed(update)
radio.on_clicked(mode_changed)
radio_qp.on_clicked(qp_mode_changed)

plt.suptitle('Gaussian Beam + Rough Mirror Interference\n(Move beam with X/Y sliders | Adjust Corr len to see Q_p change)', fontsize=11)
plt.show()

#!/usr/bin/env python3
"""
Shared Mirror Physics Module

Contains the core physics calculations for Gaussian beam + rough mirror interference.
Imported by mirror_sim.py (desktop, pygame) and mirror_sim_pi.py (device, PIL + SPI TFT).

lens_test.py predates this module and still carries its own copy of the same maths.
That copy is the older one: its compute_Qp_matrix takes two parameters it never uses,
and its Q_p reference scale is resolution-dependent where this one is fixed. Read this
file, not that one, for the physics that ships on the device.
"""

import numpy as np

# -----------------------------
# Physical Constants
# -----------------------------
WAVELENGTH = 1.0e-6  # 1 micron (IR laser)
K = 2 * np.pi / WAVELENGTH  # wavenumber
W0 = 1.0e-3  # beam waist: 1 mm
ZR = np.pi * W0**2 / WAVELENGTH  # Rayleigh range
L = 6e-3  # 6 mm field of view

# Roughness fractions of lambda
ROUGHNESS_OPTIONS = [0, 1/64, 1/32, 1/16, 1/8, 1/4, 1/2]
ROUGHNESS_LABELS = ["0", "λ/64", "λ/32", "λ/16", "λ/8", "λ/4", "λ/2"]

# Mirror and Q_p mode options
MIRROR_MODES = ["both", "quadratic", "rough", "bump"]
QP_MODES = ["statistical", "empirical"]


def compute_interference(X, Y, FX, FY, base_noise, z_m, R_m, sigma_h, corr_len, 
                         beam_x, beam_y, mirror_mode='both'):
    """
    Compute the interference pattern for given parameters.
    
    Args:
        X, Y: Meshgrid of spatial coordinates
        FX, FY: Meshgrid of frequency coordinates
        base_noise: Pre-generated random noise array
        z_m: Distance from beam waist to mirror (meters)
        R_m: Mirror radius of curvature (meters), inf = flat
        sigma_h: RMS surface roughness height (meters)
        corr_len: Roughness correlation length (meters)
        beam_x: Beam center X offset (meters, from -L/2 to L/2)
        beam_y: Beam center Y offset (meters, from -L/2 to L/2)
        mirror_mode: 'quadratic', 'rough', 'both', or 'bump'
    
    Returns:
        rough_display: Mirror roughness map (for display)
        h: Total mirror surface height
        I: Interference intensity pattern (normalized 0-1)
        A: Beam amplitude
        phi_ref: Reflected beam phase
        ref_x, ref_y: Reflected beam center position
    """
    N = X.shape[0]
    L_grid = X.max() - X.min() + (X[0, 1] - X[0, 0])  # Approximate L from grid
    
    # Beam parameters at mirror location
    if z_m != 0:
        Rz = z_m * (1 + (ZR / z_m)**2)
        gouy = np.arctan(z_m / ZR)
        wz = W0 * np.sqrt(1 + (z_m / ZR)**2)
    else:
        Rz = np.inf
        gouy = 0
        wz = W0
    
    # Shifted coordinates for beam position
    X_shifted = X - beam_x
    Y_shifted = Y - beam_y
    
    # Gaussian amplitude envelope (centered at beam_x, beam_y)
    A = np.exp(-(X_shifted**2 + Y_shifted**2) / wz**2)
    
    # Incident beam phase (spherical wavefront + Gouy phase)
    if np.isfinite(Rz):
        phi_inc = (K / (2 * Rz)) * (X_shifted**2 + Y_shifted**2) - gouy
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
    if np.isfinite(R_m) and R_m != 0:
        h_bump[bump_mask] = (X[bump_mask]**2) / (2 * R_m)
    
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
    E_ref = A * np.exp(-1j * phi_inc) * np.exp(1j * 2 * K * h)
    
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


def compute_Qp_matrix(N, corr_len, h_surface=None, qp_mode='statistical', grid_size=12):
    """
    Compute the Q_p correlation matrix.
    
    Args:
        N: Grid resolution
        corr_len: Roughness correlation length (meters)
        h_surface: Mirror surface height array (for empirical mode)
        qp_mode: 'statistical' or 'empirical'
        grid_size: Size of the Q_p matrix
    
    Returns:
        Qp: Correlation matrix (grid_size^2 x grid_size^2)
    """
    # Create a small spatial grid scaled appropriately for the correlation length
    # Use a fixed reference scale (as if N=240) so Q_p visualization is consistent
    # This ensures the checkerboard pattern is visible regardless of physics resolution
    L_small = L * (grid_size / 240.0)  # Fixed reference scale
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
            phi_sample[idx] = 2 * K * h_surface[full_iy, full_ix]
        
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


def setup_grids(N):
    """
    Setup spatial and frequency grids for a given resolution.
    
    Args:
        N: Number of grid points
        
    Returns:
        x, y: 1D coordinate arrays
        X, Y: 2D meshgrid of coordinates
        FX, FY: 2D meshgrid of frequencies
        base_noise: Random noise array (seeded for reproducibility)
    """
    dx = L / N
    x = np.linspace(-L/2, L/2, N)
    y = np.linspace(-L/2, L/2, N)
    X, Y = np.meshgrid(x, y)
    
    fx = np.fft.fftfreq(N, dx)
    fy = np.fft.fftfreq(N, dx)
    FX, FY = np.meshgrid(fx, fy)
    
    # Pre-generate roughness (fixed pattern, seeded for reproducibility)
    np.random.seed(42)
    base_noise = np.random.randn(N, N)
    
    return x, y, X, Y, FX, FY, base_noise


# Default initial parameters - optimized for visual appeal
DEFAULT_PARAMS = {
    'z_m': 0.15,          # 15 cm from waist (good beam size)
    'R_m': 0.5,           # 50 cm radius of curvature (visible curvature)
    'roughness_idx': 3,   # λ/16 (more visible roughness)
    'corr_len': 150e-6,   # 150 micron correlation length (good patterns)
    'beam_x': 0.5e-3,     # Slightly off-center (shows reflection offset)
    'beam_y': 0.3e-3,     # Slightly off-center
    'mirror_mode': 'quadratic',
    'qp_mode': 'statistical',
}

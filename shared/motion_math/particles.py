"""NumPy-accelerated 2D particle physics system.

Provides:
- EmitterConfig: dataclass describing how particles are spawned
- Force: dataclass for physics forces (gravity, wind, turbulence, drag)
- ParticleSystem: main simulation class with vectorised NumPy math
- 6 preset factory functions: confetti, sparks, snow, fire, data_stream, dust

Internal particle storage: Nx10 array
  columns: [x, y, vx, vy, size, r, g, b, age, lifetime]

get_state() returns Nx8: [x, y, size, alpha, r, g, b, age]
  alpha = 1.0 - age/lifetime  (fade out over life)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

__all__ = [
    "EmitterConfig",
    "Force",
    "ParticleSystem",
    "preset_confetti",
    "preset_sparks",
    "preset_snow",
    "preset_fire",
    "preset_data_stream",
    "preset_dust",
]

# Column indices for internal Nx10 storage
_X = 0
_Y = 1
_VX = 2
_VY = 3
_SIZE = 4
_R = 5
_G = 6
_B = 7
_AGE = 8
_LIFE = 9


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EmitterConfig:
    """Configuration for a particle emitter."""
    position: tuple[float, float]
    rate: float = 50.0            # particles per second
    lifetime: float = 2.0         # seconds
    spread_angle: float = 360.0   # degrees; 360 = omni-directional
    initial_speed: float = 50.0
    speed_randomness: float = 0.3  # 0-1 fraction of initial_speed
    direction: float = 270.0       # degrees; 270 = up (CCW from +x)
    size: float = 4.0
    size_randomness: float = 0.3
    color: tuple[float, ...] = (1.0, 1.0, 1.0)  # RGB 0-1
    color_randomness: float = 0.0


@dataclass
class Force:
    """A physics force applied to all particles each step."""
    type: str                              # "gravity", "wind", "turbulence", "drag"
    strength: float = 100.0
    direction: tuple[float, float] = (0.0, 1.0)
    frequency: float = 1.0                # used by turbulence


# ---------------------------------------------------------------------------
# ParticleSystem
# ---------------------------------------------------------------------------

class ParticleSystem:
    """NumPy-accelerated 2D particle simulation.

    Usage::

        ps = ParticleSystem(seed=42)
        ps.add_emitter(EmitterConfig(position=(400, 300), rate=100))
        ps.add_force(Force(type="gravity", strength=200))
        for frame in range(30):
            ps.step(1/30)
            state = ps.get_state()  # Nx8 array
    """

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed
        self._rng = np.random.default_rng(seed)
        self._emitters: list[EmitterConfig] = []
        self._forces: list[Force] = []
        # Internal particle storage: Nx10
        self._particles: np.ndarray = np.empty((0, 10), dtype=np.float64)
        # Accumulated fractional particles per emitter (for precise emission)
        self._accumulators: list[float] = []
        # Simulation time (for turbulence phase)
        self._time: float = 0.0

    # ------------------------------------------------------------------
    # Public API — configuration
    # ------------------------------------------------------------------

    def add_emitter(self, config: EmitterConfig) -> None:
        """Add an emitter to the system."""
        self._emitters.append(config)
        self._accumulators.append(0.0)

    def add_force(self, force: Force) -> None:
        """Add a physics force to the system."""
        self._forces.append(force)

    # ------------------------------------------------------------------
    # Public API — simulation
    # ------------------------------------------------------------------

    def step(self, dt: float) -> None:
        """Advance simulation by dt seconds."""
        # 1. Emit new particles
        new_batches: list[np.ndarray] = []
        for i, cfg in enumerate(self._emitters):
            self._accumulators[i] += cfg.rate * dt
            count = int(self._accumulators[i])
            if count > 0:
                self._accumulators[i] -= count
                batch = self._spawn_particles(cfg, count)
                new_batches.append(batch)

        # 2. Append new particles
        if new_batches:
            new_arr = np.concatenate(new_batches, axis=0)
            if self._particles.shape[0] == 0:
                self._particles = new_arr
            else:
                self._particles = np.concatenate([self._particles, new_arr], axis=0)

        # 3. Apply forces and integrate (only if particles exist)
        if self._particles.shape[0] > 0:
            self._apply_forces(dt)
            self._integrate(dt)

        # 4. Age and remove dead particles
        if self._particles.shape[0] > 0:
            self._particles[:, _AGE] += dt
            alive = self._particles[:, _AGE] < self._particles[:, _LIFE]
            self._particles = self._particles[alive]

        self._time += dt

    def get_state(self) -> np.ndarray:
        """Return current particle state as Nx8 array.

        Columns: [x, y, size, alpha, r, g, b, age]
        alpha = 1.0 - age/lifetime
        """
        n = self._particles.shape[0]
        if n == 0:
            return np.empty((0, 8), dtype=np.float64)

        p = self._particles
        lifetimes = p[:, _LIFE]
        # Avoid division by zero (lifetime > 0 guaranteed by config)
        alpha = np.clip(1.0 - p[:, _AGE] / lifetimes, 0.0, 1.0)

        out = np.empty((n, 8), dtype=np.float64)
        out[:, 0] = p[:, _X]
        out[:, 1] = p[:, _Y]
        out[:, 2] = p[:, _SIZE]
        out[:, 3] = alpha
        out[:, 4] = p[:, _R]
        out[:, 5] = p[:, _G]
        out[:, 6] = p[:, _B]
        out[:, 7] = p[:, _AGE]
        return out

    def get_frame(self, t: float) -> np.ndarray:
        """Simulate from time 0 to t and return state. Deterministic.

        Uses fixed 1/60 step size for reproducibility.
        """
        # Create a fresh copy with same seed
        ps = ParticleSystem(seed=self._seed)
        for cfg in self._emitters:
            ps.add_emitter(cfg)
        for force in self._forces:
            ps.add_force(force)

        dt = 1.0 / 60.0
        elapsed = 0.0
        while elapsed < t:
            step_dt = min(dt, t - elapsed)
            ps.step(step_dt)
            elapsed += step_dt

        return ps.get_state()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _spawn_particles(self, cfg: EmitterConfig, count: int) -> np.ndarray:
        """Spawn `count` particles from emitter config. Returns Nx10 array."""
        batch = np.zeros((count, 10), dtype=np.float64)

        # Position
        batch[:, _X] = cfg.position[0]
        batch[:, _Y] = cfg.position[1]

        # Direction and speed
        dir_rad = math.radians(cfg.direction)
        spread_rad = math.radians(cfg.spread_angle)

        # Random angle within spread around direction
        if cfg.spread_angle >= 360.0:
            angles = self._rng.uniform(0.0, 2.0 * math.pi, count)
        else:
            half = spread_rad / 2.0
            angles = self._rng.uniform(dir_rad - half, dir_rad + half, count)

        # Speed with randomness
        speed_var = cfg.initial_speed * cfg.speed_randomness
        speeds = cfg.initial_speed + self._rng.uniform(-speed_var, speed_var, count)
        speeds = np.maximum(speeds, 0.0)

        batch[:, _VX] = np.cos(angles) * speeds
        batch[:, _VY] = np.sin(angles) * speeds

        # Size with randomness
        size_var = cfg.size * cfg.size_randomness
        batch[:, _SIZE] = np.maximum(
            cfg.size + self._rng.uniform(-size_var, size_var, count),
            0.1,
        )

        # Color with randomness
        r, g, b = cfg.color[0], cfg.color[1], cfg.color[2]
        if cfg.color_randomness > 0.0:
            cr = cfg.color_randomness
            batch[:, _R] = np.clip(r + self._rng.uniform(-cr, cr, count), 0.0, 1.0)
            batch[:, _G] = np.clip(g + self._rng.uniform(-cr, cr, count), 0.0, 1.0)
            batch[:, _B] = np.clip(b + self._rng.uniform(-cr, cr, count), 0.0, 1.0)
        else:
            batch[:, _R] = r
            batch[:, _G] = g
            batch[:, _B] = b

        # Age starts at 0; lifetime from config
        batch[:, _AGE] = 0.0
        batch[:, _LIFE] = cfg.lifetime

        return batch

    def _apply_forces(self, dt: float) -> None:
        """Apply all forces to particle velocities (in-place)."""
        p = self._particles
        n = p.shape[0]
        if n == 0:
            return

        for force in self._forces:
            if force.type == "gravity":
                dx, dy = force.direction
                # Normalise direction
                mag = math.hypot(dx, dy)
                if mag > 0:
                    dx /= mag
                    dy /= mag
                p[:, _VX] += dx * force.strength * dt
                p[:, _VY] += dy * force.strength * dt

            elif force.type == "wind":
                dx, dy = force.direction
                mag = math.hypot(dx, dy)
                if mag > 0:
                    dx /= mag
                    dy /= mag
                p[:, _VX] += dx * force.strength * dt
                p[:, _VY] += dy * force.strength * dt

            elif force.type == "turbulence":
                # Noise using sin/cos with per-particle spatial variation
                freq = force.frequency
                t = self._time
                # Use particle positions as spatial seed for variety
                phase_x = p[:, _X] * 0.01 * freq + t * freq
                phase_y = p[:, _Y] * 0.01 * freq + t * freq + math.pi / 2
                noise_x = np.sin(phase_x) * force.strength
                noise_y = np.cos(phase_y) * force.strength
                p[:, _VX] += noise_x * dt
                p[:, _VY] += noise_y * dt

            elif force.type == "drag":
                # F_drag = -strength * v  (linear drag)
                p[:, _VX] -= p[:, _VX] * force.strength * dt
                p[:, _VY] -= p[:, _VY] * force.strength * dt

    def _integrate(self, dt: float) -> None:
        """Euler integration: position += velocity * dt."""
        self._particles[:, _X] += self._particles[:, _VX] * dt
        self._particles[:, _Y] += self._particles[:, _VY] * dt


# ---------------------------------------------------------------------------
# Preset factory functions
# ---------------------------------------------------------------------------

def preset_confetti(position: tuple[float, float], seed: int = 0) -> ParticleSystem:
    """Celebration confetti: colourful particles with gravity + turbulence."""
    ps = ParticleSystem(seed=seed)
    ps.add_emitter(EmitterConfig(
        position=position,
        rate=80.0,
        lifetime=3.0,
        spread_angle=360.0,
        initial_speed=150.0,
        speed_randomness=0.4,
        direction=270.0,
        size=6.0,
        size_randomness=0.5,
        color=(1.0, 0.5, 0.2),
        color_randomness=0.5,
    ))
    ps.add_force(Force(type="gravity", strength=120.0, direction=(0.0, 1.0)))
    ps.add_force(Force(type="turbulence", strength=30.0, frequency=1.5))
    return ps


def preset_sparks(
    position: tuple[float, float],
    color: tuple[float, ...] = (1.0, 0.8, 0.2),
    seed: int = 0,
) -> ParticleSystem:
    """Fast, short-lived sparks with drag (e.g., welding, fireworks)."""
    ps = ParticleSystem(seed=seed)
    ps.add_emitter(EmitterConfig(
        position=position,
        rate=200.0,
        lifetime=0.6,
        spread_angle=360.0,
        initial_speed=300.0,
        speed_randomness=0.5,
        direction=270.0,
        size=2.0,
        size_randomness=0.4,
        color=color,
        color_randomness=0.1,
    ))
    ps.add_force(Force(type="gravity", strength=200.0, direction=(0.0, 1.0)))
    ps.add_force(Force(type="drag", strength=3.0))
    return ps


def preset_snow(width: float, seed: int = 0) -> ParticleSystem:
    """Gentle snow falling across the screen width."""
    ps = ParticleSystem(seed=seed)
    # Emit along the top edge
    ps.add_emitter(EmitterConfig(
        position=(width / 2.0, -10.0),
        rate=30.0,
        lifetime=8.0,
        spread_angle=160.0,   # wide spread across screen
        initial_speed=40.0,
        speed_randomness=0.5,
        direction=90.0,       # pointing down (+y)
        size=3.0,
        size_randomness=0.6,
        color=(1.0, 1.0, 1.0),
        color_randomness=0.05,
    ))
    ps.add_force(Force(type="gravity", strength=30.0, direction=(0.0, 1.0)))
    ps.add_force(Force(type="turbulence", strength=15.0, frequency=0.3))
    return ps


def preset_fire(
    position: tuple[float, float],
    color: tuple[float, ...] = (1.0, 0.4, 0.0),
    seed: int = 0,
) -> ParticleSystem:
    """Rising fire with turbulence, fading from bright to dark."""
    ps = ParticleSystem(seed=seed)
    ps.add_emitter(EmitterConfig(
        position=position,
        rate=120.0,
        lifetime=1.5,
        spread_angle=60.0,
        initial_speed=80.0,
        speed_randomness=0.4,
        direction=270.0,      # up
        size=8.0,
        size_randomness=0.5,
        color=color,
        color_randomness=0.15,
    ))
    # Slight upward wind
    ps.add_force(Force(type="wind", strength=20.0, direction=(0.0, -1.0)))
    ps.add_force(Force(type="turbulence", strength=40.0, frequency=2.0))
    ps.add_force(Force(type="drag", strength=1.5))
    return ps


def preset_data_stream(
    width: float,
    height: float,
    direction: str = "down",
    seed: int = 0,
) -> ParticleSystem:
    """Matrix-style digital rain — columns of fast particles."""
    ps = ParticleSystem(seed=seed)

    dir_map = {
        "down": (90.0, (0.0, 1.0)),    # 90 degrees = down
        "up": (270.0, (0.0, -1.0)),
        "left": (180.0, (-1.0, 0.0)),
        "right": (0.0, (1.0, 0.0)),
    }
    angle_deg, wind_dir = dir_map.get(direction, dir_map["down"])

    ps.add_emitter(EmitterConfig(
        position=(width / 2.0, 0.0),
        rate=60.0,
        lifetime=height / 150.0,  # enough to cross screen
        spread_angle=170.0,        # wide spread across width
        initial_speed=150.0,
        speed_randomness=0.3,
        direction=angle_deg,
        size=3.0,
        size_randomness=0.2,
        color=(0.0, 1.0, 0.3),    # Matrix green
        color_randomness=0.1,
    ))
    ps.add_force(Force(type="wind", strength=150.0, direction=wind_dir))
    return ps


def preset_dust(width: float, height: float, seed: int = 0) -> ParticleSystem:
    """Slow-floating atmospheric dust particles."""
    ps = ParticleSystem(seed=seed)
    ps.add_emitter(EmitterConfig(
        position=(width / 2.0, height / 2.0),
        rate=20.0,
        lifetime=6.0,
        spread_angle=360.0,
        initial_speed=15.0,
        speed_randomness=0.8,
        direction=270.0,
        size=2.0,
        size_randomness=0.7,
        color=(0.9, 0.85, 0.8),
        color_randomness=0.1,
    ))
    ps.add_force(Force(type="turbulence", strength=10.0, frequency=0.5))
    ps.add_force(Force(type="drag", strength=0.8))
    return ps

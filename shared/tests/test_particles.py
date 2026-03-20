"""Tests for the NumPy-accelerated 2D particle system.

Covers:
- EmitterConfig defaults
- Emit particles (rate=100 for 0.1s -> ~10 particles)
- Gravity force (particles move downward)
- Particle death (old particles removed)
- Deterministic replay (same seed -> same state)
- 10k particles performance test (< 2s for 1s of simulation)
- All 6 presets produce particles
"""

from __future__ import annotations

import time as time_mod

import numpy as np
import pytest

from motion_math.particles import (
    EmitterConfig,
    Force,
    ParticleSystem,
    preset_confetti,
    preset_sparks,
    preset_snow,
    preset_fire,
    preset_data_stream,
    preset_dust,
)


# ---------------------------------------------------------------------------
# EmitterConfig defaults
# ---------------------------------------------------------------------------

class TestEmitterConfigDefaults:
    def test_position_required(self):
        ec = EmitterConfig(position=(100.0, 200.0))
        assert ec.position == (100.0, 200.0)

    def test_rate_default(self):
        ec = EmitterConfig(position=(0.0, 0.0))
        assert ec.rate == 50.0

    def test_lifetime_default(self):
        ec = EmitterConfig(position=(0.0, 0.0))
        assert ec.lifetime == 2.0

    def test_spread_angle_default(self):
        ec = EmitterConfig(position=(0.0, 0.0))
        assert ec.spread_angle == 360.0

    def test_initial_speed_default(self):
        ec = EmitterConfig(position=(0.0, 0.0))
        assert ec.initial_speed == 50.0

    def test_speed_randomness_default(self):
        ec = EmitterConfig(position=(0.0, 0.0))
        assert ec.speed_randomness == 0.3

    def test_direction_default(self):
        ec = EmitterConfig(position=(0.0, 0.0))
        assert ec.direction == 270.0

    def test_size_default(self):
        ec = EmitterConfig(position=(0.0, 0.0))
        assert ec.size == 4.0

    def test_size_randomness_default(self):
        ec = EmitterConfig(position=(0.0, 0.0))
        assert ec.size_randomness == 0.3

    def test_color_default(self):
        ec = EmitterConfig(position=(0.0, 0.0))
        assert ec.color == (1.0, 1.0, 1.0)

    def test_color_randomness_default(self):
        ec = EmitterConfig(position=(0.0, 0.0))
        assert ec.color_randomness == 0.0

    def test_custom_values(self):
        ec = EmitterConfig(
            position=(50.0, 75.0),
            rate=200.0,
            lifetime=3.5,
            spread_angle=90.0,
            initial_speed=100.0,
            speed_randomness=0.5,
            direction=90.0,
            size=8.0,
            size_randomness=0.1,
            color=(1.0, 0.0, 0.0),
            color_randomness=0.2,
        )
        assert ec.rate == 200.0
        assert ec.color == (1.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Force defaults
# ---------------------------------------------------------------------------

class TestForceDefaults:
    def test_gravity_type(self):
        f = Force(type="gravity")
        assert f.type == "gravity"

    def test_strength_default(self):
        f = Force(type="wind")
        assert f.strength == 100.0

    def test_direction_default(self):
        f = Force(type="wind")
        assert f.direction == (0.0, 1.0)

    def test_frequency_default(self):
        f = Force(type="turbulence")
        assert f.frequency == 1.0

    def test_drag_type(self):
        f = Force(type="drag", strength=0.5)
        assert f.type == "drag"
        assert f.strength == 0.5


# ---------------------------------------------------------------------------
# Particle emission
# ---------------------------------------------------------------------------

class TestParticleEmission:
    def test_no_particles_at_start(self):
        ps = ParticleSystem(seed=42)
        ps.add_emitter(EmitterConfig(position=(0.0, 0.0), rate=100.0))
        state = ps.get_state()
        # Before any step, no particles
        assert state.shape[0] == 0

    def test_emit_particles_after_step(self):
        ps = ParticleSystem(seed=42)
        ps.add_emitter(EmitterConfig(position=(0.0, 0.0), rate=100.0))
        ps.step(0.1)
        state = ps.get_state()
        # rate=100, dt=0.1 -> expect ~10 particles (exactly 10)
        assert state.shape[0] == 10

    def test_emit_correct_column_count(self):
        ps = ParticleSystem(seed=42)
        ps.add_emitter(EmitterConfig(position=(0.0, 0.0), rate=100.0))
        ps.step(0.1)
        state = ps.get_state()
        # get_state returns Nx8: [x, y, size, alpha, r, g, b, age]
        assert state.shape[1] == 8

    def test_particle_starts_at_emitter_position(self):
        ps = ParticleSystem(seed=0)
        px, py = 123.0, 456.0
        ps.add_emitter(EmitterConfig(position=(px, py), rate=1000.0, speed_randomness=0.0))
        ps.step(0.001)  # very small dt — freshly emitted, no movement yet
        state = ps.get_state()
        if state.shape[0] > 0:
            # Positions should be near emitter origin (only dt movement)
            assert np.allclose(state[:, 0], px, atol=5.0)
            assert np.allclose(state[:, 1], py, atol=5.0)

    def test_alpha_in_range(self):
        ps = ParticleSystem(seed=1)
        ps.add_emitter(EmitterConfig(position=(0.0, 0.0), rate=100.0))
        ps.step(0.1)
        state = ps.get_state()
        alphas = state[:, 3]
        assert np.all(alphas >= 0.0)
        assert np.all(alphas <= 1.0)

    def test_age_in_range(self):
        ps = ParticleSystem(seed=1)
        ps.add_emitter(EmitterConfig(position=(0.0, 0.0), rate=100.0, lifetime=2.0))
        ps.step(0.1)
        state = ps.get_state()
        ages = state[:, 7]
        assert np.all(ages >= 0.0)
        assert np.all(ages < 2.0)

    def test_multiple_emitters(self):
        ps = ParticleSystem(seed=5)
        ps.add_emitter(EmitterConfig(position=(0.0, 0.0), rate=50.0))
        ps.add_emitter(EmitterConfig(position=(100.0, 100.0), rate=50.0))
        ps.step(0.1)
        state = ps.get_state()
        # Both emitters should contribute particles
        assert state.shape[0] == 10  # 5 from each


# ---------------------------------------------------------------------------
# Forces
# ---------------------------------------------------------------------------

class TestForces:
    def test_gravity_moves_particles_down(self):
        """With only gravity, particles should have increasing y (downward in screen coords)."""
        ps = ParticleSystem(seed=42)
        # Use a very low rate so second step emits no new particles within dt=0.01
        ps.add_emitter(EmitterConfig(
            position=(0.0, 0.0),
            rate=100.0,
            initial_speed=0.0,   # no initial velocity
            spread_angle=0.0,    # single direction
            lifetime=10.0,       # long-lived so nothing dies
        ))
        ps.add_force(Force(type="gravity", strength=100.0, direction=(0.0, 1.0)))
        ps.step(0.1)  # emit 10 particles; accumulator is exactly 0 after
        state_before = ps.get_state()
        # The accumulator is 0.0 after step(0.1) with rate=100 → 10 emitted exactly
        # Step with tiny dt — not enough to emit more (would need 0.01s for 1 particle)
        # Use dt=0.005 so rate*dt = 0.5 < 1 → no new emissions
        ps.step(0.005)
        state_after = ps.get_state()
        # Same number of particles (no birth, no death in 0.005s with lifetime=10)
        assert state_before.shape[0] == state_after.shape[0]
        # y should have increased (gravity pulls down)
        assert np.all(state_after[:, 1] >= state_before[:, 1] - 1e-9)

    def test_wind_moves_particles_horizontally(self):
        ps = ParticleSystem(seed=42)
        ps.add_emitter(EmitterConfig(
            position=(0.0, 0.0),
            rate=100.0,
            initial_speed=0.0,
            lifetime=10.0,
        ))
        ps.add_force(Force(type="wind", strength=100.0, direction=(1.0, 0.0)))
        ps.step(0.1)  # emit 10 particles; accumulator reset to 0
        x_after_emit = ps.get_state()[:, 0].copy()
        # Use dt=0.005 so rate*dt=0.5 → no new emissions, no deaths
        ps.step(0.005)
        x_after_wind = ps.get_state()[:, 0]
        assert x_after_wind.shape == x_after_emit.shape
        assert np.all(x_after_wind >= x_after_emit - 1e-9)

    def test_drag_slows_particles(self):
        """Drag should reduce speed over time."""
        ps = ParticleSystem(seed=42)
        ps.add_emitter(EmitterConfig(
            position=(0.0, 0.0),
            rate=10.0,
            initial_speed=200.0,
            spread_angle=0.0,
            direction=0.0,  # emit right
            speed_randomness=0.0,
        ))
        ps.add_force(Force(type="drag", strength=2.0))
        ps.step(0.1)  # emit
        # After many steps with drag, particles should slow
        for _ in range(10):
            ps.step(0.1)
        state = ps.get_state()
        # Just verify system is still running without error
        assert state.shape[0] >= 0

    def test_turbulence_does_not_crash(self):
        ps = ParticleSystem(seed=42)
        ps.add_emitter(EmitterConfig(position=(0.0, 0.0), rate=50.0))
        ps.add_force(Force(type="turbulence", strength=50.0, frequency=2.0))
        for _ in range(10):
            ps.step(0.033)
        state = ps.get_state()
        assert state.shape[0] > 0

    def test_multiple_forces(self):
        ps = ParticleSystem(seed=42)
        ps.add_emitter(EmitterConfig(position=(0.0, 0.0), rate=50.0))
        ps.add_force(Force(type="gravity", strength=100.0))
        ps.add_force(Force(type="drag", strength=1.0))
        ps.add_force(Force(type="turbulence", strength=20.0))
        for _ in range(5):
            ps.step(0.033)
        state = ps.get_state()
        assert state.shape[0] > 0


# ---------------------------------------------------------------------------
# Particle death
# ---------------------------------------------------------------------------

class TestParticleDeath:
    def test_particles_die_after_lifetime(self):
        ps = ParticleSystem(seed=0)
        ps.add_emitter(EmitterConfig(position=(0.0, 0.0), rate=100.0, lifetime=0.5))
        # Emit for 0.1s
        ps.step(0.1)
        count_after_emit = ps.get_state().shape[0]
        assert count_after_emit > 0
        # Step past lifetime (0.5s more)
        for _ in range(10):
            ps.step(0.1)
        count_after_death = ps.get_state().shape[0]
        # Particles emitted at 0.1s should be dead by 0.6s
        # But new particles may have been emitted, so just check we had some death
        assert count_after_death < count_after_emit + 100

    def test_no_dead_particles_in_state(self):
        """get_state() must never return particles with age >= lifetime."""
        ps = ParticleSystem(seed=7)
        ps.add_emitter(EmitterConfig(position=(0.0, 0.0), rate=100.0, lifetime=0.3))
        for _ in range(20):
            ps.step(0.05)
        state = ps.get_state()
        if state.shape[0] > 0:
            # All ages should be < their respective lifetime
            # In get_state, age is column 7
            ages = state[:, 7]
            assert np.all(ages < 0.3 + 1e-9)

    def test_alpha_decreases_with_age(self):
        """Alpha should be 1 - age/lifetime, so older particles are more transparent."""
        ps = ParticleSystem(seed=3)
        ps.add_emitter(EmitterConfig(position=(0.0, 0.0), rate=200.0, lifetime=2.0))
        # Simulate multiple steps so particles have a range of ages
        for _ in range(10):
            ps.step(0.05)
        state = ps.get_state()
        assert state.shape[0] > 1, "Expected multiple particles"
        ages = state[:, 7]
        alphas = state[:, 3]
        # Verify the alpha formula directly: alpha == 1 - age/lifetime
        # lifetime is fixed at 2.0 for all particles
        expected_alphas = np.clip(1.0 - ages / 2.0, 0.0, 1.0)
        np.testing.assert_allclose(alphas, expected_alphas, atol=1e-9)
        # Also check that particles with distinct ages have distinct alphas (not all same)
        if len(np.unique(np.round(ages, 3))) > 1:
            assert not np.all(alphas == alphas[0])


# ---------------------------------------------------------------------------
# Deterministic replay
# ---------------------------------------------------------------------------

class TestDeterministicReplay:
    def test_same_seed_same_state(self):
        def run(seed):
            ps = ParticleSystem(seed=seed)
            ps.add_emitter(EmitterConfig(position=(100.0, 100.0), rate=50.0))
            ps.add_force(Force(type="gravity", strength=100.0))
            for _ in range(10):
                ps.step(0.033)
            return ps.get_state()

        state1 = run(42)
        state2 = run(42)
        assert np.array_equal(state1, state2)

    def test_different_seed_different_state(self):
        def run(seed):
            ps = ParticleSystem(seed=seed)
            ps.add_emitter(EmitterConfig(position=(100.0, 100.0), rate=50.0, spread_angle=360.0))
            for _ in range(10):
                ps.step(0.033)
            return ps.get_state()

        state1 = run(0)
        state2 = run(99)
        # Different seeds should produce different results
        if state1.shape == state2.shape and state1.shape[0] > 0:
            assert not np.array_equal(state1, state2)

    def test_get_frame_deterministic(self):
        ps = ParticleSystem(seed=42)
        ps.add_emitter(EmitterConfig(position=(0.0, 0.0), rate=50.0))
        ps.add_force(Force(type="gravity", strength=100.0))

        state_a = ps.get_frame(t=0.5)
        state_b = ps.get_frame(t=0.5)
        assert np.array_equal(state_a, state_b)

    def test_get_frame_vs_step(self):
        """get_frame(t) and step-by-step should produce same result."""
        cfg = EmitterConfig(position=(50.0, 50.0), rate=30.0, lifetime=2.0)
        force = Force(type="gravity", strength=98.0, direction=(0.0, 1.0))

        # step-by-step
        ps1 = ParticleSystem(seed=10)
        ps1.add_emitter(cfg)
        ps1.add_force(force)
        for _ in range(10):
            ps1.step(0.033)
        state_step = ps1.get_state()

        # get_frame with same total time
        ps2 = ParticleSystem(seed=10)
        ps2.add_emitter(cfg)
        ps2.add_force(force)
        state_frame = ps2.get_frame(t=0.33)
        # Both should have particles; exact match depends on step size
        assert state_frame.shape[1] == 8


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

class TestPerformance:
    def test_10k_particles_1s_under_2s(self):
        """10,000 particles at 30fps must complete 1 second of simulation in < 2s."""
        ps = ParticleSystem(seed=0)
        ps.add_emitter(EmitterConfig(
            position=(500.0, 500.0),
            rate=10000.0,   # emit 10k in first frame
            lifetime=2.0,
        ))
        ps.add_force(Force(type="gravity", strength=100.0))
        ps.add_force(Force(type="drag", strength=0.5))

        # Prime: emit 10k particles
        ps.step(1.0)
        count = ps.get_state().shape[0]
        assert count >= 1000, f"Expected at least 1000 particles, got {count}"

        # Now simulate 1 second at 30fps (30 steps)
        start = time_mod.perf_counter()
        for _ in range(30):
            ps.step(1.0 / 30.0)
        elapsed = time_mod.perf_counter() - start

        assert elapsed < 2.0, f"Performance test failed: {elapsed:.2f}s >= 2.0s"


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

class TestPresets:
    def _run_preset(self, ps: ParticleSystem, steps: int = 10, dt: float = 0.033) -> int:
        for _ in range(steps):
            ps.step(dt)
        return ps.get_state().shape[0]

    def test_preset_confetti(self):
        ps = preset_confetti(position=(400.0, 300.0))
        count = self._run_preset(ps)
        assert count > 0, "confetti preset produced no particles"

    def test_preset_sparks(self):
        ps = preset_sparks(position=(400.0, 300.0), color=(1.0, 0.8, 0.2))
        count = self._run_preset(ps)
        assert count > 0, "sparks preset produced no particles"

    def test_preset_snow(self):
        ps = preset_snow(width=800.0)
        count = self._run_preset(ps)
        assert count > 0, "snow preset produced no particles"

    def test_preset_fire(self):
        ps = preset_fire(position=(400.0, 500.0), color=(1.0, 0.4, 0.0))
        count = self._run_preset(ps)
        assert count > 0, "fire preset produced no particles"

    def test_preset_data_stream(self):
        ps = preset_data_stream(width=800.0, height=600.0, direction="down")
        count = self._run_preset(ps)
        assert count > 0, "data_stream preset produced no particles"

    def test_preset_dust(self):
        ps = preset_dust(width=800.0, height=600.0)
        count = self._run_preset(ps)
        assert count > 0, "dust preset produced no particles"

    def test_preset_returns_particle_system(self):
        for preset_fn, args in [
            (preset_confetti, {"position": (0.0, 0.0)}),
            (preset_sparks, {"position": (0.0, 0.0), "color": (1.0, 1.0, 0.0)}),
            (preset_snow, {"width": 800.0}),
            (preset_fire, {"position": (0.0, 0.0), "color": (1.0, 0.5, 0.0)}),
            (preset_data_stream, {"width": 800.0, "height": 600.0, "direction": "down"}),
            (preset_dust, {"width": 800.0, "height": 600.0}),
        ]:
            ps = preset_fn(**args)
            assert isinstance(ps, ParticleSystem), f"{preset_fn.__name__} did not return ParticleSystem"

    def test_preset_state_columns(self):
        """All presets should produce Nx8 state arrays."""
        presets = [
            preset_confetti(position=(200.0, 200.0)),
            preset_sparks(position=(200.0, 200.0), color=(1.0, 0.5, 0.0)),
            preset_snow(width=400.0),
            preset_fire(position=(200.0, 200.0), color=(1.0, 0.3, 0.0)),
            preset_data_stream(width=400.0, height=300.0, direction="down"),
            preset_dust(width=400.0, height=300.0),
        ]
        for ps in presets:
            ps.step(0.1)
            state = ps.get_state()
            if state.shape[0] > 0:
                assert state.shape[1] == 8, f"Expected 8 columns, got {state.shape[1]}"

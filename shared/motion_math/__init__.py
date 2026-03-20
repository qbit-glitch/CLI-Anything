"""Shared motion graphics math library."""
from .easing import get_easing, cubic_bezier, spring, EASING_FUNCTIONS
from .keyframes import Keyframe, KeyframeTrack
from .expressions import Expression
from .particles import ParticleSystem, EmitterConfig, Force
from .particles import preset_confetti, preset_sparks, preset_snow
from .particles import preset_fire, preset_data_stream, preset_dust
from .text_animator import CharInfo, CharacterAnimator

__all__ = [
    "get_easing", "cubic_bezier", "spring", "EASING_FUNCTIONS",
    "Keyframe", "KeyframeTrack",
    "Expression",
    "ParticleSystem", "EmitterConfig", "Force",
    "preset_confetti", "preset_sparks", "preset_snow",
    "preset_fire", "preset_data_stream", "preset_dust",
    "CharInfo", "CharacterAnimator",
]

"""
Key Mapping Utilities for Computer Use Handlers

This module provides utilities for normalizing and mapping keyboard input across different
computer use providers and tools.
"""

from __future__ import annotations

from typing import Dict, Set

# Canonical key mappings
KEY_ALIASES: Dict[str, Set[str]] = {
    # Navigation keys
    'Escape': {'esc', 'escape'},
    'Return': {'enter', 'return'},
    'BackSpace': {'backspace', 'bksp'},
    'Delete': {'del', 'delete'},
    'Tab': {'tab'},
    'space': {'space', 'spacebar'},
    # Page navigation
    'Page_Up': {'pageup', 'pgup'},
    'Page_Down': {'pagedown', 'pgdn'},
    'Home': {'home'},
    'End': {'end'},
    # Arrow keys
    'Up': {'up', 'uparrow'},
    'Down': {'down', 'downarrow'},
    'Left': {'left', 'leftarrow'},
    'Right': {'right', 'rightarrow'},
    # System keys
    'Print': {'printscreen', 'prtsc', 'prtscrn'},
    'Insert': {'ins', 'insert'},
    'Pause': {'pause', 'pausebreak'},
    'ScrollLock': {'scrolllock', 'scroll'},
    'CapsLock': {'capslock', 'caps'},
    'NumLock': {'numlock', 'num'},
    # Modifier keys
    'Super_L': {'win', 'windows', 'super', 'meta', 'cmd', 'super_l', 'super_r'},
    'ctrl': {'ctrl', 'control', 'ctrl_l', 'ctrl_r'},
    'shift': {'shift', 'shift_l', 'shift_r'},
    'alt': {'alt', 'alt_l', 'alt_r', 'option'},
}


def normalize_key_part(part: str) -> str:
    """
    Normalize a single key part.

    Args:
        part: Single key part to normalize

    Returns:
        Normalized key string
    """
    low = part.lower()

    # Check key aliases - find canonical form for any alias
    for canonical, aliases in KEY_ALIASES.items():
        if low in aliases:
            return canonical

    # Function keys
    if low.startswith('f') and low[1:].isdigit():
        return f'F{int(low[1:])}'

    # Single letters or digits: keep as-is
    if len(part) == 1:
        return part

    return part


def normalize_key_combo(combo: str) -> str:
    """
    Normalize key combinations for xdotool compatibility.

    Args:
        combo: Key combination string (e.g., 'ctrl+c', 'alt+tab')

    Returns:
        Normalized key combination string
    """
    if not isinstance(combo, str):
        return combo

    parts = [p.strip() for p in combo.replace(' ', '').split('+') if p.strip()]
    normalized = [normalize_key_part(p) for p in parts]
    return '+'.join(normalized)

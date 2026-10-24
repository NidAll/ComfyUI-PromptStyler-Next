"""PromptStyler Next: an offline, model-aware styling engine with no host dependencies."""

from .adapters import ModelAdapter, Profile
from .engine import Engine
from .errors import StylerError
from .types import Composition, Layer, Recipe

__version__ = "0.1.0"
__all__ = ["Composition", "Engine", "Layer", "ModelAdapter", "Profile", "Recipe", "StylerError"]

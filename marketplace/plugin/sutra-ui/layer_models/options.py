"""The parameters of the ways out an ask offers (A1.15)."""
import layer_consts as K
from .base import Open
from .common import T, I, N, E, Impl, Name


class OptionRaise(Open):
    __def__ = 'option.raise'
    what: E('envelope', 'ceiling')
    engine: Name = None
    calls: I(0) = None
    usd: N(0) = None
    rounds: I(0) = None


class OptionWords(Open):
    __def__ = 'option.words'
    words: T(4000, 1)


class OptionPin(Open):
    __def__ = 'option.pin'
    layer: E(*K.LAYER_NAMES)
    impl: Impl


DEFINES = {
    'option.raise': OptionRaise,
    'option.words': OptionWords,
    'option.pin': OptionPin,
}
__all__ = [
    'OptionPin', 'OptionRaise', 'OptionWords', 'DEFINES',
]

"""The settings (A1.8 to A1.12)."""
from .common import named, I, B, E, L, M


SettingWindowsBody = M(I(0, 1440))
SettingWindows = named('setting.windows', SettingWindowsBody)


SettingMake = B


SettingOrder = L(E('posts', 'line', 'functions'), 3, 1, True)


SettingSpotEveryS = I(3600, 604800)


DEFINES = {
    'setting.windows': SettingWindowsBody,
    'setting.make': SettingMake,
    'setting.order': SettingOrder,
    'setting.spot_every_s': SettingSpotEveryS,
}
__all__ = [
    'SettingMake', 'SettingOrder', 'SettingSpotEveryS', 'SettingWindows', 'SettingWindowsBody', 'DEFINES',
]

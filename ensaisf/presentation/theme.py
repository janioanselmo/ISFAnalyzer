from __future__ import annotations

APP_VERSION = "0.5.4-peak-through-envelope"

# Global color order used by all analysis screens.
# 1st curve: orange, 2nd: blue. Additional curves use high-contrast,
# visually distinct colors while preserving the same file/color mapping across tabs.
SERIES_COLORS_RGB = [
    (230, 126, 34),  # orange - first curve
    (0, 109, 204),   # blue - second curve
    (0, 150, 90),    # green - third curve
    (45, 45, 45),    # charcoal - fourth curve
    (0, 155, 170),   # teal - fifth curve
    (190, 135, 0),   # golden brown - sixth curve
    (210, 0, 125),   # magenta - seventh curve
    (120, 80, 30),   # brown - eighth curve
    (90, 55, 160),   # violet - fallback only for larger overlays
    (80, 80, 80),    # neutral gray - fallback only
]
SERIES_COLORS_HEX = [f"rgb({r},{g},{b})" for r, g, b in SERIES_COLORS_RGB]
SELECTED_PEAK_COLOR_RGB = (235, 68, 68)
ENVELOPE_IMAGE_MAX_POINTS = 8_000
POWER_METRIC_MAX_POINTS = 12_000
POWER_PLOT_MAX_POINTS = 12_000

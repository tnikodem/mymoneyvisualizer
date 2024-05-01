from mymoneyvisualizer.naming import Naming as nn

GREY_BACKGROUND_COLOR = (123, 123, 123)
DEFAULT_BACKGROUND_COLOR = (255, 255, 255)
GREEN_BACKGROUND_COLOR = (203, 255, 179)
RED_BACKGROUND_COLOR = (255, 122, 111)

PLOT_COLORS = {nn.basic: [
    (246, 112, 136),  # Soft pink
    (219, 136, 49),   # Warm orange
    (173, 156, 49),   # Muted yellow
    (119, 170, 49),   # Earthy green
    (51, 176, 122),   # Refreshing teal
    (53, 172, 164),   # Cool turquoise
    (56, 168, 197),   # Serene blue
    (110, 154, 244),  # Sky-blue
    (204, 121, 244),  # Lavender-purple
    (245, 101, 204)   # Vibrant magenta
],
    nn.optional: [
    (246, 112, 136),  # Soft pink
    (219, 136, 49),   # Warm orange
    (173, 156, 49),   # Muted yellow
    (119, 170, 49),   # Earthy green
    (51, 176, 122),   # Refreshing teal
    (53, 172, 164),   # Cool turquoise
    (56, 168, 197),   # Serene blue
    (110, 154, 244),  # Sky-blue
    (204, 121, 244),  # Lavender-purple
    (245, 101, 204)   # Vibrant magenta
], }


DEFAULT_SETTINGS = {
    "exclude_tags": [],
    nn.budget: {
        nn.basic: {
            "factor": 0.3,
            "start": 2018,
            "end": 2018,
        },
        nn.optional: {
            "factor": 0.5,
            "start": 2018,
            "end": 2018,
        }
    },
    "plot_aggregation_month": 1,
}

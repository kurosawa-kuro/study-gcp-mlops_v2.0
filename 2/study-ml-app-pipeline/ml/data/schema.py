"""Project schema constants."""

FEATURE_COLS = [
    "MedInc",
    "HouseAge",
    "AveRooms",
    "AveBedrms",
    "Population",
    "AveOccup",
    "Latitude",
    "Longitude",
]

ENGINEERED_COLS = [
    "BedroomRatio",
    "RoomsPerPerson",
]

MODEL_COLS = FEATURE_COLS + ENGINEERED_COLS
TARGET_COL = "Price"

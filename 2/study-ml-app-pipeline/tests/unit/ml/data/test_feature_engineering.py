"""Feature engineering tests."""

from ml.data.feature_engineering import engineer_features, engineer_features_input


def test_engineer_features_adds_columns(sample_df):
    result = engineer_features(sample_df)
    assert "BedroomRatio" in result.columns
    assert "RoomsPerPerson" in result.columns


def test_engineer_features_input_adds_columns():
    values = {
        "MedInc": 8.3,
        "HouseAge": 41,
        "AveRooms": 6.9,
        "AveBedrms": 1.0,
        "Population": 322,
        "AveOccup": 2.5,
        "Latitude": 37.88,
        "Longitude": -122.23,
    }
    result = engineer_features_input(values)
    assert "BedroomRatio" in result
    assert "RoomsPerPerson" in result

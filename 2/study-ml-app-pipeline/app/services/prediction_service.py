from ml.serving.inference import predict_price as predict_price_from_booster


def predict_price(booster, values: dict) -> float:
    return predict_price_from_booster(booster, values)

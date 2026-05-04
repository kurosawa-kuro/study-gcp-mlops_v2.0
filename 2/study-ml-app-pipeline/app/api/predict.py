from fastapi import APIRouter, Request

from app.schemas.predict import PredictRequest

router = APIRouter()


@router.post("/predict")
def predict(request: Request, req: PredictRequest):
    container = request.app.state.container
    price = container.predictor.predict(req.model_dump())
    return {"predicted_price": price}


@router.get("/health")
def health():
    return {"status": "ok"}

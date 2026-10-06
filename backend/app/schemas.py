from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=72)


class UserLogin(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=72)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProductResponse(BaseModel):
    sku: str
    name: str
    description: str
    quantity: int
    available_date: str | None = None
    price: float


class CartAddRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=1000)


class CartItemResponse(BaseModel):
    sku: str
    name: str
    quantity: int
    unit_price: float
    line_total: float


class CartResponse(BaseModel):
    items: list[CartItemResponse]
    item_count: int
    total: float


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str


class OrderResponse(BaseModel):
    order_id: str
    total: float
    item_count: int


class OrderSummary(BaseModel):
    order_id: str
    order_date: str | None = None
    total: float
    item_count: int
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any
from xml.etree import ElementTree as ET

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from .ai_agent import AIAgent
from .auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash,
)
from .cart import CartService
from .database import Base, engine, get_db
from .models import User
from .orders import ORDERS_DIR, save_order_to_xml
from .schemas import (
    CartAddRequest,
    CartResponse,
    ChatRequest,
    ChatResponse,
    OrderResponse,
    OrderSummary,
    ProductResponse,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
)
from .stock import StockService

logger = logging.getLogger(__name__)

stock_service = StockService()
cart_service = CartService()
agent = AIAgent(stock_service, cart_service)


def create_db_and_tables() -> None:
    Base.metadata.create_all(bind=engine)


async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    create_db_and_tables()
    yield


app = FastAPI(title="Sales Chatbot API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def list_orders_for(email: str) -> list[dict[str, Any]]:
    """Return order summaries from the orders folder for one customer."""
    if not ORDERS_DIR.is_dir():
        return []

    summaries = []
    for path in sorted(ORDERS_DIR.glob("*.xml")):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            logger.warning("Skipping unreadable order file %s", path.name)
            continue

        if (root.findtext("customer/email") or "").strip().casefold() != email.strip().casefold():
            continue

        summaries.append(
            {
                "order_id": root.findtext("order_id") or path.stem,
                "order_date": root.findtext("order_date"),
                "total": float(root.findtext("total") or 0),
                "item_count": len(root.findall("items/item")),
            }
        )

    summaries.sort(key=lambda order: order["order_date"] or "", reverse=True)
    return summaries


@app.post(
    "/api/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: UserCreate, db: Annotated[Session, Depends(get_db)]) -> User:
    email = payload.email.strip().lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(email=email, hashed_password=get_password_hash(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/auth/login", response_model=Token)
def login(payload: UserLogin, db: Annotated[Session, Depends(get_db)]) -> Token:
    user = authenticate_user(db, payload.email.strip().lower(), payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Token(access_token=create_access_token(user.email))


@app.get("/api/auth/me", response_model=UserResponse)
def read_current_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user


@app.get("/api/products", response_model=list[ProductResponse])
def list_products(
    current_user: Annotated[User, Depends(get_current_user)],
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> list[ProductResponse]:
    """List the catalogue, optionally filtered by a search query."""
    products = (
        stock_service.search_products(q) if q else stock_service.get_all_products()
    )
    return [ProductResponse.model_validate(product) for product in products]


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ChatResponse:
    """Send a message to the sales assistant on behalf of the current user."""
    try:
        reply = agent.chat(
            user_id=current_user.id,
            message=payload.message,
            user_email=current_user.email,
        )
    except RuntimeError:
        logger.exception("Chat request failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI assistant is not configured.",
        )
    return ChatResponse(reply=reply)


@app.get("/api/cart", response_model=CartResponse)
def read_cart(current_user: Annotated[User, Depends(get_current_user)]) -> CartResponse:
    """Return the current user's cart and total."""
    items = cart_service.get_cart(current_user.id)
    return CartResponse(
        items=items,
        item_count=len(items),
        total=cart_service.get_cart_total(current_user.id),
    )


@app.post("/api/cart/add", response_model=CartResponse)
def add_to_cart(
    payload: CartAddRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> CartResponse:
    """Add a product to the current user's cart, checking stock first."""
    product = stock_service.get_product_by_sku(payload.sku)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No product found with SKU {payload.sku}",
        )

    in_stock = product["quantity"] or 0
    if in_stock <= 0:
        detail = f"{product['name']} is out of stock."
        if product["available_date"]:
            detail += f" Next delivery is {product['available_date']}."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    already = sum(
        item["quantity"]
        for item in cart_service.get_cart(current_user.id)
        if item["sku"] == product["sku"]
    )
    if already + payload.quantity > in_stock:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only {in_stock} in stock, {already} already in the cart.",
        )

    items = cart_service.add_item(current_user.id, product["sku"], payload.quantity, product)
    return CartResponse(
        items=items,
        item_count=len(items),
        total=cart_service.get_cart_total(current_user.id),
    )


@app.post("/api/order", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def place_order(current_user: Annotated[User, Depends(get_current_user)]) -> OrderResponse:
    """Write the current user's cart to an order file and empty the cart."""
    items = cart_service.get_cart(current_user.id)
    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The cart is empty, there is nothing to order.",
        )

    total = cart_service.get_cart_total(current_user.id)
    path = save_order_to_xml(current_user.email, items, total)
    cart_service.clear_cart(current_user.id)

    return OrderResponse(
        order_id=Path(path).stem,
        total=total,
        item_count=len(items),
    )


@app.get("/api/orders/history", response_model=list[OrderSummary])
def order_history(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[OrderSummary]:
    """List the orders belonging to the current user, newest first."""
    return [OrderSummary.model_validate(order) for order in list_orders_for(current_user.email)]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
"""OpenAI function-calling sales agent.

The agent owns no conversation state: stock, cart and order work is delegated to
:class:`~app.stock.StockService`, :class:`~app.cart.CartService` and
:func:`~app.orders.save_order_to_xml`, which must be injected as shared
instances so carts survive between requests.
"""

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .cart import CartService
from .orders import save_order_to_xml
from .stock import StockService

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = """You are a helpful sales assistant for an online store that \
sells computer accessories: mice, keyboards, USB-C hubs, laptop stands, webcams \
and similar products.

Rules:
- Always use the provided tools to look up products, prices, stock levels and \
the cart. Never invent a product, price, or availability.
- Quote prices exactly as the tools report them, and say when a product is out \
of stock, including its next available delivery date.
- Before adding to the cart, confirm the product and quantity with the customer.
- Only call place_order after the customer has explicitly confirmed the order. \
Summarise what is in the cart and the total first.
- Keep replies short and conversational. Reply in the same language the customer \
uses.
"""

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search the product catalogue by keyword. Matches product "
            "names and descriptions. Use this whenever the customer asks about "
            "products, prices or availability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords to search for, e.g. 'wireless mouse'.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a quantity of one product to the customer's cart. "
            "The SKU must come from a previous search_products call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "Product SKU, e.g. ACC-1001."},
                    "quantity": {"type": "integer", "description": "How many to add."},
                },
                "required": ["sku", "quantity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_cart",
            "description": "Return the current cart contents and total for the customer.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "place_order",
            "description": "Place the order for the current cart and clear it. "
            "Only call this after the customer has confirmed the order.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


class AIAgent:
    """Answer customer messages by calling the store tools through OpenAI."""

    def __init__(
        self,
        stock_service: StockService,
        cart_service: CartService,
        client: OpenAI | None = None,
    ) -> None:
        """Store the shared services and optionally a preconfigured OpenAI client."""
        self.stock = stock_service
        self.cart = cart_service
        self._client = client
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    @property
    def client(self) -> OpenAI:
        """Return the OpenAI client, creating it on first use."""
        if self._client is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY is not set. Add it to backend/.env to enable the assistant."
                )
            self._client = OpenAI(api_key=api_key, base_url=os.getenv("BASE_URL", "https://api.groq.com/openai/v1"))
        return self._client

    def chat(
        self,
        user_id: int,
        message: str,
        user_email: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Send a customer message to the model and return its reply.

        Args:
            user_id: Identifies whose cart the tools operate on.
            message: The customer's latest message.
            user_email: Customer email, required to write the order file.
            history: Optional prior turns as OpenAI-style messages.

        Returns:
            The assistant's natural language reply.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": message})

        for _ in range(MAX_TOOL_ROUNDS):
            reply = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
            ).choices[0].message

            messages.append(reply.model_dump(exclude_none=True))

            if not reply.tool_calls:
                return reply.content or ""

            for call in reply.tool_calls:
                result = self._run_tool(call.function.name, call.function.arguments, user_id, user_email)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, default=str),
                    }
                )

        return "I could not complete that request. Please try again."

    def _run_tool(
        self, name: str, raw_arguments: str, user_id: int, user_email: str | None
    ) -> Any:
        """Execute one tool call and return a JSON-serialisable result."""
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return {"error": "Tool arguments were not valid JSON."}

        if not isinstance(arguments, dict):
            return {"error": "Tool arguments must be a JSON object."}

        try:
            if name == "search_products":
                return self._search_products(str(arguments.get("query", "")))
            if name == "add_to_cart":
                return self._add_to_cart(
                    user_id, str(arguments.get("sku", "")), arguments.get("quantity", 1)
                )
            if name == "view_cart":
                return self._view_cart(user_id)
            if name == "place_order":
                return self._place_order(user_id, user_email)
        except (KeyError, TypeError, ValueError) as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

        return {"error": f"Unknown tool: {name}"}

    def _search_products(self, query: str) -> dict[str, Any]:
        """Search the catalogue and return a compact product list."""
        products = self.stock.search_products(query)
        if not products:
            return {
                "found": False,
                "count": 0,
                "products": [],
                "message": f"No products matched {query!r}.",
            }
        return {
            "found": True,
            "count": len(products),
            "products": [self._brief(p) for p in products],
        }

    def _brief(self, product: dict[str, Any]) -> dict[str, Any]:
        """Reduce a stock row to the fields the model needs."""
        return {
            "sku": product["sku"],
            "name": product["name"],
            "description": product["description"],
            "price": product["price"],
            "in_stock": bool(product["quantity"] and product["quantity"] > 0),
            "available_date": product["available_date"],
        }

    def _add_to_cart(self, user_id: int, sku: str, quantity: Any) -> dict[str, Any]:
        """Add a product to the cart after checking it exists and is in stock."""
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return {"error": "Quantity must be a whole number."}

        if quantity < 1:
            return {"error": "Quantity must be at least 1."}

        product = self.stock.get_product_by_sku(sku)
        if product is None:
            return {"error": f"No product found with SKU {sku!r}."}

        in_stock = product["quantity"] or 0
        if in_stock <= 0:
            message = f"{product['name']} is out of stock."
            if product["available_date"]:
                message += f" Next delivery is {product['available_date']}."
            return {"error": message, "sku": product["sku"], "available_date": product["available_date"]}

        already = sum(
            item["quantity"] for item in self.cart.get_cart(user_id) if item["sku"] == product["sku"]
        )
        if already + quantity > in_stock:
            return {
                "error": f"Only {in_stock} in stock, {already} already in the cart.",
                "available": in_stock,
                "in_cart": already,
            }

        cart = self.cart.add_item(user_id, product["sku"], quantity, product)
        return {
            "added": quantity,
            "sku": product["sku"],
            "name": product["name"],
            "cart": cart,
            "cart_total": self.cart.get_cart_total(user_id),
        }

    def _view_cart(self, user_id: int) -> dict[str, Any]:
        """Return the customer's cart and its total."""
        cart = self.cart.get_cart(user_id)
        return {
            "items": cart,
            "item_count": len(cart),
            "total": self.cart.get_cart_total(user_id),
        }

    def _place_order(self, user_id: int, user_email: str | None) -> dict[str, Any]:
        """Write the order file and clear the cart."""
        cart = self.cart.get_cart(user_id)
        if not cart:
            return {"error": "The cart is empty, there is nothing to order."}
        if not user_email:
            return {"error": "The customer's email address is required to place an order."}

        total = self.cart.get_cart_total(user_id)
        path = save_order_to_xml(user_email, cart, total)
        self.cart.clear_cart(user_id)

        return {
            "order_id": Path(path).stem,
            "total": total,
            "item_count": len(cart),
            "file": path,
        }
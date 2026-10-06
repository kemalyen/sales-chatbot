"""In-memory shopping carts keyed by authenticated user id.

Carts live in process memory only: they are lost on restart and are not shared
between workers. That is fine for local development and a single-worker
deployment, but a real deployment needs a shared store (database or Redis).
"""

from typing import Any

CartItem = dict[str, Any]
Cart = list[CartItem]


class CartService:
    """Hold one cart per user id and compute cart totals."""

    def __init__(self) -> None:
        """Start with no carts."""
        self._carts: dict[int, Cart] = {}

    def _copy(self, cart: Cart) -> Cart:
        """Return a copy of the cart so callers cannot mutate stored items."""
        return [dict(item) for item in cart]

    def get_cart(self, user_id: int) -> Cart:
        """Return a copy of the user's cart, or an empty list if there is none."""
        return self._copy(self._carts.get(user_id, []))

    def add_item(
        self, user_id: int, sku: str, quantity: int, product: dict[str, Any]
    ) -> Cart:
        """Add ``quantity`` of ``sku`` to the cart and return the updated cart.

        ``product`` is a stock row and supplies the name and unit price. If the
        SKU is already in the cart the quantities are merged into one line.
        """
        if quantity < 1:
            raise ValueError("quantity must be at least 1")

        name = str(product["name"])
        unit_price = round(float(product["price"]), 2)
        cart = self._carts.setdefault(user_id, [])

        for item in cart:
            if item["sku"] == sku:
                item["quantity"] += quantity
                item["line_total"] = round(item["unit_price"] * item["quantity"], 2)
                return self._copy(cart)

        cart.append(
            {
                "sku": sku,
                "name": name,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": round(unit_price * quantity, 2),
            }
        )
        return self._copy(cart)

    def clear_cart(self, user_id: int) -> None:
        """Remove the user's cart. Unknown user ids are ignored."""
        self._carts.pop(user_id, None)

    def get_cart_total(self, user_id: int) -> float:
        """Return the sum of the user's line totals, rounded to 2 decimals."""
        total = sum(item["line_total"] for item in self._carts.get(user_id, []))
        return round(float(total), 2)
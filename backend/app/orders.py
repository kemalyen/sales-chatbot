"""Write a confirmed order to an XML file in the ``orders`` folder.

Each order is stored as its own document, named ``ORD-<YYYYMMDD>-<HHMMSS>.xml``.
"""

from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

ORDERS_DIR = Path(__file__).resolve().parents[1] / "orders"


def _next_order_id(directory: Path) -> str:
    """Return an order id for this second that does not collide with a saved order."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = f"ORD-{stamp}"
    suffix = 1
    while (directory / f"{candidate}.xml").exists():
        suffix += 1
        candidate = f"ORD-{stamp}-{suffix}"
    return candidate


def save_order_to_xml(
    user_email: str, cart_items: list, total: float
) -> str:
    """Save an order as XML and return the full path to the saved file.

    Args:
        user_email: Email of the customer who placed the order.
        cart_items: Cart lines, each with sku, name, quantity, unit_price
            and line_total.
        total: Order total in the same currency as the line totals.

    Returns:
        Full path of the written XML file.
    """
    ORDERS_DIR.mkdir(parents=True, exist_ok=True)
    order_id = _next_order_id(ORDERS_DIR)

    root = ET.Element("order")
    ET.SubElement(root, "order_id").text = order_id
    customer = ET.SubElement(root, "customer")
    ET.SubElement(customer, "email").text = user_email
    ET.SubElement(root, "order_date").text = datetime.now(timezone.utc).isoformat()

    items = ET.SubElement(root, "items")
    for cart_item in cart_items:
        item = ET.SubElement(items, "item")
        ET.SubElement(item, "sku").text = str(cart_item["sku"])
        ET.SubElement(item, "name").text = str(cart_item["name"])
        ET.SubElement(item, "quantity").text = str(cart_item["quantity"])
        ET.SubElement(item, "unit_price").text = f"{float(cart_item['unit_price']):.2f}"
        ET.SubElement(item, "line_total").text = f"{float(cart_item['line_total']):.2f}"

    ET.SubElement(root, "total").text = f"{float(total):.2f}"

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")

    path = ORDERS_DIR / f"{order_id}.xml"
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return str(path)
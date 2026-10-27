from decimal import Decimal

import pytest

from orders.catalog import Catalog, Product, Variant


@pytest.fixture
def catalog() -> Catalog:
    catalog = Catalog()
    shirt = Product("shirt", "Linen shirt")
    for size in ["S", "M"]:
        sku = f"SHIRT-{size}"
        shirt.variants[sku] = Variant(sku, "shirt", size, Decimal("20.00"), Decimal("0.30"), 5)
    mug = Product("mug", "Stoneware mug")
    mug.variants["MUG"] = Variant("MUG", "mug", "Blue", Decimal("12.50"), Decimal("0.50"), 10)
    kettle = Product("kettle", "Steel kettle")
    kettle.variants["KETTLE"] = Variant(
        "KETTLE", "kettle", "Steel", Decimal("49.90"), Decimal("2.00"), 2
    )
    for product in (shirt, mug, kettle):
        catalog.add_product(product)
    return catalog

/**
 * Example snippets shipped with the interface.
 *
 * Every example was executed against the local mock provider on this machine:
 * the run completes with an `approved` verdict and the paired test file passes
 * in the isolated sandbox. The tests import from `solution` because the
 * sandbox stores the candidate under that module name.
 *
 * The two rule-driven examples (`long-function`, `mutable-default`) also
 * produce a real deterministic transformation, so their diff tab shows the
 * change; the nesting example exercises the guarded-condition merge.
 */

export interface Preset {
  id: string;
  title: string;
  /** The smell the analyzer is expected to report for this snippet. */
  rule: string;
  description: string;
  code: string;
  testCode: string;
}

export const PRESETS: Preset[] = [
  {
    id: 'long-function',
    title: 'Long function — extract helpers',
    rule: 'long-function',
    description:
      'A 40-line pricing routine that mixes accumulation, branching and formatting. The pipeline extracts the repeated blocks into helpers.',
    code: `def summarize_cart(cart):
    """Compute totals for a shopping cart."""
    subtotal = 0
    item_count = 0
    discount_total = 0
    tax_total = 0
    savings = 0
    free_shipping = False
    for item in cart:
        price = item["price"]
        quantity = item["quantity"]
        line_total = price * quantity
        subtotal += line_total
        item_count += quantity
        if item.get("on_sale"):
            savings += price * 0.1 * quantity
        if item.get("bundle"):
            discount_total += price * 0.05 * quantity
    taxable = subtotal - discount_total - savings
    tax_total = taxable * 0.2
    if taxable > 100:
        free_shipping = True
    return {
        "subtotal": subtotal,
        "tax": tax_total,
        "discount": discount_total,
        "savings": savings,
        "items": item_count,
        "free_shipping": free_shipping,
    }
`,
    testCode: `from solution import summarize_cart


def test_summarize_cart_totals():
    cart = [
        {"price": 10.0, "quantity": 2},
        {"price": 5.0, "quantity": 1, "on_sale": True},
    ]
    summary = summarize_cart(cart)
    assert summary["subtotal"] == 25.0
    assert summary["items"] == 3
    assert summary["tax"] > 0
    assert summary["free_shipping"] is False


def test_summarize_cart_free_shipping():
    cart = [{"price": 60.0, "quantity": 2}]
    summary = summarize_cart(cart)
    assert summary["free_shipping"] is True
`,
  },
  {
    id: 'deep-nesting',
    title: 'Deep nesting — flatten branches',
    rule: 'deep-nesting',
    description:
      'Four levels of nested conditionals inside a routing function. The pipeline merges the nested conditionals into a single guarded condition.',
    code: `def route_order(order):
    """Decide how an order should be handled."""
    if order["total"] > 100:
        if order["customer"]["vip"]:
            if order["paid"]:
                if order["fast"]:
                    return "vip-fast-paid"
                return "vip-paid"
    return "review"
`,
    testCode: `from solution import route_order


def test_route_order_fast_vip():
    order = {"total": 200, "paid": True, "fast": True, "customer": {"vip": True}}
    assert route_order(order) == "vip-fast-paid"


def test_route_order_vip_paid():
    order = {"total": 200, "paid": True, "fast": False, "customer": {"vip": True}}
    assert route_order(order) == "vip-paid"


def test_route_order_review():
    order = {"total": 10, "paid": False, "fast": False, "customer": {"vip": False}}
    assert route_order(order) == "review"
`,
  },
  {
    id: 'mutable-default',
    title: 'Mutable default argument — fix shared state',
    rule: 'mutable-default-arg',
    description:
      'A collector that accumulates into its default list, so state leaks between calls. The pipeline rewrites the default to None.',
    code: `def collect_tags(tag, seen=[]):
    """Collect tags, remembering the ones seen before."""
    seen.append(tag)
    return seen


def merge_tags(*groups):
    """Merge several tag groups into one."""
    merged = []
    for group in groups:
        for tag in group:
            merged = collect_tags(tag, merged)
    return merged
`,
    testCode: `from solution import collect_tags, merge_tags


def test_collect_tags_does_not_share_state():
    first = collect_tags("a")
    second = collect_tags("b")
    assert first == ["a"]
    assert second == ["b"]


def test_merge_tags_keeps_every_tag():
    assert merge_tags(["a", "b"], ["c"]) == ["a", "b", "c"]
`,
  },
];

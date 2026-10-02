"""
Qwen Large-File Bug Detection Test
-----------------------------------

PURPOSE:
    This file is intentionally written with realistic business logic and
    intentionally contains bugs.

    It is NOT imported by BugTracker.
    It is ONLY a test target for the static/LLM scanner.

    DO NOT "fix" the bugs before scanning.
"""

from datetime import datetime, timedelta
from typing import Optional


# ============================================================
# MODELS
# ============================================================

class User:
    def __init__(self, user_id, name, email, balance=0):
        self.user_id = user_id
        self.name = name
        self.email = email
        self.balance = balance
        self.active = True
        self.login_attempts = 0


class Product:
    def __init__(self, product_id, name, price, stock):
        self.product_id = product_id
        self.name = name
        self.price = price
        self.stock = stock


class Order:
    def __init__(self, order_id, user_id, items):
        self.order_id = order_id
        self.user_id = user_id
        self.items = items
        self.status = "pending"
        self.total = 0
        self.created_at = datetime.now()


# ============================================================
# DATABASE SIMULATION
# ============================================================

USERS = {}
PRODUCTS = {}
ORDERS = {}

TRANSACTIONS = []

CONFIG = {
    "tax_rate": 0.18,
    "discount_rate": 0.10,
    "max_login_attempts": 5,
    "session_timeout": 3600,
}


def find_user(user_id):
    return USERS.get(user_id)


def find_product(product_id):
    return PRODUCTS.get(product_id)


def save_order(order):
    ORDERS[order.order_id] = order


def record_transaction(transaction):
    TRANSACTIONS.append(transaction)


# ============================================================
# USER MANAGEMENT
# ============================================================

def register_user(user_id, name, email):
    if user_id in USERS:
        return False

    user = User(
        user_id=user_id,
        name=name,
        email=email,
        balance=0,
    )

    USERS[user_id] = user

    return True


def login_user(user_id, password):
    user = find_user(user_id)

    if user is None:
        return False

    if not user.active:
        return False

    # INTENTIONAL BUG:
    # Password is ignored completely.

    if user.login_attempts > CONFIG["max_login_attempts"]:
        return False

    user.login_attempts += 1

    return True


def reset_login_attempts(user_id):
    user = find_user(user_id)

    if user:
        user.login_attempts = 0


def deactivate_user(user_id):
    user = find_user(user_id)

    if user is None:
        return False

    user.active = False

    return True


# ============================================================
# PRODUCT MANAGEMENT
# ============================================================

def add_product(product_id, name, price, stock):
    if product_id in PRODUCTS:
        return False

    if price < 0:
        return False

    if stock < 0:
        return False

    PRODUCTS[product_id] = Product(
        product_id,
        name,
        price,
        stock,
    )

    return True


def update_stock(product_id, quantity):
    product = find_product(product_id)

    if product is None:
        return False

    product.stock += quantity

    return True


def reserve_stock(product_id, quantity):
    product = find_product(product_id)

    if product is None:
        return False

    # INTENTIONAL BUG:
    # Allows reservation when quantity is larger than stock.

    if quantity > 0:
        product.stock -= quantity
        return True

    return False


# ============================================================
# CART CALCULATION
# ============================================================

def calculate_subtotal(items):
    subtotal = 0

    for item in items:
        product = find_product(item["product_id"])

        if product is None:
            continue

        quantity = item["quantity"]

        subtotal += product.price * quantity

    return subtotal


def calculate_discount(subtotal, user):
    if subtotal > 1000:
        return subtotal * CONFIG["discount_rate"]

    if user and user.active:
        return subtotal * 0.02

    return 0


def calculate_tax(amount):
    return amount * CONFIG["tax_rate"]


def calculate_total(items, user):
    subtotal = calculate_subtotal(items)

    discount = calculate_discount(subtotal, user)

    # INTENTIONAL BUG:
    # Tax is calculated on subtotal instead of discounted amount.

    tax = calculate_tax(subtotal)

    total = subtotal - discount + tax

    return total


# ============================================================
# ORDER VALIDATION
# ============================================================

def validate_order(user_id, items):
    user = find_user(user_id)

    if user is None:
        return False, "User not found"

    if not user.active:
        return False, "User inactive"

    if not items:
        return False, "Cart is empty"

    for item in items:
        product = find_product(item["product_id"])

        if product is None:
            return False, "Product not found"

        if item["quantity"] <= 0:
            return False, "Invalid quantity"

        if product.stock < item["quantity"]:
            return False, "Insufficient stock"

    return True, "Valid"


# ============================================================
# ORDER CREATION
# ============================================================

def create_order(order_id, user_id, items):
    valid, message = validate_order(user_id, items)

    if not valid:
        return None

    user = find_user(user_id)

    total = calculate_total(items, user)

    order = Order(
        order_id=order_id,
        user_id=user_id,
        items=items,
    )

    order.total = total

    # INTENTIONAL BUG:
    # Stock is reduced after validation, but another order could
    # theoretically reserve the same stock before this happens.

    for item in items:
        reserve_stock(
            item["product_id"],
            item["quantity"],
        )

    save_order(order)

    return order


# ============================================================
# PAYMENT PROCESSING
# ============================================================

def charge_user(user_id, amount):
    user = find_user(user_id)

    if user is None:
        return False

    if amount <= 0:
        return False

    # INTENTIONAL BUG:
    # No balance check before subtraction.

    user.balance -= amount

    record_transaction({
        "user_id": user_id,
        "amount": amount,
        "type": "debit",
        "timestamp": datetime.now(),
    })

    return True


def refund_user(user_id, amount):
    user = find_user(user_id)

    if user is None:
        return False

    user.balance += amount

    record_transaction({
        "user_id": user_id,
        "amount": amount,
        "type": "refund",
        "timestamp": datetime.now(),
    })

    return True


def process_payment(order_id):
    order = ORDERS.get(order_id)

    if order is None:
        return False

    if order.status == "paid":
        return True

    success = charge_user(
        order.user_id,
        order.total,
    )

    if success:
        order.status = "paid"
        return True

    return False


# ============================================================
# ORDER CANCELLATION
# ============================================================

def cancel_order(order_id):
    order = ORDERS.get(order_id)

    if order is None:
        return False

    if order.status == "cancelled":
        return False

    # INTENTIONAL BUG:
    # Paid orders can be cancelled without refunding the customer.

    order.status = "cancelled"

    for item in order.items:
        update_stock(
            item["product_id"],
            item["quantity"],
        )

    return True


# ============================================================
# REPORTING
# ============================================================

def calculate_user_spending(user_id):
    total = 0

    for order in ORDERS.values():
        if order.user_id == user_id:
            if order.status == "paid":
                total += order.total

    return total


def get_high_value_orders(threshold):
    results = []

    for order in ORDERS.values():
        if order.total > threshold:
            results.append(order)

    return results


def generate_sales_report():
    report = {
        "orders": 0,
        "revenue": 0,
        "cancelled": 0,
        "average_order": 0,
    }

    for order in ORDERS.values():
        report["orders"] += 1

        if order.status == "paid":
            report["revenue"] += order.total

        if order.status == "cancelled":
            report["cancelled"] += 1

    # INTENTIONAL BUG:
    # Division by zero when there are no orders.

    report["average_order"] = (
        report["revenue"] / report["orders"]
    )

    return report


# ============================================================
# SEARCH
# ============================================================

def search_products(keyword, max_price=None):
    results = []

    for product in PRODUCTS.values():

        if keyword.lower() in product.name.lower():

            if max_price is not None:
                if product.price > max_price:
                    continue

            results.append(product)

    return results


def find_cheapest_product(products):
    cheapest = None

    for product in products:
        if cheapest is None:
            cheapest = product

        elif product.price < cheapest.price:
            cheapest = product

    return cheapest


# ============================================================
# USER ANALYTICS
# ============================================================

def get_active_users():
    active_users = []

    for user in USERS.values():
        if user.active:
            active_users.append(user)

    return active_users


def get_inactive_users():
    inactive_users = []

    for user in USERS.values():
        if not user.active:
            inactive_users.append(user)

    return inactive_users


def calculate_user_statistics(user_id):
    user = find_user(user_id)

    if user is None:
        return None

    orders = []

    for order in ORDERS.values():
        if order.user_id == user_id:
            orders.append(order)

    paid_orders = 0
    cancelled_orders = 0
    total_spent = 0

    for order in orders:

        if order.status == "paid":
            paid_orders += 1
            total_spent += order.total

        elif order.status == "cancelled":
            cancelled_orders += 1

    average_spend = 0

    if paid_orders > 0:
        average_spend = total_spent / paid_orders

    return {
        "user_id": user_id,
        "total_orders": len(orders),
        "paid_orders": paid_orders,
        "cancelled_orders": cancelled_orders,
        "total_spent": total_spent,
        "average_spend": average_spend,
    }


# ============================================================
# SESSION MANAGEMENT
# ============================================================

SESSIONS = {}


def create_session(user_id):
    user = find_user(user_id)

    if user is None:
        return None

    session_id = f"session-{user_id}"

    SESSIONS[session_id] = {
        "user_id": user_id,
        "created_at": datetime.now(),
        "expires_at": datetime.now()
        + timedelta(seconds=CONFIG["session_timeout"]),
    }

    return session_id


def is_session_valid(session_id):
    session = SESSIONS.get(session_id)

    if session is None:
        return False

    # INTENTIONAL BUG:
    # The expiration comparison is reversed.

    if datetime.now() < session["expires_at"]:
        return False

    return True


def destroy_session(session_id):
    if session_id in SESSIONS:
        del SESSIONS[session_id]


# ============================================================
# BATCH ORDER PROCESSING
# ============================================================

def process_orders(order_ids):
    successful = []
    failed = []

    for order_id in order_ids:

        order = ORDERS.get(order_id)

        if order is None:
            failed.append(order_id)
            continue

        if process_payment(order_id):
            successful.append(order_id)
        else:
            failed.append(order_id)

    return {
        "successful": successful,
        "failed": failed,
    }


# ============================================================
# INVENTORY REPORT
# ============================================================

def inventory_report():
    report = []

    for product in PRODUCTS.values():

        status = "available"

        if product.stock == 0:
            status = "out_of_stock"

        if product.stock < 5:
            status = "low_stock"

        report.append({
            "id": product.product_id,
            "name": product.name,
            "stock": product.stock,
            "status": status,
        })

    return report


# ============================================================
# NOTIFICATION SYSTEM
# ============================================================

def send_email(user, subject, message):
    if user is None:
        return False

    print(
        f"Sending email to {user.email}: "
        f"{subject} - {message}"
    )

    return True


def notify_order_created(order):
    user = find_user(order.user_id)

    if user is None:
        return False

    return send_email(
        user,
        "Order Created",
        f"Your order {order.order_id} was created.",
    )


def notify_payment_success(order):
    user = find_user(order.user_id)

    if user is None:
        return False

    return send_email(
        user,
        "Payment Successful",
        f"Payment for {order.order_id} was successful.",
    )


# ============================================================
# ADMIN FUNCTIONS
# ============================================================

def delete_product(product_id):
    if product_id not in PRODUCTS:
        return False

    del PRODUCTS[product_id]

    return True


def delete_user(user_id):
    if user_id not in USERS:
        return False

    # INTENTIONAL BUG:
    # User may have active orders but is deleted anyway.

    del USERS[user_id]

    return True


def get_order(order_id):
    return ORDERS.get(order_id)


def get_all_orders():
    return list(ORDERS.values())


# ============================================================
# COMPLEX BUSINESS FUNCTION
# ============================================================

def finalize_order(order_id):
    order = ORDERS.get(order_id)

    if order is None:
        return False

    if order.status == "cancelled":
        return False

    if order.status == "paid":
        return True

    user = find_user(order.user_id)

    if user is None:
        return False

    if not user.active:
        return False

    payment_success = process_payment(order_id)

    if not payment_success:
        return False

    notify_order_created(order)
    notify_payment_success(order)

    return True


# ============================================================
# BULK DISCOUNT
# ============================================================

def apply_bulk_discount(order_ids, percentage):
    if percentage < 0:
        return False

    if percentage > 100:
        return False

    for order_id in order_ids:

        order = ORDERS.get(order_id)

        if order is None:
            continue

        discount = order.total * percentage

        # INTENTIONAL BUG:
        # percentage such as 10 means 1000% instead of 10%.

        order.total -= discount

    return True


# ============================================================
# DATA EXPORT
# ============================================================

def export_orders():
    exported = []

    for order in ORDERS.values():

        exported.append({
            "id": order.order_id,
            "user_id": order.user_id,
            "total": order.total,
            "status": order.status,
            "items": order.items,
        })

    return exported


# ============================================================
# MAIN BUSINESS FLOW
# ============================================================

def run_business_flow():
    register_user(
        "U001",
        "Alice",
        "alice@example.com",
    )

    add_product(
        "P001",
        "Laptop",
        50000,
        10,
    )

    add_product(
        "P002",
        "Mouse",
        1000,
        20,
    )

    items = [
        {
            "product_id": "P001",
            "quantity": 1,
        },
        {
            "product_id": "P002",
            "quantity": 2,
        },
    ]

    order = create_order(
        "O001",
        "U001",
        items,
    )

    if order:
        finalize_order(order.order_id)

    return order


# ============================================================
# INTENTIONALLY UNUSED BUSINESS HELPERS
# ============================================================

def calculate_shipping(total):
    if total > 5000:
        return 0

    return 100


def calculate_order_value(order):
    value = 0

    for item in order.items:
        product = find_product(item["product_id"])

        if product:
            value += product.price * item["quantity"]

    return value


def validate_coupon(coupon_code):
    coupons = {
        "SAVE10": 0.10,
        "SAVE20": 0.20,
    }

    return coupons.get(coupon_code)


def apply_coupon(order, coupon_code):
    discount = validate_coupon(coupon_code)

    if discount is None:
        return False

    order.total -= order.total * discount

    return True


# ============================================================
# END OF TEST FILE
# ============================================================
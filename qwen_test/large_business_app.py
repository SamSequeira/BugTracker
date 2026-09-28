"""
Large Business Logic Test File
================================

Purpose:
    Stress-test a local coding LLM on a single Python source file.

Domain:
    E-commerce / order management / payments / inventory / discounts /
    shipping / loyalty / reporting.

IMPORTANT:
    This file intentionally contains several semantic bugs.
    They are NOT marked inside the code.

The code is intentionally verbose and repetitive so that the model has
to reason about relationships between different parts of the file.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Tuple
import hashlib
import uuid
import math
import json
import logging
import time
import random


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class Customer:
    id: str
    name: str
    email: str
    country: str
    currency: str
    loyalty_points: int = 0
    lifetime_spend: Decimal = Decimal("0")
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Product:
    id: str
    name: str
    category: str
    price: Decimal
    cost_price: Decimal
    stock: int
    reserved_stock: int = 0
    active: bool = True


@dataclass
class CartItem:
    product_id: str
    quantity: int


@dataclass
class Cart:
    id: str
    customer_id: str
    items: List[CartItem] = field(default_factory=list)
    coupon_code: Optional[str] = None


@dataclass
class Address:
    line1: str
    city: str
    state: str
    postal_code: str
    country: str


@dataclass
class Payment:
    id: str
    order_id: str
    customer_id: str
    amount: Decimal
    currency: str
    status: str
    provider_reference: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OrderItem:
    product_id: str
    product_name: str
    quantity: int
    unit_price: Decimal
    discount: Decimal = Decimal("0")


@dataclass
class Order:
    id: str
    customer_id: str
    items: List[OrderItem]
    subtotal: Decimal
    discount: Decimal
    shipping: Decimal
    tax: Decimal
    total: Decimal
    currency: str
    status: str
    shipping_address: Address
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Coupon:
    code: str
    discount_percent: Decimal
    minimum_order: Decimal
    maximum_discount: Decimal
    expires_at: datetime
    usage_limit: int
    used_count: int = 0
    active: bool = True


@dataclass
class Shipment:
    id: str
    order_id: str
    carrier: str
    tracking_number: str
    status: str
    estimated_days: int


# ============================================================
# IN-MEMORY DATABASE
# ============================================================

CUSTOMERS: Dict[str, Customer] = {}
PRODUCTS: Dict[str, Product] = {}
CARTS: Dict[str, Cart] = {}
ORDERS: Dict[str, Order] = {}
PAYMENTS: Dict[str, Payment] = {}
COUPONS: Dict[str, Coupon] = {}
SHIPMENTS: Dict[str, Shipment] = {}


# ============================================================
# CONFIGURATION
# ============================================================

TAX_RATES = {
    "US": Decimal("0.08"),
    "IN": Decimal("0.18"),
    "UK": Decimal("0.20"),
    "DE": Decimal("0.19"),
    "CA": Decimal("0.13"),
    "AU": Decimal("0.10"),
}

FREE_SHIPPING_THRESHOLD = Decimal("100")
STANDARD_SHIPPING = Decimal("10")
EXPRESS_SHIPPING = Decimal("25")

LOYALTY_RATE = Decimal("0.01")
LOYALTY_REDEMPTION_VALUE = Decimal("0.01")

MAX_CART_ITEMS = 50
MAX_QUANTITY_PER_ITEM = 100


# ============================================================
# CUSTOMER SERVICE
# ============================================================

class CustomerService:

    def create_customer(
        self,
        name: str,
        email: str,
        country: str,
        currency: str,
    ) -> Customer:

        customer_id = str(uuid.uuid4())

        customer = Customer(
            id=customer_id,
            name=name,
            email=email,
            country=country,
            currency=currency,
        )

        CUSTOMERS[customer_id] = customer
        return customer

    def get_customer(self, customer_id: str) -> Optional[Customer]:
        return CUSTOMERS.get(customer_id)

    def deactivate_customer(self, customer_id: str) -> bool:
        customer = self.get_customer(customer_id)

        if customer is None:
            return False

        customer.active = False
        return True

    def update_lifetime_spend(
        self,
        customer_id: str,
        amount: Decimal,
    ) -> None:

        customer = self.get_customer(customer_id)

        if customer is None:
            return

        customer.lifetime_spend += amount

    def add_loyalty_points(
        self,
        customer_id: str,
        amount: Decimal,
    ) -> None:

        customer = self.get_customer(customer_id)

        if customer is None:
            return

        points = int(amount * LOYALTY_RATE)
        customer.loyalty_points += points

    def redeem_points(
        self,
        customer_id: str,
        points: int,
    ) -> Decimal:

        customer = self.get_customer(customer_id)

        if customer is None:
            raise ValueError("Customer does not exist")

        if points <= 0:
            raise ValueError("Points must be positive")

        if points > customer.loyalty_points:
            raise ValueError("Insufficient loyalty points")

        customer.loyalty_points -= points

        return Decimal(points) * LOYALTY_REDEMPTION_VALUE


# ============================================================
# PRODUCT SERVICE
# ============================================================

class ProductService:

    def create_product(
        self,
        name: str,
        category: str,
        price: Decimal,
        cost_price: Decimal,
        stock: int,
    ) -> Product:

        if price < 0:
            raise ValueError("Price cannot be negative")

        if cost_price < 0:
            raise ValueError("Cost price cannot be negative")

        if stock < 0:
            raise ValueError("Stock cannot be negative")

        product_id = str(uuid.uuid4())

        product = Product(
            id=product_id,
            name=name,
            category=category,
            price=price,
            cost_price=cost_price,
            stock=stock,
        )

        PRODUCTS[product_id] = product
        return product

    def get_product(self, product_id: str) -> Optional[Product]:
        return PRODUCTS.get(product_id)

    def reserve_stock(
        self,
        product_id: str,
        quantity: int,
    ) -> bool:

        product = self.get_product(product_id)

        if product is None:
            return False

        if quantity <= 0:
            return False

        available = product.stock - product.reserved_stock

        if quantity > available:
            return False

        product.reserved_stock += quantity
        return True

    def release_stock(
        self,
        product_id: str,
        quantity: int,
    ) -> bool:

        product = self.get_product(product_id)

        if product is None:
            return False

        if quantity > product.reserved_stock:
            return False

        product.reserved_stock -= quantity
        return True

    def commit_stock(
        self,
        product_id: str,
        quantity: int,
    ) -> bool:

        product = self.get_product(product_id)

        if product is None:
            return False

        if quantity > product.reserved_stock:
            return False

        product.stock -= quantity
        product.reserved_stock -= quantity

        return True

    def restore_stock(
        self,
        product_id: str,
        quantity: int,
    ) -> bool:

        product = self.get_product(product_id)

        if product is None:
            return False

        product.stock += quantity
        return True

    def calculate_margin(
        self,
        product_id: str,
    ) -> Decimal:

        product = self.get_product(product_id)

        if product is None:
            raise ValueError("Product not found")

        if product.price == 0:
            return Decimal("0")

        return (
            (product.price - product.cost_price)
            / product.price
        ) * Decimal("100")


# ============================================================
# CART SERVICE
# ============================================================

class CartService:

    def create_cart(self, customer_id: str) -> Cart:

        if customer_id not in CUSTOMERS:
            raise ValueError("Customer not found")

        cart_id = str(uuid.uuid4())

        cart = Cart(
            id=cart_id,
            customer_id=customer_id,
        )

        CARTS[cart_id] = cart
        return cart

    def get_cart(self, cart_id: str) -> Optional[Cart]:
        return CARTS.get(cart_id)

    def add_item(
        self,
        cart_id: str,
        product_id: str,
        quantity: int,
    ) -> None:

        cart = self.get_cart(cart_id)

        if cart is None:
            raise ValueError("Cart not found")

        if product_id not in PRODUCTS:
            raise ValueError("Product not found")

        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        if quantity > MAX_QUANTITY_PER_ITEM:
            raise ValueError("Quantity exceeds maximum")

        if len(cart.items) >= MAX_CART_ITEMS:
            raise ValueError("Cart is full")

        for item in cart.items:
            if item.product_id == product_id:
                item.quantity += quantity
                return

        cart.items.append(
            CartItem(
                product_id=product_id,
                quantity=quantity,
            )
        )

    def remove_item(
        self,
        cart_id: str,
        product_id: str,
    ) -> bool:

        cart = self.get_cart(cart_id)

        if cart is None:
            return False

        for index, item in enumerate(cart.items):
            if item.product_id == product_id:
                del cart.items[index]
                return True

        return False

    def calculate_subtotal(
        self,
        cart_id: str,
    ) -> Decimal:

        cart = self.get_cart(cart_id)

        if cart is None:
            raise ValueError("Cart not found")

        subtotal = Decimal("0")

        for item in cart.items:

            product = PRODUCTS.get(item.product_id)

            if product is None:
                continue

            subtotal += product.price * item.quantity

        return subtotal

    def set_coupon(
        self,
        cart_id: str,
        coupon_code: str,
    ) -> None:

        cart = self.get_cart(cart_id)

        if cart is None:
            raise ValueError("Cart not found")

        coupon = COUPONS.get(coupon_code)

        if coupon is None:
            raise ValueError("Coupon not found")

        cart.coupon_code = coupon_code


# ============================================================
# COUPON SERVICE
# ============================================================

class CouponService:

    def create_coupon(
        self,
        code: str,
        discount_percent: Decimal,
        minimum_order: Decimal,
        maximum_discount: Decimal,
        expires_at: datetime,
        usage_limit: int,
    ) -> Coupon:

        coupon = Coupon(
            code=code,
            discount_percent=discount_percent,
            minimum_order=minimum_order,
            maximum_discount=maximum_discount,
            expires_at=expires_at,
            usage_limit=usage_limit,
        )

        COUPONS[code] = coupon
        return coupon

    def validate_coupon(
        self,
        code: str,
        subtotal: Decimal,
    ) -> Tuple[bool, Decimal]:

        coupon = COUPONS.get(code)

        if coupon is None:
            return False, Decimal("0")

        if not coupon.active:
            return False, Decimal("0")

        if datetime.utcnow() > coupon.expires_at:
            return False, Decimal("0")

        if coupon.used_count >= coupon.usage_limit:
            return False, Decimal("0")

        if subtotal < coupon.minimum_order:
            return False, Decimal("0")

        discount = (
            subtotal * coupon.discount_percent / Decimal("100")
        )

        if discount > coupon.maximum_discount:
            discount = coupon.maximum_discount

        return True, discount

    def consume_coupon(self, code: str) -> None:

        coupon = COUPONS.get(code)

        if coupon is None:
            raise ValueError("Coupon not found")

        coupon.used_count += 1

        if coupon.used_count >= coupon.usage_limit:
            coupon.active = False


# ============================================================
# TAX SERVICE
# ============================================================

class TaxService:

    def calculate_tax(
        self,
        country: str,
        taxable_amount: Decimal,
    ) -> Decimal:

        rate = TAX_RATES.get(
            country,
            Decimal("0"),
        )

        return taxable_amount * rate

    def calculate_tax_for_customer(
        self,
        customer_id: str,
        amount: Decimal,
    ) -> Decimal:

        customer = CUSTOMERS.get(customer_id)

        if customer is None:
            raise ValueError("Customer not found")

        return self.calculate_tax(
            customer.country,
            amount,
        )


# ============================================================
# SHIPPING SERVICE
# ============================================================

class ShippingService:

    def calculate_shipping(
        self,
        subtotal: Decimal,
        country: str,
        express: bool = False,
    ) -> Decimal:

        if subtotal >= FREE_SHIPPING_THRESHOLD:
            return Decimal("0")

        if express:
            return EXPRESS_SHIPPING

        if country == "IN":
            return Decimal("5")

        if country in ("US", "CA"):
            return Decimal("12")

        return STANDARD_SHIPPING

    def estimate_days(
        self,
        country: str,
        express: bool,
    ) -> int:

        if express:
            return 2

        if country == "IN":
            return 5

        if country == "US":
            return 7

        return 10

    def create_shipment(
        self,
        order_id: str,
        country: str,
        express: bool,
    ) -> Shipment:

        shipment_id = str(uuid.uuid4())

        carrier = (
            "FastShip"
            if express
            else "StandardShip"
        )

        tracking_number = hashlib.sha256(
            f"{order_id}:{time.time()}".encode()
        ).hexdigest()[:16]

        shipment = Shipment(
            id=shipment_id,
            order_id=order_id,
            carrier=carrier,
            tracking_number=tracking_number,
            status="created",
            estimated_days=self.estimate_days(
                country,
                express,
            ),
        )

        SHIPMENTS[shipment_id] = shipment

        return shipment


# ============================================================
# PAYMENT SERVICE
# ============================================================

class PaymentService:

    def create_payment(
        self,
        order_id: str,
        customer_id: str,
        amount: Decimal,
        currency: str,
    ) -> Payment:

        payment_id = str(uuid.uuid4())

        payment = Payment(
            id=payment_id,
            order_id=order_id,
            customer_id=customer_id,
            amount=amount,
            currency=currency,
            status="pending",
        )

        PAYMENTS[payment_id] = payment

        return payment

    def authorize_payment(
        self,
        payment_id: str,
        card_number: str,
    ) -> bool:

        payment = PAYMENTS.get(payment_id)

        if payment is None:
            return False

        if payment.status != "pending":
            return False

        if len(card_number) < 12:
            payment.status = "failed"
            return False

        payment.status = "authorized"

        payment.provider_reference = (
            hashlib.sha256(
                card_number.encode()
            ).hexdigest()[:20]
        )

        return True

    def capture_payment(
        self,
        payment_id: str,
    ) -> bool:

        payment = PAYMENTS.get(payment_id)

        if payment is None:
            return False

        if payment.status != "authorized":
            return False

        payment.status = "captured"

        return True

    def refund_payment(
        self,
        payment_id: str,
        amount: Optional[Decimal] = None,
    ) -> Decimal:

        payment = PAYMENTS.get(payment_id)

        if payment is None:
            raise ValueError("Payment not found")

        if payment.status != "captured":
            raise ValueError("Payment is not captured")

        refund_amount = (
            amount
            if amount is not None
            else payment.amount
        )

        if refund_amount > payment.amount:
            raise ValueError("Refund exceeds payment")

        payment.status = "refunded"

        return refund_amount


# ============================================================
# ORDER SERVICE
# ============================================================

class OrderService:

    def __init__(self):
        self.customer_service = CustomerService()
        self.product_service = ProductService()
        self.cart_service = CartService()
        self.coupon_service = CouponService()
        self.tax_service = TaxService()
        self.shipping_service = ShippingService()
        self.payment_service = PaymentService()

    def create_order(
        self,
        cart_id: str,
        shipping_address: Address,
        express_shipping: bool = False,
        loyalty_points: int = 0,
    ) -> Order:

        cart = self.cart_service.get_cart(cart_id)

        if cart is None:
            raise ValueError("Cart not found")

        customer = self.customer_service.get_customer(
            cart.customer_id
        )

        if customer is None:
            raise ValueError("Customer not found")

        if not customer.active:
            raise ValueError("Customer is inactive")

        if not cart.items:
            raise ValueError("Cart is empty")

        subtotal = self.cart_service.calculate_subtotal(
            cart_id
        )

        discount = Decimal("0")

        # Coupon processing
        if cart.coupon_code:

            valid, coupon_discount = (
                self.coupon_service.validate_coupon(
                    cart.coupon_code,
                    subtotal,
                )
            )

            if valid:
                discount += coupon_discount

        # Loyalty processing
        if loyalty_points > 0:

            loyalty_discount = (
                self.customer_service.redeem_points(
                    customer.id,
                    loyalty_points,
                )
            )

            discount += loyalty_discount

        taxable_amount = subtotal - discount

        if taxable_amount < 0:
            taxable_amount = Decimal("0")

        tax = self.tax_service.calculate_tax_for_customer(
            customer.id,
            taxable_amount,
        )

        shipping = self.shipping_service.calculate_shipping(
            subtotal,
            customer.country,
            express_shipping,
        )

        total = (
            subtotal
            - discount
            + tax
            + shipping
        )

        if total < 0:
            total = Decimal("0")

        order_items = []

        # Reserve inventory
        for cart_item in cart.items:

            product = self.product_service.get_product(
                cart_item.product_id
            )

            if product is None:
                raise ValueError(
                    f"Product {cart_item.product_id} missing"
                )

            if not product.active:
                raise ValueError(
                    f"Product {product.name} inactive"
                )

            success = self.product_service.reserve_stock(
                product.id,
                cart_item.quantity,
            )

            if not success:
                raise ValueError(
                    f"Insufficient stock for {product.name}"
                )

            order_items.append(
                OrderItem(
                    product_id=product.id,
                    product_name=product.name,
                    quantity=cart_item.quantity,
                    unit_price=product.price,
                )
            )

        order_id = str(uuid.uuid4())

        order = Order(
            id=order_id,
            customer_id=customer.id,
            items=order_items,
            subtotal=subtotal,
            discount=discount,
            shipping=shipping,
            tax=tax,
            total=total,
            currency=customer.currency,
            status="pending_payment",
            shipping_address=shipping_address,
        )

        ORDERS[order_id] = order

        if cart.coupon_code:
            self.coupon_service.consume_coupon(
                cart.coupon_code
            )

        return order

    def cancel_order(
        self,
        order_id: str,
    ) -> bool:

        order = ORDERS.get(order_id)

        if order is None:
            return False

        if order.status in (
            "cancelled",
            "shipped",
            "delivered",
        ):
            return False

        for item in order.items:

            self.product_service.release_stock(
                item.product_id,
                item.quantity,
            )

        order.status = "cancelled"

        return True

    def mark_paid(
        self,
        order_id: str,
    ) -> bool:

        order = ORDERS.get(order_id)

        if order is None:
            return False

        if order.status != "pending_payment":
            return False

        for item in order.items:

            success = self.product_service.commit_stock(
                item.product_id,
                item.quantity,
            )

            if not success:
                return False

        order.status = "paid"

        self.customer_service.update_lifetime_spend(
            order.customer_id,
            order.total,
        )

        self.customer_service.add_loyalty_points(
            order.customer_id,
            order.total,
        )

        return True

    def ship_order(
        self,
        order_id: str,
        express: bool = False,
    ) -> Shipment:

        order = ORDERS.get(order_id)

        if order is None:
            raise ValueError("Order not found")

        if order.status != "paid":
            raise ValueError(
                "Only paid orders can be shipped"
            )

        shipment = (
            self.shipping_service.create_shipment(
                order.id,
                order.shipping_address.country,
                express,
            )
        )

        order.status = "shipped"

        return shipment

    def deliver_order(
        self,
        order_id: str,
    ) -> bool:

        order = ORDERS.get(order_id)

        if order is None:
            return False

        if order.status != "shipped":
            return False

        order.status = "delivered"

        return True


# ============================================================
# REPORTING SERVICE
# ============================================================

class ReportingService:

    def daily_revenue(
        self,
        date: datetime,
    ) -> Decimal:

        start = datetime(
            date.year,
            date.month,
            date.day,
        )

        end = start + timedelta(days=1)

        revenue = Decimal("0")

        for order in ORDERS.values():

            if order.status not in (
                "paid",
                "shipped",
                "delivered",
            ):
                continue

            if start <= order.created_at < end:
                revenue += order.total

        return revenue

    def customer_revenue(
        self,
        customer_id: str,
    ) -> Decimal:

        total = Decimal("0")

        for order in ORDERS.values():

            if order.customer_id != customer_id:
                continue

            if order.status in (
                "paid",
                "shipped",
                "delivered",
            ):
                total += order.total

        return total

    def product_units_sold(
        self,
        product_id: str,
    ) -> int:

        quantity = 0

        for order in ORDERS.values():

            if order.status == "cancelled":
                continue

            for item in order.items:

                if item.product_id == product_id:
                    quantity += item.quantity

        return quantity

    def top_products(
        self,
        limit: int = 10,
    ) -> List[Tuple[str, int]]:

        sales: Dict[str, int] = {}

        for order in ORDERS.values():

            if order.status == "cancelled":
                continue

            for item in order.items:

                sales[item.product_id] = (
                    sales.get(item.product_id, 0)
                    + item.quantity
                )

        ranked = sorted(
            sales.items(),
            key=lambda pair: pair[1],
            reverse=True,
        )

        return ranked[:limit]

    def average_order_value(
        self,
    ) -> Decimal:

        completed = [
            order
            for order in ORDERS.values()
            if order.status in (
                "paid",
                "shipped",
                "delivered",
            )
        ]

        if not completed:
            return Decimal("0")

        total = sum(
            order.total
            for order in completed
        )

        return total / len(completed)

    def profit_estimate(
        self,
    ) -> Decimal:

        profit = Decimal("0")

        for order in ORDERS.values():

            if order.status == "cancelled":
                continue

            for item in order.items:

                product = PRODUCTS.get(
                    item.product_id
                )

                if product is None:
                    continue

                revenue = (
                    item.unit_price
                    * item.quantity
                )

                cost = (
                    product.cost_price
                    * item.quantity
                )

                profit += revenue - cost

        return profit


# ============================================================
# FRAUD DETECTION
# ============================================================

class FraudDetectionService:

    def __init__(self):
        self.failed_attempts: Dict[str, int] = {}
        self.last_attempt: Dict[str, datetime] = {}

    def check_customer(
        self,
        customer_id: str,
        amount: Decimal,
    ) -> Tuple[bool, str]:

        customer = CUSTOMERS.get(customer_id)

        if customer is None:
            return False, "customer_not_found"

        if not customer.active:
            return False, "inactive_customer"

        if amount > Decimal("10000"):
            return False, "amount_too_large"

        failures = self.failed_attempts.get(
            customer_id,
            0,
        )

        if failures >= 5:
            return False, "too_many_failures"

        return True, "approved"

    def record_failure(
        self,
        customer_id: str,
    ) -> None:

        self.failed_attempts[customer_id] = (
            self.failed_attempts.get(customer_id, 0)
            + 1
        )

        self.last_attempt[customer_id] = (
            datetime.utcnow()
        )

    def reset_failures(
        self,
        customer_id: str,
    ) -> None:

        self.failed_attempts.pop(
            customer_id,
            None,
        )


# ============================================================
# NOTIFICATION SERVICE
# ============================================================

class NotificationService:

    def send_email(
        self,
        email: str,
        subject: str,
        body: str,
    ) -> bool:

        if not email:
            return False

        logger.info(
            "Sending email to %s: %s",
            email,
            subject,
        )

        return True

    def order_created(
        self,
        customer: Customer,
        order: Order,
    ) -> bool:

        body = (
            f"Order {order.id} created. "
            f"Total: {order.total}"
        )

        return self.send_email(
            customer.email,
            "Order Confirmation",
            body,
        )

    def order_shipped(
        self,
        customer: Customer,
        order: Order,
        shipment: Shipment,
    ) -> bool:

        body = (
            f"Order {order.id} shipped. "
            f"Tracking: {shipment.tracking_number}"
        )

        return self.send_email(
            customer.email,
            "Order Shipped",
            body,
        )


# ============================================================
# PRICING ENGINE
# ============================================================

class PricingEngine:

    CATEGORY_DISCOUNTS = {
        "electronics": Decimal("0.05"),
        "books": Decimal("0.10"),
        "clothing": Decimal("0.15"),
        "home": Decimal("0.08"),
    }

    def category_discount(
        self,
        category: str,
        amount: Decimal,
    ) -> Decimal:

        rate = self.CATEGORY_DISCOUNTS.get(
            category,
            Decimal("0"),
        )

        return amount * rate

    def bulk_discount(
        self,
        quantity: int,
        amount: Decimal,
    ) -> Decimal:

        if quantity >= 100:
            return amount * Decimal("0.20")

        if quantity >= 50:
            return amount * Decimal("0.15")

        if quantity >= 20:
            return amount * Decimal("0.10")

        if quantity >= 10:
            return amount * Decimal("0.05")

        return Decimal("0")

    def customer_discount(
        self,
        customer: Customer,
        amount: Decimal,
    ) -> Decimal:

        if customer.lifetime_spend >= Decimal("10000"):
            return amount * Decimal("0.10")

        if customer.lifetime_spend >= Decimal("5000"):
            return amount * Decimal("0.07")

        if customer.lifetime_spend >= Decimal("1000"):
            return amount * Decimal("0.03")

        return Decimal("0")

    def final_price(
        self,
        product: Product,
        quantity: int,
        customer: Customer,
    ) -> Decimal:

        amount = product.price * quantity

        category_discount = (
            self.category_discount(
                product.category,
                amount,
            )
        )

        bulk_discount = (
            self.bulk_discount(
                quantity,
                amount,
            )
        )

        customer_discount = (
            self.customer_discount(
                customer,
                amount,
            )
        )

        discount = (
            category_discount
            + bulk_discount
            + customer_discount
        )

        if discount > amount:
            discount = amount

        return amount - discount


# ============================================================
# INVENTORY REPORT
# ============================================================

class InventoryReportService:

    def low_stock_products(
        self,
        threshold: int = 10,
    ) -> List[Product]:

        result = []

        for product in PRODUCTS.values():

            available = (
                product.stock
                - product.reserved_stock
            )

            if available <= threshold:
                result.append(product)

        return result

    def inventory_value(self) -> Decimal:

        total = Decimal("0")

        for product in PRODUCTS.values():

            available = (
                product.stock
                - product.reserved_stock
            )

            total += (
                product.cost_price
                * available
            )

        return total

    def inventory_retail_value(self) -> Decimal:

        total = Decimal("0")

        for product in PRODUCTS.values():

            total += (
                product.price
                * product.stock
            )

        return total


# ============================================================
# SEARCH SERVICE
# ============================================================

class ProductSearchService:

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        minimum_price: Optional[Decimal] = None,
        maximum_price: Optional[Decimal] = None,
    ) -> List[Product]:

        query = query.lower()

        results = []

        for product in PRODUCTS.values():

            if not product.active:
                continue

            if query not in product.name.lower():
                continue

            if category:
                if product.category != category:
                    continue

            if minimum_price is not None:
                if product.price < minimum_price:
                    continue

            if maximum_price is not None:
                if product.price > maximum_price:
                    continue

            results.append(product)

        return results


# ============================================================
# SUBSCRIPTION SERVICE
# ============================================================

@dataclass
class Subscription:
    id: str
    customer_id: str
    product_id: str
    quantity: int
    interval_days: int
    next_billing: datetime
    active: bool = True


SUBSCRIPTIONS: Dict[str, Subscription] = {}


class SubscriptionService:

    def create_subscription(
        self,
        customer_id: str,
        product_id: str,
        quantity: int,
        interval_days: int,
    ) -> Subscription:

        if customer_id not in CUSTOMERS:
            raise ValueError("Customer not found")

        if product_id not in PRODUCTS:
            raise ValueError("Product not found")

        if quantity <= 0:
            raise ValueError("Invalid quantity")

        if interval_days <= 0:
            raise ValueError("Invalid interval")

        subscription_id = str(uuid.uuid4())

        subscription = Subscription(
            id=subscription_id,
            customer_id=customer_id,
            product_id=product_id,
            quantity=quantity,
            interval_days=interval_days,
            next_billing=(
                datetime.utcnow()
                + timedelta(days=interval_days)
            ),
        )

        SUBSCRIPTIONS[subscription_id] = subscription

        return subscription

    def cancel_subscription(
        self,
        subscription_id: str,
    ) -> bool:

        subscription = SUBSCRIPTIONS.get(
            subscription_id
        )

        if subscription is None:
            return False

        subscription.active = False
        return True

    def due_subscriptions(
        self,
    ) -> List[Subscription]:

        now = datetime.utcnow()

        return [
            subscription
            for subscription in SUBSCRIPTIONS.values()
            if subscription.active
            and subscription.next_billing <= now
        ]

    def advance_billing(
        self,
        subscription_id: str,
    ) -> None:

        subscription = SUBSCRIPTIONS.get(
            subscription_id
        )

        if subscription is None:
            return

        subscription.next_billing = (
            subscription.next_billing
            + timedelta(
                days=subscription.interval_days
            )
        )


# ============================================================
# REFUND SERVICE
# ============================================================

class RefundService:

    def refund_order(
        self,
        order_id: str,
        reason: str,
    ) -> Decimal:

        order = ORDERS.get(order_id)

        if order is None:
            raise ValueError("Order not found")

        if order.status not in (
            "paid",
            "shipped",
            "delivered",
        ):
            raise ValueError(
                "Order cannot be refunded"
            )

        payment = None

        for candidate in PAYMENTS.values():

            if candidate.order_id == order_id:
                payment = candidate
                break

        if payment is None:
            raise ValueError(
                "Payment not found"
            )

        refund = PaymentService().refund_payment(
            payment.id
        )

        order.status = "refunded"

        logger.info(
            "Order %s refunded because %s",
            order_id,
            reason,
        )

        return refund


# ============================================================
# ANALYTICS SERVICE
# ============================================================

class AnalyticsService:

    def conversion_rate(
        self,
        visitors: int,
        orders: int,
    ) -> Decimal:

        if visitors <= 0:
            return Decimal("0")

        return (
            Decimal(orders)
            / Decimal(visitors)
            * Decimal("100")
        )

    def refund_rate(
        self,
        total_orders: int,
        refunded_orders: int,
    ) -> Decimal:

        if total_orders == 0:
            return Decimal("0")

        return (
            Decimal(refunded_orders)
            / Decimal(total_orders)
            * Decimal("100")
        )

    def customer_retention(
        self,
        previous_customers: int,
        returning_customers: int,
    ) -> Decimal:

        if previous_customers == 0:
            return Decimal("0")

        return (
            Decimal(returning_customers)
            / Decimal(previous_customers)
            * Decimal("100")
        )

    def revenue_growth(
        self,
        previous: Decimal,
        current: Decimal,
    ) -> Decimal:

        if previous == 0:
            return Decimal("0")

        return (
            (current - previous)
            / previous
            * Decimal("100")
        )


# ============================================================
# BATCH PROCESSOR
# ============================================================

class BatchOrderProcessor:

    def __init__(self):
        self.order_service = OrderService()
        self.payment_service = PaymentService()

    def process_orders(
        self,
        order_ids: List[str],
    ) -> Dict[str, str]:

        results = {}

        for order_id in order_ids:

            order = ORDERS.get(order_id)

            if order is None:
                results[order_id] = "not_found"
                continue

            if order.status != "pending_payment":
                results[order_id] = (
                    "invalid_status"
                )
                continue

            payment = (
                self.payment_service.create_payment(
                    order.id,
                    order.customer_id,
                    order.total,
                    order.currency,
                )
            )

            if self.payment_service.authorize_payment(
                payment.id,
                "4111111111111111",
            ):

                self.payment_service.capture_payment(
                    payment.id
                )

                self.order_service.mark_paid(
                    order.id
                )

                results[order_id] = "paid"

            else:
                results[order_id] = "payment_failed"

        return results


# ============================================================
# CACHE SERVICE
# ============================================================

class ProductCache:

    def __init__(self):
        self.cache: Dict[str, Tuple[Product, float]] = {}
        self.ttl = 300

    def get(
        self,
        product_id: str,
    ) -> Optional[Product]:

        cached = self.cache.get(product_id)

        if cached is None:
            return None

        product, timestamp = cached

        if time.time() - timestamp > self.ttl:
            del self.cache[product_id]
            return None

        return product

    def set(
        self,
        product: Product,
    ) -> None:

        self.cache[product.id] = (
            product,
            time.time(),
        )

    def invalidate(
        self,
        product_id: str,
    ) -> None:

        self.cache.pop(
            product_id,
            None,
        )


PRODUCT_CACHE = ProductCache()


# ============================================================
# BUSINESS WORKFLOW
# ============================================================

class BusinessWorkflow:

    def __init__(self):

        self.customers = CustomerService()
        self.products = ProductService()
        self.carts = CartService()
        self.orders = OrderService()
        self.reports = ReportingService()
        self.fraud = FraudDetectionService()
        self.notifications = NotificationService()
        self.pricing = PricingEngine()
        self.analytics = AnalyticsService()
        self.inventory = InventoryReportService()
        self.search = ProductSearchService()
        self.subscriptions = SubscriptionService()
        self.refunds = RefundService()

    def checkout(
        self,
        customer_id: str,
        cart_id: str,
        address: Address,
        card_number: str,
        express: bool = False,
        loyalty_points: int = 0,
    ) -> Order:

        customer = self.customers.get_customer(
            customer_id
        )

        if customer is None:
            raise ValueError("Customer not found")

        if customer.id != CARTS[cart_id].customer_id:
            raise ValueError(
                "Cart does not belong to customer"
            )

        cart = self.carts.get_cart(cart_id)

        if cart is None:
            raise ValueError("Cart not found")

        subtotal = self.carts.calculate_subtotal(
            cart_id
        )

        allowed, reason = self.fraud.check_customer(
            customer_id,
            subtotal,
        )

        if not allowed:
            raise ValueError(
                f"Fraud check failed: {reason}"
            )

        order = self.orders.create_order(
            cart_id=cart_id,
            shipping_address=address,
            express_shipping=express,
            loyalty_points=loyalty_points,
        )

        payment = self.orders.payment_service.create_payment(
            order.id,
            customer.id,
            order.total,
            customer.currency,
        )

        authorized = (
            self.orders.payment_service.authorize_payment(
                payment.id,
                card_number,
            )
        )

        if not authorized:

            self.orders.cancel_order(
                order.id
            )

            self.fraud.record_failure(
                customer_id
            )

            raise ValueError(
                "Payment authorization failed"
            )

        self.orders.payment_service.capture_payment(
            payment.id
        )

        self.orders.mark_paid(
            order.id
        )

        self.fraud.reset_failures(
            customer_id
        )

        self.notifications.order_created(
            customer,
            order,
        )

        return order

    def ship(
        self,
        order_id: str,
        express: bool = False,
    ) -> Shipment:

        shipment = self.orders.ship_order(
            order_id,
            express,
        )

        order = ORDERS[order_id]
        customer = CUSTOMERS[order.customer_id]

        self.notifications.order_shipped(
            customer,
            order,
            shipment,
        )

        return shipment

    def refund(
        self,
        order_id: str,
        reason: str,
    ) -> Decimal:

        return self.refunds.refund_order(
            order_id,
            reason,
        )


# ============================================================
# ADMIN OPERATIONS
# ============================================================

class AdminService:

    def deactivate_product(
        self,
        product_id: str,
    ) -> bool:

        product = PRODUCTS.get(product_id)

        if product is None:
            return False

        product.active = False

        PRODUCT_CACHE.invalidate(
            product_id
        )

        return True

    def change_price(
        self,
        product_id: str,
        new_price: Decimal,
    ) -> bool:

        product = PRODUCTS.get(product_id)

        if product is None:
            return False

        if new_price < 0:
            return False

        product.price = new_price

        PRODUCT_CACHE.invalidate(
            product_id
        )

        return True

    def restock(
        self,
        product_id: str,
        quantity: int,
    ) -> bool:

        product = PRODUCTS.get(product_id)

        if product is None:
            return False

        if quantity <= 0:
            return False

        product.stock += quantity

        return True


# ============================================================
# IMPORT / EXPORT
# ============================================================

class DataExportService:

    def export_customers(self) -> str:

        data = []

        for customer in CUSTOMERS.values():

            data.append({
                "id": customer.id,
                "name": customer.name,
                "email": customer.email,
                "country": customer.country,
                "currency": customer.currency,
                "points": customer.loyalty_points,
                "lifetime_spend": str(
                    customer.lifetime_spend
                ),
            })

        return json.dumps(data)

    def export_orders(self) -> str:

        data = []

        for order in ORDERS.values():

            data.append({
                "id": order.id,
                "customer_id": order.customer_id,
                "subtotal": str(order.subtotal),
                "discount": str(order.discount),
                "shipping": str(order.shipping),
                "tax": str(order.tax),
                "total": str(order.total),
                "currency": order.currency,
                "status": order.status,
            })

        return json.dumps(data)


# ============================================================
# INITIAL DATA
# ============================================================

def seed_products() -> None:

    product_service = ProductService()

    product_service.create_product(
        name="Laptop Pro",
        category="electronics",
        price=Decimal("1200"),
        cost_price=Decimal("900"),
        stock=50,
    )

    product_service.create_product(
        name="Wireless Mouse",
        category="electronics",
        price=Decimal("40"),
        cost_price=Decimal("20"),
        stock=200,
    )

    product_service.create_product(
        name="Python Programming",
        category="books",
        price=Decimal("60"),
        cost_price=Decimal("30"),
        stock=100,
    )

    product_service.create_product(
        name="Office Chair",
        category="home",
        price=Decimal("250"),
        cost_price=Decimal("140"),
        stock=30,
    )


def seed_coupons() -> None:

    coupon_service = CouponService()

    coupon_service.create_coupon(
        code="WELCOME10",
        discount_percent=Decimal("10"),
        minimum_order=Decimal("50"),
        maximum_discount=Decimal("100"),
        expires_at=(
            datetime.utcnow()
            + timedelta(days=30)
        ),
        usage_limit=1000,
    )

    coupon_service.create_coupon(
        code="SAVE20",
        discount_percent=Decimal("20"),
        minimum_order=Decimal("200"),
        maximum_discount=Decimal("150"),
        expires_at=(
            datetime.utcnow()
            + timedelta(days=60)
        ),
        usage_limit=500,
    )


# ============================================================
# SIMULATION
# ============================================================

def run_demo() -> None:

    seed_products()
    seed_coupons()

    workflow = BusinessWorkflow()

    customer = workflow.customers.create_customer(
        name="Demo User",
        email="demo@example.com",
        country="IN",
        currency="INR",
    )

    cart = workflow.carts.create_cart(
        customer.id
    )

    products = list(PRODUCTS.values())

    workflow.carts.add_item(
        cart.id,
        products[0].id,
        1,
    )

    workflow.carts.add_item(
        cart.id,
        products[1].id,
        2,
    )

    workflow.carts.set_coupon(
        cart.id,
        "WELCOME10",
    )

    address = Address(
        line1="123 Main Street",
        city="Ponda",
        state="Goa",
        postal_code="403401",
        country="IN",
    )

    try:

        order = workflow.checkout(
            customer_id=customer.id,
            cart_id=cart.id,
            address=address,
            card_number="4111111111111111",
            express=False,
        )

        print(
            "Order created:",
            order.id,
            order.total,
        )

        shipment = workflow.ship(
            order.id
        )

        print(
            "Shipment:",
            shipment.tracking_number,
        )

    except Exception as exc:

        logger.exception(
            "Checkout failed: %s",
            exc,
        )


if __name__ == "__main__":
    run_demo()


# ============================================================
# ADDITIONAL BUSINESS UTILITIES
# ============================================================

def normalize_email(email: str) -> str:
    return email.strip().lower()


def calculate_percentage(
    value: Decimal,
    percentage: Decimal,
) -> Decimal:

    return value * percentage / Decimal("100")


def format_currency(
    amount: Decimal,
    currency: str,
) -> str:

    return f"{currency} {amount:.2f}"


def is_business_day(date: datetime) -> bool:
    return date.weekday() < 5


def calculate_delivery_date(
    start: datetime,
    days: int,
) -> datetime:

    current = start
    remaining = days

    while remaining > 0:

        current += timedelta(days=1)

        if is_business_day(current):
            remaining -= 1

    return current


def generate_order_reference(
    order_id: str,
) -> str:

    digest = hashlib.sha256(
        order_id.encode()
    ).hexdigest()

    return digest[:12].upper()


def mask_email(email: str) -> str:

    if "@" not in email:
        return "***"

    username, domain = email.split(
        "@",
        1,
    )

    if len(username) <= 2:
        masked = "*" * len(username)
    else:
        masked = (
            username[0]
            + "*" * (len(username) - 2)
            + username[-1]
        )

    return masked + "@" + domain


def calculate_compound_growth(
    initial: Decimal,
    rate: Decimal,
    periods: int,
) -> Decimal:

    result = initial

    for _ in range(periods):
        result *= (
            Decimal("1")
            + rate
        )

    return result


def paginate(
    values: List,
    page: int,
    page_size: int,
) -> List:

    if page < 1:
        raise ValueError("Invalid page")

    if page_size <= 0:
        raise ValueError("Invalid page size")

    start = (
        page - 1
    ) * page_size

    end = start + page_size

    return values[start:end]


def safe_decimal(
    value: str,
) -> Decimal:

    try:
        return Decimal(value)
    except Exception:
        return Decimal("0")


def calculate_order_hash(
    order: Order,
) -> str:

    payload = (
        order.id
        + order.customer_id
        + str(order.total)
        + order.currency
    )

    return hashlib.sha256(
        payload.encode()
    ).hexdigest()


# ============================================================
# END OF FILE
# ============================================================
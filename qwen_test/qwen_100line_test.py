"""
Qwen Semantic Bug Detection Test

This file intentionally contains 10 real programming bugs.
The bugs are distributed across different categories so we can measure
how well the local Qwen model detects semantic defects.
"""

import json
import os
import sqlite3


# BUG 1: Division by zero
def calculate_average(total, count):
    return total / count


# BUG 2: None dereference
def get_username(users, user_id):
    user = next((u for u in users if u["id"] == user_id), None)
    return user["name"]


# BUG 3: Mutable default argument
def add_notification(message, notifications=[]):
    notifications.append(message)
    return notifications


# BUG 4: Off-by-one error
def get_last_three(items):
    result = []
    for i in range(len(items) - 3):
        result.append(items[i])
    return result


# BUG 5: Incorrect boolean logic
def can_access(user):
    if user["role"] == "admin" or "manager":
        return True
    return False


# BUG 6: SQL injection
def find_user_by_name(connection, name):
    query = "SELECT * FROM users WHERE name = '" + name + "'"
    return connection.execute(query).fetchall()


# BUG 7: Resource leak
def read_config(path):
    file = open(path, "r")
    data = file.read()
    return json.loads(data)


# BUG 8: Wrong dictionary key assumption
def calculate_total(order):
    total = 0
    for item in order["items"]:
        total += item["price"] * item["quantity"]
    return total


# BUG 9: Incorrect exception handling
def parse_number(value):
    try:
        return int(value)
    except TypeError:
        return 0


# BUG 10: Race-prone file update / lost update
def increment_counter(path):
    with open(path, "r") as file:
        value = int(file.read())

    value += 1

    with open(path, "w") as file:
        file.write(str(value))


# -------------------------
# CORRECT CODE
# -------------------------

def calculate_discount(price, percentage):
    if percentage < 0 or percentage > 100:
        raise ValueError("percentage must be between 0 and 100")
    return price - (price * percentage / 100)


def find_user(users, user_id):
    for user in users:
        if user.get("id") == user_id:
            return user
    return None


def safe_average(values):
    if not values:
        return 0
    return sum(values) / len(values)


def build_user_map(users):
    return {user["id"]: user for user in users}


def format_username(user):
    return user.get("name", "Unknown")


def is_valid_email(email):
    return isinstance(email, str) and "@" in email


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def calculate_tax(amount, rate):
    return amount * rate / 100


def find_maximum(values):
    if not values:
        return None
    return max(values)


def create_connection(database):
    return sqlite3.connect(database)


def normalize_name(name):
    return name.strip().lower()


def count_active_users(users):
    return sum(1 for user in users if user.get("active", False))


def get_setting(settings, key, default=None):
    return settings.get(key, default)


def safe_percentage_change(old, new):
    if old == 0:
        return None
    return ((new - old) / old) * 100


def validate_age(age):
    if not isinstance(age, int):
        return False
    return 0 <= age <= 120


def close_connection(connection):
    connection.close()


def build_summary(users):
    return {
        "total": len(users),
        "active": count_active_users(users),
    }
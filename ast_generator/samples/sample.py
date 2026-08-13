# Sample Python file with intentional bug patterns

def calculate_average(numbers):
    # Bug: Division by zero when numbers is empty
    return sum(numbers) / len(numbers)

def get_user_name(user_dict):
    # Bug: No check if 'name' key exists
    return user_dict['name'].upper()

def read_config():
    # Bug: Resource leak - file not properly closed
    file = open('config.txt', 'r')
    data = file.read()
    return data

def get_element(items, index):
    # Bug: No bounds checking
    return items[index]

def process_data(value):
    # Bug: Uninitialized variable in some paths
    if value > 0:
        result = value * 2
    elif value < 0:
        result = abs(value)
    # If value == 0, result is undefined
    return result

def execute_query(user_input):
    # Bug: SQL injection vulnerability
    query = f"SELECT * FROM users WHERE username = '{user_input}'"
    return query

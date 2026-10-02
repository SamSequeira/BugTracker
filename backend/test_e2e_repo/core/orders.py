def process_order(order):
    customer_name = order['customer']
    items = order['items']
    total = order['total_price']
    return {'customer': customer_name, 'total': total}

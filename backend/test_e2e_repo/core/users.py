def get_user_city(user_id, users):
    user = next((u for u in users if u['id'] == user_id), None)
    return user['city']

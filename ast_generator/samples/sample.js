// Sample JavaScript file with intentional bug patterns

function calculateAverage(numbers) {
    // Bug: Division by zero when numbers is empty
    return numbers.reduce((a, b) => a + b) / numbers.length;
}

function getUserName(user) {
    // Bug: No check if user or user.name exists
    return user.name.toUpperCase();
}

function readConfig() {
    // Bug: Resource leak - file handle not properly managed
    const fs = require('fs');
    const data = fs.readFileSync('config.txt', 'utf8');
    return data;
}

function getElement(items, index) {
    // Bug: No bounds checking
    return items[index];
}

function processData(value) {
    // Bug: Uninitialized variable in some paths
    let result;
    if (value > 0) {
        result = value * 2;
    } else if (value < 0) {
        result = Math.abs(value);
    }
    // If value == 0, result is undefined
    return result;
}

function executeQuery(userInput) {
    // Bug: SQL injection vulnerability
    const query = `SELECT * FROM users WHERE username = '${userInput}'`;
    return query;
}

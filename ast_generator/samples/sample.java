// Sample Java file with intentional bug patterns

import java.io.*;
import java.util.List;

public class Sample {
    
    // Bug: Division by zero when numbers is empty
    public static double calculateAverage(List<Integer> numbers) {
        int sum = 0;
        for (int num : numbers) {
            sum += num;
        }
        return sum / numbers.size();
    }
    
    // Bug: Potential NullPointerException
    public static String getUserName(User user) {
        return user.getName().toUpperCase();
    }
    
    // Bug: Resource leak - file not closed properly
    public static String readConfig() throws IOException {
        FileReader file = new FileReader("config.txt");
        BufferedReader reader = new BufferedReader(file);
        String data = reader.readLine();
        return data;
    }
    
    // Bug: Array index out of bounds
    public static int getElement(int[] items, int index) {
        return items[index];
    }
    
    // Bug: Variable might not be initialized
    public static int processData(int value) {
        int result;
        if (value > 0) {
            result = value * 2;
        } else if (value < 0) {
            result = Math.abs(value);
        }
        // If value == 0, result is uninitialized
        return result;
    }
    
    // Bug: SQL injection vulnerability
    public static String executeQuery(String userInput) {
        String query = "SELECT * FROM users WHERE username = '" + userInput + "'";
        return query;
    }
}

class User {
    private String name;
    
    public String getName() {
        return name;
    }
}

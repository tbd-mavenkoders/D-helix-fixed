// Simple C++ test for D-Helix
#include <iostream>

class Calculator {
public:
    int add(int a, int b) {
        return a + b;
    }
    
    int multiply(int a, int b) {
        return a * b;
    }
};

int global_add(int x, int y) {
    return x + y;
}

int main() {
    Calculator calc;
    int result = calc.add(5, 3);
    int result2 = global_add(10, 20);
    std::cout << result << std::endl;
    return 0;
}

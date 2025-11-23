"""Calculator toolkit following Agno patterns."""

import json
import math

from roma_dspy.tools.base.base import BaseToolkit


class CalculatorToolkit(BaseToolkit):
    """
    Mathematical calculator toolkit providing arithmetic and mathematical operations.

    Based on Agno CalculatorTools implementation with DSPy integration.
    Provides safe mathematical operations with proper error handling.
    """

    def _setup_dependencies(self) -> None:
        """Setup calculator toolkit dependencies."""
        # No external dependencies required - using built-in math module
        pass

    def _initialize_tools(self) -> None:
        """Initialize calculator toolkit configuration."""
        # Get precision setting from config, default to 10 decimal places
        self.precision = self.config.get("precision", 10)
        self.max_factorial_input = self.config.get("max_factorial_input", 1000)

    def add(self, a: float, b: float) -> str:
        """
        Add two numbers together.

        Use this tool to perform addition of two numerical values.
        Supports both integers and floating-point numbers with configurable precision.

        Args:
            a: First number to add
            b: Second number to add

        Returns:
            JSON string with the sum result

        Examples:
            add(5, 3) - Returns 8
            add(2.5, 1.7) - Returns 4.2
        """
        try:
            result = round(a + b, self.precision)
            self.log_debug(f"Addition: {a} + {b} = {result}")
            return json.dumps(
                {
                    "success": True,
                    "operation": "addition",
                    "operands": [a, b],
                    "result": result,
                }
            )
        except Exception as e:
            error_msg = f"Error in addition: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    def subtract(self, a: float, b: float) -> str:
        """
        Subtract one number from another.

        Use this tool to perform subtraction of two numerical values.
        Calculates a - b with configurable precision for the result.

        Args:
            a: Number to subtract from (minuend)
            b: Number to subtract (subtrahend)

        Returns:
            JSON string with the difference result

        Examples:
            subtract(10, 3) - Returns 7
            subtract(5.5, 2.2) - Returns 3.3
        """
        try:
            result = round(a - b, self.precision)
            self.log_debug(f"Subtraction: {a} - {b} = {result}")
            return json.dumps(
                {
                    "success": True,
                    "operation": "subtraction",
                    "operands": [a, b],
                    "result": result,
                }
            )
        except Exception as e:
            error_msg = f"Error in subtraction: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    def multiply(self, a: float, b: float) -> str:
        """
        Multiply two numbers together.

        Use this tool to perform multiplication of two numerical values.
        Supports both integers and floating-point numbers with proper precision handling.

        Args:
            a: First number to multiply
            b: Second number to multiply

        Returns:
            JSON string with the product result

        Examples:
            multiply(4, 5) - Returns 20
            multiply(2.5, 3.2) - Returns 8.0
        """
        try:
            result = round(a * b, self.precision)
            self.log_debug(f"Multiplication: {a} * {b} = {result}")
            return json.dumps(
                {
                    "success": True,
                    "operation": "multiplication",
                    "operands": [a, b],
                    "result": result,
                }
            )
        except Exception as e:
            error_msg = f"Error in multiplication: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    def divide(self, a: float, b: float) -> str:
        """
        Divide one number by another with zero-division protection.

        Use this tool to perform division of two numerical values.
        Includes protection against division by zero with clear error messaging.

        Args:
            a: Number to be divided (dividend)
            b: Number to divide by (divisor)

        Returns:
            JSON string with the quotient result or error if division by zero

        Examples:
            divide(15, 3) - Returns 5
            divide(7, 2) - Returns 3.5
            divide(10, 0) - Returns error about division by zero
        """
        try:
            if b == 0:
                error_msg = "Division by zero is not allowed"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            result = round(a / b, self.precision)
            self.log_debug(f"Division: {a} / {b} = {result}")
            return json.dumps(
                {
                    "success": True,
                    "operation": "division",
                    "operands": [a, b],
                    "result": result,
                }
            )
        except Exception as e:
            error_msg = f"Error in division: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    def exponentiate(self, a: float, b: float) -> str:
        """
        Raise a number to the power of another number.

        Use this tool to perform exponentiation (power) operations.
        Calculates a raised to the power of b (a^b).

        Args:
            a: Base number
            b: Exponent (power to raise to)

        Returns:
            JSON string with the power result

        Examples:
            exponentiate(2, 3) - Returns 8 (2^3)
            exponentiate(5, 2) - Returns 25 (5^2)
            exponentiate(4, 0.5) - Returns 2 (square root of 4)
        """
        try:
            result = round(a**b, self.precision)
            self.log_debug(f"Exponentiation: {a} ^ {b} = {result}")
            return json.dumps(
                {
                    "success": True,
                    "operation": "exponentiation",
                    "operands": [a, b],
                    "result": result,
                }
            )
        except Exception as e:
            error_msg = f"Error in exponentiation: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    def factorial(self, n: int) -> str:
        """
        Calculate the factorial of a non-negative integer.

        Use this tool to calculate n! (n factorial). Includes protection against
        negative numbers and very large inputs that could cause performance issues.

        Args:
            n: Non-negative integer to calculate factorial for

        Returns:
            JSON string with the factorial result

        Examples:
            factorial(5) - Returns 120 (5! = 5*4*3*2*1)
            factorial(0) - Returns 1 (0! = 1 by definition)
            factorial(-1) - Returns error for negative input
        """
        try:
            if n < 0:
                error_msg = "Factorial is not defined for negative numbers"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            if n > self.max_factorial_input:
                error_msg = f"Input {n} exceeds maximum allowed factorial input ({self.max_factorial_input})"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            result = math.factorial(n)
            self.log_debug(f"Factorial: {n}! = {result}")
            return json.dumps(
                {
                    "success": True,
                    "operation": "factorial",
                    "operand": n,
                    "result": result,
                }
            )
        except Exception as e:
            error_msg = f"Error calculating factorial: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    def is_prime(self, n: int) -> str:
        """
        Check if a number is prime.

        Use this tool to determine whether a given integer is a prime number.
        A prime number is a natural number greater than 1 that has no positive
        divisors other than 1 and itself.

        Args:
            n: Integer to check for primality

        Returns:
            JSON string indicating whether the number is prime

        Examples:
            is_prime(7) - Returns True (7 is prime)
            is_prime(12) - Returns False (12 = 2*2*3, not prime)
            is_prime(1) - Returns False (1 is not considered prime)
        """
        try:
            if n < 2:
                is_prime_result = False
            elif n == 2:
                is_prime_result = True
            elif n % 2 == 0:
                is_prime_result = False
            else:
                is_prime_result = True
                for i in range(3, int(math.sqrt(n)) + 1, 2):
                    if n % i == 0:
                        is_prime_result = False
                        break

            self.log_debug(
                f"Prime check: {n} is {'prime' if is_prime_result else 'not prime'}"
            )
            return json.dumps(
                {
                    "success": True,
                    "operation": "prime_check",
                    "operand": n,
                    "result": is_prime_result,
                }
            )
        except Exception as e:
            error_msg = f"Error checking primality: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    def square_root(self, n: float) -> str:
        """
        Calculate the square root of a number.

        Use this tool to find the square root of a non-negative number.
        Includes protection against negative inputs (complex numbers not supported).

        Args:
            n: Non-negative number to calculate square root for

        Returns:
            JSON string with the square root result

        Examples:
            square_root(16) - Returns 4
            square_root(2) - Returns approximately 1.414
            square_root(-4) - Returns error for negative input
        """
        try:
            if n < 0:
                error_msg = "Square root of negative numbers is not supported"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            result = round(math.sqrt(n), self.precision)
            self.log_debug(f"Square root: √{n} = {result}")
            return json.dumps(
                {
                    "success": True,
                    "operation": "square_root",
                    "operand": n,
                    "result": result,
                }
            )
        except Exception as e:
            error_msg = f"Error calculating square root: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

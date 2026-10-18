"""Small trusted algorithms with known asymptotic running-time classes."""


def constant(_size: int) -> int:
    """Return immediately: O(1) time and O(1) auxiliary space."""
    return 1


def logarithmic(size: int) -> int:
    """Count halvings: O(log n) time and O(1) space."""
    steps = 0
    remaining = size
    while remaining > 1:
        remaining //= 2
        steps += 1
    return steps


def linear(size: int) -> int:
    """Sum a range: O(n) time and O(1) additional space."""
    total = 0
    for value in range(size):
        total += value
    return total


def linearithmic(size: int) -> int:
    """Visit n items once per doubling phase: O(n log n) time."""
    visits = 0
    width = 1
    while width < size:
        for _ in range(size):
            visits += 1
        width *= 2
    return visits


def quadratic(size: int) -> int:
    """Count all pairs: O(n²) time and O(1) additional space."""
    pairs = 0
    for left in range(size):
        for right in range(size):
            pairs += left == right
    return pairs


def exponential(size: int) -> int:
    """Count binary strings: O(2ⁿ) time; use only small sizes."""
    count = 0
    for _ in range(2**size):
        count += 1
    return count


__all__ = [
    "constant",
    "logarithmic",
    "linear",
    "linearithmic",
    "quadratic",
    "exponential",
]

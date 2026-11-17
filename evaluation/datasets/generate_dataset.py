"""
Generates the 22-problem representative evaluation dataset and validates it
against the EvaluationDataset Pydantic schema.
"""

import json
from pathlib import Path
from evaluation.schemas.dataset import EvaluationDataset

DATASET = {
    "name": "EdgeMind Representative Coding Benchmark",
    "version": "1.0.0",
    "description": "22 representative algorithmic and data structure problems designed to benchmark multi-step AI reasoning, tool selection, constraint parsing, and edge-case synthesis.",
    "examples": [
        {
            "id": "eval-001-two-sum",
            "name": "Two Sum",
            "description": "Find indices of two numbers that add up to a specific target.",
            "problem_statement": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target. You may assume that each input would have exactly one solution, and you may not use the same element twice. Constraints: 2 <= nums.length <= 10^4, -10^9 <= nums[i] <= 10^9, -10^9 <= target <= 10^9.",
            "code_snippet": "def two_sum(nums: list[int], target: int) -> list[int]:\n    seen = {}\n    for i, num in enumerate(nums):\n        complement = target - num\n        if complement in seen:\n            return [seen[complement], i]\n        seen[num] = i\n    return []",
            "filename": "two_sum.py",
            "test_cases": [
                {"input_data": {"nums": [2, 7, 11, 15], "target": 9}}
            ],
            "problem_context": {
                "title": "Two Sum",
                "constraints": [
                    "2 <= nums.length <= 10^4",
                    "-10^9 <= nums[i] <= 10^9",
                    "-10^9 <= target <= 10^9"
                ]
            },
            "expected_constraints": [
                "2 <= nums.length <= 10^4",
                "-10^9 <= nums[i] <= 10^9",
                "-10^9 <= target <= 10^9"
            ],
            "expected_edge_case_categories": [
                "SINGLETON",
                "ZERO_VALUE",
                "NEGATIVE_VALUES",
                "DUPLICATE_ELEMENTS",
                "TARGET_NOT_FOUND",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "expected_response_structure": {
                "required_fields": ["status", "session_id", "execution_mode", "code_analysis", "test_intelligence"],
                "allowed_statuses": ["SUCCESS", "STATIC_ONLY", "PROVIDER_UNAVAILABLE"],
                "min_candidates": 1,
                "require_code_analysis": True,
                "require_test_intelligence": True
            },
            "tags": ["arrays", "hash-table", "boundary-conditions", "ci-smoke", "easy"],
            "difficulty": "easy",
            "metadata": {"category": "Arrays & Hashing"}
        },
        {
            "id": "eval-002-valid-parentheses",
            "name": "Valid Parentheses",
            "description": "Determine if input string containing brackets is valid.",
            "problem_statement": "Given a string s containing just the characters '(', ')', '{', '}', '[' and ']', determine if the input string is valid. Open brackets must be closed by the same type of brackets in the correct order. Constraints: 1 <= s.length <= 10^4, s consists of parentheses only '()[]{}'.",
            "code_snippet": "def is_valid(s: str) -> bool:\n    stack = []\n    mapping = {')': '(', '}': '{', ']': '['}\n    for char in s:\n        if char in mapping:\n            top_element = stack.pop() if stack else '#'\n            if mapping[char] != top_element:\n                return False\n        else:\n            stack.append(char)\n    return not stack",
            "filename": "valid_parentheses.py",
            "test_cases": [
                {"input_data": {"s": "()"}}
            ],
            "problem_context": {
                "title": "Valid Parentheses",
                "constraints": [
                    "1 <= s.length <= 10^4",
                    "s consists of parentheses only '()[]{}'"
                ]
            },
            "expected_constraints": [
                "1 <= s.length <= 10^4",
                "s consists of parentheses only"
            ],
            "expected_edge_case_categories": [
                "EMPTY_COLLECTION",
                "SINGLETON",
                "NESTED_BRACKETS",
                "BRACKET_PATTERN",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "expected_response_structure": {
                "required_fields": ["status", "session_id", "execution_mode", "code_analysis", "test_intelligence"],
                "allowed_statuses": ["SUCCESS", "STATIC_ONLY", "PROVIDER_UNAVAILABLE"],
                "min_candidates": 1,
                "require_code_analysis": True,
                "require_test_intelligence": True
            },
            "tags": ["strings", "stacks", "boundary-conditions", "ci-smoke", "easy"],
            "difficulty": "easy",
            "metadata": {"category": "Stacks"}
        },
        {
            "id": "eval-003-binary-search",
            "name": "Binary Search",
            "description": "Search target in sorted ascending array in O(log n) runtime.",
            "problem_statement": "Given an array of integers nums which is sorted in ascending order, and an integer target, write a function to search target in nums. If target exists, return its index. Otherwise, return -1. Constraints: 1 <= nums.length <= 10^4, -10^4 < nums[i], target < 10^4, all integers in nums are unique, nums is sorted in ascending order.",
            "code_snippet": "def search(nums: list[int], target: int) -> int:\n    left, right = 0, len(nums) - 1\n    while left <= right:\n        mid = (left + right) // 2\n        if nums[mid] == target:\n            return mid\n        elif nums[mid] < target:\n            left = mid + 1\n        else:\n            right = mid - 1\n    return -1",
            "filename": "binary_search.py",
            "test_cases": [
                {"input_data": {"nums": [-1, 0, 3, 5, 9, 12], "target": 9}}
            ],
            "problem_context": {
                "title": "Binary Search",
                "constraints": [
                    "1 <= nums.length <= 10^4",
                    "-10^4 <= nums[i], target <= 10^4",
                    "nums is sorted in ascending order"
                ]
            },
            "expected_constraints": [
                "1 <= nums.length <= 10^4",
                "-10^4 <= nums[i], target <= 10^4",
                "nums is sorted in ascending order"
            ],
            "expected_edge_case_categories": [
                "SINGLETON",
                "TARGET_NOT_FOUND",
                "TARGET_AT_BOUNDARIES",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND",
                "ZERO_VALUE"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "binary-search", "boundary-conditions", "easy"],
            "difficulty": "easy",
            "metadata": {"category": "Binary Search"}
        },
        {
            "id": "eval-004-longest-substring-without-repeating",
            "name": "Longest Substring Without Repeating Characters",
            "description": "Find length of longest substring without duplicate characters.",
            "problem_statement": "Given a string s, find the length of the longest substring without repeating characters. Constraints: 0 <= s.length <= 5 * 10^4, s consists of English letters, digits, symbols and spaces.",
            "code_snippet": "def length_of_longest_substring(s: str) -> int:\n    char_map = {}\n    left = 0\n    max_len = 0\n    for right, char in enumerate(s):\n        if char in char_map and char_map[char] >= left:\n            left = char_map[char] + 1\n        char_map[char] = right\n        max_len = max(max_len, right - left + 1)\n    return max_len",
            "filename": "longest_substring.py",
            "test_cases": [
                {"input_data": {"s": "abcabcbb"}}
            ],
            "problem_context": {
                "title": "Longest Substring Without Repeating Characters",
                "constraints": [
                    "0 <= s.length <= 50000",
                    "s consists of English letters, digits, symbols and spaces"
                ]
            },
            "expected_constraints": [
                "0 <= s.length <= 50000"
            ],
            "expected_edge_case_categories": [
                "EMPTY_COLLECTION",
                "SINGLETON",
                "IDENTICAL_ALL",
                "DUPLICATE_ELEMENTS",
                "SPECIAL_CHARACTERS",
                "SLIDING_WINDOW_PATTERN"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["strings", "sliding-window", "hash-table", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Sliding Window"}
        },
        {
            "id": "eval-005-container-with-most-water",
            "name": "Container With Most Water",
            "description": "Find two lines that together with the x-axis form a container containing the most water.",
            "problem_statement": "Given an integer array height of length n. Find two lines that together with the x-axis form a container, such that the container contains the most water. Return the maximum amount of water a container can store. Constraints: n == height.length, 2 <= n <= 10^5, 0 <= height[i] <= 10^4.",
            "code_snippet": "def max_area(height: list[int]) -> int:\n    left, right = 0, len(height) - 1\n    max_water = 0\n    while left < right:\n        width = right - left\n        current_height = min(height[left], height[right])\n        max_water = max(max_water, width * current_height)\n        if height[left] < height[right]:\n            left += 1\n        else:\n            right -= 1\n    return max_water",
            "filename": "container_water.py",
            "test_cases": [
                {"input_data": {"height": [1, 8, 6, 2, 5, 4, 8, 3, 7]}}
            ],
            "problem_context": {
                "title": "Container With Most Water",
                "constraints": [
                    "2 <= height.length <= 10^5",
                    "0 <= height[i] <= 10^4"
                ]
            },
            "expected_constraints": [
                "2 <= height.length <= 10^5",
                "0 <= height[i] <= 10^4"
            ],
            "expected_edge_case_categories": [
                "ZERO_VALUE",
                "IDENTICAL_ALL",
                "DUPLICATE_ELEMENTS",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND",
                "REVERSE_SORTED",
                "ALREADY_SORTED"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "two-pointers", "greedy", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Two Pointers"}
        },
        {
            "id": "eval-006-three-sum",
            "name": "3Sum",
            "description": "Find all unique triplets in the array which gives the sum of zero.",
            "problem_statement": "Given an integer array nums, return all the triplets [nums[i], nums[j], nums[k]] such that i != j, i != k, and j != k, and nums[i] + nums[j] + nums[k] == 0. Notice that the solution set must not contain duplicate triplets. Constraints: 3 <= nums.length <= 3000, -10^5 <= nums[i] <= 10^5.",
            "code_snippet": "def three_sum(nums: list[int]) -> list[list[int]]:\n    nums.sort()\n    res = []\n    for i in range(len(nums) - 2):\n        if i > 0 and nums[i] == nums[i-1]:\n            continue\n        l, r = i + 1, len(nums) - 1\n        while l < r:\n            total = nums[i] + nums[l] + nums[r]\n            if total < 0:\n                l += 1\n            elif total > 0:\n                r -= 1\n            else:\n                res.append([nums[i], nums[l], nums[r]])\n                while l < r and nums[l] == nums[l+1]:\n                    l += 1\n                while l < r and nums[r] == nums[r-1]:\n                    r -= 1\n                l += 1\n                r -= 1\n    return res",
            "filename": "three_sum.py",
            "test_cases": [
                {"input_data": {"nums": [-1, 0, 1, 2, -1, -4]}}
            ],
            "problem_context": {
                "title": "3Sum",
                "constraints": [
                    "3 <= nums.length <= 3000",
                    "-10^5 <= nums[i] <= 10^5"
                ]
            },
            "expected_constraints": [
                "3 <= nums.length <= 3000",
                "-10^5 <= nums[i] <= 10^5"
            ],
            "expected_edge_case_categories": [
                "ZERO_VALUE",
                "IDENTICAL_ALL",
                "DUPLICATE_ELEMENTS",
                "NEGATIVE_VALUES",
                "TARGET_NOT_FOUND",
                "LOWER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "two-pointers", "sorting", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Two Pointers"}
        },
        {
            "id": "eval-007-merge-intervals",
            "name": "Merge Intervals",
            "description": "Merge all overlapping intervals into non-overlapping intervals.",
            "problem_statement": "Given an array of intervals where intervals[i] = [starti, endi], merge all overlapping intervals, and return an array of the non-overlapping intervals that cover all the intervals in the input. Constraints: 1 <= intervals.length <= 10^4, intervals[i].length == 2, 0 <= starti <= endi <= 10^4.",
            "code_snippet": "def merge(intervals: list[list[int]]) -> list[list[int]]:\n    if not intervals:\n        return []\n    intervals.sort(key=lambda x: x[0])\n    merged = [intervals[0]]\n    for current in intervals[1:]:\n        prev = merged[-1]\n        if current[0] <= prev[1]:\n            prev[1] = max(prev[1], current[1])\n        else:\n            merged.append(current)\n    return merged",
            "filename": "merge_intervals.py",
            "test_cases": [
                {"input_data": {"intervals": [[1, 3], [2, 6], [8, 10], [15, 18]]}}
            ],
            "problem_context": {
                "title": "Merge Intervals",
                "constraints": [
                    "1 <= intervals.length <= 10^4",
                    "0 <= start <= end <= 10^4"
                ]
            },
            "expected_constraints": [
                "1 <= intervals.length <= 10^4",
                "0 <= start <= end <= 10^4"
            ],
            "expected_edge_case_categories": [
                "SINGLETON",
                "DUPLICATE_ELEMENTS",
                "IDENTICAL_ALL",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "sorting", "intervals", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Intervals"}
        },
        {
            "id": "eval-008-maximum-subarray",
            "name": "Maximum Subarray",
            "description": "Find contiguous subarray with largest sum using Kadane's algorithm.",
            "problem_statement": "Given an integer array nums, find the subarray with the largest sum, and return its sum. Constraints: 1 <= nums.length <= 10^5, -10^4 <= nums[i] <= 10^4.",
            "code_snippet": "def max_sub_array(nums: list[int]) -> int:\n    max_current = max_global = nums[0]\n    for i in range(1, len(nums)):\n        max_current = max(nums[i], max_current + nums[i])\n        if max_current > max_global:\n            max_global = max_current\n    return max_global",
            "filename": "max_subarray.py",
            "test_cases": [
                {"input_data": {"nums": [-2, 1, -3, 4, -1, 2, 1, -5, 4]}}
            ],
            "problem_context": {
                "title": "Maximum Subarray",
                "constraints": [
                    "1 <= nums.length <= 10^5",
                    "-10^4 <= nums[i] <= 10^4"
                ]
            },
            "expected_constraints": [
                "1 <= nums.length <= 10^5",
                "-10^4 <= nums[i] <= 10^4"
            ],
            "expected_edge_case_categories": [
                "SINGLETON",
                "NEGATIVE_VALUES",
                "ZERO_VALUE",
                "IDENTICAL_ALL",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "dynamic-programming", "divide-and-conquer", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Dynamic Programming"}
        },
        {
            "id": "eval-009-climbing-stairs",
            "name": "Climbing Stairs",
            "description": "Calculate distinct ways to climb n stairs taking 1 or 2 steps.",
            "problem_statement": "You are climbing a staircase. It takes n steps to reach the top. Each time you can either climb 1 or 2 steps. In how many distinct ways can you climb to the top? Constraints: 1 <= n <= 45.",
            "code_snippet": "def climb_stairs(n: int) -> int:\n    if n <= 2:\n        return n\n    first, second = 1, 2\n    for _ in range(3, n + 1):\n        first, second = second, first + second\n    return second",
            "filename": "climb_stairs.py",
            "test_cases": [
                {"input_data": {"n": 3}}
            ],
            "problem_context": {
                "title": "Climbing Stairs",
                "constraints": [
                    "1 <= n <= 45"
                ]
            },
            "expected_constraints": [
                "1 <= n <= 45"
            ],
            "expected_edge_case_categories": [
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND",
                "SINGLETON"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["math", "dynamic-programming", "memoization", "easy"],
            "difficulty": "easy",
            "metadata": {"category": "1-D Dynamic Programming"}
        },
        {
            "id": "eval-010-coin-change",
            "name": "Coin Change",
            "description": "Compute fewest coins needed to make up amount, or -1 if impossible.",
            "problem_statement": "You are given an integer array coins representing coins of different denominations and an integer amount representing a total amount of money. Return the fewest number of coins that you need to make up that amount. If that amount of money cannot be made up by any combination of the coins, return -1. Constraints: 1 <= coins.length <= 12, 1 <= coins[i] <= 2^31 - 1, 0 <= amount <= 10^4.",
            "code_snippet": "def coin_change(coins: list[int], amount: int) -> int:\n    dp = [float('inf')] * (amount + 1)\n    dp[0] = 0\n    for coin in coins:\n        for x in range(coin, amount + 1):\n            dp[x] = min(dp[x], dp[x - coin] + 1)\n    return dp[amount] if dp[amount] != float('inf') else -1",
            "filename": "coin_change.py",
            "test_cases": [
                {"input_data": {"coins": [1, 2, 5], "amount": 11}}
            ],
            "problem_context": {
                "title": "Coin Change",
                "constraints": [
                    "1 <= coins.length <= 12",
                    "1 <= coins[i] <= 2^31 - 1",
                    "0 <= amount <= 10000"
                ]
            },
            "expected_constraints": [
                "1 <= coins.length <= 12",
                "0 <= amount <= 10000"
            ],
            "expected_edge_case_categories": [
                "ZERO_VALUE",
                "TARGET_NOT_FOUND",
                "SINGLETON",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "dynamic-programming", "bfs", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "1-D Dynamic Programming"}
        },
        {
            "id": "eval-011-product-except-self",
            "name": "Product of Array Except Self",
            "description": "Compute array such that output[i] is product of all elements except nums[i] in O(n) without division.",
            "problem_statement": "Given an integer array nums, return an array answer such that answer[i] is equal to the product of all the elements of nums except nums[i]. The product of any prefix or suffix of nums is guaranteed to fit in a 32-bit integer. You must write an algorithm that runs in O(n) time and without using the division operation. Constraints: 2 <= nums.length <= 10^5, -30 <= nums[i] <= 30.",
            "code_snippet": "def product_except_self(nums: list[int]) -> list[int]:\n    n = len(nums)\n    res = [1] * n\n    prefix = 1\n    for i in range(n):\n        res[i] = prefix\n        prefix *= nums[i]\n    postfix = 1\n    for i in range(n - 1, -1, -1):\n        res[i] *= postfix\n        postfix *= nums[i]\n    return res",
            "filename": "product_except_self.py",
            "test_cases": [
                {"input_data": {"nums": [1, 2, 3, 4]}}
            ],
            "problem_context": {
                "title": "Product of Array Except Self",
                "constraints": [
                    "2 <= nums.length <= 10^5",
                    "-30 <= nums[i] <= 30"
                ]
            },
            "expected_constraints": [
                "2 <= nums.length <= 10^5",
                "-30 <= nums[i] <= 30"
            ],
            "expected_edge_case_categories": [
                "ZERO_VALUE",
                "DUPLICATE_ELEMENTS",
                "NEGATIVE_VALUES",
                "IDENTICAL_ALL",
                "LOWER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "prefix-sum", "boundary-conditions", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Arrays & Hashing"}
        },
        {
            "id": "eval-012-valid-anagram",
            "name": "Valid Anagram",
            "description": "Determine if two strings are anagrams of each other.",
            "problem_statement": "Given two strings s and t, return true if t is an anagram of s, and false otherwise. An Anagram is a word or phrase formed by rearranging the letters of a different word or phrase, typically using all the original letters exactly once. Constraints: 1 <= s.length, t.length <= 5 * 10^4, s and t consist of lowercase English letters.",
            "code_snippet": "def is_anagram(s: str, t: str) -> bool:\n    if len(s) != len(t):\n        return False\n    count = {}\n    for c in s:\n        count[c] = count.get(c, 0) + 1\n    for c in t:\n        if c not in count or count[c] == 0:\n            return False\n        count[c] -= 1\n    return True",
            "filename": "valid_anagram.py",
            "test_cases": [
                {"input_data": {"s": "anagram", "t": "nagaram"}}
            ],
            "problem_context": {
                "title": "Valid Anagram",
                "constraints": [
                    "1 <= s.length, t.length <= 50000",
                    "s and t consist of lowercase English letters"
                ]
            },
            "expected_constraints": [
                "1 <= s.length, t.length <= 50000"
            ],
            "expected_edge_case_categories": [
                "SINGLETON",
                "DUPLICATE_ELEMENTS",
                "IDENTICAL_ALL",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["strings", "hash-table", "sorting", "easy"],
            "difficulty": "easy",
            "metadata": {"category": "Arrays & Hashing"}
        },
        {
            "id": "eval-013-rotate-matrix",
            "name": "Rotate Image",
            "description": "Rotate n x n 2D matrix by 90 degrees clockwise in-place.",
            "problem_statement": "You are given an n x n 2D matrix representing an image, rotate the image by 90 degrees (clockwise) in-place without allocating another matrix. Constraints: n == matrix.length == matrix[i].length, 1 <= n <= 20, -1000 <= matrix[i][j] <= 1000.",
            "code_snippet": "def rotate(matrix: list[list[int]]) -> None:\n    n = len(matrix)\n    for i in range(n):\n        for j in range(i + 1, n):\n            matrix[i][j], matrix[j][i] = matrix[j][i], matrix[i][j]\n    for row in matrix:\n        row.reverse()",
            "filename": "rotate_image.py",
            "test_cases": [
                {"input_data": {"matrix": [[1, 2, 3], [4, 5, 6], [7, 8, 9]]}}
            ],
            "problem_context": {
                "title": "Rotate Image",
                "constraints": [
                    "n == matrix.length == matrix[i].length",
                    "1 <= n <= 20",
                    "-1000 <= matrix[i][j] <= 1000"
                ]
            },
            "expected_constraints": [
                "1 <= n <= 20",
                "-1000 <= matrix[i][j] <= 1000"
            ],
            "expected_edge_case_categories": [
                "MATRIX_DIMENSIONS",
                "SINGLETON",
                "ZERO_VALUE",
                "NEGATIVE_VALUES",
                "IDENTICAL_ALL",
                "LOWER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "matrix", "math", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Math & Geometry"}
        },
        {
            "id": "eval-014-group-anagrams",
            "name": "Group Anagrams",
            "description": "Group an array of strings into sub-lists of anagrams.",
            "problem_statement": "Given an array of strings strs, group the anagrams together. You can return the answer in any order. Constraints: 1 <= strs.length <= 10^4, 0 <= strs[i].length <= 100, strs[i] consists of lowercase English letters.",
            "code_snippet": "from collections import defaultdict\n\ndef group_anagrams(strs: list[str]) -> list[list[str]]:\n    groups = defaultdict(list)\n    for s in strs:\n        key = tuple(sorted(s))\n        groups[key].append(s)\n    return list(groups.values())",
            "filename": "group_anagrams.py",
            "test_cases": [
                {"input_data": {"strs": ["eat", "tea", "tan", "ate", "nat", "bat"]}}
            ],
            "problem_context": {
                "title": "Group Anagrams",
                "constraints": [
                    "1 <= strs.length <= 10000",
                    "0 <= strs[i].length <= 100"
                ]
            },
            "expected_constraints": [
                "1 <= strs.length <= 10000",
                "0 <= strs[i].length <= 100"
            ],
            "expected_edge_case_categories": [
                "EMPTY_COLLECTION",
                "SINGLETON",
                "DUPLICATE_ELEMENTS",
                "IDENTICAL_ALL",
                "LOWER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "strings", "hash-table", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Arrays & Hashing"}
        },
        {
            "id": "eval-015-search-rotated-array",
            "name": "Search in Rotated Sorted Array",
            "description": "Search target in rotated sorted array in O(log n) time.",
            "problem_statement": "There is an integer array nums sorted in ascending order (with distinct values). Prior to being passed to your function, nums is possibly rotated at an unknown pivot index. Given nums after the possible rotation and an integer target, return the index of target if it is in nums, or -1 if it is not in nums. Constraints: 1 <= nums.length <= 5000, -10^4 <= nums[i] <= 10^4, all values of nums are unique, -10^4 <= target <= 10^4.",
            "code_snippet": "def search_rotated(nums: list[int], target: int) -> int:\n    l, r = 0, len(nums) - 1\n    while l <= r:\n        mid = (l + r) // 2\n        if nums[mid] == target:\n            return mid\n        if nums[l] <= nums[mid]:\n            if nums[l] <= target < nums[mid]:\n                r = mid - 1\n            else:\n                l = mid + 1\n        else:\n            if nums[mid] < target <= nums[r]:\n                l = mid + 1\n            else:\n                r = mid - 1\n    return -1",
            "filename": "search_rotated.py",
            "test_cases": [
                {"input_data": {"nums": [4, 5, 6, 7, 0, 1, 2], "target": 0}}
            ],
            "problem_context": {
                "title": "Search in Rotated Sorted Array",
                "constraints": [
                    "1 <= nums.length <= 5000",
                    "-10^4 <= nums[i] <= 10^4",
                    "-10^4 <= target <= 10^4"
                ]
            },
            "expected_constraints": [
                "1 <= nums.length <= 5000",
                "-10^4 <= nums[i] <= 10^4",
                "-10^4 <= target <= 10^4"
            ],
            "expected_edge_case_categories": [
                "SINGLETON",
                "TARGET_NOT_FOUND",
                "TARGET_AT_BOUNDARIES",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND",
                "ALREADY_SORTED"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "binary-search", "boundary-conditions", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Binary Search"}
        },
        {
            "id": "eval-016-trapping-rain-water",
            "name": "Trapping Rain Water",
            "description": "Compute how much water can be trapped after raining given elevation map.",
            "problem_statement": "Given n non-negative integers representing an elevation map where the width of each bar is 1, compute how much water it can trap after raining. Constraints: n == height.length, 1 <= n <= 2 * 10^4, 0 <= height[i] <= 10^5.",
            "code_snippet": "def trap(height: list[int]) -> int:\n    if not height:\n        return 0\n    l, r = 0, len(height) - 1\n    left_max, right_max = height[l], height[r]\n    water = 0\n    while l < r:\n        if left_max < right_max:\n            l += 1\n            left_max = max(left_max, height[l])\n            water += left_max - height[l]\n        else:\n            r -= 1\n            right_max = max(right_max, height[r])\n            water += right_max - height[r]\n    return water",
            "filename": "trapping_rain_water.py",
            "test_cases": [
                {"input_data": {"height": [0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1]}}
            ],
            "problem_context": {
                "title": "Trapping Rain Water",
                "constraints": [
                    "1 <= height.length <= 20000",
                    "0 <= height[i] <= 100000"
                ]
            },
            "expected_constraints": [
                "1 <= height.length <= 20000",
                "0 <= height[i] <= 100000"
            ],
            "expected_edge_case_categories": [
                "SINGLETON",
                "ZERO_VALUE",
                "IDENTICAL_ALL",
                "ALREADY_SORTED",
                "REVERSE_SORTED",
                "LOWER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "two-pointers", "dynamic-programming", "hard"],
            "difficulty": "hard",
            "metadata": {"category": "Two Pointers"}
        },
        {
            "id": "eval-017-kth-largest-element",
            "name": "Kth Largest Element in an Array",
            "description": "Find the kth largest element in an unsorted array.",
            "problem_statement": "Given an integer array nums and an integer k, return the kth largest element in the array. Note that it is the kth largest element in the sorted order, not the kth distinct element. Constraints: 1 <= k <= nums.length <= 10^5, -10^4 <= nums[i] <= 10^4.",
            "code_snippet": "import heapq\n\ndef find_kth_largest(nums: list[int], k: int) -> int:\n    return heapq.nlargest(k, nums)[-1]",
            "filename": "kth_largest.py",
            "test_cases": [
                {"input_data": {"nums": [3, 2, 1, 5, 6, 4], "k": 2}}
            ],
            "problem_context": {
                "title": "Kth Largest Element in an Array",
                "constraints": [
                    "1 <= k <= nums.length <= 100000",
                    "-10^4 <= nums[i] <= 10^4"
                ]
            },
            "expected_constraints": [
                "1 <= k <= nums.length <= 100000",
                "-10^4 <= nums[i] <= 10^4"
            ],
            "expected_edge_case_categories": [
                "SINGLETON",
                "DUPLICATE_ELEMENTS",
                "NEGATIVE_VALUES",
                "ZERO_VALUE",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "heaps", "sorting", "quickselect", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Heap / Priority Queue"}
        },
        {
            "id": "eval-018-word-search",
            "name": "Word Search",
            "description": "Given an m x n grid of characters and string word, return true if word exists in grid.",
            "problem_statement": "Given an m x n grid of characters board and a string word, return true if word exists in the grid. The word can be constructed from letters of sequentially adjacent cells (horizontally or vertically neighboring). The same letter cell may not be used more than once. Constraints: m == board.length, n == board[i].length, 1 <= m, n <= 6, 1 <= word.length <= 15, board and word consist of only lowercase and uppercase English letters.",
            "code_snippet": "def exist(board: list[list[str]], word: str) -> bool:\n    rows, cols = len(board), len(board[0])\n    def dfs(r, c, idx):\n        if idx == len(word):\n            return True\n        if r < 0 or c < 0 or r >= rows or c >= cols or board[r][c] != word[idx]:\n            return False\n        temp = board[r][c]\n        board[r][c] = '#'\n        found = (dfs(r+1, c, idx+1) or dfs(r-1, c, idx+1) or\n                 dfs(r, c+1, idx+1) or dfs(r, c-1, idx+1))\n        board[r][c] = temp\n        return found\n    for r in range(rows):\n        for c in range(cols):\n            if dfs(r, c, 0):\n                return True\n    return False",
            "filename": "word_search.py",
            "test_cases": [
                {"input_data": {"board": [["A","B","C","E"],["S","F","C","S"],["A","D","E","E"]], "word": "ABCCED"}}
            ],
            "problem_context": {
                "title": "Word Search",
                "constraints": [
                    "1 <= m, n <= 6",
                    "1 <= word.length <= 15"
                ]
            },
            "expected_constraints": [
                "1 <= m, n <= 6",
                "1 <= word.length <= 15"
            ],
            "expected_edge_case_categories": [
                "MATRIX_DIMENSIONS",
                "SINGLETON",
                "TARGET_NOT_FOUND",
                "IDENTICAL_ALL",
                "LOWER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "matrix", "backtracking", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Backtracking"}
        },
        {
            "id": "eval-019-number-of-islands",
            "name": "Number of Islands",
            "description": "Given an m x n 2D binary grid, return the number of islands surrounded by water.",
            "problem_statement": "Given an m x n 2D binary grid grid which represents a map of '1's (land) and '0's (water), return the number of islands. An island is surrounded by water and is formed by connecting adjacent lands horizontally or vertically. Constraints: m == grid.length, n == grid[i].length, 1 <= m, n <= 300, grid[i][j] is '0' or '1'.",
            "code_snippet": "def num_islands(grid: list[list[str]]) -> int:\n    if not grid:\n        return 0\n    rows, cols = len(grid), len(grid[0])\n    count = 0\n    def dfs(r, c):\n        if r < 0 or c < 0 or r >= rows or c >= cols or grid[r][c] != '1':\n            return\n        grid[r][c] = '0'\n        dfs(r + 1, c)\n        dfs(r - 1, c)\n        dfs(r, c + 1)\n        dfs(r, c - 1)\n    for r in range(rows):\n        for c in range(cols):\n            if grid[r][c] == '1':\n                count += 1\n                dfs(r, c)\n    return count",
            "filename": "num_islands.py",
            "test_cases": [
                {"input_data": {"grid": [["1", "1", "0"], ["1", "1", "0"], ["0", "0", "1"]]}}
            ],
            "problem_context": {
                "title": "Number of Islands",
                "constraints": [
                    "1 <= m, n <= 300",
                    "grid[i][j] is '0' or '1'"
                ]
            },
            "expected_constraints": [
                "1 <= m, n <= 300"
            ],
            "expected_edge_case_categories": [
                "MATRIX_DIMENSIONS",
                "SINGLETON",
                "ZERO_VALUE",
                "IDENTICAL_ALL",
                "LOWER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["matrix", "graphs", "dfs", "bfs", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Graphs"}
        },
        {
            "id": "eval-020-valid-sudoku",
            "name": "Valid Sudoku",
            "description": "Determine if a 9 x 9 Sudoku board is valid according to standard rules.",
            "problem_statement": "Determine if a 9 x 9 Sudoku board is valid. Only the filled cells need to be validated according to the following rules: Each row must contain the digits 1-9 without repetition. Each column must contain the digits 1-9 without repetition. Each of the nine 3 x 3 sub-boxes must contain the digits 1-9 without repetition. Constraints: board.length == 9, board[i].length == 9, board[i][j] is a digit 1-9 or '.'.",
            "code_snippet": "def is_valid_sudoku(board: list[list[str]]) -> bool:\n    rows = [set() for _ in range(9)]\n    cols = [set() for _ in range(9)]\n    boxes = [set() for _ in range(9)]\n    for r in range(9):\n        for c in range(9):\n            val = board[r][c]\n            if val == '.':\n                continue\n            box_idx = (r // 3) * 3 + (c // 3)\n            if val in rows[r] or val in cols[c] or val in boxes[box_idx]:\n                return False\n            rows[r].add(val)\n            cols[c].add(val)\n            boxes[box_idx].add(val)\n    return True",
            "filename": "valid_sudoku.py",
            "test_cases": [
                {"input_data": {"board": [["5","3",".",".","7",".",".",".","."],["6",".",".","1","9","5",".",".","."],[".","9","8",".",".",".",".","6","."],["8",".",".",".","6",".",".",".","3"],["4",".",".","8",".","3",".",".","1"],["7",".",".",".","2",".",".",".","6"],[".","6",".",".",".",".","2","8","."],[".",".",".","4","1","9",".",".","5"],[".",".",".",".","8",".",".","7","9"]]}}
            ],
            "problem_context": {
                "title": "Valid Sudoku",
                "constraints": [
                    "board.length == 9",
                    "board[i].length == 9",
                    "board[i][j] is a digit 1-9 or '.'"
                ]
            },
            "expected_constraints": [
                "board.length == 9",
                "board[i].length == 9"
            ],
            "expected_edge_case_categories": [
                "MATRIX_DIMENSIONS",
                "DUPLICATE_ELEMENTS",
                "IDENTICAL_ALL",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "matrix", "hash-table", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Arrays & Hashing"}
        },
        {
            "id": "eval-021-subsets",
            "name": "Subsets",
            "description": "Given an integer array nums of unique elements, return all possible subsets (the power set).",
            "problem_statement": "Given an integer array nums of unique elements, return all possible subsets (the power set). The solution set must not contain duplicate subsets. Return the solution in any order. Constraints: 1 <= nums.length <= 10, -10 <= nums[i] <= 10, all numbers of nums are unique.",
            "code_snippet": "def subsets(nums: list[int]) -> list[list[int]]:\n    res = []\n    subset = []\n    def dfs(i):\n        if i >= len(nums):\n            res.append(subset.copy())\n            return\n        subset.append(nums[i])\n        dfs(i + 1)\n        subset.pop()\n        dfs(i + 1)\n    dfs(0)\n    return res",
            "filename": "subsets.py",
            "test_cases": [
                {"input_data": {"nums": [1, 2, 3]}}
            ],
            "problem_context": {
                "title": "Subsets",
                "constraints": [
                    "1 <= nums.length <= 10",
                    "-10 <= nums[i] <= 10"
                ]
            },
            "expected_constraints": [
                "1 <= nums.length <= 10",
                "-10 <= nums[i] <= 10"
            ],
            "expected_edge_case_categories": [
                "SINGLETON",
                "ZERO_VALUE",
                "NEGATIVE_VALUES",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["arrays", "backtracking", "bit-manipulation", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Backtracking"}
        },
        {
            "id": "eval-022-palindrome-partitioning",
            "name": "Palindrome Partitioning",
            "description": "Partition string such that every substring of the partition is a palindrome.",
            "problem_statement": "Given a string s, partition s such that every substring of the partition is a palindrome. Return all possible palindrome partitioning of s. Constraints: 1 <= s.length <= 16, s contains only lowercase English letters.",
            "code_snippet": "def partition(s: str) -> list[list[str]]:\n    res = []\n    part = []\n    def is_pali(sub, l, r):\n        while l < r:\n            if sub[l] != sub[r]:\n                return False\n            l, r = l + 1, r - 1\n        return True\n    def dfs(i):\n        if i >= len(s):\n            res.append(part.copy())\n            return\n        for j in range(i, len(s)):\n            if is_pali(s, i, j):\n                part.append(s[i:j+1])\n                dfs(j + 1)\n                part.pop()\n    dfs(0)\n    return res",
            "filename": "palindrome_partition.py",
            "test_cases": [
                {"input_data": {"s": "aab"}}
            ],
            "problem_context": {
                "title": "Palindrome Partitioning",
                "constraints": [
                    "1 <= s.length <= 16",
                    "s contains only lowercase English letters"
                ]
            },
            "expected_constraints": [
                "1 <= s.length <= 16"
            ],
            "expected_edge_case_categories": [
                "SINGLETON",
                "IDENTICAL_ALL",
                "DUPLICATE_ELEMENTS",
                "LOWER_CONSTRAINT_BOUND",
                "UPPER_CONSTRAINT_BOUND"
            ],
            "expected_relevant_tools": [
                "analyze_problem_structure",
                "parse_problem_constraints",
                "detect_coverage_gaps",
                "generate_candidate_inputs",
                "validate_candidate_inputs",
                "rank_candidate_inputs"
            ],
            "tags": ["strings", "dynamic-programming", "backtracking", "medium"],
            "difficulty": "medium",
            "metadata": {"category": "Backtracking"}
        }
    ]
}

def main():
    # 1. Validate dataset against Pydantic schema
    dataset_model = EvaluationDataset(**DATASET)
    print(f"Dataset successfully validated! Total examples: {len(dataset_model.examples)}")

    # 2. Write formatted JSON to coding_problems.json
    out_path = Path(__file__).parent / "coding_problems.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(DATASET, f, indent=2)
    print(f"Written dataset to {out_path.resolve()}")

if __name__ == "__main__":
    main()

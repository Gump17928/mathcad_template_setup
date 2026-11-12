"""Tests for the plain-arithmetic formula parser."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tool"))

from formula import BinOp, Neg, Num, Parens, Var, evaluate, parse, rename_variables, to_text, variables  # noqa: E402


class ParseTest(unittest.TestCase):
    def test_precedence_multiplication_binds_tighter_than_addition(self):
        self.assertEqual(parse("a+b*c"), BinOp("+", Var("a"), BinOp("*", Var("b"), Var("c"))))

    def test_power_is_right_associative(self):
        self.assertEqual(parse("a^b^c"), BinOp("^", Var("a"), BinOp("^", Var("b"), Var("c"))))

    def test_subtraction_is_left_associative(self):
        self.assertEqual(parse("a-b-c"), BinOp("-", BinOp("-", Var("a"), Var("b")), Var("c")))

    def test_unary_minus_and_parentheses(self):
        self.assertEqual(parse("-(a)"), Neg(Parens(Var("a"))))

    def test_numbers_keep_their_text(self):
        self.assertEqual(parse("1.50e3"), Num("1.50e3"))

    def test_rejects_things_that_are_not_plain_arithmetic(self):
        for bad in ("sqrt(a)", "a +", "(a", "a b", "a $ b", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse(bad)


class TreeOperationsTest(unittest.TestCase):
    def test_variables(self):
        self.assertEqual(variables(parse("a*(b+a)/2")), {"a", "b"})

    def test_rename_variables_leaves_numbers_alone(self):
        self.assertEqual(to_text(rename_variables(parse("2*a+b"), {"a": "X_a", "b": "X_b"})), "2*X_a+X_b")

    def test_evaluate(self):
        self.assertAlmostEqual(evaluate(parse("(a+1)^2/4-b"), {"a": 3, "b": 1}), 3.0)

    def test_evaluate_reports_problems_instead_of_returning_nonsense(self):
        with self.assertRaises(ZeroDivisionError):
            evaluate(parse("1/a"), {"a": 0})
        with self.assertRaises(KeyError):
            evaluate(parse("a"), {})
        with self.assertRaises(ValueError):  # a negative number to a fractional power is complex
            evaluate(parse("a^0.5"), {"a": -4})

    def test_to_text_round_trips(self):
        self.assertEqual(to_text(parse("a * ( b + 2 ) ^ 3")), "a*(b+2)^3")


if __name__ == "__main__":
    unittest.main()

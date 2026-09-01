import unittest

from segnatura.categories import (INTERNAL_TO_PUBLIC, PUBLIC_CATEGORIES,
                                  PUBLIC_TO_INTERNAL, to_internal, to_public)


class CategoriesTest(unittest.TestCase):
    def test_public_and_internal_categories_are_one_bijection(self):
        self.assertEqual(set(PUBLIC_CATEGORIES), set(PUBLIC_TO_INTERNAL))
        self.assertEqual(len(PUBLIC_CATEGORIES), len(set(PUBLIC_CATEGORIES)))
        for internal, public in INTERNAL_TO_PUBLIC.items():
            self.assertEqual(public, to_public(internal))
            self.assertEqual(internal, to_internal(public))

    def test_unknown_categories_fail_instead_of_silently_drifting(self):
        with self.assertRaises(ValueError):
            to_public("unknown")
        with self.assertRaises(ValueError):
            to_internal("unknown")


if __name__ == "__main__":
    unittest.main()

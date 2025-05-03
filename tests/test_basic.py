"""
Basic tests for the Youtubingest application.
"""
import unittest
import sys
import os

# Add the parent directory to the path so we can import the application modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class BasicTests(unittest.TestCase):
    """Basic test cases."""

    def test_import(self):
        """Test that the main modules can be imported."""
        try:
            import main
            import models
            import services
            self.assertTrue(True)
        except ImportError as e:
            self.fail(f"Import failed: {e}")

    def test_environment(self):
        """Test that the environment is properly set up."""
        # This is just a placeholder test
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'README.md')))
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')))

if __name__ == '__main__':
    unittest.main()
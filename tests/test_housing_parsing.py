
import unittest
from app.services.housing_service import parse_housing_email_body

class TestHousingParsing(unittest.TestCase):

    def test_parse_standard_email(self):
        email_body = """
        Property Inquiry Details:
        Name : John Housing
        Mobile : +91-9876543210
        Email : john.housing@example.com
        Project : Green Valley Heights
        Location : Whitefield, Bangalore
        Budget : 50L - 75L
        """
        data = parse_housing_email_body(email_body)
        self.assertIsNotNone(data)
        self.assertEqual(data['name'], 'John Housing')
        self.assertEqual(data['phone'], '9876543210')
        self.assertEqual(data['email'], 'john.housing@example.com')
        self.assertEqual(data['project'], 'Green Valley Heights')
        self.assertEqual(data['location'], 'Whitefield, Bangalore')
        self.assertEqual(data['budget'], '50L - 75L')

    def test_parse_alternate_format(self):
        email_body = """
        Customer Name: Alice Builder
        Contact: 9898989898
        Email ID: alice@test.com
        City: Mumbai
        Property: Sea View Apts
        """
        data = parse_housing_email_body(email_body)
        self.assertIsNotNone(data)
        self.assertEqual(data['name'], 'Alice Builder')
        self.assertEqual(data['phone'], '9898989898')
        self.assertEqual(data['location'], 'Mumbai')
        self.assertEqual(data['project'], 'Sea View Apts')

    def test_parse_missing_fields(self):
        email_body = """
        Just a phone number: 9999988888
        """
        data = parse_housing_email_body(email_body)
        self.assertIsNotNone(data)
        self.assertEqual(data['phone'], '9999988888')
        # Others should be missing but not error
        self.assertIsNone(data.get('email'))

    def test_parse_invalid_email(self):
        email_body = """
        No contact info here.
        """
        data = parse_housing_email_body(email_body)
        self.assertIsNone(data)

if __name__ == '__main__':
    unittest.main()

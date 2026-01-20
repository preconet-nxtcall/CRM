
import unittest
import re

# Mocking the parse function structure to test regex logic in isolation
# Copying regex patterns from service file to ensure test validity
def parse_justdial_email_body(email_body):
    """
    Parses the email body from JustDial to extract lead details.
    """
    data = {}
    
    # Regex Patterns (Refined based on standard JustDial formats)
    patterns = {
        'name': r"Caller Name\s*[:\-]\s*(.+)",
        'mobile': r"Caller Mobile\s*[:\-]\s*(\+?\d+)",
        'email': r"Caller Email\s*[:\-]\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
        'area': r"Area\s*[:\-]\s*(.+)",
        'category': r"Category\s*[:\-]\s*(.+)",
        'requirement': r"Requirement\s*[:\-]\s*(.+)" 
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, email_body, re.IGNORECASE)
        if match:
            data[key] = match.group(1).strip()
    
    return data

class TestJustDialParsing(unittest.TestCase):
    
    def test_parse_standard_email(self):
        email_body = """
        JustDial Enquiry
        
        Caller Name : John Doe
        Caller Mobile : +919876543210
        Caller Email : johndoe@example.com
        Area : Mumbai
        Category : Real Estate Agents
        Requirement : Looking for 2BHK flat
        
        Regards,
        JustDial Team
        """
        
        result = parse_justdial_email_body(email_body)
        
        self.assertEqual(result.get('name'), "John Doe")
        self.assertEqual(result.get('mobile'), "+919876543210")
        self.assertEqual(result.get('email'), "johndoe@example.com")
        self.assertEqual(result.get('area'), "Mumbai")
        self.assertEqual(result.get('category'), "Real Estate Agents")

    def test_parse_missing_fields(self):
        email_body = """
        Caller Name : Jane Smith
        Caller Mobile : 9876543210
        """
        result = parse_justdial_email_body(email_body)
        
        self.assertEqual(result.get('name'), "Jane Smith")
        self.assertIsNone(result.get('email'))

if __name__ == '__main__':
    unittest.main()

"""
Password Security Policy for Africa SPA System

Implements strong password security measures similar to Kali Linux:
- Minimum length requirements
- Complexity requirements
- Dictionary word prevention
- Common password detection
- Password history tracking
- Expiration policies
"""

import re
import hashlib
import secrets
import string
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from flask import current_app

class PasswordPolicy:
    """Kali Linux-style password security implementation"""
    
    def __init__(self):
        self.min_length = 8
        self.max_length = 128
        self.min_uppercase = 1
        self.min_lowercase = 1
        self.min_digits = 1
        self.min_special = 1
        self.max_consecutive = 3
        self.password_history = 5
        self.expire_days = 90
        
        # Common passwords to reject
        self.common_passwords = {
            'password', '123456', '12345678', 'qwerty', 'abc123', 'password123',
            'admin', 'root', 'toor', 'pass', 'letmein', 'welcome', 'monkey',
            'dragon', 'master', 'sunshine', 'iloveyou', 'football', 'baseball',
            'shadow', 'superman', 'batman', 'spiderman', 'ironman', 'hulk',
            'thor', 'captain', 'marvel', 'dc', 'comics', 'hero', 'villain',
            'kali', 'linux', 'ubuntu', 'debian', 'mint', 'arch', 'fedora',
            'centos', 'redhat', 'suse', 'gentoo', 'slackware', 'bsd',
            'security', 'hacker', 'crack', 'break', 'test', 'demo', 'temp',
            'guest', 'user', 'staff', 'manager', 'admin123', 'password1',
            'changeme', 'default', 'blank', 'empty', 'null', 'void',
            '123', '1234', '12345', '1234567', '123456789', '1234567890',
            'qwertyuiop', 'asdfghjkl', 'zxcvbnm', 'qazwsx', '1qaz2wsx',
            'password!', 'password@', 'password#', 'password$', 'password%'
        }
        
        # Dictionary words (basic set)
        self.dictionary_words = {
            'africa', 'kenya', 'nairobi', 'nigeria', 'lagos', 'ghana', 'accra',
            'south', 'africa', 'johannesburg', 'cape', 'town', 'egypt', 'cairo',
            'tanzania', 'dar', 'es', 'salaam', 'uganda', 'kampala', 'salon',
            'spa', 'beauty', 'hair', 'style', 'cosmetic', 'makeup', 'nails',
            'massage', 'therapy', 'treatment', 'service', 'customer', 'client',
            'business', 'company', 'system', 'software', 'application', 'database',
            'network', 'server', 'computer', 'internet', 'online', 'digital',
            'mobile', 'phone', 'email', 'address', 'contact', 'information',
            'data', 'file', 'document', 'report', 'record', 'account', 'profile'
        }
        
        # Special characters allowed
        self.special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        
        # Patterns to detect weak passwords
        self.weak_patterns = [
            r'(.)\1{2,}',  # Repeated characters (aaa, bbb)
            r'(123|234|345|456|567|678|789|890|012)',  # Sequential numbers
            r'(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)',  # Sequential letters
            r'(qwe|wer|ert|rty|tyu|yui|uio|iop|pas|asd|sdf|dfg|fgh|ghj|hjk|jkl)',  # Keyboard patterns
            r'(\d)\1{2,}',  # Repeated digits (111, 222)
        ]
    
    def validate_password(self, password: str, username: str = None, email: str = None) -> Dict[str, any]:
        """
        Validate password against Kali Linux-style security policy
        
        Args:
            password: Password to validate
            username: User's username (to prevent inclusion)
            email: User's email (to prevent inclusion)
            
        Returns:
            Dictionary with validation results
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'strength': 0,
            'score': 0
        }
        
        # Basic length check
        if len(password) < self.min_length:
            result['valid'] = False
            result['errors'].append(f'Password must be at least {self.min_length} characters long')
        
        if len(password) > self.max_length:
            result['valid'] = False
            result['errors'].append(f'Password must not exceed {self.max_length} characters')
        
        # Character complexity checks
        uppercase_count = sum(1 for c in password if c.isupper())
        lowercase_count = sum(1 for c in password if c.islower())
        digit_count = sum(1 for c in password if c.isdigit())
        special_count = sum(1 for c in password if c in self.special_chars)
        
        if uppercase_count < self.min_uppercase:
            result['valid'] = False
            result['errors'].append(f'Password must contain at least {self.min_uppercase} uppercase letter(s)')
        
        if lowercase_count < self.min_lowercase:
            result['valid'] = False
            result['errors'].append(f'Password must contain at least {self.min_lowercase} lowercase letter(s)')
        
        if digit_count < self.min_digits:
            result['valid'] = False
            result['errors'].append(f'Password must contain at least {self.min_digits} digit(s)')
        
        if special_count < self.min_special:
            result['valid'] = False
            result['errors'].append(f'Password must contain at least {self.min_special} special character(s)')
        
        # Check for common passwords
        if password.lower() in self.common_passwords:
            result['valid'] = False
            result['errors'].append('Password is too common and easily guessable')
        
        # Check for dictionary words
        password_lower = password.lower()
        found_words = [word for word in self.dictionary_words if word in password_lower]
        if found_words:
            result['warnings'].append(f'Password contains common word(s): {", ".join(found_words)}')
        
        # Check for personal information (less restrictive)
        if username and len(username) >= 3 and username.lower() in password_lower:
            # Only reject if username is a significant part of password (more than 50%)
            username_ratio = len(username) / len(password)
            if username_ratio > 0.5:
                result['valid'] = False
                result['errors'].append('Password cannot contain your username as a major component')
        
        if email:
            email_parts = email.split('@')[0].lower()
            if email_parts in password_lower:
                result['valid'] = False
                result['errors'].append('Password cannot contain your email address')
        
        # Check for weak patterns
        for pattern in self.weak_patterns:
            if re.search(pattern, password_lower):
                result['valid'] = False
                result['errors'].append('Password contains weak patterns (sequential or repeated characters)')
        
        # Check for consecutive characters
        for i in range(len(password) - self.max_consecutive + 1):
            if len(set(password[i:i+self.max_consecutive])) == 1:
                result['valid'] = False
                result['errors'].append(f'Password cannot contain more than {self.max_consecutive} consecutive identical characters')
        
        # Calculate password strength
        result['strength'] = self._calculate_strength(password)
        result['score'] = result['strength']
        
        # Add recommendations based on strength
        if result['strength'] < 60:
            result['warnings'].append('Password is weak - consider using a stronger password')
        elif result['strength'] < 80:
            result['warnings'].append('Password could be stronger - consider adding more complexity')
        
        return result
    
    def _calculate_strength(self, password: str) -> int:
        """Calculate password strength score (0-100)"""
        score = 0
        
        # Length contribution
        length_score = min(len(password) * 2, 30)
        score += length_score
        
        # Character variety
        if any(c.isupper() for c in password):
            score += 10
        if any(c.islower() for c in password):
            score += 10
        if any(c.isdigit() for c in password):
            score += 10
        if any(c in self.special_chars for c in password):
            score += 15
        
        # Complexity bonus
        unique_chars = len(set(password))
        if unique_chars >= len(password) * 0.7:
            score += 15
        
        # Penalty for common patterns
        password_lower = password.lower()
        if any(pattern in password_lower for pattern in ['123', 'abc', 'qwe']):
            score -= 10
        
        return min(score, 100)
    
    def generate_strong_password(self, length: int = 16) -> str:
        """Generate a strong password meeting all requirements"""
        if length < self.min_length:
            length = self.min_length
        
        # Ensure we have at least one of each required character type
        password_chars = []
        
        # Add required characters
        password_chars.append(secrets.choice(string.ascii_uppercase))
        password_chars.append(secrets.choice(string.ascii_lowercase))
        password_chars.append(secrets.choice(string.digits))
        password_chars.append(secrets.choice(self.special_chars))
        
        # Fill the rest with random characters
        all_chars = string.ascii_letters + string.digits + self.special_chars
        for _ in range(length - 4):
            password_chars.append(secrets.choice(all_chars))
        
        # Shuffle the password
        secrets.SystemRandom().shuffle(password_chars)
        
        return ''.join(password_chars)
    
    def check_password_history(self, user_id: int, new_password: str, password_history: List[str]) -> bool:
        """Check if new password has been used before"""
        for old_password in password_history:
            if self._passwords_similar(new_password, old_password):
                return False
        return True
    
    def _passwords_similar(self, pwd1: str, pwd2: str) -> bool:
        """Check if two passwords are too similar"""
        if pwd1 == pwd2:
            return True
        
        # Check for high similarity (Levenshtein distance)
        if len(pwd1) > 0 and len(pwd2) > 0:
            distance = self._levenshtein_distance(pwd1, pwd2)
            max_len = max(len(pwd1), len(pwd2))
            similarity = 1 - (distance / max_len)
            
            if similarity > 0.8:  # 80% similarity or more
                return True
        
        return False
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def is_password_expired(self, last_changed: datetime) -> bool:
        """Check if password has expired"""
        if not last_changed:
            return True
        
        return datetime.utcnow() > last_changed + timedelta(days=self.expire_days)
    
    def get_password_requirements(self) -> Dict[str, any]:
        """Get password requirements for display"""
        return {
            'min_length': self.min_length,
            'max_length': self.max_length,
            'min_uppercase': self.min_uppercase,
            'min_lowercase': self.min_lowercase,
            'min_digits': self.min_digits,
            'min_special': self.min_special,
            'special_chars': self.special_chars,
            'expire_days': self.expire_days,
            'password_history': self.password_history
        }

# Global instance
password_policy = PasswordPolicy()

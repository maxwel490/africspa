#!/usr/bin/env python3
"""
Clean up debug and development code for production
"""

import os
import re

def clean_debug_statements():
    """Remove or comment out debug print statements"""
    
    debug_files = []
    for root, dirs, files in os.walk('app'):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Look for debug statements
                    if 'print(' in content:
                        debug_files.append(file_path)
                        print(f"Found debug statements in: {file_path}")
                        
                        # Comment out debug statements
                        lines = content.split('\n')
                        modified_lines = []
                        for line in lines:
                            if 'print(' in line and not line.strip().startswith('#'):
                                modified_lines.append(f"# DEBUG: {line}")
                            else:
                                modified_lines.append(line)
                        
                        # Write back the file
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write('\n'.join(modified_lines))
                            
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")
    
    return debug_files

def clean_console_logs():
    """Remove console.log statements from HTML templates"""
    
    template_files = []
    for root, dirs, files in os.walk('app/templates'):
        for file in files:
            if file.endswith('.html'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Look for console.log statements
                    if 'console.log(' in content:
                        template_files.append(file_path)
                        print(f"Found console.log in: {file_path}")
                        
                        # Remove console.log statements
                        content = re.sub(r'console\.log\([^)]*\);?', '', content)
                        
                        # Write back the file
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                            
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")
    
    return template_files

def remove_test_files():
    """Remove test and development files"""
    
    test_files = [
        'test_pricing.py',
        'test_tenant_isolation.py',
        'simple_pricing_test.py',
        'checkdb.py',
        'check_db.py',  # Our temporary check script
    ]
    
    removed_files = []
    for test_file in test_files:
        if os.path.exists(test_file):
            os.remove(test_file)
            removed_files.append(test_file)
            print(f"Removed test file: {test_file}")
    
    return removed_files

if __name__ == "__main__":
    print("=== Cleaning up debug and development code ===")
    
    debug_files = clean_debug_statements()
    template_files = clean_console_logs()
    test_files = remove_test_files()
    
    print(f"\n=== Cleanup Summary ===")
    print(f"Debug statements cleaned in: {len(debug_files)} files")
    print(f"Console.log cleaned in: {len(template_files)} files")
    print(f"Test files removed: {len(test_files)} files")
    print("✓ Debug cleanup completed")

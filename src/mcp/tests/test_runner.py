#!/usr/bin/env python3
"""
Test runner script for MCP service tests
This script can be used to run all tests for the MCP service
"""

import subprocess
import sys
import os


def run_tests():
    """Run all tests for the MCP service"""
    
    # Change to the mcp directory
    mcp_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(mcp_dir)
    
    print(f"Running tests in directory: {mcp_dir}")
    print("=" * 60)
    
    try:
        # Run pytest with verbose output
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/", "-v", "--tb=short"
        ], capture_output=True, text=True)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)
        
        print(f"\nTest run completed with return code: {result.returncode}")
        
        if result.returncode == 0:
            print("✅ All tests passed!")
        else:
            print("❌ Some tests failed!")
            
        return result.returncode
        
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
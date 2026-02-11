import sys
from unittest.mock import patch, MagicMock
import pytest
from roma_dspy.utils.lazy_imports import is_available, require_module, get_missing_features, lazy_import

def test_is_available_existing_module():
    """Test is_available returns True for existing standard library module."""
    assert is_available("os") is True
    assert is_available("sys") is True

def test_is_available_non_existing_module():
    """Test is_available returns False for non-existing module."""
    assert is_available("non_existent_module_xyz_123") is False

def test_require_module_success():
    """Test require_module does not raise error when module exists."""
    # 'os' should always exist
    require_module("os", "OS Feature", "os-extra")

def test_require_module_failure():
    """Test require_module raises ImportError with helpful message when module missing."""
    with pytest.raises(ImportError) as excinfo:
        require_module("non_existent_module_xyz_123", "Cool Feature", "cool-extra")
    
    error_msg = str(excinfo.value)
    assert "Cool Feature requires non_existent_module_xyz_123" in error_msg
    assert "uv pip install roma-dspy[cool-extra]" in error_msg

def test_get_missing_features():
    """Test get_missing_features returns a dict."""
    missing = get_missing_features()
    assert isinstance(missing, dict)
    # We can't guarantee what's missing in the test environment, but we can check the values structure if any exist
    for install_cmd in missing.values():
        assert "uv pip install" in install_cmd

def test_lazy_import_success():
    """Test lazy_import returns module if it exists."""
    os_mod = lazy_import("os")
    assert os_mod is not None
    assert os_mod.__name__ == "os"

def test_lazy_import_failure():
    """Test lazy_import returns None if module does not exist."""
    mod = lazy_import("non_existent_module_xyz_123")
    assert mod is None

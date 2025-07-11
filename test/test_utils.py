import pytest
from datetime import datetime, timezone
from app import convert_timeframe_to_milliseconds, parse_timestamp


class TestConvertTimeframeToMilliseconds:
    """Test suite for convert_timeframe_to_milliseconds function."""
    
    def test_minutes_conversion(self):
        """Test conversion of minutes to milliseconds."""
        assert convert_timeframe_to_milliseconds("5m") == 5 * 60 * 1000
        assert convert_timeframe_to_milliseconds("15m") == 15 * 60 * 1000
        assert convert_timeframe_to_milliseconds("30m") == 30 * 60 * 1000
        assert convert_timeframe_to_milliseconds("60m") == 60 * 60 * 1000
    
    def test_hours_conversion(self):
        """Test conversion of hours to milliseconds."""
        assert convert_timeframe_to_milliseconds("1h") == 1 * 3600 * 1000
        assert convert_timeframe_to_milliseconds("4h") == 4 * 3600 * 1000
        assert convert_timeframe_to_milliseconds("12h") == 12 * 3600 * 1000
        assert convert_timeframe_to_milliseconds("24h") == 24 * 3600 * 1000
    
    def test_days_conversion(self):
        """Test conversion of days to milliseconds."""
        assert convert_timeframe_to_milliseconds("1d") == 1 * 86400 * 1000
        assert convert_timeframe_to_milliseconds("7d") == 7 * 86400 * 1000
        assert convert_timeframe_to_milliseconds("30d") == 30 * 86400 * 1000
    
    def test_case_insensitivity(self):
        """Test that timeframe conversion is case-insensitive."""
        assert convert_timeframe_to_milliseconds("5M") == 5 * 60 * 1000
        assert convert_timeframe_to_milliseconds("1H") == 1 * 3600 * 1000
        assert convert_timeframe_to_milliseconds("1D") == 1 * 86400 * 1000
        assert convert_timeframe_to_milliseconds("5m") == convert_timeframe_to_milliseconds("5M")
    
    def test_invalid_format_handling(self):
        """Test handling of invalid timeframe formats."""
        with pytest.raises(ValueError, match="Invalid timeframe format"):
            convert_timeframe_to_milliseconds("5")
        
        with pytest.raises(ValueError, match="Invalid timeframe format"):
            convert_timeframe_to_milliseconds("5x")
        
        with pytest.raises(ValueError, match="Invalid timeframe format"):
            convert_timeframe_to_milliseconds("invalid")
        
        with pytest.raises(ValueError, match="Invalid timeframe format"):
            convert_timeframe_to_milliseconds("")
    
    def test_invalid_number_format(self):
        """Test handling of invalid number in timeframe."""
        with pytest.raises(ValueError):
            convert_timeframe_to_milliseconds("am")
        
        with pytest.raises(ValueError):
            convert_timeframe_to_milliseconds("h")
        
        with pytest.raises(ValueError):
            convert_timeframe_to_milliseconds("1.5h")


class TestParseTimestamp:
    """Test suite for parse_timestamp function."""
    
    def test_unix_milliseconds_parsing(self):
        """Test Unix milliseconds parsing."""
        assert parse_timestamp("1609459200000") == 1609459200000
        assert parse_timestamp("0") == 0
        assert parse_timestamp("1234567890123") == 1234567890123
    
    def test_negative_unix_milliseconds(self):
        """Test negative Unix milliseconds parsing."""
        assert parse_timestamp("-1000") == -1000
        assert parse_timestamp("-1609459200000") == -1609459200000
    
    def test_iso_format_parsing(self):
        """Test ISO format parsing (with timezone)."""
        # Test with UTC timezone
        result = parse_timestamp("2021-01-01T00:00:00+00:00")
        assert result == 1609459200000
        
        # Test with no timezone (assumes local)
        dt = datetime(2021, 1, 1, 0, 0, 0)
        expected = int(dt.timestamp() * 1000)
        result = parse_timestamp("2021-01-01T00:00:00")
        assert result == expected
    
    def test_iso_format_with_microseconds(self):
        """Test ISO format with microseconds."""
        result = parse_timestamp("2021-01-01T00:00:00.123456+00:00")
        # Should round down to milliseconds
        assert result == 1609459200123
    
    def test_invalid_format_handling(self):
        """Test invalid format handling."""
        with pytest.raises(ValueError, match="Invalid timestamp format"):
            parse_timestamp("invalid")
        
        with pytest.raises(ValueError, match="Invalid timestamp format"):
            parse_timestamp("2021-13-01T00:00:00")  # Invalid month
        
        with pytest.raises(ValueError, match="Invalid timestamp format"):
            parse_timestamp("abc123")
        
        with pytest.raises(ValueError, match="Invalid timestamp format"):
            parse_timestamp("")
    
    def test_edge_cases(self):
        """Test edge cases."""
        # Very large timestamp
        assert parse_timestamp("9999999999999") == 9999999999999
        
        # Test with spaces (int() strips spaces, so this works)
        assert parse_timestamp(" 1609459200000 ") == 1609459200000
        
        # Test float string (should fail because int() doesn't accept float strings directly)
        with pytest.raises(ValueError):
            parse_timestamp("1609459200000.5")
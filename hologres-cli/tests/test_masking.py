"""Tests for masking module."""

from __future__ import annotations

import pytest

from hologres_cli.masking import (
    _mask_bank_card,
    _mask_email,
    _mask_id_card,
    _mask_password,
    _mask_phone,
    get_mask_function,
    mask_rows,
)


class TestMaskPhone:
    """Tests for _mask_phone function."""

    def test_mask_phone_standard(self):
        """Test masking standard 11-digit Chinese mobile number."""
        result = _mask_phone("13812345678")
        assert result == "138****5678"

    def test_mask_phone_11_digits(self):
        """Test masking 11-digit number."""
        result = _mask_phone("15900001111")
        assert result == "159****1111"

    def test_mask_phone_with_spaces(self):
        """Test phone with spaces."""
        result = _mask_phone("138 1234 5678")
        # Extracts digits: 13812345678
        assert result == "138****5678"

    def test_mask_phone_with_dashes(self):
        """Test phone with dashes."""
        result = _mask_phone("138-1234-5678")
        assert result == "138****5678"

    def test_mask_phone_short_less_than_7(self):
        """Test phone with less than 7 digits returns all asterisks."""
        result = _mask_phone("123456")
        # Length of original string is 6, all masked
        assert result == "******"

    def test_mask_phone_exactly_7_digits(self):
        """Test phone with exactly 7 digits."""
        result = _mask_phone("1234567")
        # 7 digits: 3 + (7-7=0 asterisks) + 4 = 1234567
        assert result == "1234567"

    def test_mask_phone_none(self):
        """Test None value returns empty string."""
        result = _mask_phone(None)
        assert result == ""

    def test_mask_phone_empty_string(self):
        """Test empty string."""
        result = _mask_phone("")
        # Empty string has 0 digits, returns 0 asterisks = ""
        assert result == ""

    def test_mask_phone_long_number(self):
        """Test longer phone number."""
        result = _mask_phone("13812345678901")  # 14 digits
        assert result == "138*******8901"


class TestMaskEmail:
    """Tests for _mask_email function."""

    def test_mask_email_standard(self):
        """Test masking standard email."""
        result = _mask_email("test@example.com")
        assert result == "t***@example.com"

    def test_mask_email_short_local(self):
        """Test email with 1-char local part."""
        result = _mask_email("a@example.com")
        assert result == "a***@example.com"

    def test_mask_email_long_local(self):
        """Test email with long local part."""
        result = _mask_email("verylongemail@domain.org")
        assert result == "v***@domain.org"

    def test_mask_email_no_at(self):
        """Test string without @ returns ***."""
        result = _mask_email("noemail")
        assert result == "***"

    def test_mask_email_none(self):
        """Test None value returns empty string."""
        result = _mask_email(None)
        assert result == ""

    def test_mask_email_empty_string(self):
        """Test empty string."""
        result = _mask_email("")
        assert result == "***"

    def test_mask_email_multiple_at(self):
        """Test email with multiple @ symbols uses rsplit."""
        result = _mask_email("test@sub@example.com")
        # rsplit with maxsplit=1: local="test@sub", domain="example.com"
        assert result == "t***@example.com"

    def test_mask_email_empty_local(self):
        """Test email with empty local part."""
        result = _mask_email("@example.com")
        # local="" -> empty, so returns "***"
        assert result == "***"


class TestMaskPassword:
    """Tests for _mask_password function."""

    def test_mask_password_any(self):
        """Test any password returns ********."""
        result = _mask_password("secret123")
        assert result == "********"

    def test_mask_password_none(self):
        """Test None value returns ********."""
        result = _mask_password(None)
        assert result == "********"

    def test_mask_password_empty(self):
        """Test empty string returns ********."""
        result = _mask_password("")
        assert result == "********"

    def test_mask_password_long(self):
        """Test long password."""
        result = _mask_password("verylongpassword123!@#")
        assert result == "********"


class TestMaskIdCard:
    """Tests for _mask_id_card function."""

    def test_mask_id_card_18_digits(self):
        """Test masking 18-digit ID card."""
        result = _mask_id_card("330102199001011234")
        assert result == "330***********1234"

    def test_mask_id_card_15_digits(self):
        """Test masking 15-digit ID card."""
        result = _mask_id_card("330102900101123")
        # 15 digits: 3 + (15-7=8 asterisks) + 4 = 330********1123
        assert result == "330********1123"

    def test_mask_id_card_short_less_than_7(self):
        """Test ID card with less than 7 chars returns all asterisks."""
        result = _mask_id_card("123456")
        assert result == "******"

    def test_mask_id_card_exactly_7_chars(self):
        """Test ID card with exactly 7 chars."""
        result = _mask_id_card("1234567")
        # 7 chars: 3 + (7-7=0 asterisks) + 4 = 1234567
        assert result == "1234567"

    def test_mask_id_card_none(self):
        """Test None value returns empty string."""
        result = _mask_id_card(None)
        assert result == ""

    def test_mask_id_card_empty_string(self):
        """Test empty string."""
        result = _mask_id_card("")
        assert result == ""

    def test_mask_id_card_with_x(self):
        """Test 18-digit ID card ending with X."""
        result = _mask_id_card("33010219900101123X")
        assert result == "330***********123X"


class TestMaskBankCard:
    """Tests for _mask_bank_card function."""

    def test_mask_bank_card_16_digits(self):
        """Test masking 16-digit bank card."""
        result = _mask_bank_card("6222021234567890")
        assert result == "************7890"

    def test_mask_bank_card_19_digits(self):
        """Test masking 19-digit bank card."""
        result = _mask_bank_card("6222021234567890123")
        assert result == "***************0123"

    def test_mask_bank_card_with_spaces(self):
        """Test bank card with spaces."""
        result = _mask_bank_card("6222 0212 3456 7890")
        # Extracts digits: 6222021234567890
        assert result == "************7890"

    def test_mask_bank_card_short_less_than_4(self):
        """Test bank card with less than 4 digits returns all asterisks."""
        result = _mask_bank_card("123")
        assert result == "***"

    def test_mask_bank_card_exactly_4_digits(self):
        """Test bank card with exactly 4 digits."""
        result = _mask_bank_card("1234")
        assert result == "1234"

    def test_mask_bank_card_5_digits(self):
        """Test bank card with 5 digits."""
        result = _mask_bank_card("12345")
        assert result == "*2345"

    def test_mask_bank_card_none(self):
        """Test None value returns empty string."""
        result = _mask_bank_card(None)
        assert result == ""

    def test_mask_bank_card_empty_string(self):
        """Test empty string."""
        result = _mask_bank_card("")
        assert result == ""


class TestGetMaskFunction:
    """Tests for get_mask_function function."""

    def test_get_mask_function_phone(self):
        """Test column name containing 'phone'."""
        func = get_mask_function("user_phone")
        assert func == _mask_phone

    def test_get_mask_function_mobile(self):
        """Test column name containing 'mobile'."""
        func = get_mask_function("mobile_number")
        assert func == _mask_phone

    def test_get_mask_function_tel(self):
        """Test column name containing 'tel'."""
        func = get_mask_function("tel")
        assert func == _mask_phone

    def test_get_mask_function_cellular(self):
        """Test column name containing 'cellular'."""
        func = get_mask_function("cellular")
        assert func == _mask_phone

    def test_get_mask_function_email(self):
        """Test column name containing 'email'."""
        func = get_mask_function("email_address")
        assert func == _mask_email

    def test_get_mask_function_mail(self):
        """Test column name containing 'mail'."""
        func = get_mask_function("mail")
        assert func == _mask_email

    def test_get_mask_function_password(self):
        """Test column name containing 'password'."""
        func = get_mask_function("password")
        assert func == _mask_password

    def test_get_mask_function_pwd(self):
        """Test column name containing 'pwd'."""
        func = get_mask_function("pwd")
        assert func == _mask_password

    def test_get_mask_function_passwd(self):
        """Test column name containing 'passwd'."""
        func = get_mask_function("passwd")
        assert func == _mask_password

    def test_get_mask_function_secret(self):
        """Test column name containing 'secret'."""
        func = get_mask_function("secret")
        assert func == _mask_password

    def test_get_mask_function_token(self):
        """Test column name containing 'token'."""
        func = get_mask_function("access_token")
        assert func == _mask_password

    def test_get_mask_function_api_key(self):
        """Test column name containing 'api_key'."""
        func = get_mask_function("api_key")
        assert func == _mask_password

    def test_get_mask_function_id_card(self):
        """Test column name containing 'id_card'."""
        func = get_mask_function("id_card")
        assert func == _mask_id_card

    def test_get_mask_function_idcard(self):
        """Test column name containing 'idcard'."""
        func = get_mask_function("idcard")
        assert func == _mask_id_card

    def test_get_mask_function_id_number(self):
        """Test column name containing 'id_number'."""
        func = get_mask_function("id_number")
        assert func == _mask_id_card

    def test_get_mask_function_identity(self):
        """Test column name containing 'identity'."""
        func = get_mask_function("identity")
        assert func == _mask_id_card

    def test_get_mask_function_bank_card(self):
        """Test column name containing 'bank_card'."""
        func = get_mask_function("bank_card")
        assert func == _mask_bank_card

    def test_get_mask_function_bankcard(self):
        """Test column name containing 'bankcard'."""
        func = get_mask_function("bankcard")
        assert func == _mask_bank_card

    def test_get_mask_function_credit_card(self):
        """Test column name containing 'credit_card'."""
        func = get_mask_function("credit_card")
        assert func == _mask_bank_card

    def test_get_mask_function_card_number(self):
        """Test column name containing 'card_number'."""
        func = get_mask_function("card_number")
        assert func == _mask_bank_card

    def test_get_mask_function_no_match(self):
        """Test column name not matching any pattern."""
        func = get_mask_function("username")
        assert func is None

    def test_get_mask_function_case_insensitive(self):
        """Test case insensitive matching."""
        func = get_mask_function("PHONE")
        assert func == _mask_phone

        func = get_mask_function("Email")
        assert func == _mask_email

        func = get_mask_function("PASSWORD")
        assert func == _mask_password

    def test_get_mask_function_partial_match(self):
        """Test partial match in column name."""
        func = get_mask_function("user_phone_number")
        assert func == _mask_phone

        func = get_mask_function("customer_email_address")
        assert func == _mask_email


class TestMaskRows:
    """Tests for mask_rows function."""

    def test_mask_rows_empty(self):
        """Test empty list returns empty list."""
        result = mask_rows([])
        assert result == []

    def test_mask_rows_no_sensitive(self):
        """Test rows without sensitive columns."""
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        result = mask_rows(rows)
        assert result == rows

    def test_mask_rows_with_phone(self):
        """Test rows with phone column."""
        rows = [{"id": 1, "phone": "13812345678"}]
        result = mask_rows(rows)
        assert result[0]["phone"] == "138****5678"
        assert result[0]["id"] == 1

    def test_mask_rows_with_email(self):
        """Test rows with email column."""
        rows = [{"id": 1, "email": "test@example.com"}]
        result = mask_rows(rows)
        assert result[0]["email"] == "t***@example.com"

    def test_mask_rows_with_password(self):
        """Test rows with password column."""
        rows = [{"id": 1, "password": "secret123"}]
        result = mask_rows(rows)
        assert result[0]["password"] == "********"

    def test_mask_rows_with_id_card(self):
        """Test rows with id_card column."""
        rows = [{"id": 1, "id_card": "330102199001011234"}]
        result = mask_rows(rows)
        assert result[0]["id_card"] == "330***********1234"

    def test_mask_rows_with_bank_card(self):
        """Test rows with bank_card column."""
        rows = [{"id": 1, "bank_card": "6222021234567890"}]
        result = mask_rows(rows)
        assert result[0]["bank_card"] == "************7890"

    def test_mask_rows_null_values(self):
        """Test rows with None values - keeps None."""
        rows = [{"id": 1, "phone": None, "email": None}]
        result = mask_rows(rows)
        # None values are kept as None (not masked)
        assert result[0]["phone"] is None
        assert result[0]["email"] is None

    def test_mask_rows_multiple_sensitive(self):
        """Test rows with multiple sensitive columns."""
        rows = [{
            "id": 1,
            "phone": "13812345678",
            "email": "test@example.com",
            "password": "secret",
        }]
        result = mask_rows(rows)
        assert result[0]["phone"] == "138****5678"
        assert result[0]["email"] == "t***@example.com"
        assert result[0]["password"] == "********"

    def test_mask_rows_preserves_non_sensitive(self):
        """Test that non-sensitive columns are preserved."""
        rows = [{
            "id": 1,
            "name": "Alice",
            "phone": "13812345678",
            "created_at": "2024-01-01",
        }]
        result = mask_rows(rows)
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Alice"
        assert result[0]["phone"] == "138****5678"
        assert result[0]["created_at"] == "2024-01-01"

    def test_mask_rows_multiple_rows(self):
        """Test masking multiple rows."""
        rows = [
            {"id": 1, "phone": "13812345678"},
            {"id": 2, "phone": "15900001111"},
        ]
        result = mask_rows(rows)
        assert len(result) == 2
        assert result[0]["phone"] == "138****5678"
        assert result[1]["phone"] == "159****1111"

    def test_mask_rows_empty_string_value(self):
        """Test rows with empty string values."""
        rows = [{"id": 1, "phone": ""}]
        result = mask_rows(rows)
        # Empty string is masked (not None), returns ""
        assert result[0]["phone"] == ""

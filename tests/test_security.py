"""Security module tests"""

from security.auth import password_manager, token_manager, security_utils


def test_password_hashing():
    """Test password hashing with Argon2"""
    password = "TestPassword123!@#"
    hashed = password_manager.hash_password(password)
    
    assert hashed != password
    assert password_manager.verify_password(password, hashed)
    assert not password_manager.verify_password("wrong", hashed)


def test_password_strength():
    """Test password strength validation"""
    valid, _ = password_manager.validate_password_strength("Strong123!@#")
    assert valid
    
    valid, msg = password_manager.validate_password_strength("weak")
    assert not valid
    assert "Min" in msg and "characters" in msg


def test_jwt_tokens():
    """Test JWT token creation and validation"""
    token = token_manager.create_access_token({"sub": "12345"})
    assert token
    
    payload = token_manager.verify_token(token)
    assert payload["sub"] == "12345"
    assert payload["type"] == "access"


def test_referral_code_generation():
    """Test referral code generation"""
    code1 = security_utils.generate_referral_code()
    code2 = security_utils.generate_referral_code()
    
    assert len(code1) == 8
    assert len(code2) == 8
    assert code1 != code2  # Should be unique


def test_wallet_validation():
    """Test Solana wallet address validation"""
    # Valid address
    valid = security_utils.is_valid_wallet_address("7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU")
    assert valid
    
    # Invalid addresses
    assert not security_utils.is_valid_wallet_address("invalid")
    assert not security_utils.is_valid_wallet_address("123")
    assert not security_utils.is_valid_wallet_address("")

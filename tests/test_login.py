import pyotp


def test_totp_code_generation():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    code = totp.now()
    assert len(code) == 6
    assert code.isdigit()


def test_totp_code_verification():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    code = totp.now()
    assert totp.verify(code) is True
    assert totp.verify("000000") is False

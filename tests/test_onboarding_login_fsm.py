from onboarding.login_fsm import match_handler_name


def test_match_identifier():
    assert match_handler_name("https://accounts.google.com/v3/signin/identifier?x=1") == "type_email"

def test_match_pwd():
    assert match_handler_name("https://accounts.google.com/v3/signin/challenge/pwd?x") == "type_password"

def test_match_ipe_verify():
    assert match_handler_name("https://accounts.google.com/v3/signin/challenge/ipe/verify?x") == "submit_recovery_code"

def test_match_selection():
    assert match_handler_name("https://accounts.google.com/v3/signin/challenge/selection?x") == "pick_recovery_option"

def test_match_gds_recovery():
    assert match_handler_name("https://gds.google.com/web/recoveryoptions?c=0") == "click_skip"

def test_match_gds_homeaddress():
    assert match_handler_name("https://gds.google.com/web/homeaddress?c=1") == "click_skip"

def test_match_gds_generic():
    assert match_handler_name("https://gds.google.com/web/somethingnew") == "click_skip"

def test_match_done_myaccount():
    assert match_handler_name("https://myaccount.google.com/?utm_source=x") == "DONE"

def test_match_done_youtube():
    assert match_handler_name("https://www.youtube.com/") == "DONE"

def test_match_unknown():
    assert match_handler_name("https://example.com/foo") is None

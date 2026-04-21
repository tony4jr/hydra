from onboarding.report import Report, GoalStatus


def test_report_add_and_summarize():
    r = Report(account_id=42)
    r.add("login", GoalStatus.DONE)
    r.skip("ui_lang_ko", "already_done")
    r.error("channel_handle", "ytcp-anchor not found")
    r.add("avatar", GoalStatus.FAILED, reason="replace-button timeout")

    assert r.account_id == 42
    entries = r.as_dict()["entries"]
    assert entries[0] == {"goal": "login", "status": "done", "reason": None}
    assert entries[1] == {"goal": "ui_lang_ko", "status": "skipped", "reason": "already_done"}
    assert entries[2] == {"goal": "channel_handle", "status": "error", "reason": "ytcp-anchor not found"}
    assert entries[3] == {"goal": "avatar", "status": "failed", "reason": "replace-button timeout"}
    assert r.overall_ok() is False


def test_report_overall_ok_when_required_all_done():
    r = Report(account_id=1)
    for g in ("login", "ui_lang_ko", "display_name", "identity_challenge", "channel_name"):
        r.add(g, GoalStatus.DONE)
    r.add("channel_handle", GoalStatus.FAILED, reason="14day limit")
    assert r.overall_ok() is True

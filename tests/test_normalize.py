from app.normalize import normalize_input, normalize_one


def test_plain_username():
    assert normalize_one("yoga_bijo") == ("yoga_bijo", None)


def test_at_prefix():
    assert normalize_one("@yoga_bijo") == ("yoga_bijo", None)


def test_url_forms():
    assert normalize_one("https://www.instagram.com/yoga_bijo")[0] == "yoga_bijo"
    assert normalize_one("https://www.instagram.com/yoga_bijo/")[0] == "yoga_bijo"
    assert normalize_one("instagram.com/yoga_bijo")[0] == "yoga_bijo"


def test_reserved_url_path_rejected():
    user, reason = normalize_one("https://www.instagram.com/p/Cabc123/")
    assert user is None and reason is not None


def test_invalid_chars():
    user, reason = normalize_one("bad user!")
    assert user is None


def test_empty():
    user, reason = normalize_one("   ")
    assert user is None and reason == "空入力"


def test_dedupe_and_case_insensitive():
    res = normalize_input("yoga_bijo\n@Yoga_Bijo\nhttps://instagram.com/yoga_bijo")
    assert res.accounts == ["yoga_bijo"]


def test_comma_and_newline_split():
    res = normalize_input("a_one, b_two\nc_three")
    assert res.accounts == ["a_one", "b_two", "c_three"]


def test_over_limit():
    many = "\n".join(f"user_{i}" for i in range(25))
    res = normalize_input(many)
    assert res.over_limit is True
    assert len(res.accounts) == 20


def test_rejected_collected():
    res = normalize_input("good_user\nbad!!user")
    assert "good_user" in res.accounts
    assert any("bad!!user" == raw for raw, _ in res.rejected)

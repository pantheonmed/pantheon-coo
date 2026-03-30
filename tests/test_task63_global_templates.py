"""Task 63 — global market templates."""
import templates as tpl


def _by_id(tid: str):
    return tpl.get_template_by_id(tid)


def test_uae_vat_template_trn():
    t = _by_id("uae_vat_invoice")
    assert t
    assert "trn_number" in (t.get("variables") or [])
    assert t.get("category") == "finance"


def test_us_invoice_dollar_amount():
    t = _by_id("us_invoice")
    assert t
    assert "amount" in (t.get("variables") or [])
    assert "{amount}" in t["command"] or "$" in t["command"]


def test_german_gdpr_template():
    t = _by_id("german_datenschutz")
    assert t
    assert t.get("category") == "communicate"


def test_japanese_keigo_template():
    t = _by_id("japanese_keigo_email")
    assert t
    assert "recipient_company" in (t.get("variables") or [])


def test_new_templates_have_category():
    for tid in (
        "arabic_proposal",
        "cold_email_us",
        "nota_fiscal",
        "nigeria_business_letter",
        "indonesia_proposal",
    ):
        t = _by_id(tid)
        assert t and t.get("category")


def test_templates_loadable():
    assert len(tpl.TEMPLATES) > 50
    assert any(x.get("id") == "uae_vat_invoice" for x in tpl.TEMPLATES)

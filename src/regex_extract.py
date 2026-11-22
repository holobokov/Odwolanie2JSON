from __future__ import annotations

import re
from typing import Any

from .normalizer import normalize_account, normalize_bzp, normalize_date, normalize_digits, normalize_ted


def is_obvious_negative(text: str) -> str | None:
    """Fast deterministic rejection of obvious negative documents (0 LLM calls)."""
    low = text.casefold()
    has_appeal_filing = any(
        marker in low
        for marker in (
            "wnoszę odwołanie",
            "wnosimy odwołanie",
            "składam odwołanie",
            "prezesa krajowej izby odwoławczej",
            "prezes krajowej izby odwoławczej",
        )
    )
    # 1. TED / OJ S contract notices (e.g. 2025-OJS107-00364525)
    if (
        "see the notice on ted website" in low
        or "ogłoszenie o zamówieniu lub ogłoszenie o koncesji" in low
        or ("1. nabywca" in low and "2. procedura" in low)
    ) and not has_appeal_filing:
        return "TED/OJS_NOTICE"

    # 2. BZP contract notices (e.g. 2025_BZP 00143067)
    if "biuletyn zamówień publicznych" in low and "sekcja i" in low and not has_appeal_filing:
        return "BZP_NOTICE"

    # 3. KIO Verdicts / Decisions (e.g. KIO_KIO 2617-21.pdf)
    if (
        "krajowa izba odwoławcza" in low
        and ("w składzie:" in low or "przewodniczący:" in low)
        and ("po rozpoznaniu" in low or "orzeka:" in low)
        and not has_appeal_filing
    ):
        return "KIO_VERDICT"

    # 4. Tax brochures / JPK
    if "jpk_fa" in low and "odwołani" not in low:
        return "BROCHURE_JPK"

    return None


def extract_odwolanie_anchors(text: str) -> dict[str, Any]:
    """Deterministic hints + fallback values for odwolanie."""
    anchors: dict[str, Any] = {}

    # Top-of-page city + date: "Warszawa, dnia 16 czerwca 2025 r." or "Pruszków 13.10.2025"
    head = text[:1200]
    m_head = re.search(
        r"(?m)^\s*([A-ZŻŹĆĄŚĘŁÓŃ][a-ząćęłńóśźż\-]{2,30})\s*,?\s*(?:dnia\s+)?(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}|\d{1,2}\s+[a-ząćęłńóśźż]+\s+\d{4}(?:\s*r\.?)?)",
        head,
    )
    if m_head:
        anchors["miejscowosc"] = m_head.group(1).strip()
        anchors["data"] = normalize_date(m_head.group(2))

    # BZP & TED numbers
    m_bzp = re.search(r"20\d{2}\s*/\s*BZP\s*\d{8}(?:\s*/\s*\d{2})?", text, flags=re.I)
    if m_bzp:
        anchors["numer_bzp"] = normalize_bzp(m_bzp.group(0))

    m_ted = re.search(r"\b\d{4}\s*/\s*S\s*\d+\s*-\s*\d{5,8}\b|\b\d{5,8}\s*-\s*20\d{2}\b", text, flags=re.I)
    if m_ted:
        anchors["numer_ted"] = normalize_ted(m_ted.group(0))

    # Emails (prefer non-UZP email for pełnomocnik)
    emails = [e for e in re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", head + text[-1500:]) if "uzp.gov.pl" not in e.lower()]
    if emails:
        anchors["pelnomocnik_mail"] = emails[0]

    # Section-anchored KRS / NIP / REGON
    m_odw = re.search(r"Odwołując[ya]:(.*?)(?:Zamawiając[ya]:|Dotyczy:|ODWOŁANIE)", text, flags=re.S | re.I)
    if m_odw:
        sec = m_odw.group(1)
        if m := re.search(r"KRS[:\s]*(\d[\d\s\-]{8,14})", sec, flags=re.I):
            anchors["odw_krs"] = normalize_digits(m.group(1), (10,), zero_pad=10)
        if m := re.search(r"NIP[:\s]*((?:PL)?[\d\s\-]{10,15})", sec, flags=re.I):
            anchors["odw_nip"] = normalize_digits(m.group(1), (10,))
        if m := re.search(r"REGON[:\s]*(\d[\d\s\-]{8,16})", sec, flags=re.I):
            anchors["odw_regon"] = normalize_digits(m.group(1), (9, 14))

    m_zam = re.search(r"Zamawiając[ya]:(.*?)(?:Dotyczy:|ODWOŁANIE|Działając)", text, flags=re.S | re.I)
    if m_zam:
        sec = m_zam.group(1)
        if m := re.search(r"KRS[:\s]*(\d[\d\s\-]{8,14})", sec, flags=re.I):
            anchors["zam_krs"] = normalize_digits(m.group(1), (10,), zero_pad=10)
        if m := re.search(r"NIP[:\s]*((?:PL)?[\d\s\-]{10,15})", sec, flags=re.I):
            anchors["zam_nip"] = normalize_digits(m.group(1), (10,))
        if m := re.search(r"REGON[:\s]*(\d[\d\s\-]{8,16})", sec, flags=re.I):
            anchors["zam_regon"] = normalize_digits(m.group(1), (9, 14))

    return {k: v for k, v in anchors.items() if v is not None}


def focus_odwolanie_text(text: str, max_chars: int = 7000) -> str:
    """Keep header + first-zarzut window + signature block; drop middle legal boilerplate."""
    if len(text) <= max_chars:
        return text
    head = text[:3800]
    tail = text[-1400:]
    mid = ""
    m = re.search(r"(?:Zarzut|Zaskarżon|Wskazanie naruszeń|Wnoszę|Wniosek\s*\(żądanie\))", text[1500:], flags=re.I)
    if m:
        pos = 1500 + m.start()
        if pos > 3400:
            mid = "\n...\n" + text[pos : pos + 1800]
    return (head + mid + "\n...\n" + tail)[:max_chars]


def try_deterministic_przelew(text: str) -> dict[str, Any] | None:
    """High-confidence zero-LLM extractor for clear bank transfer confirmations."""
    low = text.casefold()
    if not any(k in low for k in ("potwierdzenie przelewu", "potwierdzenie wykonania przelewu", "potwierdzenie transakcji", "potwierdzenie operacji")):
        return None
    accounts = []
    for raw in re.findall(r"(?:PL)?\s*\d{2}(?:[\s\-]?\d{4}){5,6}(?:[\s\-]?\d{2})?", text, flags=re.I):
        acc = normalize_account(raw)
        if acc and acc not in accounts:
            accounts.append(acc)
    if len(accounts) < 2:
        return None

    m_amt = re.search(r"(?:Kwota|Wartość)[:\s]+([\d\s.,]+)\s*(?:PLN|zł)", text, flags=re.I)
    m_date = re.search(r"(?:Data\s+(?:operacji|wykonania|waluty|księgowania))[:\s]+([^\n]+)", text, flags=re.I)
    m_title = re.search(r"(?:Tytuł(?:\s+przelewu|\s+operacji)?)[:\s]+(.+?)(?:\n[A-ZŻŹĆĄŚĘŁÓŃ][a-ząćęłńóśźż ]+:|$)", text, flags=re.S | re.I)
    m_tx = re.search(r"(?:Numer\s+(?:transakcji|operacji|referencyjny)|ID\s+transakcji)[:\s]+([A-Za-z0-9\-_/]+)", text, flags=re.I)

    if not (m_amt and m_date and m_title):
        return None

    # Order usually: nadawca (z_rachunku) then odbiorca (na_rachunek), or explicit labels
    m_from = re.search(r"(?:Rachunek\s+nadawcy|Z\s+rachunku|Nadawca).*?((?:PL)?[\d\s\-]{20,34})", text, flags=re.S | re.I)
    m_to = re.search(r"(?:Rachunek\s+odbiorcy|Na\s+rachunek|Odbiorca).*?((?:PL)?[\d\s\-]{20,34})", text, flags=re.S | re.I)
    z_acc = normalize_account(m_from.group(1)) if m_from else accounts[0]
    na_acc = normalize_account(m_to.group(1)) if m_to else accounts[1]

    from .normalizer import _nullable_float
    kwota = _nullable_float(m_amt.group(1))
    data_op = normalize_date(m_date.group(1))
    if not (kwota and data_op and z_acc and na_acc):
        return None

    return {
        "przelew_bankowy": {
            "data_operacji": data_op,
            "kwota": kwota,
            "na_rachunek": na_acc,
            "numer_transakcji": m_tx.group(1).strip() if m_tx else None,
            "tytul": " ".join(m_title.group(1).split()),
            "z_rachunku": z_acc,
        }
    }
from __future__ import annotations

import re
from datetime import datetime
from typing import Any


CZYNNOSC_LOOKUP: dict[int, str] = {
    1: "Decyzja o odrzuceniu oferty",
    2: "Ogłoszenie wyboru oferty",
    3: "Decyzja o wykluczeniu wykonawcy",
    4: "Publikacja specyfikacji warunków zamówienia (SWZ)",
    5: "Modyfikacja treści SWZ",
    6: "Odpowiedzi/wyjaśnienia do SWZ",
    7: "Zaniechanie odrzucenia oferty",
    8: "Zaniechanie wykluczenia wykonawcy",
    9: "Decyzja o unieważnieniu postępowania",
    10: "Zaniechanie unieważnienia postępowania",
    11: "Opis przedmiotu zamówienia (OPZ)",
    12: "Projektowane postanowienia umowy",
}

_MONTHS = {
    "stycznia": 1, "styczeń": 1, "lutego": 2, "luty": 2, "marca": 3, "marzec": 3,
    "kwietnia": 4, "kwiecień": 4, "maja": 5, "maj": 5, "czerwca": 6, "czerwiec": 6,
    "lipca": 7, "lipiec": 7, "sierpnia": 8, "sierpień": 8, "września": 9, "wrzesień": 9,
    "października": 10, "październik": 10, "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzień": 12,
}

_PLACEHOLDERS = {"null", "none", "n/a", "brak", "nie dotyczy", "redacted", "[redacted]", "-"}


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    if not text or text.casefold() in _PLACEHOLDERS or re.fullmatch(r"[*█■_xX\-]+", text):
        return None
    return text


def normalize_date(value: Any) -> str | None:
    text = _clean_str(value)
    if not text:
        return None
    text = re.sub(r"\br\.?$", "", text.lower().replace("\xa0", " ")).strip()
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        year, month, day = map(int, match.groups())
    else:
        match = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", text)
        if match:
            day, month, year = map(int, match.groups())
        else:
            match = re.search(r"(\d{1,2})\s+([ąćęłńóśźża-z]+)\s+(\d{4})", text)
            if not match:
                return None
            day = int(match.group(1))
            month = _MONTHS.get(match.group(2), 0)
            year = int(match.group(3))
    if month not in range(1, 13):
        return None
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None


def normalize_digits(value: Any, allowed_lengths: tuple[int, ...], zero_pad: int | None = None) -> str | None:
    cleaned = _clean_str(value)
    if not cleaned:
        return None
    text = re.sub(r"[\s\-./]+", "", cleaned.upper())
    text = re.sub(r"^PL", "", text)
    digits = re.sub(r"\D", "", text)
    if zero_pad and 0 < len(digits) <= zero_pad:
        digits = digits.zfill(zero_pad)
    return digits if len(digits) in allowed_lengths else None


def normalize_account(value: Any) -> str | None:
    cleaned = _clean_str(value)
    if not cleaned:
        return None
    text = re.sub(r"[\s\-]+", "", cleaned.upper())
    if text.startswith("PL"):
        text = text[2:]
    digits = re.sub(r"\D", "", text)
    return digits if 16 <= len(digits) <= 28 else None


def normalize_ted(value: Any) -> str | None:
    cleaned = _clean_str(value)
    if not cleaned:
        return None
    text = cleaned.upper()
    match = re.search(r"\b(\d{4})\s*/\s*S\s*\d+\s*-\s*(\d{5,8})\b", text)
    if match:
        return f"{match.group(2)}-{match.group(1)}"
    match = re.search(r"\b(\d{5,8})\s*[-/]\s*(20\d{2})\b", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None


def normalize_bzp(value: Any) -> str | None:
    cleaned = _clean_str(value)
    if not cleaned:
        return None
    text = cleaned.upper().replace(" ", "")
    match = re.search(r"(20\d{2}|19\d{2})/?BZP/?(\d{8})(?:/?(\d{2}))?", text)
    if not match:
        return None
    suffix = f"/{match.group(3)}" if match.group(3) else ""
    # NOTE: Check dane/przyklad_* whether expected format is '/BZP ' (with space) or '/BZP' (no space)!
    return f"{match.group(1)}/BZP{match.group(2)}{suffix}"

def _nullable_int(value: Any, allowed: tuple[int, ...]) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number in allowed else None


def _nullable_pesel(value: Any) -> int | None:
    cleaned = _clean_str(value)
    if not cleaned:
        return None
    digits = re.sub(r"\D", "", cleaned)
    return int(digits) if len(digits) == 11 else None


def _nullable_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    cleaned = _clean_str(value)
    if not cleaned:
        return None
    s = re.sub(r"(zł|zl|pln)", "", cleaned, flags=re.I).replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", s)
    return round(float(match.group(0)), 2) if match else None


def _clean_generic(value: Any) -> Any:
    """Generic normalizer so any newly added YAML document class works without code edits."""
    if isinstance(value, dict):
        return {k: _clean_generic(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_generic(v) for v in value]
    if isinstance(value, str):
        return _clean_str(value)
    return value


def normalize_document(class_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    if class_id == "odwolanie":
        root = data.get("OdwolanieKIO") if isinstance(data.get("OdwolanieKIO"), dict) else {}
        action_id = _nullable_int(root.get("czynnosc_powod_id"), tuple(CZYNNOSC_LOOKUP))
        result: dict[str, Any] = {
            "OdwolanieKIO": {
                "data": normalize_date(root.get("data")),
                "czynnosc_dzien": normalize_date(root.get("czynnosc_dzien")),
                "czynnosc_powod_id": action_id,
                "czynnosc_opis": CZYNNOSC_LOOKUP.get(action_id) if action_id else None,
                "miejscowosc": _clean_str(root.get("miejscowosc")),
            },
            "Odwolujacy": [],
            "Zamawiajacy": [],
            "ZamowieniePubliczne": {},
        }
        for item in data.get("Odwolujacy") or []:
            if not isinstance(item, dict):
                continue
            pien = item.get("pelnomocnik") if isinstance(item.get("pelnomocnik"), dict) else {}
            pien_name = _clean_str(pien.get("imie_nazwisko"))
            if pien_name:
                pien_name = pien_name.split(",")[0].strip()
            result["Odwolujacy"].append({
                "krs": normalize_digits(item.get("krs"), (10,), zero_pad=10),
                "nazwa": _clean_str(item.get("nazwa")),
                "nip": normalize_digits(item.get("nip"), (10,)),
                "regon": normalize_digits(item.get("regon"), (9, 14)),
                "przez-pelnomocnika": 1 if item.get("przez-pelnomocnika") in (1, "1", True) else 0,
                "pelnomocnik": {
                    "imie_nazwisko": pien_name,
                    "nazwa": _clean_str(pien.get("nazwa")),
                    "mail": _clean_str(pien.get("mail")),
                },
            })
        authorities = [a for a in (data.get("Zamawiajacy") or []) if isinstance(a, dict)]
        multiple = len(authorities) > 1
        for item in authorities:
            lead = _nullable_int(item.get("prowadzacy_postepowanie"), (0, 1))
            result["Zamawiajacy"].append({
                "krs": normalize_digits(item.get("krs"), (10,), zero_pad=10),
                "nazwa": _clean_str(item.get("nazwa")),
                "nip": normalize_digits(item.get("nip"), (10,)),
                "regon": normalize_digits(item.get("regon"), (9, 14)),
                "prowadzacy_postepowanie": lead if multiple else None,
            })
        procurement = data.get("ZamowieniePubliczne") if isinstance(data.get("ZamowieniePubliczne"), dict) else {}
        result["ZamowieniePubliczne"] = {
            "numer_bzp": normalize_bzp(procurement.get("numer_bzp")),
            "numer_postepowania": _clean_str(procurement.get("numer_postepowania")),
            "numer_ted": normalize_ted(procurement.get("numer_ted")),
            "tytul": _clean_str(procurement.get("tytul")),
        }
        return result

    if class_id == "pelnomocnictwo":
        result = {"mocodawca": [], "pelnomocnicy": []}
        for item in data.get("mocodawca") or []:
            if not isinstance(item, dict):
                continue
            body = item.get("data") if isinstance(item.get("data"), dict) else {}
            signers = [
                {"imie_nazwisko": name}
                for s in (item.get("podpisujacy") or [])
                if isinstance(s, dict) and (name := _clean_str(s.get("imie_nazwisko")))
            ]
            typ = body.get("typ") if body.get("typ") in ("osoba_prawna", "osoba_fizyczna") else "osoba_fizyczna"
            result["mocodawca"].append({
                "data": {
                    "imie_nazwisko": _clean_str(body.get("imie_nazwisko")) if typ == "osoba_fizyczna" else None,
                    "krs": normalize_digits(body.get("krs"), (10,), zero_pad=10) if typ == "osoba_prawna" else None,
                    "nazwa": _clean_str(body.get("nazwa")),
                    "nip": normalize_digits(body.get("nip"), (10,)),
                    "typ": typ,
                },
                "podpisujacy": signers,
            })
        for item in data.get("pelnomocnicy") or []:
            if not isinstance(item, dict):
                continue
            result["pelnomocnicy"].append({
                "imie_nazwisko": _clean_str(item.get("imie_nazwisko")) or "",
                "pesel": _nullable_pesel(item.get("pesel")),
            })
        return result

    if class_id == "przelew":
        bank = data.get("przelew_bankowy") if isinstance(data.get("przelew_bankowy"), dict) else {}
        return {
            "przelew_bankowy": {
                "data_operacji": normalize_date(bank.get("data_operacji")),
                "kwota": _nullable_float(bank.get("kwota")),
                "na_rachunek": normalize_account(bank.get("na_rachunek")),
                "numer_transakcji": _clean_str(bank.get("numer_transakcji")),
                "tytul": _clean_str(bank.get("tytul")),
                "z_rachunku": normalize_account(bank.get("z_rachunku")),
            }
        }

    # IMPORTANT: Support any newly added YAML class dynamically instead of returning {}!
    return _clean_generic(data)
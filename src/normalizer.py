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
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5,
    "czerwca": 6, "lipca": 7, "sierpnia": 8, "września": 9,
    "października": 10, "listopada": 11, "grudnia": 12,
}


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace("\xa0", " ")
    if not text:
        return None
    text = re.sub(r"\br\.", "", text).strip()
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


def normalize_digits(value: Any, allowed_lengths: tuple[int, ...]) -> str | None:
    if value is None:
        return None
    text = str(value).upper().strip()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[-./]", "", text)
    text = re.sub(r"^PL", "", text)
    digits = re.sub(r"\D", "", text)
    return digits if len(digits) in allowed_lengths else None


def normalize_identifier(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    digits = re.sub(r"\D", "", text)
    return digits or None


def normalize_ted(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).upper()
    match = re.search(r"(\d{6})\s*[-/]\s*(20\d{2}|\d{4})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    match = re.search(r"\b(\d{4})\s*/\s*S\s+\d+-(\d{6})\b", text)
    if match:
        return f"{match.group(2)}-{match.group(1)}"
    match = re.search(r"\b(\d{6})\b", text)
    if match:
        year_match = re.search(r"\b(20\d{2}|\d{4})\b", text)
        if year_match:
            return f"{match.group(1)}-{year_match.group(1)}"
    return None


def normalize_bzp(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).upper().replace(" ", "")
    match = re.search(r"(20\d{2}|19\d{2})/?BZP/?(\d{8})(?:/?(\d{2}))?", text)
    if not match:
        match = re.search(r"(20\d{2}|19\d{2})", text)
        number_match = re.search(r"\d{8}", text)
        if match and number_match:
            suffix_match = re.search(r"/(\d{2})(?!\d)", text)
            suffix = f"/{suffix_match.group(1)}" if suffix_match else ""
            return f"{match.group(1)}/BZP{number_match.group(0)}{suffix}"
        return None
    suffix = f"/{match.group(3)}" if match.group(3) else ""
    return f"{match.group(1)}/BZP{match.group(2)}{suffix}"


def _nullable_int(value: Any, allowed: tuple[int, ...]) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number in allowed else None


def _nullable_pesel(value: Any) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) != 11:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _nullable_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "").replace("\xa0", "")
    text = text.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def normalize_document(class_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    if class_id == "odwolanie":
        root = data.get("OdwolanieKIO") or {}
        action_id = _nullable_int(root.get("czynnosc_powod_id"), tuple(CZYNNOSC_LOOKUP))
        result: dict[str, Any] = {
            "OdwolanieKIO": {
                "data": normalize_date(root.get("data")),
                "czynnosc_dzien": normalize_date(root.get("czynnosc_dzien")),
                "czynnosc_powod_id": action_id,
                "czynnosc_opis": CZYNNOSC_LOOKUP.get(action_id) if action_id else None,
                "miejscowosc": root.get("miejscowosc") if root.get("miejscowosc") else None,
            },
            "Odwolujacy": [],
            "Zamawiajacy": [],
            "ZamowieniePubliczne": {},
        }
        for item in data.get("Odwolujacy") or []:
            if not isinstance(item, dict):
                continue
            pien = item.get("pelnomocnik") or {}
            result["Odwolujacy"].append({
                "krs": normalize_digits(item.get("krs"), (10,)),
                "nazwa": item.get("nazwa") or None,
                "nip": normalize_digits(item.get("nip"), (10,)),
                "regon": normalize_digits(item.get("regon"), (9, 14)),
                "przez-pelnomocnika": 1 if item.get("przez-pelnomocnika") in (1, "1", True) else 0,
                "pelnomocnik": {
                    "imie_nazwisko": pien.get("imie_nazwisko").split(",")[0].strip() if pien.get("imie_nazwisko") else None,
                    "nazwa": pien.get("nazwa") or None,
                    "mail": pien.get("mail") or None,
                },
            })
        authorities = data.get("Zamawiajacy") or []
        multiple = len(authorities) > 1
        for item in authorities:
            if not isinstance(item, dict):
                continue
            lead = _nullable_int(item.get("prowadzacy_postepowanie"), (0, 1))
            result["Zamawiajacy"].append({
                "krs": normalize_digits(item.get("krs"), (10,)),
                "nazwa": item.get("nazwa") or None,
                "nip": normalize_digits(item.get("nip"), (10,)),
                "regon": normalize_digits(item.get("regon"), (9, 14)),
                "prowadzacy_postepowanie": lead if multiple else None,
            })
        procurement = data.get("ZamowieniePubliczne") or {}
        result["ZamowieniePubliczne"] = {
            "numer_bzp": normalize_bzp(procurement.get("numer_bzp")),
            "numer_postepowania": procurement.get("numer_postepowania") or None,
            "numer_ted": normalize_ted(procurement.get("numer_ted")),
            "tytul": procurement.get("tytul") or None,
        }
        return result
    if class_id == "pelnomocnictwo":
        result = {"mocodawca": [], "pelnomocnicy": []}
        for item in data.get("mocodawca") or []:
            if not isinstance(item, dict):
                continue
            body = item.get("data") or {}
            signers: list[dict[str, str]] = []
            for signer in item.get("podpisujacy") or []:
                if isinstance(signer, dict) and signer.get("imie_nazwisko"):
                    signers.append({"imie_nazwisko": str(signer["imie_nazwisko"])})
            result["mocodawca"].append({
                "data": {
                    "imie_nazwisko": body.get("imie_nazwisko") or None,
                    "krs": normalize_digits(body.get("krs"), (10,)),
                    "nazwa": body.get("nazwa") or None,
                    "nip": normalize_digits(body.get("nip"), (10,)),
                    "typ": body.get("typ") if body.get("typ") in ("osoba_prawna", "osoba_fizyczna") else "osoba_fizyczna",
                },
                "podpisujacy": signers,
            })
        for item in data.get("pelnomocnicy") or []:
            if not isinstance(item, dict):
                continue
            result["pelnomocnicy"].append({
                "imie_nazwisko": str(item.get("imie_nazwisko") or ""),
                "pesel": _nullable_pesel(item.get("pesel")),
            })
        return result
    if class_id == "przelew":
        bank = data.get("przelew_bankowy") or {}
        return {"przelew_bankowy": {
            "data_operacji": normalize_date(bank.get("data_operacji")),
            "kwota": _nullable_float(bank.get("kwota")),
            "na_rachunek": normalize_digits(bank.get("na_rachunek"), (26,)),
            "numer_transakcji": bank.get("numer_transakcji") or None,
            "tytul": bank.get("tytul") or None,
            "z_rachunku": normalize_digits(bank.get("z_rachunku"), (26,)),
        }}
    return {}

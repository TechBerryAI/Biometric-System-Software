"""Authoritative organization roster for bulk employee purge."""

from __future__ import annotations

from dataclasses import dataclass

# (device_user_id, full_name) — 53 active employees
ORGANIZATION_ROSTER: tuple[tuple[str, str], ...] = (
    ("TBI001", "Unmesh Tari"),
    ("TBI174", "Nilesh Bhaurao Ingle"),
    ("12", "Ajit Thakur"),
    ("1", "Niraj Tiwari"),
    ("TBI188", "Asaram Balasaheb Bhand"),
    ("TBC209", "Janavi Dhanaji Utekar"),
    ("TBC228", "Salman Khan"),
    ("TBI243", "Manohar Gurunath Naik"),
    ("TBI286", "Sahil Niranjan Panda"),
    ("TBI289", "Raj Harishchandra Kadam"),
    ("TBI297", "Mujammil Mujib Mullani"),
    ("TBI298", "Syed Rehan Ali Syed Samad Ali"),
    ("TBI311", "Pooja Sadashiv Patil"),
    ("TBI313", "Sayali Arvind Kharat"),
    ("TBI314", "Sanskar Vijay Sonawane"),
    ("TBI316", "Asmita Dattatray Patil"),
    ("TBI321", "Archana Santosh Lokre"),
    ("TBI333", "Ganesh Arjun Shelke"),
    ("TBI347", "Ajay Ravindra Patil"),
    ("TBI349", "Kunal Prakash Kolambkar"),
    ("TBI355", "Tanvi Ganesh Chavan"),
    ("TBC236", "Siddhartha Shripat Jadhav"),
    ("TBI379", "Nisha Vasanta Warkhede"),
    ("TBC263", "Vrinda Subhash Sawant"),
    ("TBI389", "Mohammed Sohail Yakub Kureshi"),
    ("TBC237", "Dinesh Rohidas Dhoke"),
    ("TBC249", "Pracheta Meshram"),
    ("TBC251", "Sakshi Tiwari"),
    ("TTC29", "Amol Mhatre"),
    ("TBC256", "Nikhil Dilip Raut"),
    ("TBC259", "Suyog Virendra Yadav"),
    ("TBC261", "Ganesh Amirchand Gupta"),
    ("TBC262", "Abhishek Shankar Chettiar"),
    ("TTC30", "Ashwini Hanmant Waghmare"),
    ("TBC132", "Rahul Roshan"),
    ("TBC266", "Raj Kondiram Pawar"),
    ("TBC268", "Pratik Maurya"),
    ("TBC270", "Sumit Sharad Gidde"),
    ("TBC271", "Vivek Shashikant Chavan"),
    ("TBC272", "Vivek Dilip Kumar Chauhan"),
    ("TBC273", "Riya Sajanlal Gupta"),
    ("TBC274", "Radheshyam Vishwanath Vishwakarma"),
    ("15", "Swapnil Bamble"),
    ("TBC276", "Muzammil Akbar Momin"),
    ("TTC33", "Shubham Munna Singh"),
    ("TBC277", "Rahul Sanjay Kudtadkar"),
    ("TBC278", "Chetan Padmakar Gore"),
    ("16", "Kajal Vijay Pratap Sharma"),
    ("17", "Vinod Mandhare"),
    ("TBC279", "Yogesh Bhimsen Joshi"),
    ("TTC34", "Kiran Kalagi"),
    ("TTC35", "Prashant Mali"),
    ("TTC36", "Tushar Pachare"),
)

KEEP_DEVICE_USER_IDS: frozenset[str] = frozenset(code for code, _ in ORGANIZATION_ROSTER)

# Same first+last but different individuals — never match by name alone.
_FALSE_POSITIVE_NAME_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("yogesh joshi", "yogesh bhimsen joshi"),
    }
)


@dataclass(frozen=True, slots=True)
class RosterMatch:
    device_user_id: str
    roster_code: str
    roster_name: str
    match_kind: str  # "code" | "exact_name" | "prefix_name" | "truncated_name" | "first_last_name" | "first_name_unique"


def normalize_person_name(name: str) -> str:
    """Lowercase, collapse whitespace, strip placeholder prefixes."""
    cleaned = " ".join(str(name or "").lower().split())
    if cleaned.startswith("user "):
        cleaned = cleaned[5:].strip()
    return cleaned


def _name_tokens(name: str) -> list[str]:
    return normalize_person_name(name).split()


def _first_name_unique(first: str, roster: tuple[tuple[str, str], ...]) -> bool:
    hits = 0
    for _, roster_name in roster:
        tokens = _name_tokens(roster_name)
        if tokens and tokens[0] == first:
            hits += 1
    return hits == 1


def match_employee_to_roster(
    *,
    device_user_id: str,
    name: str,
    roster: tuple[tuple[str, str], ...] = ORGANIZATION_ROSTER,
) -> RosterMatch | None:
    """
    Return roster entry if employee should be kept.

    Matches by device_user_id first, then by normalized name (exact, prefix,
    first+last with surname, or unique first-name-only on device).
    """
    code = str(device_user_id or "").strip()
    normalized = normalize_person_name(name)
    if not normalized:
        return None

    roster_by_code = {c: n for c, n in roster}
    if code in roster_by_code:
        return RosterMatch(
            device_user_id=code,
            roster_code=code,
            roster_name=roster_by_code[code],
            match_kind="code",
        )

    emp_tokens = _name_tokens(name)
    for roster_code, roster_name in roster:
        roster_norm = normalize_person_name(roster_name)
        roster_tokens = _name_tokens(roster_name)
        if normalized == roster_norm:
            return RosterMatch(
                device_user_id=code,
                roster_code=roster_code,
                roster_name=roster_name,
                match_kind="exact_name",
            )
        if roster_norm.startswith(normalized + " "):
            return RosterMatch(
                device_user_id=code,
                roster_code=roster_code,
                roster_name=roster_name,
                match_kind="prefix_name",
            )
        if normalized.startswith(roster_norm + " "):
            return RosterMatch(
                device_user_id=code,
                roster_code=roster_code,
                roster_name=roster_name,
                match_kind="prefix_name",
            )

        if len(emp_tokens) >= 2 and len(roster_tokens) >= len(emp_tokens):
            if emp_tokens[:-1] == roster_tokens[: len(emp_tokens) - 1]:
                roster_tail = roster_tokens[len(emp_tokens) - 1]
                emp_tail = emp_tokens[-1]
                if len(emp_tail) >= 2 and roster_tail.startswith(emp_tail):
                    return RosterMatch(
                        device_user_id=code,
                        roster_code=roster_code,
                        roster_name=roster_name,
                        match_kind="truncated_name",
                    )

        if len(emp_tokens) == 1 and emp_tokens[0] == roster_tokens[0]:
            if _first_name_unique(emp_tokens[0], roster):
                return RosterMatch(
                    device_user_id=code,
                    roster_code=roster_code,
                    roster_name=roster_name,
                    match_kind="first_name_unique",
                )

        if len(emp_tokens) >= 2 and len(roster_tokens) >= 2:
            if emp_tokens[0] == roster_tokens[0] and emp_tokens[-1] == roster_tokens[-1]:
                pair = (normalized, roster_norm)
                if pair in _FALSE_POSITIVE_NAME_PAIRS:
                    continue
                return RosterMatch(
                    device_user_id=code,
                    roster_code=roster_code,
                    roster_name=roster_name,
                    match_kind="first_last_name",
                )

    return None


def is_kept_employee(
    *,
    device_user_id: str,
    name: str,
    roster: tuple[tuple[str, str], ...] = ORGANIZATION_ROSTER,
) -> bool:
    return match_employee_to_roster(
        device_user_id=device_user_id,
        name=name,
        roster=roster,
    ) is not None

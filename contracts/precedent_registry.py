# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json


STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is",
    "was", "were", "be", "been", "with", "that", "this", "it", "as", "by",
    "at", "from", "not", "did", "does", "do", "has", "have", "had", "but",
}


def _normalize_address(value) -> Address:
    if isinstance(value, Address):
        return value
    if isinstance(value, int):
        return Address(value.to_bytes(20, "big"))
    return Address(value)


def _zero_address() -> Address:
    return Address(int(0).to_bytes(20, "big"))


def _significant_words(text):
    words = text.lower().replace(",", " ").replace(".", " ").split()
    result = set()
    for w in words:
        if len(w) > 2 and w not in STOPWORDS:
            result.add(w)
    return result


class PrecedentRegistry(gl.Contract):
    owner: Address
    first_instance_court: Address
    first_instance_court_set: bool
    appeals_court: Address
    appeals_court_set: bool
    next_entry_id: u256
    entries: TreeMap[u256, str]

    def __init__(self):
        self.owner = gl.message.sender_address
        self.first_instance_court = _zero_address()
        self.first_instance_court_set = False
        self.appeals_court = _zero_address()
        self.appeals_court_set = False
        self.next_entry_id = u256(0)

    @gl.public.write
    def set_first_instance_court(self, first_instance_court_address) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("only owner can set first instance court")
        if self.first_instance_court_set:
            raise gl.vm.UserError("first instance court already set")
        self.first_instance_court = _normalize_address(first_instance_court_address)
        self.first_instance_court_set = True

    @gl.public.write
    def set_appeals_court(self, appeals_court_address) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("only owner can set appeals court")
        if self.appeals_court_set:
            raise gl.vm.UserError("appeals court already set")
        self.appeals_court = _normalize_address(appeals_court_address)
        self.appeals_court_set = True

    @gl.public.write
    def record_verdict(self, case_id: u256, description: str, verdict: str, tier: str) -> None:
        sender = gl.message.sender_address
        is_first_instance = self.first_instance_court_set and sender == self.first_instance_court
        is_appeals = self.appeals_court_set and sender == self.appeals_court
        if not is_first_instance and not is_appeals:
            raise gl.vm.UserError("only the configured court contracts can record a verdict")

        entry = {
            "case_id": int(case_id),
            "description": description,
            "verdict": verdict,
            "tier": tier,
        }
        entry_id = self.next_entry_id
        self.entries[entry_id] = json.dumps(entry)
        self.next_entry_id = self.next_entry_id + 1

    @gl.public.view
    def search_precedents(self, description: str, max_results: u256) -> str:
        query_words = _significant_words(description)
        count = int(self.next_entry_id)
        limit = int(max_results)
        matches = []
        i = count - 1
        while i >= 0:
            if len(matches) >= limit:
                break
            idx = u256(i)
            raw = self.entries[idx]
            entry = json.loads(raw)
            entry_description = ""
            if "description" in entry:
                entry_description = entry["description"]
            entry_words = _significant_words(entry_description)
            shared = query_words & entry_words
            if len(shared) > 0:
                matches.append(entry)
            i = i - 1
        return json.dumps(matches)

    @gl.public.view
    def get_entry(self, entry_id: u256) -> str:
        if entry_id not in self.entries:
            raise gl.vm.UserError("entry not found")
        return self.entries[entry_id]

    @gl.public.view
    def get_entry_count(self) -> u256:
        return self.next_entry_id

# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json


STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is",
    "was", "were", "be", "been", "with", "that", "this", "it", "as", "by",
    "at", "from", "not", "did", "does", "do", "has", "have", "had", "but",
}


def _significant_words(text):
    words = text.lower().replace(",", " ").replace(".", " ").split()
    result = set()
    for w in words:
        if len(w) > 2 and w not in STOPWORDS:
            result.add(w)
    return result


class PrecedentRegistry(gl.Contract):
    next_entry_id: u256
    entries: TreeMap[u256, str]

    def __init__(self):
        self.next_entry_id = u256(0)

    @gl.public.write
    def record_verdict(self, case_id: u256, description: str, verdict: str, tier: str) -> None:
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

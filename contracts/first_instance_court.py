# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json


def _normalize_address(value) -> Address:
    if isinstance(value, Address):
        return value
    if isinstance(value, int):
        return Address(value.to_bytes(20, "big"))
    return Address(value)


def _extract_json_object(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start:end + 1]
    return t


TIER_LOW = "low"
TIER_MEDIUM = "medium"
TIER_HIGH = "high"

VERDICT_BREACH = "BREACH"
VERDICT_NO_BREACH = "NO_BREACH"


class FirstInstanceCourt(gl.Contract):
    owner: Address
    precedent_registry: Address
    appeals_court: Address
    appeals_court_set: bool
    low_threshold: u256
    high_threshold: u256
    next_case_id: u256
    cases: TreeMap[u256, str]

    def __init__(self, precedent_registry_address, low_threshold: u256, high_threshold: u256):
        self.owner = gl.message.sender_address
        self.precedent_registry = _normalize_address(precedent_registry_address)
        self.appeals_court = Address(int(0).to_bytes(20, "big"))
        self.appeals_court_set = False
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.next_case_id = u256(0)

    @gl.public.write
    def set_appeals_court(self, appeals_court_address) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("only owner can set appeals court")
        if self.appeals_court_set:
            raise gl.vm.UserError("appeals court already set")
        self.appeals_court = _normalize_address(appeals_court_address)
        self.appeals_court_set = True

    @gl.public.write
    def file_case(
        self,
        defendant,
        description: str,
        claimed_amount: u256,
        canonical_fact: str,
        evidence_url: str,
    ) -> u256:
        defendant_addr = _normalize_address(defendant)
        claimant_addr = gl.message.sender_address

        # Cross-contract .view() MUST happen outside any nondet block.
        precedent_context = gl.get_contract_at(self.precedent_registry).view().search_precedents(
            description, u256(3)
        )

        case_id = self.next_case_id
        self.next_case_id = self.next_case_id + 1

        if claimed_amount < self.low_threshold:
            tier = TIER_LOW
            verdict = self._resolve_low(canonical_fact, evidence_url)
        elif claimed_amount < self.high_threshold:
            tier = TIER_MEDIUM
            verdict = self._resolve_medium(description, canonical_fact, precedent_context)
        else:
            tier = TIER_HIGH
            verdict = self._resolve_high(description, canonical_fact, precedent_context)

        record = {
            "case_id": int(case_id),
            "claimant": str(claimant_addr),
            "defendant": str(defendant_addr),
            "description": description,
            "claimed_amount": int(claimed_amount),
            "tier": tier,
            "verdict": verdict,
            "appealed": False,
        }
        self.cases[case_id] = json.dumps(record)

        # Cross-contract .emit() (fire-and-forget, async) also happens
        # outside any nondet block.
        gl.get_contract_at(self.precedent_registry).emit().record_verdict(
            case_id, description, verdict, tier
        )

        return case_id

    def _resolve_low(self, canonical_fact: str, evidence_url: str) -> str:
        fact_lower = canonical_fact.strip().lower()

        def fetch_and_check() -> str:
            page = gl.nondet.web.render(evidence_url, mode="text")
            return "MATCH" if fact_lower in page.lower() else "NO_MATCH"

        result = gl.eq_principle.strict_eq(fetch_and_check)
        return VERDICT_BREACH if result == "MATCH" else VERDICT_NO_BREACH

    def _resolve_medium(self, description: str, canonical_fact: str, precedent_context: str) -> str:
        def analyze() -> str:
            prompt = (
                "You are evaluating a dispute under two independent readings, "
                "then giving one final verdict.\n\n"
                "Case description:\n<case>\n" + description + "\n</case>\n\n"
                "Claimant's canonical fact assertion:\n<fact>\n" + canonical_fact + "\n</fact>\n\n"
                "Relevant prior similar cases (for consistency, not binding):\n"
                "<precedents>\n" + precedent_context + "\n</precedents>\n\n"
                "Step 1 - Strict literal reading: using only the literal wording of "
                "any agreement referenced above, does the described conduct count as "
                "a breach? Answer BREACH or NO_BREACH.\n"
                "Step 2 - Reasonable-person spirit reading: using the evident intent "
                "of any agreement referenced above, does the described conduct count "
                "as a breach? Answer BREACH or NO_BREACH.\n"
                "Step 3 - Combine: if both readings agree, use that as the final "
                "verdict. If they disagree, use NO_BREACH (a disagreement can still "
                "be escalated on appeal).\n\n"
                "Respond with strict JSON only, no other text, no markdown fence:\n"
                '{"literal_reading": "BREACH or NO_BREACH", '
                '"spirit_reading": "BREACH or NO_BREACH", '
                '"final_verdict": "BREACH or NO_BREACH"}'
            )
            raw = gl.nondet.exec_prompt(prompt)
            return _extract_json_object(raw)

        verdict_json = gl.eq_principle.prompt_comparative(
            analyze,
            "Two-reading breach assessment must reach the same final_verdict.",
        )
        try:
            parsed = json.loads(verdict_json)
            verdict = parsed.get("final_verdict", VERDICT_NO_BREACH)
        except Exception:
            verdict = VERDICT_NO_BREACH
        if verdict not in (VERDICT_BREACH, VERDICT_NO_BREACH):
            verdict = VERDICT_NO_BREACH
        return verdict

    def _resolve_high(self, description: str, canonical_fact: str, precedent_context: str) -> str:
        def analyze() -> str:
            prompt = (
                "You are the leading reviewer for a high-value dispute. Produce a "
                "thorough written assessment.\n\n"
                "Case description:\n<case>\n" + description + "\n</case>\n\n"
                "Claimant's canonical fact assertion:\n<fact>\n" + canonical_fact + "\n</fact>\n\n"
                "Relevant prior similar cases (for consistency, not binding):\n"
                "<precedents>\n" + precedent_context + "\n</precedents>\n\n"
                "Analyze the dispute in detail, then give a final verdict.\n\n"
                "Respond with strict JSON only, no other text, no markdown fence:\n"
                '{"reasoning": "<detailed analysis, max 800 chars>", '
                '"final_verdict": "BREACH or NO_BREACH"}'
            )
            raw = gl.nondet.exec_prompt(prompt)
            return _extract_json_object(raw)

        verdict_json = gl.eq_principle.prompt_non_comparative(
            analyze,
            task="Produce a thorough breach assessment with reasoning and a final verdict.",
            criteria=(
                "The final_verdict must be exactly BREACH or NO_BREACH, must follow "
                "from the stated reasoning, and the reasoning must reference both "
                "the case description and the canonical fact assertion."
            ),
        )
        try:
            parsed = json.loads(verdict_json)
            verdict = parsed.get("final_verdict", VERDICT_NO_BREACH)
        except Exception:
            verdict = VERDICT_NO_BREACH
        if verdict not in (VERDICT_BREACH, VERDICT_NO_BREACH):
            verdict = VERDICT_NO_BREACH
        return verdict

    @gl.public.write.payable
    def request_appeal(self, case_id: u256) -> None:
        if not self.appeals_court_set:
            raise gl.vm.UserError("appeals court not configured yet")
        if case_id not in self.cases:
            raise gl.vm.UserError("case not found")

        record = json.loads(self.cases[case_id])
        if str(gl.message.sender_address) != record.get("claimant"):
            raise gl.vm.UserError("only the recorded claimant can appeal this case")
        if record.get("appealed"):
            raise gl.vm.UserError("case already appealed")
        record["appealed"] = True
        self.cases[case_id] = json.dumps(record)

        bond = gl.message.value
        # Cross-contract .emit() with value, outside any nondet block.
        gl.get_contract_at(self.appeals_court).emit(value=bond).file_appeal(
            case_id, json.dumps(record)
        )

    @gl.public.view
    def get_case(self, case_id: u256) -> str:
        if case_id not in self.cases:
            raise gl.vm.UserError("case not found")
        return self.cases[case_id]

    @gl.public.view
    def get_case_count(self) -> u256:
        return self.next_case_id

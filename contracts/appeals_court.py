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


VERDICT_BREACH = "BREACH"
VERDICT_NO_BREACH = "NO_BREACH"


class AppealsCourt(gl.Contract):
    owner: Address
    precedent_registry: Address
    first_instance_court: Address
    first_instance_court_set: bool
    next_appeal_id: u256
    appeals: TreeMap[u256, str]

    def __init__(self, precedent_registry_address):
        self.owner = gl.message.sender_address
        self.precedent_registry = _normalize_address(precedent_registry_address)
        self.first_instance_court = Address(int(0).to_bytes(20, "big"))
        self.first_instance_court_set = False
        self.next_appeal_id = u256(0)

    @gl.public.write
    def set_first_instance_court(self, first_instance_court_address) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("only owner can set first instance court")
        if self.first_instance_court_set:
            raise gl.vm.UserError("first instance court already set")
        self.first_instance_court = _normalize_address(first_instance_court_address)
        self.first_instance_court_set = True

    @gl.public.write.payable
    def file_appeal(self, case_id: u256, case_json: str) -> None:
        if not self.first_instance_court_set:
            raise gl.vm.UserError("first instance court not configured yet")
        if gl.message.sender_address != self.first_instance_court:
            raise gl.vm.UserError("only the configured first instance court can file an appeal")

        bond = gl.message.value
        case_record = json.loads(case_json)
        description = case_record.get("description", "")
        original_verdict = case_record.get("verdict", VERDICT_NO_BREACH)
        appellant_address = _normalize_address(case_record.get("claimant"))

        precedent_context = gl.get_contract_at(self.precedent_registry).view().search_precedents(
            description, u256(3)
        )

        final_verdict = self._review(description, original_verdict, precedent_context)
        overturned = final_verdict != original_verdict

        appeal_id = self.next_appeal_id
        self.next_appeal_id = self.next_appeal_id + 1
        appeal_record = {
            "appeal_id": int(appeal_id),
            "case_id": int(case_id),
            "original_verdict": original_verdict,
            "final_verdict": final_verdict,
            "overturned": overturned,
            "bond": int(bond),
            "appellant": str(appellant_address),
        }
        self.appeals[appeal_id] = json.dumps(appeal_record)

        gl.get_contract_at(self.precedent_registry).emit().record_verdict(
            case_id, description, final_verdict, "appeal"
        )

        if overturned and bond > 0:
            gl.get_contract_at(appellant_address).emit_transfer(value=bond)

    def _review(self, description: str, original_verdict: str, precedent_context: str) -> str:
        def analyze() -> str:
            prompt = (
                "You are an appeals panel re-reviewing a dispute that was already "
                "decided once. Consider it under three separate, independent "
                "framings before giving one final verdict.\n\n"
                "Case description:\n<case>\n" + description + "\n</case>\n\n"
                "Original first-instance verdict (may be wrong, do not defer to "
                "it):\n<original>\n" + original_verdict + "\n</original>\n\n"
                "Relevant prior similar cases (for consistency, not binding):\n"
                "<precedents>\n" + precedent_context + "\n</precedents>\n\n"
                "Framing A - Strict literal reading of any referenced agreement.\n"
                "Framing B - Reasonable-person spirit/intent reading.\n"
                "Framing C - A skeptical, evidence-first reading that assumes "
                "nothing not explicitly stated in the case description.\n\n"
                "Give each framing's answer (BREACH or NO_BREACH), then a "
                "final_verdict that is the majority of the three (if all three "
                "differ in a way that prevents a majority, use NO_BREACH).\n\n"
                "Respond with strict JSON only, no other text, no markdown fence:\n"
                '{"framing_a": "BREACH or NO_BREACH", '
                '"framing_b": "BREACH or NO_BREACH", '
                '"framing_c": "BREACH or NO_BREACH", '
                '"final_verdict": "BREACH or NO_BREACH"}'
            )
            raw = gl.nondet.exec_prompt(prompt)
            return _extract_json_object(raw)

        verdict_json = gl.eq_principle.prompt_comparative(
            analyze,
            "Three-framing appeal review must reach the same final_verdict.",
        )
        try:
            parsed = json.loads(verdict_json)
            verdict = parsed.get("final_verdict", VERDICT_NO_BREACH)
        except Exception:
            verdict = VERDICT_NO_BREACH
        if verdict not in (VERDICT_BREACH, VERDICT_NO_BREACH):
            verdict = VERDICT_NO_BREACH
        return verdict

    @gl.public.view
    def get_appeal(self, appeal_id: u256) -> str:
        if appeal_id not in self.appeals:
            raise gl.vm.UserError("appeal not found")
        return self.appeals[appeal_id]

    @gl.public.view
    def get_appeal_count(self) -> u256:
        return self.next_appeal_id

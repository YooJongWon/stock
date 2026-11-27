"""Extract narrowly defined investor facts from the original EDGAR submission."""
import re
from datetime import datetime
from html.parser import HTMLParser

MONTH_DATE = r"(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}"
LISTING_ACTION = re.compile(
    rf"\b(?:trading\b[^.;]{{0,105}}?\b(?:will be|was|has been) suspended|"
    rf"(?:shares|stock|securities|listing)\b[^.;]{{0,100}}?\b(?:will be|was|has been) (?:delisted|removed from listing))"
    rf"[^.;]{{0,140}}?\b({MONTH_DATE})", re.I,
)
CONDITIONAL = re.compile(r"\b(?:if|unless|subject to|in the event|could|may|would|not)\b", re.I)
RECOVERY = re.compile(r"\b(?:exchange|nasdaq|nyse)\b[^.;]{0,140}\b(?:has regained compliance|has determined that .{1,70} (?:regained compliance|is in compliance))\b", re.I)
FOLLOWUP = re.compile(r"\b(?:stay (?:of|has been granted)|(?:hearing|appeal) (?:request )?(?:will|would|has) stay|pending (?:the|a) (?:hearing|appeal)|will (?:list|trade) on (?:the )?(?:nasdaq|nyse))\b", re.I)

GUIDANCE = {
    "1.03": "회생이나 청산 과정에서 기존 보통주의 가치가 크게 줄 수 있습니다. 보유 중이면 월말 전에 비중 축소를 검토할 근거입니다.",
    "2.04": "빚을 예정대로 갚을 수 있는지가 중요합니다. 채권자 합의나 자금 확보가 확인되지 않으면 월말 전 비중 축소를 검토할 근거입니다.",
    "4.02": "수정될 숫자에 의존한 투자 판단은 다시 점검해야 합니다. 수정 범위와 현금흐름 영향이 불분명하면 월말 전 비중 축소를 검토할 근거입니다.",
    "2.06": "회계상 손실이 그만큼의 즉시 현금 유출로 이어지지는 않습니다. 반복 손상이나 사업 전망 악화가 있는지 지켜볼 근거입니다.",
    "6-K": "해외 발행사의 공시 유형만으로 매도 판단을 내리기 어렵습니다.",
}

class FilingText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "ix:header"}:
            self.hidden = True
        if tag in {"p", "div", "br", "tr", "td"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "ix:header"}:
            self.hidden = False
        if tag in {"p", "div", "tr", "td"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def document_text(submission, forms):
    sections = re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", submission, re.I | re.S)
    for section in sections:
        kind = re.search(r"<TYPE>\s*([^\s<]+)", section, re.I)
        if kind and kind[1].upper() in forms:
            payload = re.search(r"<TEXT>(.*?)</TEXT>", section, re.I | re.S)
            if payload:
                parser = FilingText()
                parser.feed(payload[1])
                return " ".join("".join(parser.parts).split())
    return ""


def amount_in_millions(number, unit):
    return float(number.replace(",", "")) * ({"million": 1, "billion": 1000}[unit.lower()])


def earnings_facts(text):
    facts = []
    cash = re.search(r"cash(?:, cash equivalents,? and marketable securities| and cash equivalents)\s+(?:were|was)\s+\$([\d,.]+)\s+(million|billion)", text, re.I)
    if cash:
        comparison = re.search(r"compared to\s+\$([\d,.]+)\s+(million|billion)", text[cash.end():cash.end()+150], re.I)
        if comparison:
            facts.append(f"비교 시점의 현금성 자산은 미화 {amount_in_millions(*comparison.groups()):,.1f}백만 달러였습니다.")
        facts.append(f"공시가 밝힌 현금성 자산은 미화 {amount_in_millions(*cash.groups()):,.1f}백만 달러입니다.")
    loss = re.search(r"net loss (?:was|of)\s+\$([\d,.]+)\s+(million|billion)[^;]{0,180}?compared to\s+\$([\d,.]+)\s+(million|billion)", text, re.I)
    if loss:
        current, previous = (amount_in_millions(*loss.groups()[i:i+2]) for i in (0, 2))
        direction = "늘었습니다" if current > previous else "줄었습니다" if current < previous else "같았습니다"
        facts.append(f"순손실은 비교 기간 {previous:,.1f}백만 달러에서 {current:,.1f}백만 달러로 {direction}.")
    offering = re.search(r"public offering[^.;]{0,65}raising approximately \$([\d,.]+)\s+(million|billion) in gross proceeds", text, re.I)
    if offering:
        facts.append(f"공개 주식 발행으로 비용 차감 전 미화 {amount_in_millions(*offering.groups()):,.1f}백만 달러를 조달했습니다.")
    return facts


def interpret_filing(code, body, exhibit=""):
    if code == "3.01":
        if RECOVERY.search(body):
            return "resolved", ["공시 본문에 거래소 상장 요건을 다시 충족했다는 내용이 있습니다."], "해당 상장 요건에 대한 경고는 낮아졌습니다. 다른 위험 신호와 구분해 판단하세요."
        action = next((
            match for match in LISTING_ACTION.finditer(body)
            if not CONDITIONAL.search(body[body.rfind(".", 0, match.start()) + 1:match.end()])
        ), None)
        if action and not FOLLOWUP.search(body):
            try:
                date = datetime.strptime(action[1], "%B %d, %Y").date()
            except ValueError:
                action = None
            else:
                return "review", [f"공시 본문에 거래 정지 또는 상장폐지 일정이 명시되어 있습니다. 미국 현지 날짜 {date.isoformat()}."], "보유 중이라면 월말까지 기다리기 전에 해당 거래소에서 주문을 낼 수 있는 기간과 거래 경로를 우선 확인하고 비중 축소를 검토하세요."
        facts = ["공시 본문에 거래 정지 또는 폐지 일정과 함께 집행 유예나 거래소 이전 가능성을 나타내는 내용이 있습니다. 현재 적용되는 일정은 확인되지 않았습니다."] if action else ["공시 본문에서 실제 거래 정지·폐지 날짜를 확정할 수 없습니다."]
        return "watch", facts, "개선 기한이나 거래소 후속 결정이 핵심입니다. 통지만으로 즉시 매도하기보다 거래 정지 일정이나 상장 요건 회복 여부를 우선 확인하세요."
    if code == "2.02":
        facts = earnings_facts(exhibit)
        return "notice", facts or ["첨부 실적 자료에서 자동으로 검증할 수 있는 수치를 확보하지 못했습니다."], "실적 발표만으로 월중 매도로 판단하기는 어렵습니다. 자금 여력과 적자 흐름을 함께 보고, 다음 실적이나 자금 조달 공시에서 보유 근거가 달라지는지 확인하세요."
    if code in {"25", "25-NSE"}:
        return "review", ["거래소 상장 또는 등록을 종료하기 위한 Form 25가 접수됐습니다."], "다른 거래소로 이전하는 경우도 있습니다. 보유 중이면 기존 거래소에서 언제까지 매도할 수 있는지와 이전 거래소에서 거래할 수 있는지를 먼저 확인하세요."
    return None, [], GUIDANCE.get(code, "")

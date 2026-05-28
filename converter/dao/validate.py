"""DAO ↔ Mapper XML 검증 유틸리티.

자동 변환된 DAO + Mapper XML 을 사용자가 가공한 뒤,
다음 항목을 교차 검증한다.

    - XML 문법 (well-formed, namespace 속성, 중복 id)
    - Java 중괄호 / 괄호 균형
    - DAO 의 ``uxbDAO.select("NS.id", paramMap)`` 호출이 XML 에 실존하는지
    - DAO ``paramMap.put("k", ...)`` 키 ↔ XML ``#{k}`` 의 양방향 매칭
"""

from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv(override=True)

# Windows 한글 콘솔(cp1252) 인코딩 오류 방지
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

logger = logging.getLogger(__name__)
console = Console()


_VALIDATE_DIR = os.getenv("VALIDATE_DIR", "converter/dao/output")
DEFAULT_JAVA_DIR = Path(os.getenv("VALIDATE_JAVA_DIR", _VALIDATE_DIR))
DEFAULT_XML_DIR = Path(os.getenv("VALIDATE_XML_DIR", _VALIDATE_DIR))
DEFAULT_REPORT_PATH: Path | None = (
    Path(os.getenv("VALIDATE_REPORT")) if os.getenv("VALIDATE_REPORT") else None
)

LEVEL_ERROR = "ERROR"
LEVEL_WARN = "WARN"
LEVEL_INFO = "INFO"

_LEVEL_STYLE = {
    LEVEL_ERROR: "bold red",
    LEVEL_WARN: "yellow",
    LEVEL_INFO: "cyan",
}


# ─────────────────────────────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────────────────────────────
@dataclass
class Issue:
    level: str
    file: str
    location: str
    category: str
    message: str


@dataclass
class MapperQuery:
    id: str
    tag: str
    params: set[str] = field(default_factory=set)
    dollar_params: set[str] = field(default_factory=set)


@dataclass
class DaoCall:
    raw_id: str
    namespace: str
    query_id: str
    op: str
    param_keys: set[str]
    method_name: str


# ─────────────────────────────────────────────────────────────────────
# 마스킹: 문자열·주석을 공백으로 치환해 라인 번호와 길이를 유지
# ─────────────────────────────────────────────────────────────────────
def _mask_to_spaces(s: str, keep_quotes: bool = False) -> str:
    """문자열을 공백으로 치환하되 개행은 유지한다."""
    if keep_quotes and len(s) >= 2:
        return s[0] + "".join(c if c == "\n" else " " for c in s[1:-1]) + s[-1]
    return "".join(c if c == "\n" else " " for c in s)


def mask_strings_and_comments(text: str) -> str:
    """문자열·주석을 공백 마스크로 치환한 코드를 반환한다.

    원본과 동일한 길이·라인 번호를 유지하므로 brace 카운팅·메서드 추출에 안전하다.

    문자 단위 스캔으로 처리 순서를 Java 렉서 규칙과 동일하게 유지한다.
    (regex 방식은 문자열 안의 /* 가 다른 문자열 안의 */ 와 매칭되는 오탐을 유발함)
    """
    result: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        # 줄 주석 //
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = i
            while j < n and text[j] != "\n":
                j += 1
            result.append("".join("\n" if c == "\n" else " " for c in text[i:j]))
            i = j
            continue

        # 블록 주석 /* ... */
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = i + 2
            while j < n - 1 and not (text[j] == "*" and text[j + 1] == "/"):
                j += 1
            j += 2  # */ 포함
            result.append("".join("\n" if c == "\n" else " " for c in text[i:j]))
            i = j
            continue

        # 문자열 리터럴 "..."  (Java 8 — 개행 포함 불가)
        if ch == '"':
            j = i + 1
            while j < n and text[j] != "\n":
                if text[j] == "\\" and j + 1 < n:
                    j += 2
                elif text[j] == '"':
                    j += 1
                    break
                else:
                    j += 1
            segment = text[i:j]
            if len(segment) >= 2:
                masked = segment[0] + "".join("\n" if c == "\n" else " " for c in segment[1:-1]) + segment[-1]
            else:
                masked = segment
            result.append(masked)
            i = j
            continue

        # 문자 리터럴 '.'
        if ch == "'":
            j = i + 1
            while j < n and text[j] != "\n":
                if text[j] == "\\" and j + 1 < n:
                    j += 2
                elif text[j] == "'":
                    j += 1
                    break
                else:
                    j += 1
            segment = text[i:j]
            if len(segment) >= 2:
                masked = segment[0] + "".join("\n" if c == "\n" else " " for c in segment[1:-1]) + segment[-1]
            else:
                masked = segment
            result.append(masked)
            i = j
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


# ─────────────────────────────────────────────────────────────────────
# XML 분석기
# ─────────────────────────────────────────────────────────────────────
class XmlAnalyzer:
    _PARAM_RE = re.compile(r"#\{\s*(\w+)(?:\s*,[^}]*)?\s*\}")
    _DOLLAR_RE = re.compile(r"\$\{\s*(\w+)(?:\s*,[^}]*)?\s*\}")
    _QUERY_TAGS = {"select", "insert", "update", "delete"}
    # <if test="...">, <when test="..."> 속성에서 OGNL 식별자 추출
    # ET.tostring 은 항상 double-quote 로 출력하므로 내부 single-quote 를 허용
    _TEST_ATTR_RE = re.compile(r'\btest\s*=\s*"([^"]+)"')
    _STR_LITERAL_RE = re.compile(r"'[^']*'")  # OGNL 문자열 리터럴 제거용
    _OGNL_IDENT_RE = re.compile(r'\b([a-zA-Z_]\w*)\b(?!\s*\()')
    _OGNL_KEYWORDS = frozenset({
        "null", "true", "false", "and", "or", "not", "in", "instanceof",
        "new", "eq", "neq", "lt", "lte", "gt", "gte",
        "String", "list", "array", "isEmpty", "size",
    })

    def analyze(
        self, xml_path: Path
    ) -> tuple[str | None, dict[str, MapperQuery], list[Issue]]:
        issues: list[Issue] = []
        try:
            text = xml_path.read_text(encoding="utf-8")
        except OSError as e:
            issues.append(Issue(LEVEL_ERROR, xml_path.name, "", "IO", f"읽기 실패: {e}"))
            return None, {}, issues

        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            issues.append(
                Issue(LEVEL_ERROR, xml_path.name, "", "XML_PARSE", f"XML 파싱 실패: {e}")
            )
            return None, {}, issues

        if root.tag.lower() != "mapper":
            issues.append(
                Issue(
                    LEVEL_WARN,
                    xml_path.name,
                    "",
                    "XML_ROOT",
                    f"루트 태그가 <mapper> 가 아님: <{root.tag}>",
                )
            )

        namespace = root.attrib.get("namespace")
        if not namespace:
            issues.append(
                Issue(LEVEL_ERROR, xml_path.name, "", "XML_NS", "namespace 속성 없음")
            )

        queries: dict[str, MapperQuery] = {}
        for child in root:
            tag = child.tag.lower()
            if tag not in self._QUERY_TAGS:
                continue
            qid = child.attrib.get("id")
            if not qid:
                issues.append(
                    Issue(
                        LEVEL_ERROR,
                        xml_path.name,
                        "",
                        "XML_ID",
                        f"<{tag}> 태그에 id 속성 없음",
                    )
                )
                continue
            if qid in queries:
                issues.append(
                    Issue(
                        LEVEL_ERROR,
                        xml_path.name,
                        qid,
                        "XML_DUP",
                        f"id 중복: {qid}",
                    )
                )

            inner = ET.tostring(child, encoding="unicode", method="xml")
            params = set(self._PARAM_RE.findall(inner))
            dollars = set(self._DOLLAR_RE.findall(inner))

            # <if test="...">, <when test="..."> 속성의 OGNL 변수도 수집
            for test_expr in self._TEST_ATTR_RE.findall(inner):
                # 'T', 'SOD' 같은 문자열 리터럴을 먼저 제거
                clean_expr = self._STR_LITERAL_RE.sub(" ", test_expr)
                for ident in self._OGNL_IDENT_RE.findall(clean_expr):
                    if ident not in self._OGNL_KEYWORDS:
                        params.add(ident)

            queries[qid] = MapperQuery(id=qid, tag=tag, params=params, dollar_params=dollars)

        return namespace, queries, issues


# ─────────────────────────────────────────────────────────────────────
# Java(DAO) 분석기
# ─────────────────────────────────────────────────────────────────────
class JavaAnalyzer:
    _CLASS_RE = re.compile(r"\bclass\s+(\w+)")
    _METHOD_RE = re.compile(
        r"\b(?:public|private|protected)\b"
        r"[^;{]*?"
        r"\b(\w+)\s*\([^)]*\)\s*"
        r"(?:throws[\w\s,.]+)?\s*\{"
    )
    _UXB_CALL_RE = re.compile(
        r"\b\w+\.(select|selectOne|insert|update|delete)\s*\(\s*"
        r'"([^"]+)"\s*,\s*(\w+)\s*\)'
    )
    _PUT_RE = re.compile(r"(\w+)\s*\.\s*put\s*\(\s*\"([^\"]+)\"\s*,")

    def analyze(
        self, java_path: Path
    ) -> tuple[str | None, list[DaoCall], list[Issue]]:
        issues: list[Issue] = []
        try:
            text = java_path.read_text(encoding="utf-8")
        except OSError as e:
            issues.append(Issue(LEVEL_ERROR, java_path.name, "", "IO", f"읽기 실패: {e}"))
            return None, [], issues

        masked = mask_strings_and_comments(text)

        self._check_balance(masked, java_path.name, issues)

        cls_match = self._CLASS_RE.search(masked)
        class_name = cls_match.group(1) if cls_match else None
        if not class_name:
            issues.append(
                Issue(LEVEL_WARN, java_path.name, "", "JAVA_CLS", "클래스 선언을 찾지 못함")
            )

        calls: list[DaoCall] = []
        method_ranges = self._find_methods(masked)
        for name, start, end in method_ranges:
            body_orig = text[start:end]
            body_mask = masked[start:end]

            for cm in self._UXB_CALL_RE.finditer(body_orig):
                op = cm.group(1)
                raw_id = cm.group(2)
                param_var = cm.group(3)

                if op == "selectOne":
                    op = "select"

                if "." in raw_id:
                    ns, qid = raw_id.split(".", 1)
                else:
                    ns, qid = "", raw_id
                    issues.append(
                        Issue(
                            LEVEL_WARN,
                            java_path.name,
                            name,
                            "DAO_NSID",
                            f'호출 id 에 namespace 없음: "{raw_id}"',
                        )
                    )

                # 같은 메서드 본문에서 paramMap.put(...) 키 수집
                # 호출 시점 이전 put 만 유효하지만, 같은 변수에 대한 put 만 본다.
                keys = set()
                for pm in self._PUT_RE.finditer(body_orig):
                    if pm.group(1) == param_var:
                        keys.add(pm.group(2))

                calls.append(
                    DaoCall(
                        raw_id=raw_id,
                        namespace=ns,
                        query_id=qid,
                        op=op,
                        param_keys=keys,
                        method_name=name,
                    )
                )

        return class_name, calls, issues

    def _check_balance(self, masked: str, fname: str, issues: list[Issue]) -> None:
        for open_ch, close_ch, label in [("{", "}", "중괄호"), ("(", ")", "괄호")]:
            o = masked.count(open_ch)
            c = masked.count(close_ch)
            if o != c:
                issues.append(
                    Issue(
                        LEVEL_ERROR,
                        fname,
                        "",
                        "BRACE",
                        f"{label} 불균형: '{open_ch}'={o} '{close_ch}'={c}",
                    )
                )

    def _find_methods(self, masked: str) -> list[tuple[str, int, int]]:
        """(메서드명, 본문 시작 idx, 본문 끝 idx) 리스트.

        본문 시작은 여는 `{` 위치, 끝은 닫는 `}` 의 다음 인덱스.
        """
        results: list[tuple[str, int, int]] = []
        for m in self._METHOD_RE.finditer(masked):
            name = m.group(1)
            open_brace = m.end() - 1
            depth = 0
            end_idx = -1
            for j in range(open_brace, len(masked)):
                ch = masked[j]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end_idx = j + 1
                        break
            if end_idx > 0:
                results.append((name, open_brace, end_idx))
        return results


# ─────────────────────────────────────────────────────────────────────
# 검증기 (Validator)
# ─────────────────────────────────────────────────────────────────────
class Validator:
    def __init__(self, directory: Path | str | None = None) -> None:
        if directory:
            self.java_dir = Path(directory)
            self.xml_dir = Path(directory)
        else:
            self.java_dir = DEFAULT_JAVA_DIR
            self.xml_dir = DEFAULT_XML_DIR
        self.java_analyzer = JavaAnalyzer()
        self.xml_analyzer = XmlAnalyzer()

    def run(self, report_path: Path | str | None = None) -> list[Issue]:
        if report_path is None:
            report_path = DEFAULT_REPORT_PATH
        for d in {self.java_dir, self.xml_dir}:
            if not d.exists():
                console.print(f"[bold red]대상 폴더 없음:[/] {d}")
                return []

        java_files = sorted(self.java_dir.glob("*.java"))
        xml_files = sorted(self.xml_dir.glob("*.xml"))

        if not java_files and not xml_files:
            if self.java_dir == self.xml_dir:
                console.print(f"[yellow]대상 파일 없음:[/] {self.java_dir}")
            else:
                console.print(f"[yellow]대상 파일 없음:[/] {self.java_dir} / {self.xml_dir}")
            return []

        # 파일 쌍 매칭: XxxDAO.java ↔ XxxMapper.xml
        pairs, orphans = self._match_pairs(java_files, xml_files)

        all_issues: list[Issue] = []

        for fname, issue in orphans:
            all_issues.append(issue)

        for dao_path, xml_path in pairs:
            all_issues.extend(self._validate_pair(dao_path, xml_path))

        self._print_summary(pairs, orphans, all_issues)
        self._print_issues(all_issues)

        if report_path:
            self._write_report(Path(report_path), pairs, orphans, all_issues)
            console.print(f"[green]보고서 저장:[/] {report_path}")

        return all_issues

    # ── 페어 매칭 ────────────────────────────────────────────────
    _DAO_RE = re.compile(r"^(.+?)DAO(.*)")

    def _match_pairs(
        self, java_files: list[Path], xml_files: list[Path]
    ) -> tuple[list[tuple[Path, Path]], list[tuple[str, Issue]]]:
        """DAO.java <-> Mapper.xml 쌍을 만든다.

        매칭 규칙: XxxDAO*.java ↔ XxxMapper.xml
        XxxDAO_BACKUP.java, XxxDAO_BACKUP_1.java 등 접미사가 붙은 파일도 포함.
        쌍을 찾지 못한 파일은 orphan 으로 기록한다.
        """
        dao_files = [f for f in java_files if self._DAO_RE.match(f.stem)]
        mapper_files = {f.stem: f for f in xml_files if f.stem.endswith("Mapper")}

        pairs: list[tuple[Path, Path]] = []
        used_mappers: set[str] = set()
        orphans: list[tuple[str, Issue]] = []

        for dao in dao_files:
            m = self._DAO_RE.match(dao.stem)
            assert m is not None
            prefix = m.group(1)   # "SCBPosition"
            suffix = m.group(2)   # "" | "_BACKUP" | "_BACKUP_1"
            mapper_stem = prefix + suffix + "Mapper"
            if mapper_stem in mapper_files:
                pairs.append((dao, mapper_files[mapper_stem]))
                used_mappers.add(mapper_stem)
            else:
                orphans.append(
                    (
                        dao.name,
                        Issue(
                            LEVEL_ERROR,
                            dao.name,
                            "",
                            "PAIR",
                            f"짝이 되는 Mapper XML 없음 (기대: {mapper_stem}.xml)",
                        ),
                    )
                )

        for stem, xml in mapper_files.items():
            if stem not in used_mappers:
                base = stem[:-6]  # remove "Mapper"
                dao_name = f"{base}DAO.java"
                orphans.append(
                    (
                        xml.name,
                        Issue(
                            LEVEL_WARN,
                            xml.name,
                            "",
                            "PAIR",
                            f"짝이 되는 DAO 없음 (기대: {dao_name})",
                        ),
                    )
                )

        # DAO 가 포함되지 않은 .java 는 단순 정보로 표시
        for f in java_files:
            if not self._DAO_RE.match(f.stem):
                orphans.append(
                    (
                        f.name,
                        Issue(
                            LEVEL_INFO,
                            f.name,
                            "",
                            "PAIR",
                            "파일명에 'DAO' 가 없어 매핑 대상에서 제외",
                        ),
                    )
                )

        return pairs, orphans

    # ── 페어 검증 ────────────────────────────────────────────────
    def _validate_pair(self, dao_path: Path, xml_path: Path) -> list[Issue]:
        issues: list[Issue] = []
        class_name, calls, java_issues = self.java_analyzer.analyze(dao_path)
        namespace, queries, xml_issues = self.xml_analyzer.analyze(xml_path)

        issues.extend(java_issues)
        issues.extend(xml_issues)

        # XML 파싱 자체가 실패했으면 (queries 비어있고 ERROR 있음) 교차검증은 스킵
        xml_broken = not queries and any(
            i.level == LEVEL_ERROR and i.category == "XML_PARSE" for i in xml_issues
        )
        if xml_broken:
            issues.append(
                Issue(
                    LEVEL_INFO,
                    xml_path.name,
                    "",
                    "SKIP_CROSS",
                    "XML 파싱 실패로 교차검증 스킵 (XML 먼저 수정 필요)",
                )
            )
            return issues

        # 1) 네임스페이스 vs 클래스명
        if class_name and namespace:
            expected_ns = (
                class_name[:-3] if class_name.endswith("DAO") else class_name
            )
            if namespace != expected_ns:
                issues.append(
                    Issue(
                        LEVEL_WARN,
                        xml_path.name,
                        "",
                        "NS_MISMATCH",
                        f"XML namespace='{namespace}' ↔ 예상 '{expected_ns}'",
                    )
                )

        # 2) 호출별 검증
        called_ids: set[str] = set()
        for call in calls:
            called_ids.add(call.query_id)

            if call.namespace and namespace and call.namespace != namespace:
                issues.append(
                    Issue(
                        LEVEL_WARN,
                        dao_path.name,
                        call.method_name,
                        "CALL_NS",
                        f'호출 namespace "{call.namespace}" ↔ XML "{namespace}"',
                    )
                )

            if call.query_id not in queries:
                issues.append(
                    Issue(
                        LEVEL_ERROR,
                        dao_path.name,
                        call.method_name,
                        "MISSING_ID",
                        f'XML 에 없는 id 호출: "{call.raw_id}"',
                    )
                )
                continue

            q = queries[call.query_id]

            if call.op != q.tag:
                issues.append(
                    Issue(
                        LEVEL_WARN,
                        dao_path.name,
                        call.method_name,
                        "OP_MISMATCH",
                        f"호출종류 DAO={call.op} ↔ XML=<{q.tag}> ({call.query_id})",
                    )
                )

            xml_keys = q.params | q.dollar_params
            missing = xml_keys - call.param_keys
            if missing:
                issues.append(
                    Issue(
                        LEVEL_ERROR,
                        dao_path.name,
                        call.method_name,
                        "PARAM_MISSING",
                        f"DAO 에서 put 누락: {sorted(missing)} (id={call.query_id})",
                    )
                )
            unused = call.param_keys - xml_keys
            if unused:
                issues.append(
                    Issue(
                        LEVEL_WARN,
                        dao_path.name,
                        call.method_name,
                        "PARAM_UNUSED",
                        f"XML 에서 미사용 키: {sorted(unused)} (id={call.query_id})",
                    )
                )

        # 3) XML 에만 정의되고 DAO 에서 호출 안 한 id
        orphan_ids = set(queries) - called_ids
        if orphan_ids:
            issues.append(
                Issue(
                    LEVEL_INFO,
                    xml_path.name,
                    "",
                    "ORPHAN_XML",
                    f"DAO 에서 호출되지 않는 XML id: {sorted(orphan_ids)}",
                )
            )

        return issues

    # ── 콘솔 출력 ────────────────────────────────────────────────
    def _print_summary(
        self,
        pairs: list[tuple[Path, Path]],
        orphans: list[tuple[str, Issue]],
        issues: list[Issue],
    ) -> None:
        counts = {LEVEL_ERROR: 0, LEVEL_WARN: 0, LEVEL_INFO: 0}
        for it in issues:
            counts[it.level] = counts.get(it.level, 0) + 1

        console.rule("[bold cyan]검증 요약")
        if self.java_dir == self.xml_dir:
            console.print(f"대상 폴더 : {self.java_dir}")
        else:
            console.print(f"DAO  폴더 : {self.java_dir}")
            console.print(f"XML  폴더 : {self.xml_dir}")
        console.print(f"매칭 페어 : {len(pairs)}쌍")
        console.print(
            f"문제 건수 : "
            f"[red]ERROR {counts[LEVEL_ERROR]}[/]  "
            f"[yellow]WARN {counts[LEVEL_WARN]}[/]  "
            f"[cyan]INFO {counts[LEVEL_INFO]}[/]"
        )

    def _print_issues(self, issues: list[Issue]) -> None:
        if not issues:
            console.print("[bold green]문제 없음. 검증 통과 ✓[/]")
            return

        table = Table(show_lines=False, header_style="bold")
        table.add_column("LV", width=5)
        table.add_column("파일", overflow="fold")
        table.add_column("위치")
        table.add_column("카테고리")
        table.add_column("메시지", overflow="fold")

        order = {LEVEL_ERROR: 0, LEVEL_WARN: 1, LEVEL_INFO: 2}
        for it in sorted(issues, key=lambda x: (order.get(x.level, 9), x.file, x.location)):
            style = _LEVEL_STYLE.get(it.level, "")
            table.add_row(
                f"[{style}]{it.level}[/]",
                it.file,
                it.location or "-",
                it.category,
                it.message,
            )
        console.print(table)

    # ── 보고서 파일 출력 ─────────────────────────────────────────
    def _write_report(
        self,
        path: Path,
        pairs: list[tuple[Path, Path]],
        orphans: list[tuple[str, Issue]],
        issues: list[Issue],
    ) -> None:
        import datetime

        path.parent.mkdir(parents=True, exist_ok=True)
        counts = {LEVEL_ERROR: 0, LEVEL_WARN: 0, LEVEL_INFO: 0}
        for it in issues:
            counts[it.level] = counts.get(it.level, 0) + 1

        W = 80
        rule = "─" * W

        def section(title: str) -> str:
            pad = W - len(title) - 2
            return f"┌─ {title} " + "─" * pad + "┐" if pad > 0 else f"┌─ {title} ┐"

        def row(label: str, value: str) -> str:
            return f"  {label:<14} {value}"

        lines: list[str] = []

        # ── 헤더 ──
        lines.append(rule)
        lines.append(f"  DAO <-> Mapper 검증 보고서")
        lines.append(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(rule)

        if self.java_dir == self.xml_dir:
            lines.append(row("대상 폴더", str(self.java_dir)))
        else:
            lines.append(row("DAO  폴더", str(self.java_dir)))
            lines.append(row("XML  폴더", str(self.xml_dir)))
        lines.append(row("매칭 페어", f"{len(pairs)}쌍"))
        lines.append(
            row("문제 건수",
                f"ERROR {counts[LEVEL_ERROR]}  /  WARN {counts[LEVEL_WARN]}  /  INFO {counts[LEVEL_INFO]}")
        )
        lines.append(rule)

        # ── 매칭 페어 ──
        lines.append("")
        lines.append("  [ 매칭된 페어 ]")
        lines.append("")
        if pairs:
            for dao, xml in pairs:
                lines.append(f"    {dao.name:<45} <->  {xml.name}")
        else:
            lines.append("    (없음)")
        lines.append("")

        # ── 이슈 목록 ──
        lines.append(rule)
        lines.append("")
        lines.append("  [ 이슈 목록 ]")
        lines.append("")

        if not issues:
            lines.append("    문제 없음. 검증 통과 ✓")
        else:
            order = {LEVEL_ERROR: 0, LEVEL_WARN: 1, LEVEL_INFO: 2}
            sorted_issues = sorted(
                issues, key=lambda x: (order.get(x.level, 9), x.file, x.location)
            )

            # 컬럼 너비 계산
            w_file = max((len(it.file) for it in sorted_issues), default=10)
            w_loc  = max((len(it.location or "-") for it in sorted_issues), default=6)
            w_cat  = max((len(it.category) for it in sorted_issues), default=8)

            header = (
                f"  {'LV':<5}  {'파일':<{w_file}}  {'위치':<{w_loc}}  {'카테고리':<{w_cat}}  메시지"
            )
            lines.append(header)
            lines.append("  " + "─" * (W - 2))

            prev_level = None
            for it in sorted_issues:
                if it.level != prev_level:
                    if prev_level is not None:
                        lines.append("")
                    prev_level = it.level

                loc = it.location or "-"
                line = (
                    f"  {it.level:<5}  {it.file:<{w_file}}  {loc:<{w_loc}}  "
                    f"{it.category:<{w_cat}}  {it.message}"
                )
                lines.append(line)

        lines.append("")
        lines.append(rule)

        path.write_text("\n".join(lines), encoding="utf-8")

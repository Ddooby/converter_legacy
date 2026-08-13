"""
checkbox_value_scan.py
=======================
CheckBox 컴포넌트의 Layout(value/truevalue/falsevalue)과 Script 안에서 실제로
비교하는 리터럴이 서로 안 맞는 후보를 찾아 리포트한다.

주의: 이 스크립트는 자동 수정을 하지 않는다. 후보 리스트만 뽑아준다 — layout의
truevalue/falsevalue는 실제 DB 컬럼에 저장되는 값이라, 잘못 자동 수정하면 다른
화면/배치가 같은 컬럼을 읽을 때 영향이 갈 수 있어서 파일별 수동 검토 후 적용 권장.

바인딩 체인:
  <CheckBox id="X" ... truevalue=".." falsevalue=".."/>
      → <BindItem compid="X" propid="value" datasetid="DS" columnid="COL"/>
      → Script 안 this.DS.getColumn(*, "COL") == "리터럴" 또는 this.X.value == "리터럴"

한계: 같은 파일 안에서 CheckBox/BindItem/Script가 전부 존재하는 경우만 잡는다.
서브폼에 정의된 CheckBox를 부모 폼의 BindItem이 참조하는 것처럼 파일이 나뉘어
있는 케이스(예: compid="div_eu_input.form.ck_dtSettle")는 이 스캔이 못 잡는다 —
그런 케이스는 수동으로 확인해야 함.

사용법:
  python -m converter.nexacro.checkbox_value_scan <스캔 대상 폴더>
  예) python -m converter.nexacro.checkbox_value_scan "C:\\Projects\\Panocean\\nexacro"

결과:
  converter/nexacro/patterns/checkbox_value_mismatch_report.json
"""

import re
import sys
import json
from pathlib import Path

_CHECKBOX_TAG_RE = re.compile(r'<CheckBox\b([^>]*)>')
_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
_BINDITEM_RE = re.compile(r'<BindItem\b([^>]*)/?>')
_SCRIPT_RE = re.compile(r'<Script[^>]*><!\[CDATA\[(.*?)\]\]></Script>', re.DOTALL)

_NUM_STYLE = {"0", "1"}
_BOOL_STYLE = {"true", "false"}
_YN_STYLE = {"y", "n"}


def _classify(v: str) -> str | None:
    lv = v.lower()
    if lv in _NUM_STYLE:
        return "num"
    if lv in _BOOL_STYLE:
        return "bool"
    if lv in _YN_STYLE:
        return "yn"
    return None


def _parse_attrs(attr_str: str) -> dict:
    return {m.group(1): m.group(2) for m in _ATTR_RE.finditer(attr_str)}


def scan_file(path: Path) -> list[dict]:
    try:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return []

    checkboxes = {}
    for m in _CHECKBOX_TAG_RE.finditer(content):
        attrs = _parse_attrs(m.group(1))
        cid = attrs.get("id")
        if not cid or "value" not in attrs or "truevalue" not in attrs or "falsevalue" not in attrs:
            continue
        checkboxes[cid] = {
            "id": cid,
            "value": attrs["value"],
            "truevalue": attrs["truevalue"],
            "falsevalue": attrs["falsevalue"],
            "binddataset": attrs.get("binddataset"),
        }

    binditems: dict[str, tuple[str, str]] = {}  # compid -> (datasetid, columnid)
    for m in _BINDITEM_RE.finditer(content):
        attrs = _parse_attrs(m.group(1))
        if attrs.get("propid") != "value":
            continue
        compid = attrs.get("compid")
        if not compid:
            continue
        binditems[compid] = (attrs.get("datasetid"), attrs.get("columnid"))

    script = "\n".join(m.group(1) for m in _SCRIPT_RE.finditer(content))
    if not script or not checkboxes:
        return []

    findings = []
    for cid, cb in checkboxes.items():
        style_tv = _classify(cb["truevalue"])
        style_fv = _classify(cb["falsevalue"])
        if style_tv is None or style_fv is None or style_tv != style_fv:
            # layout 자체가 판별 불가한 스타일(업무 코드값 등)이면 대상에서 제외
            continue
        allowed = {cb["value"].lower(), cb["truevalue"].lower(), cb["falsevalue"].lower()}

        literals: list[tuple[str, str]] = []  # (literal, matched snippet)

        # ① 컴포넌트 직접 참조: this.<id>.value == "리터럴"
        for lm in re.finditer(
            rf'this\.{re.escape(cid)}\.value\s*(?:==|!=)\s*[\'"]([^\'"]*)[\'"]',
            script,
        ):
            literals.append((lm.group(1), lm.group(0)))

        # ② 데이터셋 컬럼 참조: this.<datasetid>.getColumn(*, "<columnid>") == "리터럴"
        #    (datasetid 까지 일치해야 매칭 — 컬럼명만 같은 다른 데이터셋 오탐 방지)
        ds_col = binditems.get(cid)
        if ds_col and ds_col[0] and ds_col[1]:
            datasetid, columnid = ds_col
            pat_fwd = rf'this\.{re.escape(datasetid)}\.getColumn\([^()]*,\s*[\'"]{re.escape(columnid)}[\'"]\)\s*(?:==|!=)\s*[\'"]([^\'"]*)[\'"]'
            for lm in re.finditer(pat_fwd, script):
                literals.append((lm.group(1), lm.group(0)))
            pat_rev = rf'[\'"]([^\'"]*)[\'"]\s*(?:==|!=)\s*this\.{re.escape(datasetid)}\.getColumn\([^()]*,\s*[\'"]{re.escape(columnid)}[\'"]\)'
            for lm in re.finditer(pat_rev, script):
                literals.append((lm.group(1), lm.group(0)))
        else:
            ds_col = None

        if not literals:
            continue

        mismatches = [lit for lit in literals if lit[0].lower() not in allowed]
        if not mismatches:
            continue

        mismatch_values = sorted({lit[0] for lit in mismatches})
        match_count = len(literals) - len(mismatches)
        # 스크립트에서 발견된 비교 리터럴이 전부 하나의 다른 값으로 일관되면 high,
        # layout과 일치하는 참조와 안 하는 참조가 섞여 있으면 medium (수동 판단 필요)
        confidence = "high" if match_count == 0 and len(mismatch_values) == 1 else "medium"

        findings.append({
            "checkbox_id": cid,
            "layout_value": cb["value"],
            "layout_truevalue": cb["truevalue"],
            "layout_falsevalue": cb["falsevalue"],
            "binddataset": cb.get("binddataset"),
            "bind_column": ds_col[1] if ds_col else None,
            "script_mismatch_literals": mismatch_values,
            "total_script_refs": len(literals),
            "mismatched_refs": len(mismatches),
            "confidence": confidence,
            "examples": [snip for _, snip in literals[:5]],
        })

    return findings


def main():
    if len(sys.argv) < 2:
        print("사용법: python -m converter.nexacro.checkbox_value_scan <스캔 대상 폴더>")
        sys.exit(1)

    root = Path(sys.argv[1])
    if not root.exists():
        print(f"경로 없음: {root}")
        sys.exit(1)

    files = sorted(root.rglob("*.xfdl"))
    all_findings = []
    for f in files:
        for finding in scan_file(f):
            finding["file"] = str(f)
            all_findings.append(finding)

    high = [f for f in all_findings if f["confidence"] == "high"]
    medium = [f for f in all_findings if f["confidence"] == "medium"]

    output = {
        "_summary": {
            "scanned_files": len(files),
            "total_findings": len(all_findings),
            "high_confidence": len(high),
            "medium_confidence": len(medium),
        },
        "high_confidence": high,
        "medium_confidence": medium,
    }

    out_path = Path(__file__).parent / "patterns" / "checkbox_value_mismatch_report.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"스캔 완료: {len(files)}개 파일")
    print(f"발견: {len(all_findings)}건 (high: {len(high)}, medium: {len(medium)})")
    print(f"결과 저장: {out_path}")
    print("\n주의: 자동 수정 아님. truevalue/falsevalue는 실제 DB 저장값이라")
    print("파일별로 직접 확인 후 적용할 것. high 부터 보는 걸 추천.")


if __name__ == "__main__":
    main()

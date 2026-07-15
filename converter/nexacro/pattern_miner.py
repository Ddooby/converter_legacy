"""
pattern_miner.py
================
as-is(2차 변환본) vs to-be(수작업본) XFDL 쌍을 비교해
Script 영역 변경 패턴을 추출하고 mined_patterns.json 으로 저장한다.

사용법:
  python converter/nexacro/pattern_miner.py

결과:
  converter/nexacro/patterns/mined_patterns.json  — 검토용 후보 패턴
  (검토 후 converter/nexacro/patterns/nexacro_convert_patterns.json 에 수동 반영)
"""

import re
import json
import difflib
from pathlib import Path
from collections import defaultdict, Counter

AS_IS_DIR  = Path(__file__).parent / "as-is"
TO_BE_DIR  = Path(__file__).parent / "to-be"
OUTPUT_FILE = Path(__file__).parent / "patterns" / "mined_patterns.json"

SCRIPT_START = '<Script type="xscript5.1"><![CDATA['
SCRIPT_END   = "]]></Script>"

# ──────────────────────────────────────────
# 스크립트 추출
# ──────────────────────────────────────────

def extract_scripts(content: str) -> list[str]:
    """XFDL 에서 Script CDATA 블록만 추출"""
    scripts, remaining = [], content
    while SCRIPT_START in remaining:
        s = remaining.find(SCRIPT_START)
        e = remaining.find(SCRIPT_END, s)
        if e == -1:
            break
        scripts.append(remaining[s + len(SCRIPT_START): e])
        remaining = remaining[e + len(SCRIPT_END):]
    return scripts


# ──────────────────────────────────────────
# 라인 단위 diff
# ──────────────────────────────────────────

def diff_scripts(old_lines: list[str], new_lines: list[str]) -> list[tuple[str, str]]:
    """
    1:1 교체 라인 쌍 반환 (공백 무시 비교, 실제 값 보존)
    """
    pairs = []
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "replace":
            continue
        old_block = old_lines[i1:i2]
        new_block = new_lines[j1:j2]
        # 길이가 같을 때만 1:1 매칭
        if len(old_block) == len(new_block):
            for o, n in zip(old_block, new_block):
                o_s, n_s = o.strip(), n.strip()
                if o_s and n_s and o_s != n_s:
                    pairs.append((o_s, n_s))
        else:
            # 블록 크기 다른 경우 — 삽입/삭제 패턴으로 별도 기록
            pairs.append(("__BLOCK__:" + "\n".join(o.strip() for o in old_block),
                           "__BLOCK__:" + "\n".join(n.strip() for n in new_block)))
    return pairs


# ──────────────────────────────────────────
# 인라인 변경 추출 (partial change)
# ──────────────────────────────────────────

def find_inline_change(old: str, new: str) -> dict | None:
    """
    같은 라인에서 달라진 부분만 추출.
    ex) 'this.ds.getColumn(0, "a")' vs 'this.ds.getColumn(nRow, "a")'
        → from_frag='0', to_frag='nRow'
    반환: {"context_before": ..., "from": ..., "to": ..., "context_after": ...}
    """
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    ops = sm.get_opcodes()

    replace_ops = [op for op in ops if op[0] == "replace"]
    insert_ops  = [op for op in ops if op[0] == "insert"]
    delete_ops  = [op for op in ops if op[0] == "delete"]

    # 변경이 1군데인 simple replace
    if len(replace_ops) == 1 and not insert_ops and not delete_ops:
        _, i1, i2, j1, j2 = replace_ops[0]
        ctx_before = old[max(0, i1-30):i1]
        ctx_after  = old[i2:i2+30]
        return {
            "context_before": ctx_before,
            "from_frag": old[i1:i2],
            "to_frag":   new[j1:j2],
            "context_after": ctx_after,
            "example_from": old,
            "example_to":   new,
        }
    return None


# ──────────────────────────────────────────
# 패턴 클러스터링
# ──────────────────────────────────────────

def is_regex_like(s: str) -> bool:
    """변수처럼 보이면 True (공백 없고 camelCase 또는 숫자)"""
    return bool(re.match(r'^[\w.]+$', s))


def cluster_inline_changes(changes: list[dict]) -> list[dict]:
    """
    from_frag / to_frag 가 동일한 변경을 묶어 빈도순 정렬
    """
    counter: Counter = Counter()
    examples: dict = {}
    for ch in changes:
        key = (ch["from_frag"], ch["to_frag"])
        counter[key] += 1
        if key not in examples:
            examples[key] = ch

    result = []
    for (frm, to), cnt in counter.most_common():
        ch = examples[(frm, to)]
        result.append({
            "type": "inline_replace",
            "count": cnt,
            "from_frag": frm,
            "to_frag":   to,
            "context_before": ch["context_before"],
            "context_after":  ch["context_after"],
            "example_from": ch["example_from"],
            "example_to":   ch["example_to"],
        })
    return result


def cluster_line_changes(pairs: list[tuple[str, str]]) -> list[dict]:
    """
    완전 라인 교체 중 inline 분해 불가 케이스 집계
    """
    counter: Counter = Counter(pairs)
    result = []
    for (frm, to), cnt in counter.most_common():
        result.append({
            "type": "line_replace",
            "count": cnt,
            "from": frm,
            "to":   to,
        })
    return result


# ──────────────────────────────────────────
# 메인
# ──────────────────────────────────────────

def mine():
    as_is_files = list(AS_IS_DIR.rglob("*.xfdl"))
    if not as_is_files:
        print(f"⚠  as-is 폴더에 xfdl 파일이 없습니다: {AS_IS_DIR}")
        return

    inline_changes: list[dict] = []
    line_pairs:     list[tuple[str, str]] = []
    file_count = 0
    skipped = []

    for as_is_path in sorted(as_is_files):
        rel = as_is_path.relative_to(AS_IS_DIR)
        to_be_path = TO_BE_DIR / rel

        if not to_be_path.exists():
            skipped.append(str(rel))
            continue

        try:
            old_content = as_is_path.read_text(encoding="utf-8-sig", errors="replace")
            new_content = to_be_path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as e:
            print(f"  읽기 오류 {rel}: {e}")
            continue

        old_scripts = extract_scripts(old_content)
        new_scripts = extract_scripts(new_content)

        if not old_scripts or not new_scripts:
            continue

        file_count += 1
        for old_sc, new_sc in zip(old_scripts, new_scripts):
            old_lines = old_sc.split("\n")
            new_lines = new_sc.split("\n")
            pairs = diff_scripts(old_lines, new_lines)

            for old_s, new_s in pairs:
                if old_s.startswith("__BLOCK__:"):
                    # 블록 변경은 별도 집계
                    line_pairs.append((old_s, new_s))
                    continue

                inline = find_inline_change(old_s, new_s)
                if inline:
                    inline_changes.append(inline)
                else:
                    # inline 분해 불가 → 전체 라인 교체로
                    line_pairs.append((old_s, new_s))

    print(f"분석 완료: {file_count}개 파일 쌍, "
          f"inline 변경 {len(inline_changes)}건, "
          f"라인 교체 {len(line_pairs)}건")
    if skipped:
        print(f"to-be 없음 (스킵): {len(skipped)}개")

    # 클러스터링
    inline_clusters = cluster_inline_changes(inline_changes)
    line_clusters   = cluster_line_changes(line_pairs)

    # 임계값: 2개 이상 파일에서 반복된 패턴만 유력 후보
    THRESHOLD = 2
    candidate_inline = [c for c in inline_clusters if c["count"] >= THRESHOLD]
    candidate_line   = [c for c in line_clusters   if c["count"] >= THRESHOLD]
    rare_inline      = [c for c in inline_clusters if c["count"] <  THRESHOLD]
    rare_line        = [c for c in line_clusters   if c["count"] <  THRESHOLD]

    output = {
        "_summary": {
            "file_pairs": file_count,
            "inline_total": len(inline_changes),
            "line_total": len(line_pairs),
            "candidate_inline": len(candidate_inline),
            "candidate_line":   len(candidate_line),
            "rare_inline": len(rare_inline),
            "rare_line":   len(rare_line),
        },
        "candidates": {
            "inline_replace": candidate_inline,
            "line_replace":   candidate_line,
        },
        "rare": {
            "inline_replace": rare_inline[:50],   # 상위 50개만
            "line_replace":   rare_line[:50],
        },
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n결과 저장: {OUTPUT_FILE}")
    print(f"  유력 후보 — inline: {len(candidate_inline)}개, 라인: {len(candidate_line)}개")
    print(f"  희귀 변경 — inline: {len(rare_inline)}개, 라인: {len(rare_line)}개")
    print("\n다음 단계:")
    print("  1. patterns/mined_patterns.json 검토")
    print("  2. 적용할 패턴을 converter/nexacro/patterns/nexacro_convert_patterns.json 에 추가")
    print("  3. python nexacroMain.py 실행")


if __name__ == "__main__":
    mine()

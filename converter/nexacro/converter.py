"""
Nexacro XFDL Converter
1차 AI변환 XFDL → 정제본 XFDL 자동 변환기
"""

import re
import json
import logging
import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

PATTERNS_FILE = Path(__file__).parent / "patterns" / "nexacro_convert_patterns.json"

SCRIPT_START = '<Script type="xscript5.1"><![CDATA['
SCRIPT_END = "]]></Script>"

_ARITH_OP_RE = re.compile(r'[+\-*/]')
_ROUND_PAT_RE = re.compile(r'nexacro\.round\(')
_GETCOL_RE = re.compile(r'\.getColumn\(')
_OP_TO_METHOD = {'+': 'add', '-': 'sub', '*': 'mul', '/': 'div'}

_FINANCIAL_KW = {'amt', 'amount', 'rate', 'vat', 'cost', 'fee'}
_CAMEL_SPLIT_RE = re.compile(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[A-Z]|\d+')

_MANUAL_CONVERT_ROW_RE = re.compile(
    r'\*(\s*)2025\.09\.DD(\s+)수동변환자(\s+)수동변환(?!\()'
)


class XfdlConverter:
    def __init__(self, patterns_file: Path = PATTERNS_FILE):
        with open(patterns_file, encoding="utf-8") as f:
            self.p = json.load(f)

    # ──────────────────────────────────────────
    # Public
    # ──────────────────────────────────────────

    def convert_file(self, input_path: Path, output_path: Path) -> None:
        # newline="" : 원본 줄바꿈(CRLF/LF) 그대로 보존 — read_text/write_text 기본값은
        # universal newline 변환을 적용해 CRLF 원본이 LF로 깨지는 문제가 있었음
        with open(input_path, encoding="utf-8-sig", newline="") as f:  # BOM 자동 제거
            content = f.read()
        result = self.convert(content, form_name=input_path.stem)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            f.write(result)
        logger.info("변환 완료: %s", output_path)

    def convert(self, content: str, form_name: str = "") -> str:
        if SCRIPT_START not in content:
            return self._convert_layout(content)

        script_count = content.count(SCRIPT_START)
        if script_count > 1:
            logger.warning("Script 블록 %d개 감지 — 모두 변환합니다: %s", script_count, form_name)

        result = []
        remaining = content
        first = True

        while SCRIPT_START in remaining:
            idx_start = remaining.find(SCRIPT_START)
            idx_end = remaining.find(SCRIPT_END, idx_start)

            if idx_end == -1:
                logger.warning("Script 닫힘 태그 없음 — 나머지는 layout으로 처리: %s", form_name)
                result.append(self._convert_layout(remaining))
                remaining = ""
                break

            layout = remaining[:idx_start]
            script = remaining[idx_start + len(SCRIPT_START): idx_end]
            remaining = remaining[idx_end + len(SCRIPT_END):]

            result.append(self._convert_layout(layout))
            result.append(SCRIPT_START)
            result.append(self._convert_script(script, form_name=form_name if first else ""))
            result.append(SCRIPT_END)
            first = False

        result.append(self._convert_layout(remaining))
        return "".join(result)

    # ──────────────────────────────────────────
    # Layout section
    # ──────────────────────────────────────────

    def _convert_layout(self, content: str) -> str:
        # Grid 태그에 takegrid / countcomp 기본 속성 추가 (이미 있으면 스킵)
        def _grid_default_attrs(m: re.Match) -> str:
            tag = m.group(0)
            pos = tag.rindex(">")
            prefix, suffix = tag[:pos], tag[pos:]
            extra = ""
            if "takegrid=" not in tag:
                extra += ' takegrid="sort,rowcount"'
            if "countcomp=" not in tag:
                extra += ' countcomp=""'
            return prefix + extra + suffix
        content = re.sub(r"<Grid\b[^>]*>", _grid_default_attrs, content)
        content = self._fix_radio_cssclass_border(content)
        content = self._fix_calendar_autoselect(content)
        lines = content.split("\n")
        result = []
        in_body_band = False
        for ln in lines:
            if '<Band id="body"' in ln:
                in_body_band = True
            elif "</Band>" in ln:
                in_body_band = False
            if "<Cell" in ln:
                ln = self._convert_cell_line(ln, in_body_band)
            result.append(ln)
        return "\n".join(result)

    def _fix_radio_cssclass_border(self, content: str) -> str:
        """<Radio> 태그 cssclass 에 rdo_border 클래스 추가.
        cssclass 가 없으면 새로 추가, 있으면 기존값 뒤에 병합(중복이면 건드리지 않음)"""
        def _add_border(m: re.Match) -> str:
            tag = m.group(0)
            existing = self._extract_attr(tag, "cssclass")
            if existing is None:
                new_val = "rdo_border"
            else:
                classes = [c.strip() for c in existing.split(",") if c.strip()]
                if "rdo_border" in classes:
                    return tag
                new_val = existing + ", rdo_border"
            return self._set_attr(tag, "cssclass", new_val)
        return re.sub(r"<Radio\b[^>]*>", _add_border, content)

    def _fix_calendar_autoselect(self, content: str) -> str:
        """<Calendar> 태그 autoselect 를 true 로 강제.
        속성이 없으면 추가, false 로 되어있으면 true 로 교체, 이미 true 면 그대로"""
        def _set_true(m: re.Match) -> str:
            tag = m.group(0)
            existing = self._extract_attr(tag, "autoselect")
            if existing == "true":
                return tag
            return self._set_attr(tag, "autoselect", "true")
        return re.sub(r"<Calendar\b[^>]*>", _set_true, content)

    def _convert_cell_line(self, line: str, in_body_band: bool = False) -> str:
        cell_p = self.p["layout_cell_patterns"]

        for r in cell_p["expr_replacements"]:
            line = line.replace(r["from"], r["to"])

        for r in cell_p["aichanger_marker_removals"]:
            line = line.replace(r["from"], r["to"])

        line = self._convert_cell_cssclass(line, cell_p)

        if in_body_band:
            line = self._convert_cell_date_format(line)

        return line

    def _convert_cell_date_format(self, line: str) -> str:
        """body 밴드 내 displaytype="date" 셀에 calendardateformat="yyyy-MM-dd" 추가"""
        if 'displaytype="date"' in line and "calendardateformat=" not in line:
            line = line.replace('displaytype="date"', 'displaytype="date" calendardateformat="yyyy-MM-dd"')
        return line

    def _convert_cell_cssclass(self, line: str, cell_p: dict) -> str:
        rules = cell_p["property_to_cssclass"]
        color_repls = {r["from"]: r["to"] for r in rules["color_value_replacements"]}

        for rule in rules["rules"]:
            prop = rule["property"]
            action = rule["action"]

            if prop == "background":
                if action == "rename_to_cssclass" and f' {prop}=' in line and 'cssclass=' not in line:
                    line = line.replace(f' {prop}=', ' cssclass=')

                elif action == "replace_cssclass_with_value":
                    if f' {prop}=' in line and 'cssclass=' in line and 'expr:' not in line:
                        bac_val = self._extract_attr(line, prop)
                        if bac_val:
                            line = self._remove_attr(line, prop)
                            line = self._set_attr(line, "cssclass", bac_val)

                elif action == "append_to_cssclass_expr":
                    if f' {prop}=' in line and 'cssclass=' in line and 'expr:' in line:
                        bac_val = self._extract_attr(line, prop)
                        if bac_val:
                            css_val = self._extract_attr(line, "cssclass")
                            bac_clean = bac_val.replace("expr:", "")
                            new_css = f'{css_val}+&quot;,&quot;+{bac_clean}'
                            line = self._remove_attr(line, prop)
                            line = self._set_attr(line, "cssclass", new_css)

            elif prop == "color" and f' color=' in line:
                color_val = self._extract_attr(line, "color")
                if color_val:
                    color_mapped = color_repls.get(color_val, color_val)
                    line = self._remove_attr(line, "color")
                    if color_mapped:
                        if 'cssclass=' in line:
                            css_val = self._extract_attr(line, "cssclass")
                            if css_val:
                                line = self._set_attr(line, "cssclass", f'{css_val}+&quot;,&quot;+&quot;{color_mapped}&quot;')
                        else:
                            line = line.replace("/>", f' cssclass="{color_mapped}"/>')

        return line

    # ──────────────────────────────────────────
    # Script section
    # ──────────────────────────────────────────

    def _convert_script(self, content: str, form_name: str = "") -> str:
        """
        변환 순서:
        1. fnAuthButtonControl 전용 패턴 (경고 주석 포함 상태에서 매칭)
        2. 경고 주석 제거 (범용)
        3. AIChanger 마커 (script 내)
        4. UXB INFO getBindDataset
        5. SVC_LOC URL 변환 (com.pageCtx + Servlet → camelCase path)
        6. Dataset getColumn 컬럼명 camelCase 변환
        7. this. 누락 보정 — 함수(isCheck/isDate/isExistCbMapping/inquiryCallback 등) 선언/호출부,
           폼레벨 플래그 변수(isAdmin/isCam) 선언/참조부
        8. take.nvl() 누락 보정 — wrapQuote/MultiSearch 결과/cntr_no/check_item getColumn/getTrim
        9. '이중정렬방식처리관련 로직' 깨진 주석 블록(// 로만 열려 SyntaxError 나는 케이스) 복구
        10. com.isEmpty(this, X) → com.isEmpty(X) (pThis 잔재 인자 제거, DetailForm 계열)
        11. 부모(List) 폼 전달 파라미터(approvalMode/cntrNo/cpDtRsn/isAdministrator/isCamGrp/reasonFlag/view)
            this.parent.X 로 승격 (DetailForm 계열)
        12. G_OzTimerID/G_OzTimeout 참조 이원화 (e.timerid== 비교는 com., setTimer()는 common_oz.)
        13. AllWindows/DivMain MDI 창 순회 리프레시 패턴 → this.opener.parent.parent.fnSearch() 대체
        14. this["A"] / this["A.B"] 브래킷 표기 → 점 표기 (.form. 하위폼 접근 컨벤션 포함)
        15. OZ리포트 += 조립 시 com.G_OzDel 앞 값 take.nvl 래핑
        16. 텍스트 치환 (com.isEmpty(pThis, 먼저, pThis→this 마지막)
        17. 소스 수정 이력 플레이스홀더 → 오늘 날짜 + 정철환 + 수동변환(1차)
        18. 세미콜론 앞 중복 공백 정리
        19. 외부 JS 참조 주입 (sa.* / so.* / ins.* 호출 감지 → take.loadJs)
        20. async/await 변환 — com.* 호출 함수 전체 래핑
        """
        content = self._fix_fnauth_button_control(content)
        content = self._apply_warning_removals(content)
        content = self._apply_aichanger_markers(content)
        content = self._apply_uxb_info(content)
        content = self._convert_svc_url(content)
        content = self._convert_dataset_get_column(content)
        content = self._fix_is_null_trim_check(content)
        content = self._fix_export_excel_grid(content)
        content = self._fix_missing_this_on_functions(content)
        content = self._fix_missing_this_on_known_flags(content)
        content = self._fix_wrap_quote_nvl(content)
        content = self._fix_multisearch_result_nvl(content)
        content = self._fix_cntrno_getcolumn_nvl(content)
        content = self._fix_checkitem_getcolumn_nvl(content)
        content = self._fix_gettrim_cbmapping_nvl(content)
        content = self._fix_double_sort_comment_block(content)
        content = self._fix_isempty_remove_this_arg(content)
        content = self._fix_missing_parent_on_known_params(content)
        content = self._fix_oztimer_refs(content)
        content = self._fix_mdi_allwindows_refresh(content)
        content = self._fix_this_bracket_notation(content)
        content = self._wrap_ozdel_concat_nvl(content)
        content = self._convert_arithmetic_to_decimal(content)
        content = self._apply_text_replacements(content)
        content = self._stamp_manual_convert_date(content)
        content = self._fix_semicolon_spacing(content)
        content = self._convert_fn_message_domain(content)
        if form_name:
            content = self._replace_system_form_name(content, form_name)
        content = self._comment_out_auth_button_callers(content)
        content = self._inject_external_js_refs(content)
        content = self._apply_async_patterns(content)
        return content

    def _replace_system_form_name(self, content: str, form_name: str) -> str:
        """JSDoc 헤더의 'SYSTEM FORM NAME' 플레이스홀더 → xfdl 파일명(확장자 제외)으로 치환"""
        return content.replace("SYSTEM FORM NAME", form_name)

    def _apply_warning_removals(self, content: str) -> str:
        for r in self.p["script_warning_removals"]:
            if r.get("is_regex"):
                flags = re.DOTALL if r.get("flags") == "DOTALL" else 0
                content = re.sub(r["from_pattern"], r["to"], content, flags=flags)
            else:
                content = content.replace(r["from"], r["to"])
        return content

    def _apply_aichanger_markers(self, content: str) -> str:
        for r in self.p["script_aichanger_markers"]["items"]:
            content = content.replace(r["from"], r["to"])
        return content

    def _apply_uxb_info(self, content: str) -> str:
        r = self.p["script_uxb_info"]["get_bind_dataset"]
        return re.sub(r["from_pattern"], r["to"], content)

    def _convert_svc_url(self, content: str) -> str:
        """
        "SVC_LOC::" + com.pageCtx + "/XxxServlet" 패턴을 찾아
        직전에 나온 functionGubun 값을 기반으로 REST URL로 변환.
        예) SalesOpportunityListServlet + functionGubun=ONLOAD_LIST
            → "SVC_LOC::salesOpportunityList/ONLOAD_LIST.do"
        """
        url_pat = re.compile(
            r'"SVC_LOC::"\s*\+\s*com\.pageCtx\s*\+\s*"/([\w]+Servlet)"'
        )
        result = []
        last_end = 0
        for m in url_pat.finditer(content):
            result.append(content[last_end:m.start()])
            servlet_name = m.group(1)
            preceding = content[:m.start()]
            gubun_pat = re.compile(r'functionGubun\s*=\s*[\'"]?([A-Za-z0-9_]+)[\'"]?')
            gubun_matches = list(gubun_pat.finditer(preceding))
            if not gubun_matches:
                # functionGubun이 URL 뒤(같은 transaction 호출 내)에 있는 경우도 탐색
                line_end = content.find(";", m.end())
                following = content[m.end(): line_end if line_end != -1 else m.end() + 200]
                gubun_matches = list(gubun_pat.finditer(following))
            if gubun_matches:
                func_gubun = gubun_matches[-1].group(1)
                path = servlet_name[:-7] if servlet_name.endswith("Servlet") else servlet_name
                path = path[0].lower() + path[1:]
                result.append(f'"SVC_LOC::{path}/{func_gubun}.do"')
            else:
                result.append(m.group(0))
            last_end = m.end()
        result.append(content[last_end:])
        return "".join(result)

    def _snake_to_camel(self, name: str) -> str:
        parts = name.split("_")
        return parts[0] + "".join(p.capitalize() for p in parts[1:])

    # snake_case → camelCase 일반 규칙이 맞지 않는 컬럼명 예외 매핑
    _COL_NAME_OVERRIDES = {
        "user_name": "userNm",
        "userName": "userNm",   # 이전 변환에서 잘못 생성된 케이스 대비
    }

    def _col_to_camel(self, col: str) -> str:
        """컬럼명 변환: 예외 매핑 우선, 없으면 snake_case → camelCase"""
        return self._COL_NAME_OVERRIDES.get(col, self._snake_to_camel(col))

    def _convert_dataset_get_column(self, content: str) -> str:
        """getColumn 컬럼명 snake_case → camelCase 변환 (단/쌍따옴표 모두 처리, 쌍따옴표로 통일)"""
        # gdsCCDUserMDS → gdsUserInfo 이름 변환 (row index 있으면 유지, 없으면 0 기본값)
        def _replace_ccd(m: re.Match) -> str:
            row_idx = m.group(1)  # row index (없으면 None)
            col_name = self._col_to_camel(m.group(2))
            idx = row_idx.strip() if row_idx else "0"
            return f'gdsUserInfo.getColumn({idx}, "{col_name}")'

        content = re.sub(
            r"gdsCCDUserMDS\.getColumn\((?:([^,)]+),\s*)?['\"]([^'\"]+)['\"]\)",
            _replace_ccd,
            content,
        )
        # gdsUserInfo.getColumn([rowIdx,] 'col'/"col") → camelCase, row index 없으면 0 삽입
        def _replace_gds(m: re.Match) -> str:
            prefix = m.group(1)   # "gdsUserInfo.getColumn(" 또는 "gdsUserInfo.getColumn(0, " 등
            col_name = self._col_to_camel(m.group(2))
            suffix = m.group(3)
            if prefix.rstrip().endswith("("):
                return f'{prefix}0, "{col_name}"{suffix}'
            return f'{prefix}"{col_name}"{suffix}'

        content = re.sub(
            r"(gdsUserInfo\.getColumn\([^)]*)['\"]([^'\"]+)[\'\"](\s*\))",
            _replace_gds,
            content,
        )
        return content

    def _inject_external_js_refs(self, content: str) -> str:
        """
        스크립트 내 sa.* / so.* / ins.* 호출을 감지해
        //공통 라이브러리 호출 주석 바로 아래에 take.loadJs 라인을 삽입한다.
        이미 take.loadJs가 있으면 중복 삽입하지 않는다.
        """
        ANCHOR = "//공통 라이브러리 호출"
        JS_MAP = {
            "sa": '/biz/commonJs/sa.js',
            "so": '/biz/commonJs/so.js',
            "ins": '/biz/commonJs/ins.js',
        }

        anchor_pos = content.find(ANCHOR)
        if anchor_pos == -1:
            return content

        needed: list[str] = []
        for prefix, js_path in JS_MAP.items():
            load_line = f'take.loadJs(this, "{prefix}JsLoad_" + this.name, "{js_path}");'
            if load_line in content:
                continue
            if re.search(rf'\b{prefix}\.', content):
                needed.append(load_line)

        if not needed:
            return content

        insert_after = anchor_pos + len(ANCHOR)
        inject = "\n" + "\n".join(needed)
        return content[:insert_after] + inject + content[insert_after:]
    def _convert_fn_message_domain(self, content: str) -> str:
        """따옴표 없이 나오는 Domain.msg~ → "Domain.msg~" 로 감싸기"""
        return re.sub(r"(?<!['\"])(Domain\.msg[\w.]+)(?!['\"])", r'"\1"', content)

    def _apply_text_replacements(self, content: str) -> str:
        for r in self.p["script_text_replacements"]:
            if r.get("is_regex"):
                flags = re.DOTALL if r.get("flags") == "DOTALL" else 0
                content = re.sub(r["from_pattern"], r["to"], content, flags=flags)
            else:
                content = content.replace(r["from"], r["to"])
        return content


    def _fix_is_null_trim_check(self, content: str) -> str:
        """com.isNullTrimCheck / com.isNullFieldGrid 첫 인자 this 추가
        이미 첫 인자가 this 인 경우는 건드리지 않음"""
        for fn in ("isNullTrimCheck", "isNullFieldGrid", "commAllCodeInquiry"):
            content = re.sub(
                r'com\.' + fn + r'\((this\.[^\s,)]+)',
                r'com.' + fn + r'(this, \1',
                content,
            )
        return content

    def _fix_export_excel_grid(self, content: str) -> str:
        """ExportExcelGrid("Sheet1", "A1", false, true, true)
        → ExportExcelGrid(this.titletext + "_" + com.somToday(this), "Sheet1")"""
        return re.sub(
            r'\.ExportExcelGrid\("[^"]+",\s*"[aA][0-9]+",\s*false,\s*true,\s*true\)',
            r'.ExportExcelGrid(this.titletext + "_" + com.somToday(this), "Sheet1")',
            content,
        )

    def _fix_wrap_quote_nvl(self, content: str) -> str:
        """nexacro.wrapQuote(this.xxx.value) → nexacro.wrapQuote(take.nvl(this.xxx.value))
        nexacro.wrapQuote(this.xxx.getColumn(...)) 처럼 getColumn 호출이 인자인 경우도 포함.
        이미 take.nvl 로 감싼 경우 건드리지 않음"""
        content = re.sub(
            r'nexacro\.wrapQuote\((?!take\.nvl)(this\.[a-zA-Z_][a-zA-Z0-9_.]*\.getColumn\([^()]*\))\)',
            r'nexacro.wrapQuote(take.nvl(\1))',
            content,
        )
        content = re.sub(
            r'nexacro\.wrapQuote\((?!take\.nvl)(this\.[a-zA-Z_][a-zA-Z0-9_.]*)\)',
            r'nexacro.wrapQuote(take.nvl(\1))',
            content,
        )
        return content

    # ──────────────────────────────────────────
    # this. 누락 / take.nvl() 누락 보정
    # (ContractListCGR/CGO/FFASubForm 수동변환본 패턴 기반 — Contract List 계열 반복 화면 대상)
    # ──────────────────────────────────────────

    _FUNC_DECL_ANY_RE = re.compile(r'(?:this\.)?([A-Za-z_]\w*)\s*=\s*function\s*\(')
    # Dataset/컴포넌트의 CanColumnChange, CanChange 이벤트 — 리턴값을 Nexacro가
    # 동기적으로 평가해 변경을 취소/허용하므로 async 래핑 대상에서 제외해야 함
    _SYNC_EVENT_HANDLER_RE = re.compile(r'_Can(?:ColumnChange|Change)$')
    _KNOWN_FORM_FLAGS = (
        "isAdmin", "isCam",
        "index_link", "isHdgDSChgChk", "isExit", "isModify", "isUpdate",
    )
    _MULTISEARCH_NVL_RE = re.compile(
        r'\.set_value\((?!take\.nvl)((?:this\.)?\w*MultiSearchDS\.getColumn\([^()]*\))\)'
    )
    _CNTRNO_GETCOL_NVL_RE = re.compile(
        r'(?<!take\.nvl\()(?<![\w.])((?:this\.)?[\w.]*\bgetColumn\([^()]*"cntr_no"[^()]*\))'
    )
    _CHECKITEM_GETCOL_NVL_RE = re.compile(
        r'(?<!take\.nvl\()(?<![\w.])((?:this\.)?[\w.]*\bgetColumn\([^()]*"check_item"[^()]*\))'
    )
    _GETTRIM_CBMAPPING_NVL_RE = re.compile(
        r'take\.getTrim\((?!take\.nvl\()(this\.cbMappingCntrNo)\)'
    )
    _DOUBLE_SORT_COMMENT_RE = re.compile(
        r'//이중정렬방식처리관련 로직\r?\n'
        r'(?:[^\r\n]*\r?\n){0,4}?'
        r'[^\r\n]*마이플랫폼지원문서 참고a?[^\r\n]*\r?\n?'
    )
    _DOUBLE_SORT_COMMENT_FIX = (
        "/*\n"
        " * 이중정렬방식처리관련 로직\n"
        " *        prarm_grid : 정렬할 Grid ID명\n"
        " *\n"
        " *    Author : Ssong(20090428) _ 마이플랫폼지원문서 참고\n"
        " */\n"
    )

    def _fix_missing_this_on_functions(self, content: str) -> str:
        """this.NAME = function(...) 형태로 선언/호출돼야 할 함수가
        NAME = function(...) / NAME(...) 처럼 this. 없이 쓰인 경우 (AIChanger 자동변환
        시 흔한 this. 누락 패턴) this. 를 선언부/호출부 모두에 일괄로 붙여준다.
        예: isCheck, isDate, isExistCbMapping, inquiryCallback 등
        주석 처리된 라인(//, /*, *) 은 건드리지 않음"""
        names = set(self._FUNC_DECL_ANY_RE.findall(content))
        if not names:
            return content
        decl_pats = [(n, re.compile(r'(?<![.\w])' + re.escape(n) + r'(\s*=\s*function\s*\()')) for n in names]
        call_pats = [(n, re.compile(r'(?<![.\w])' + re.escape(n) + r'(\s*\()')) for n in names]
        lines = content.split('\n')
        for idx, line in enumerate(lines):
            if line.lstrip().startswith(('//', '/*', '*')):
                continue
            for n, pat in decl_pats:
                line = pat.sub(lambda m, nn=n: f'this.{nn}{m.group(1)}', line)
            for n, pat in call_pats:
                line = pat.sub(lambda m, nn=n: f'this.{nn}{m.group(1)}', line)
            lines[idx] = line
        return '\n'.join(lines)

    def _fix_missing_this_on_known_flags(self, content: str) -> str:
        """isAdmin / isCam 처럼 폼레벨 플래그 변수가 this. 없이 선언/참조되는 경우
        this. 를 붙여준다. (Contract List 계열 화면에서 반복되는 패턴)
        주석 처리된 라인(//, /*, *) 은 건드리지 않음"""
        pats = [(n, re.compile(r'(?<![.\w])' + n + r'\b')) for n in self._KNOWN_FORM_FLAGS]
        lines = content.split('\n')
        for idx, line in enumerate(lines):
            if line.lstrip().startswith(('//', '/*', '*')):
                continue
            for n, pat in pats:
                line = pat.sub(f'this.{n}', line)
            lines[idx] = line
        return '\n'.join(lines)

    def _fix_multisearch_result_nvl(self, content: str) -> str:
        """MultiSearch 팝업 결과 set_value(...MultiSearchDS.getColumn(0, "codename"/"codeName"))
        에 take.nvl 누락된 경우 감싸기"""
        return self._MULTISEARCH_NVL_RE.sub(r'.set_value(take.nvl(\1))', content)

    def _fix_cntrno_getcolumn_nvl(self, content: str) -> str:
        """....getColumn(..., "cntr_no") 형태 호출 전체(변수 대입/함수 인자/setColumn 3번째 인자 등
        위치 불문)에서 take.nvl 누락된 경우 감싸기"""
        return self._CNTRNO_GETCOL_NVL_RE.sub(r'take.nvl(\1)', content)

    def _fix_checkitem_getcolumn_nvl(self, content: str) -> str:
        """....getColumn(..., "check_item") 형태 호출에서 take.nvl 누락된 경우 감싸기"""
        return self._CHECKITEM_GETCOL_NVL_RE.sub(r'take.nvl(\1)', content)

    def _fix_gettrim_cbmapping_nvl(self, content: str) -> str:
        """take.getTrim(this.cbMappingCntrNo) 에 take.nvl 누락된 경우 감싸기"""
        return self._GETTRIM_CBMAPPING_NVL_RE.sub(r'take.getTrim(take.nvl(\1))', content)

    def _fix_double_sort_comment_block(self, content: str) -> str:
        """'이중정렬방식처리관련 로직' 주석이 // 로만 시작되고 /* 로 안 닫혀서
        다음 줄들(* prarm_grid...)이 그대로 구문으로 파싱되어 SyntaxError 가 나는 케이스를
        정상적인 블록주석(/* ... */)으로 복구한다."""
        return self._DOUBLE_SORT_COMMENT_RE.sub(self._DOUBLE_SORT_COMMENT_FIX, content)

    # ──────────────────────────────────────────
    # DetailForm 계열 전용 보정
    # (ContractCGO/CGR/FFADetailForm 수동변환본 패턴 기반 — Contract Detail 계열 반복 화면 대상)
    # ──────────────────────────────────────────

    def _fix_isempty_remove_this_arg(self, content: str) -> str:
        """com.isEmpty(this, X) → com.isEmpty(X)
        MiPlatform pThis 인자 전달 관례의 잔재. 실제 com.js 의 com.isEmpty(pValue, pPath) 시그니처와
        맞지 않으므로(pPath 는 MaskEdit 하위경로 전용 파라미터) 무조건 제거해야 함.
        기존 script_text_replacements 의 pThis 제거 규칙은 AS-IS 소스가 이미
        "com.isEmpty(this, ..." 형태로 넘어오는 경우(AIChanger가 pThis→this 를 먼저 치환해버린 케이스)를
        못 잡아서 별도로 추가."""
        return re.sub(r'com\.isEmpty\(this,\s*', 'com.isEmpty(', content)

    _KNOWN_PARENT_PARAMS = ("approvalMode", "cntrNo", "cpDtRsn", "isAdministrator", "isCamGrp", "reasonFlag", "view")
    _KNOWN_PARENT_PARAMS_BARE_ONLY = ("isAdministrator", "isCamGrp")

    def _fix_missing_parent_on_known_params(self, content: str) -> str:
        """DetailForm 은 List(부모) 폼에서 열릴 때 approvalMode/cntrNo/cpDtRsn/isAdministrator/
        isCamGrp/reasonFlag/view 값을 전달받는다. this.X 또는 bare X 로 남아있으면 this.parent.X 로 승격.
        (param 은 지역변수로 훨씬 많이 쓰여서 목록에서 제외 — 무조건 승격 시 로직 파괴 위험)
        isModify 는 함수별로 '부모 최초값 읽기' 와 '폼 자체 dirty-flag' 두 가지 의미로 혼용되므로
        이 메소드에서 다루지 않음 — 화면별 컨텍스트 확인 후 수동 처리 권장.
        주석 처리된 라인(//, /*, *) 은 건드리지 않음"""
        this_pats = [(n, re.compile(r'this\.' + n + r'\b(?!\.)(?!\s*=\s*"")')) for n in self._KNOWN_PARENT_PARAMS]
        bare_pats = [(n, re.compile(r'(?<![.\w])' + n + r'\b')) for n in self._KNOWN_PARENT_PARAMS_BARE_ONLY]
        lines = content.split('\n')
        for idx, line in enumerate(lines):
            if line.lstrip().startswith(('//', '/*', '*')):
                continue
            for n, pat in this_pats:
                line = pat.sub(f'this.parent.{n}', line)
            for n, pat in bare_pats:
                line = pat.sub(f'this.parent.{n}', line)
            lines[idx] = line
        return '\n'.join(lines)

    def _fix_oztimer_refs(self, content: str) -> str:
        """G_OzTimerID/G_OzTimeout 참조 문맥별 이원화:
        - e.timerid== 비교 → com.G_OzTimerID
        - this.setTimer(...) 호출 인자 → common_oz.G_OzTimerID / common_oz.G_OzTimeout
        (com/common_oz 두 네임스페이스 모두 동일 값을 갖고 있으나, 참고 화면들의 수동변환 관례를 따름)"""
        content = content.replace('e.timerid==this.G_OzTimerID', 'e.timerid==com.G_OzTimerID')
        content = re.sub(
            r'this\.setTimer\(this\.G_OzTimerID,\s*this\.G_OzTimeout\)',
            'this.setTimer(common_oz.G_OzTimerID,common_oz.G_OzTimeout)',
            content,
        )
        return content

    _MDI_REFRESH_ANCHOR = 'var winCnt = this.AllWindows.com.length;'

    def _fix_mdi_allwindows_refresh(self, content: str) -> str:
        """AllWindows 전체 창 순회로 List Form 을 찾아 fnInquiry() 를 호출해 새로고침하는
        MiPlatform MDI 패턴은 Nexacro 에 대응 개념이 없음. 참고 3개 DetailForm 모두
        this.opener.parent.parent.fnSearch() 로 대체하고 기존 로직은 주석처리하는 동일한 패턴이었으므로
        그대로 자동화. cbListFormID 값 등 세부는 화면마다 달라도 무방(주석처리만 되면 됨)."""
        result = []
        pos = 0
        while True:
            anchor_idx = content.find(self._MDI_REFRESH_ANCHOR, pos)
            if anchor_idx == -1:
                result.append(content[pos:])
                break
            line_start = content.rfind('\n', 0, anchor_idx) + 1
            # 이미 주석처리되어 처리된 블록이면(idempotent) 건드리지 않고 다음 탐색으로
            if content[line_start:anchor_idx].lstrip().startswith('//'):
                result.append(content[pos:anchor_idx + len(self._MDI_REFRESH_ANCHOR)])
                pos = anchor_idx + len(self._MDI_REFRESH_ANCHOR)
                continue
            for_open = content.find('{', anchor_idx)
            close = self._find_matching_brace(content, for_open) if for_open != -1 else -1
            if for_open == -1 or close == -1:
                # 예상 구조와 다르면 건드리지 않고 다음 탐색 지점으로
                result.append(content[pos:anchor_idx + len(self._MDI_REFRESH_ANCHOR)])
                pos = anchor_idx + len(self._MDI_REFRESH_ANCHOR)
                continue
            block_end = content.find('\n', close)
            block_end = block_end + 1 if block_end != -1 else close + 1

            result.append(content[pos:line_start])
            block = content[line_start:block_end]
            commented = '\n'.join(
                (ln if not ln.strip() else '//' + ln) for ln in block.split('\n')
            )
            replacement = (
                '\tif (!com.isEmpty(this.opener.parent.parent)) {\n'
                '\t\tthis.opener.parent.parent.fnSearch();\n'
                '\t}\n'
            )
            result.append(replacement + commented)
            pos = block_end
        return ''.join(result)

    _THIS_BRACKET_RE = re.compile(r'this\["(\w+)(?:\.(\w+))?"\]')

    def _fix_this_bracket_notation(self, content: str) -> str:
        """this["SCTCgoPositionDS"] → this.SCTCgoPositionDS (단순 프로퍼티)
        this["dv_sctOrgCpInfo.CCDAttachFileInfoDS"] → this.dv_sctOrgCpInfo.form.CCDAttachFileInfoDS
        (하위 폼에 바인딩된 데이터셋은 .form. 을 끼워 넣어야 함 — Nexacro 하위폼 접근 컨벤션)"""
        def _repl(m: re.Match) -> str:
            outer, inner = m.group(1), m.group(2)
            if inner:
                return f'this.{outer}.form.{inner}'
            return f'this.{outer}'
        return self._THIS_BRACKET_RE.sub(_repl, content)

    def _fix_semicolon_spacing(self, content: str) -> str:
        """'strDS_1 += "" + com.G_OzDel  ;' 처럼 세미콜론 앞에 공백 2개 이상 남는 경우 정리.
        AIChanger가 더 긴 표현식을 짧은 값으로 치환하면서 남긴 흔적."""
        return re.sub(r' {2,};', ';', content)

    _OZDEL_NVL_RE = re.compile(
        r'(?<!take\.nvl\()(this\.[\w.]+\.(?:value|text)|this\.[\w.]+\.getColumn\([^()]*\))(\s*\+\s*com\.G_OzDel)'
    )

    def _wrap_ozdel_concat_nvl(self, content: str) -> str:
        """OZ리포트 += 문자열 조립: com.G_OzDel 앞의 this.xxx.value/.text/.getColumn(...)을
        take.nvl(...)로 감싸 null 이 그대로 이어붙는 것을 방지.
        이미 take.nvl 로 감싼 경우는 건드리지 않음"""
        return self._OZDEL_NVL_RE.sub(r'take.nvl(\1)\2', content)

    def _stamp_manual_convert_date(self, content: str) -> str:
        """소스 수정 이력의 '2025.09.DD 수동변환자 수동변환' 플레이스홀더를
        실행 시점의 오늘 날짜 + 정철환 + 수동변환(1차) 로 치환.
        (JSON 정적 패턴이 아니라 실행 코드로 처리 — 날짜는 매 실행마다 달라져야 하므로)"""
        today = datetime.date.today().strftime('%Y.%m.%d')

        def _repl(m: re.Match) -> str:
            return f'*{m.group(1)}{today}{m.group(2)}정철환{m.group(3)}수동변환(1차)'

        return _MANUAL_CONVERT_ROW_RE.sub(_repl, content)


    def _comment_out_auth_button_callers(self, content: str) -> str:
        """
        com.fnAuthButtonControl()을 내부에서 호출하는 함수명을 찾아
        그 함수를 호출하는 라인을 // 주석처리
        예) this.cntrCvc_authButtonControl = function(){...com.fnAuthButtonControl...}
            → this.cntrCvc_authButtonControl(); 호출 라인을 주석처리
        """
        func_names: set[str] = set()
        lines = content.split("\n")

        i = 0
        while i < len(lines):
            m = re.match(r"\s*this\.(\w+)\s*=\s*function", lines[i])
            if m:
                func_name = m.group(1)
                depth = 0
                body: list[str] = []
                j = i
                while j < len(lines):
                    depth += lines[j].count("{") - lines[j].count("}")
                    body.append(lines[j])
                    if depth <= 0 and j > i:
                        break
                    j += 1
                if "com.fnAuthButtonControl" in "\n".join(body):
                    func_names.add(func_name)
                i = j + 1
            else:
                i += 1

        for name in func_names:
            pattern = (
                r"^(\s*)(await\s+)?this\."
                + re.escape(name)
                + r"\s*\(([^)]*)\)\s*;"
            )
            def _make_repl(fn: str):
                def _repl(m: re.Match) -> str:
                    indent  = m.group(1)
                    aw      = m.group(2) or ""
                    args    = m.group(3)
                    return f"{indent}//{aw}this.{fn}({args});"
                return _repl
            content = re.sub(pattern, _make_repl(name), content, flags=re.MULTILINE)

        return content

    def _fix_fnauth_button_control(self, content: str) -> str:
        """경고 주석이 아직 남아 있는 상태에서 fnAuthButtonControl 패턴 적용"""
        fna = self.p["script_fnauth_button_control"]

        r1 = fna["is_exist_var_fix"]
        content = re.sub(r1["from_pattern"], r1["to"], content, flags=re.DOTALL)

        r2 = fna["com_call_guard_fix"]
        content = re.sub(r2["from_pattern"], r2["to"], content)

        return content

    # ──────────────────────────────────────────
    # Async / await
    # ──────────────────────────────────────────

    def _apply_async_patterns(self, content: str) -> str:
        """
        1단계: 모든 함수 body 수집
        2단계: com.* 직접 호출이 있는 함수 → async 대상
        3단계: async 함수를 호출하는 함수도 async로 전파
        4단계: 역순으로 래핑 — return (async () => {...}).call(this)
        """
        await_cfg = self.p["async_patterns"]["com_functions_need_await"]
        await_com_funcs: list = await_cfg["items"]
        com_prefix_await: bool = await_cfg.get("com_prefix_await", False)
        excl: set = set(await_cfg.get("com_prefix_sync_exclusions", []))

        decl_pat = re.compile(r'this\.(\w+)\s*=\s*function\s*\([^)]*\)')

        # 1단계: 원본 content 기준 함수 body 수집
        func_bodies: dict[str, str] = {}
        for m in decl_pat.finditer(content):
            fname = m.group(1)
            op = content.find("{", m.end())
            if op == -1:
                continue
            cp = self._find_matching_brace(content, op)
            if cp == -1:
                continue
            func_bodies[fname] = content[op + 1: cp]

        # 2단계: com.* / so.* / sa.* / ins.* 직접 호출 → async 대상
        async_funcs: set[str] = set()
        ext_js_pat = re.compile(r'\b((?:so|sa|ins)\.\w+)\(')
        for fname, body in func_bodies.items():
            needs = any(f in body for f in await_com_funcs)
            if not needs and com_prefix_await:
                needs = any(c not in excl for c in re.findall(r'\b(com\.\w+)\(', body))
            if not needs:
                needs = bool(ext_js_pat.search(body))
            if needs:
                async_funcs.add(fname)

        # 3단계: async 함수를 호출하는 함수도 async로 전파
        changed = True
        while changed:
            changed = False
            for fname, body in func_bodies.items():
                if fname in async_funcs:
                    continue
                if any(re.search(rf'\bthis\.{re.escape(af)}\s*\(', body) for af in async_funcs):
                    async_funcs.add(fname)
                    changed = True

        # 3.4단계: Can* 동기 이벤트 핸들러(CanColumnChange, CanChange 등)는 async 래핑 대상에서 제외.
        # Nexacro는 이 핸들러의 리턴값(boolean)을 동기적으로 평가해서 변경을 취소/허용하므로,
        # (async () => {...}).call(this) 로 감싸면 실제 로직이 끝나기 전에 함수가 먼저 리턴돼버려
        # 취소 로직(return false)이 무시되는 등 오동작한다. await 가 필요한 로직은 별도 화살표
        # 함수로 분리해 fire-and-forget 으로 호출하는 수작업 리팩터링이 필요 — 자동 변환 대상 아님.
        async_funcs -= {f for f in async_funcs if self._SYNC_EVENT_HANDLER_RE.search(f)}

        # 3.5단계: 다른 async 함수에서 호출되는 함수 파악 → 해당 함수만 return 필요
        called_by_async: set[str] = set()
        for fname in async_funcs:
            body = func_bodies.get(fname, "")
            for af in async_funcs:
                if af != fname and re.search(rf'\bthis\.{re.escape(af)}\s*\(', body):
                    called_by_async.add(af)

        # 4단계: 역순 래핑 (뒤에서부터 수정해야 앞 위치 유지)
        tab = self.p["async_patterns"].get("wrapper_indent", "\t")
        for m in reversed(list(decl_pat.finditer(content))):
            fname = m.group(1)
            if fname not in async_funcs:
                continue

            op = content.find("{", m.end())
            if op == -1:
                continue
            cp = self._find_matching_brace(content, op)
            if cp == -1:
                continue

            inner = content[op + 1: cp]
            if "(async () =>" in inner:
                continue

            inner = self._add_await_to_content(inner, await_com_funcs, com_prefix_await, excl, async_funcs)

            # rstrip()은 공백/탭만 제거 — CRLF 원본의 trailing '\r'까지 같이 날아가는 것 방지
            indented = "\n".join(f"{tab}{ln}".rstrip(" \t") for ln in inner.split("\n"))
            if fname in called_by_async:
                wrapped = f"{{\n{tab}return (async () => {{{indented}\n{tab}}}).call(this);\n}}"
            else:
                wrapped = f"{{\n{tab}(async () => {{{indented}\n{tab}}}).call(this);\n}}"

            content = content[:op] + wrapped + content[cp + 1:]

        return content

    def _add_await_to_content(self, content: str, await_funcs: list,
                               com_prefix_await: bool = False, com_exclusions: set = None,
                               async_script_funcs: set = None) -> str:
        lines = content.split("\n")
        result = []
        in_block_comment = False
        for ln in lines:
            stripped = ln.lstrip()
            if in_block_comment:
                result.append(ln)
                if '*/' in ln:
                    in_block_comment = False
                continue
            if stripped.startswith('/*'):
                if '*/' not in ln:
                    in_block_comment = True
                result.append(ln)
                continue
            result.append(self._add_await_to_line(ln, await_funcs, com_prefix_await, com_exclusions, async_script_funcs))
        return "\n".join(result)

    def _add_await_to_line(self, line: str, await_funcs: list,
                            com_prefix_await: bool = False, com_exclusions: set = None,
                            async_script_funcs: set = None) -> str:
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            return line
        # 명시적 com.* 함수 — 한 줄에 여러 호출 모두 처리
        for func in await_funcs:
            if func in line and f'await {func}' not in line:
                line = line.replace(func, "await " + func)
        # 광범위 com.* 프리픽스 — 한 줄 내 모든 매치 처리
        if com_prefix_await:
            excl = com_exclusions or set()
            for cm in re.finditer(r'\b(com\.\w+)\(', line):
                full_call = cm.group(1)
                if full_call not in excl and full_call not in await_funcs and f'await {full_call}' not in line:
                    line = line.replace(full_call + "(", "await " + full_call + "(", 1)
        # Script 내 async 함수 호출 — 한 줄 내 모든 매치 처리
        if async_script_funcs:
            for sm in re.finditer(r'\bthis\.(\w+)\s*\(', line):
                if sm.group(1) in async_script_funcs:
                    call = f"this.{sm.group(1)}("
                    if f'await {call}' not in line:
                        line = line.replace(call, "await " + call, 1)
        # 외부 JS 함수 호출 — 한 줄 내 모든 매치 처리
        for em in re.finditer(r'\b((?:so|sa|ins)\.\w+)\(', line):
            ext_call = em.group(1) + "("
            if f'await {ext_call}' not in line:
                line = line.replace(ext_call, "await " + ext_call, 1)
        return line

    # ──────────────────────────────────────────
    # Decimal arithmetic conversion
    # ──────────────────────────────────────────

    def _convert_arithmetic_to_decimal(self, content: str) -> str:
        """
        산술 연산을 nexacro.Decimal 체인으로 변환:
        1) nexacro.round(expr) 내 산술식
        2) identifier = expr (getColumn 2개 이상 산술식)
        """
        content = self._convert_round_args_to_decimal(content)
        content = self._convert_getcol_assign_to_decimal(content)
        return content

    def _convert_round_args_to_decimal(self, content: str) -> str:
        result, last_end = [], 0
        for m in _ROUND_PAT_RE.finditer(content):
            arg_start = m.end()
            first_arg, arg_end = self._extract_first_func_arg(content, arg_start)
            if not _ARITH_OP_RE.search(first_arg) or 'nexacro.Decimal' in first_arg:
                continue
            try:
                converted = self._arith_to_decimal(first_arg)
            except Exception:
                continue
            if converted == first_arg:
                continue
            result.append(content[last_end:arg_start])
            result.append(converted)
            last_end = arg_end
        result.append(content[last_end:])
        return ''.join(result)

    def _convert_getcol_assign_to_decimal(self, content: str) -> str:
        # CRLF 원본 보존: '\n' 기준 split 시 각 라인 끝에 '\r'가 남는데,
        # _try_convert_assign_line 내부에서 strip() 하면서 이 '\r'가 유실되므로 분리해뒀다가 재부착
        lines = content.split('\n')
        out = []
        for ln in lines:
            has_cr = ln.endswith('\r')
            core = ln[:-1] if has_cr else ln
            converted = self._try_convert_assign_line(core)
            out.append(converted + '\r' if has_cr else converted)
        return '\n'.join(out)

    def _try_convert_assign_line(self, line: str) -> str:
        stripped = line.strip()
        if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
            return line
        # var_kw=("var "|""), lhs_var=변수명, eq=(" = "), rhs=식, suffix=(";")
        m = re.match(r'^(var\s+)?(\w+)(\s*=\s*)(.+?)(\s*;?\s*)$', stripped)
        if not m:
            return line
        var_kw, lhs_var, eq_part, rhs, suffix = m.group(1) or '', m.group(2), m.group(3), m.group(4), m.group(5)
        rhs_s = rhs.strip()

        if 'nexacro.Decimal' in rhs_s:
            return line

        indent = line[: len(line) - len(line.lstrip())]
        is_fin = self._is_financial_var(lhs_var)

        # Case 1: 금액 변수 숫자 리터럴 초기화 (var X = 0)
        if is_fin and re.match(r'^\d+(\.\d+)?$', rhs_s):
            return f'{indent}{var_kw}{lhs_var}{eq_part}new nexacro.Decimal({rhs_s}){suffix}'

        # Case 2: 금액 변수 단일 getColumn 대입 (X = DS.getColumn(...))
        if is_fin and '.getColumn(' in rhs_s and not _ARITH_OP_RE.search(rhs_s) and 'take.nvl(' not in rhs_s:
            return f'{indent}{var_kw}{lhs_var}{eq_part}new nexacro.Decimal(take.nvl({rhs_s}, 0)){suffix}'

        # Case 2b: 비금액 변수 단일 getColumn 대입 (X = this.DS.getColumn(...)) → take.nvl만 래핑 (Decimal 아님)
        if (
            not is_fin
            and 'take.nvl(' not in rhs_s
            and re.match(r'^this\.[\w.]+\.getColumn\([^()]*\)$', rhs_s)
        ):
            return f'{indent}{var_kw}{lhs_var}{eq_part}take.nvl({rhs_s}){suffix}'

        # Case 3: 산술 대입 (getColumn 2개↑ 또는 금액 변수)
        has_getcol2   = len(_GETCOL_RE.findall(rhs_s)) >= 2
        has_financial = self._is_financial_arithmetic(lhs_var, rhs_s)
        if (
            not (has_getcol2 or has_financial)
            or not _ARITH_OP_RE.search(rhs_s)
            or 'nexacro.round(' in rhs_s
            or re.search(r'[<>!]|==|&&|\|\|', rhs_s)
        ):
            return line
        try:
            converted = self._arith_to_decimal(rhs_s)
            if converted != rhs_s:
                return f'{indent}{var_kw}{lhs_var}{eq_part}{converted}{suffix}'
        except Exception:
            pass
        return line

    def _is_financial_var(self, name: str) -> bool:
        """변수명의 카멜케이스 토큰 중 금액 키워드가 있으면 True (부분문자열 오탐 방지)"""
        tokens = []
        for part in name.split('_'):
            tokens.extend(_CAMEL_SPLIT_RE.findall(part))
        return any(t.lower() in _FINANCIAL_KW for t in tokens) or name.lower() in _FINANCIAL_KW

    def _is_financial_arithmetic(self, lhs_var: str, rhs: str) -> bool:
        """LHS 또는 RHS 피연산자 중 금액 관련 변수명이 있으면 True"""
        if self._is_financial_var(lhs_var):
            return True
        try:
            tokens = self._tokenize_arith(rhs)
            return any(self._is_financial_var(t['v']) for t in tokens if t['t'] == 'atom')
        except Exception:
            return False

    def _extract_first_func_arg(self, content: str, start: int) -> tuple[str, int]:
        """함수 호출 '(' 직후 start 위치에서 첫 번째 인자와 종료 위치 반환"""
        depth, i = 0, start
        while i < len(content):
            c = content[i]
            if c == '(':
                depth += 1
            elif c == ')':
                if depth == 0:
                    return content[start:i].strip(), i
                depth -= 1
            elif c == ',' and depth == 0:
                return content[start:i].strip(), i
            i += 1
        return content[start:].strip(), i

    def _arith_to_decimal(self, expr: str) -> str:
        """산술식 → nexacro.Decimal 체인 문자열"""
        tokens = self._tokenize_arith(expr)
        node, _ = self._parse_add(tokens, 0)
        return self._emit_chain(node)

    def _tokenize_arith(self, expr: str) -> list[dict]:
        """괄호 중첩을 추적해 함수 호출(getColumn 등)을 단일 atom으로 처리"""
        tokens, i = [], 0
        expr = expr.strip()
        n = len(expr)
        while i < n:
            c = expr[i]
            if c in ' \t\n\r':
                i += 1
            elif c == '(':
                tokens.append({'t': 'lp'})
                i += 1
            elif c == ')':
                tokens.append({'t': 'rp'})
                i += 1
            elif c in '+-*/':
                tokens.append({'t': 'op', 'v': c})
                i += 1
            else:
                j, depth = i, 0
                while i < n:
                    ch = expr[i]
                    if ch == '(':
                        depth += 1; i += 1
                    elif ch == ')':
                        if depth == 0: break
                        depth -= 1; i += 1
                    elif ch in '+-*/' and depth == 0:
                        break
                    else:
                        i += 1
                val = expr[j:i].strip()
                if val:
                    tokens.append({'t': 'atom', 'v': val})
        return tokens

    def _parse_add(self, toks: list, pos: int) -> tuple[dict, int]:
        left, pos = self._parse_mul(toks, pos)
        while pos < len(toks) and toks[pos]['t'] == 'op' and toks[pos]['v'] in '+-':
            op = toks[pos]['v']; pos += 1
            right, pos = self._parse_mul(toks, pos)
            left = {'t': 'bin', 'op': op, 'l': left, 'r': right}
        return left, pos

    def _parse_mul(self, toks: list, pos: int) -> tuple[dict, int]:
        left, pos = self._parse_primary(toks, pos)
        while pos < len(toks) and toks[pos]['t'] == 'op' and toks[pos]['v'] in '*/':
            op = toks[pos]['v']; pos += 1
            right, pos = self._parse_primary(toks, pos)
            left = {'t': 'bin', 'op': op, 'l': left, 'r': right}
        return left, pos

    def _parse_primary(self, toks: list, pos: int) -> tuple[dict, int]:
        if pos >= len(toks):
            raise ValueError("Unexpected end of tokens")
        tok = toks[pos]
        # 단항 마이너스 처리 (-expr)
        if tok['t'] == 'op' and tok['v'] == '-':
            node, pos = self._parse_primary(toks, pos + 1)
            if node['t'] == 'atom':
                return {'t': 'atom', 'v': f'-{node["v"]}'}, pos
            return {'t': 'bin', 'op': '-', 'l': {'t': 'atom', 'v': '0'}, 'r': node}, pos
        if tok['t'] == 'lp':
            node, pos = self._parse_add(toks, pos + 1)
            if pos < len(toks) and toks[pos]['t'] == 'rp':
                pos += 1
            return node, pos
        if tok['t'] == 'atom':
            return {'t': 'atom', 'v': tok['v']}, pos + 1
        raise ValueError(f"Unexpected token: {tok}")

    def _emit_chain(self, node: dict) -> str:
        """AST → nexacro.Decimal 체인 (체인의 시작점, new nexacro.Decimal 래핑)"""
        if node['t'] == 'atom':
            return f"new nexacro.Decimal({self._nvl_wrap(node['v'])})"
        method = _OP_TO_METHOD[node['op']]
        return f"{self._emit_chain(node['l'])}.{method}({self._emit_arg(node['r'])})"

    def _emit_arg(self, node: dict) -> str:
        """AST → Decimal 메서드 인자 (복잡한 우변은 체인으로 재귀)"""
        if node['t'] == 'atom':
            return self._nvl_wrap(node['v'])
        return self._emit_chain(node)

    def _nvl_wrap(self, value: str) -> str:
        """getColumn 호출이면 take.nvl(value, 0)으로 감싸기"""
        return f'take.nvl({value}, 0)' if '.getColumn(' in value else value

    # ──────────────────────────────────────────
    # Brace matching
    # ──────────────────────────────────────────

    def _find_matching_brace(self, content: str, open_pos: int) -> int:
        """open_pos 위치의 { 에 매칭되는 } 위치 반환 (문자열/주석 내부 중괄호 무시)"""
        depth = 0
        i = open_pos
        n = len(content)
        in_single = False
        in_double = False
        in_block = False

        while i < n:
            c = content[i]

            if in_block:
                if c == '*' and i + 1 < n and content[i + 1] == '/':
                    in_block = False
                    i += 2
                else:
                    i += 1
                continue

            if in_single:
                if c == '\\':
                    i += 2
                elif c == "'":
                    in_single = False
                    i += 1
                else:
                    i += 1
                continue

            if in_double:
                if c == '\\':
                    i += 2
                elif c == '"':
                    in_double = False
                    i += 1
                else:
                    i += 1
                continue

            if c == '/' and i + 1 < n:
                if content[i + 1] == '/':
                    eol = content.find('\n', i)
                    i = eol + 1 if eol != -1 else n
                    continue
                if content[i + 1] == '*':
                    in_block = True
                    i += 2
                    continue

            if c == "'":
                in_single = True
            elif c == '"':
                in_double = True
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return i
            i += 1

        return -1

    # ──────────────────────────────────────────
    # XML attribute helpers
    # ──────────────────────────────────────────

    def _extract_attr(self, line: str, attr: str) -> str | None:
        m = re.search(rf'\s{attr}="([^"]*)"', line)
        return m.group(1) if m else None

    def _remove_attr(self, line: str, attr: str) -> str:
        return re.sub(rf'\s{attr}="[^"]*"', " ", line)

    def _set_attr(self, line: str, attr: str, value: str) -> str:
        if f'{attr}=' in line:
            return re.sub(rf'{attr}="[^"]*"', f'{attr}="{value}"', line)
        if '/>' in line:
            return line.replace("/>", f' {attr}="{value}"/>', 1)
        # 비자기닫힘 태그(<Cell ...>) 처리
        return re.sub(r'(?<!/)(>)', f' {attr}="{value}">', line, count=1)

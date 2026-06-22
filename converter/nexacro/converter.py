"""
Nexacro XFDL Converter
1차 AI변환 XFDL → 정제본 XFDL 자동 변환기
"""

import re
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PATTERNS_FILE = Path(__file__).parent / "patterns" / "nexacro_convert_patterns.json"

SCRIPT_START = '<Script type="xscript5.1"><![CDATA['
SCRIPT_END = "]]></Script>"

_ARITH_OP_RE = re.compile(r'[+\-*/]')
_ROUND_PAT_RE = re.compile(r'nexacro\.round\(')
_GETCOL_RE = re.compile(r'\.getColumn\(')
_OP_TO_METHOD = {'+': 'add', '-': 'sub', '*': 'mul', '/': 'div'}


class XfdlConverter:
    def __init__(self, patterns_file: Path = PATTERNS_FILE):
        with open(patterns_file, encoding="utf-8") as f:
            self.p = json.load(f)

    # ──────────────────────────────────────────
    # Public
    # ──────────────────────────────────────────

    def convert_file(self, input_path: Path, output_path: Path) -> None:
        content = input_path.read_text(encoding="utf-8-sig")  # BOM 자동 제거
        result = self.convert(content, form_name=input_path.stem)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
        logger.info("변환 완료: %s", output_path)

    def convert(self, content: str, form_name: str = "") -> str:
        idx_start = content.find(SCRIPT_START)
        idx_end = content.find(SCRIPT_END)

        if idx_start == -1 or idx_end == -1:
            return self._convert_layout(content)

        layout = content[:idx_start]
        script = content[idx_start + len(SCRIPT_START): idx_end]
        tail = content[idx_end + len(SCRIPT_END):]

        layout = self._convert_layout(layout)
        script = self._convert_script(script, form_name=form_name)

        return layout + SCRIPT_START + script + SCRIPT_END + tail

    # ──────────────────────────────────────────
    # Layout section
    # ──────────────────────────────────────────

    def _convert_layout(self, content: str) -> str:
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
                                line = self._set_attr(line, "cssclass", f'{css_val}+&quot;,&quot;+{color_mapped}')
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
        7. 텍스트 치환 (com.isEmpty(pThis, 먼저, pThis→this 마지막)
        8. 외부 JS 참조 주입 (sa.* / so.* / ins.* 호출 감지 → take.loadJs)
        9. async/await 변환 — com.* 호출 함수 전체 래핑
        """
        content = self._fix_fnauth_button_control(content)
        content = self._apply_warning_removals(content)
        content = self._apply_aichanger_markers(content)
        content = self._apply_uxb_info(content)
        content = self._convert_svc_url(content)
        content = self._convert_dataset_get_column(content)
        content = self._convert_arithmetic_to_decimal(content)
        content = self._apply_text_replacements(content)
        content = self._convert_fn_message_domain(content)
        if form_name:
            content = self._replace_system_form_name(content, form_name)
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
            gubun_pat = re.compile(r'functionGubun\s*=\s*"?([A-Za-z0-9_]+)"?')
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

    def _convert_dataset_get_column(self, content: str) -> str:
        """getColumn 컬럼명 snake_case → camelCase 변환 (단/쌍따옴표 모두 처리, 쌍따옴표로 통일)"""
        # gdsCCDUserMDS → gdsUserInfo 이름 변환 (단일/두 파라미터 모두)
        content = re.sub(
            r"gdsCCDUserMDS\.getColumn\((?:[^,)]+,\s*)?['\"]([^'\"]+)['\"]\)",
            lambda m: f'gdsUserInfo.getColumn("{self._snake_to_camel(m.group(1))}")',
            content,
        )
        # gdsUserInfo.getColumn([rowIdx,] 'col'/"col") → camelCase
        content = re.sub(
            r"(gdsUserInfo\.getColumn\([^)]*)['\"]([^'\"]+)['\"](\s*\))",
            lambda m: f'{m.group(1)}"{self._snake_to_camel(m.group(2))}"{m.group(3)}',
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

        # 2단계: com.* 직접 호출 → async 대상
        async_funcs: set[str] = set()
        for fname, body in func_bodies.items():
            needs = any(f in body for f in await_com_funcs)
            if not needs and com_prefix_await:
                needs = any(c not in excl for c in re.findall(r'\b(com\.\w+)\(', body))
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

            indented = "\n".join(f"{tab}{ln}".rstrip() for ln in inner.split("\n"))
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
        return "\n".join(
            self._add_await_to_line(ln, await_funcs, com_prefix_await, com_exclusions, async_script_funcs)
            for ln in lines
        )

    def _add_await_to_line(self, line: str, await_funcs: list,
                            com_prefix_await: bool = False, com_exclusions: set = None,
                            async_script_funcs: set = None) -> str:
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("/*") or "await " in line:
            return line
        # 명시적 com.* 함수
        for func in await_funcs:
            if func in line:
                line = line.replace(func, "await " + func, 1)
                return line
        # 광범위 com.* 프리픽스
        if com_prefix_await:
            excl = com_exclusions or set()
            cm = re.search(r'\b(com\.\w+)\(', line)
            if cm:
                full_call = cm.group(1)
                if full_call not in excl and full_call not in await_funcs:
                    line = line.replace(full_call + "(", "await " + full_call + "(", 1)
                    return line
        # Script 내 async 함수 호출 (this.fnXxx())
        if async_script_funcs:
            sm = re.search(r'\bthis\.(\w+)\s*\(', line)
            if sm and sm.group(1) in async_script_funcs:
                call = f"this.{sm.group(1)}("
                line = line.replace(call, "await " + call, 1)
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
        lines = content.split('\n')
        return '\n'.join(self._try_convert_assign_line(ln) for ln in lines)

    def _try_convert_assign_line(self, line: str) -> str:
        stripped = line.strip()
        if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
            return line
        m = re.match(r'^((?:var\s+)?\w+\s*=\s*)(.+?)(\s*;?\s*)$', stripped)
        if not m:
            return line
        rhs = m.group(2)
        if (
            len(_GETCOL_RE.findall(rhs)) < 2
            or not _ARITH_OP_RE.search(rhs)
            or 'nexacro.Decimal' in rhs
            or 'nexacro.round(' in rhs
            or re.search(r'[<>!]|==|&&|\|\|', rhs)
        ):
            return line
        try:
            converted = self._arith_to_decimal(rhs)
            if converted != rhs:
                indent = line[: len(line) - len(line.lstrip())]
                return f'{indent}{m.group(1)}{converted}{m.group(3)}'
        except Exception:
            pass
        return line

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
        """open_pos 위치의 { 에 매칭되는 } 위치 반환 (문자열/주석 미인식, 단순 카운팅)"""
        depth = 0
        for i in range(open_pos, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    return i
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
        return line.replace("/>", f' {attr}="{value}"/>')

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")
PATTERNS_FILE = Path("patterns/learned_patterns.json")


class RuleEngine:
    """patterns JSON의 치환 규칙을 코드로 적용."""

    def apply(self, code: str, patterns: dict) -> str:
        # 1. import 문자열 치환 (패키지 경로 변경 / 삭제)
        for rule in patterns.get("import_replacements", []):
            frm, to = rule.get("from", ""), rule.get("to", "")
            if frm:
                code = code.replace(frm, to)

        # 2. 특정 prefix 로 시작하는 import 라인 전체 제거
        prefix_removals = patterns.get("import_prefix_removals", [])
        if prefix_removals:
            lines = code.splitlines(keepends=True)
            code = "".join(
                line for line in lines
                if not any(line.strip().startswith(p) for p in prefix_removals)
            )

        # 3. 새 import 추가 (중복 제외, package 선언 바로 뒤에 삽입)
        additions = patterns.get("import_additions", [])
        for imp in additions:
            if imp not in code:
                code = re.sub(
                    r'(package\s+[\w.]+;\s*\n)',
                    r'\1' + imp + '\n',
                    code,
                    count=1
                )

        # 4. 어노테이션 치환
        for rule in patterns.get("annotation_replacements", []):
            frm, to = rule.get("from", ""), rule.get("to", "")
            if frm:
                code = re.sub(re.escape(frm) + r'\b', to, code)

        # 5. 일반 텍스트 치환
        for rule in patterns.get("text_replacements", []):
            frm, to = rule.get("from", ""), rule.get("to", "")
            if frm:
                code = code.replace(frm, to)

        return code


class DaoTransformer:
    """DAO 파일 변환 엔진 — API 없이 내장 규칙으로 처리."""

    # (정규식 패턴, 치환 문자열) 목록
    _LINE_RULES: list[tuple[str, str]] = [
        # DbWrap 선언 제거
        (r'\bDbWrap\s+\w+\s*=\s*new\s+DbWrap\(\)\s*;', ''),
        # setObject/getObject/getObjects: conn 파라미터 제거 (prefix 치환으로 괄호 중첩 문제 회피)
        (r'\b\w+\.setObject\(conn,\s*', r'commonDao.setObject('),
        (r'\b\w+\.getObjects\(conn,\s*', r'commonDao.getObjects('),
        (r'\b\w+\.getObject\(conn,\s*', r'commonDao.getObject('),
        # Connection conn 파라미터 제거
        (r',\s*Connection\s+conn\b', ''),
        (r'\bConnection\s+conn\s*,\s*', ''),
        (r'\bConnection\s+conn\b', ''),
        # UserBean userBean 파라미터 제거
        (r',\s*UserBean\s+userBean\b', ''),
        (r'\bUserBean\s+userBean\s*,\s*', ''),
        # Formatter.nullTrim(rs.getString("X")) 조합 우선 처리 (중첩 괄호 문제 방지)
        (r'\bFormatter\.nullTrim\(\s*rs\d*\.getString\("(\w+)"\)\s*\)',
         r'StringUtil.nvl(map.get("\1"), "")'),
        # Formatter.nullTrim 일반 (단순 인자)
        (r'\bFormatter\.nullTrim\((\w+)\)', r'StringUtil.nvl(\1, "")'),
        # ResultSet 컬럼 읽기 → Map 변환 (래핑 형태 우선 처리)
        (r'new\s+Long\(\s*rs\d*\.getLong\("(\w+)"\)\s*\)',
         r'Formatter.nullLong(StringUtil.nvl(map.get("\1"), "0"))'),
        (r'new\s+Double\(\s*rs\d*\.getDouble\("(\w+)"\)\s*\)',
         r'Formatter.nullDouble(StringUtil.nvl(map.get("\1"), "0.0"))'),
        (r'\brs\d*\.getString\("(\w+)"\)', r'map.get("\1")'),
        (r"\brs\d*\.getString\('(\w+)'\)", r'map.get("\1")'),
        (r'\brs\d*\.getLong\("(\w+)"\)',
         r'StringUtil.toLong((String) map.get("\1"), 0L)'),
        (r'\brs\d*\.getDouble\("(\w+)"\)',
         r'StringUtil.toDouble((String) map.get("\1"), 0.0)'),
        (r'\brs\d*\.getInt\("(\w+)"\)',
         r'StringUtil.toInt((String) map.get("\1"), 0)'),
        (r'\brs\d*\.getTimestamp\("(\w+)"\)',
         r'Formatter.parseToDate(map.get("\1"))'),
        # finally 블록 내 close() 제거
        (r'if\s*\(\s*rs\d*\s*!=\s*null\s*\)\s*rs\d*\.close\(\)\s*;', ''),
        (r'if\s*\(\s*ps\d*\s*!=\s*null\s*\)\s*ps\d*\.close\(\)\s*;', ''),
        (r'\brs\d*\.close\(\)\s*;', ''),
        (r'\bps\d*\.close\(\)\s*;', ''),
        # PreparedStatement / ResultSet 선언 제거
        (r'\bPreparedStatement\s+\w+(\s*=\s*null)?\s*;', ''),
        (r'\bResultSet\s+\w+(\s*=\s*null)?\s*;', ''),
        # throw new Exception("ERR-...") → UxbBizException (문자열 코드 버전)
        (r'throw\s+new\s+Exception\s*\(\s*"([^"]+)"\s*\)',
         r'throw new UxbBizException("\1")'),
    ]

    def __init__(self, class_name: str):
        self.class_name = class_name
        self.namespace = re.sub(r'(?i)DAO$', '', class_name)

    def transform(self, code: str) -> tuple[str, str]:
        code = self._apply_line_rules(code)
        code = self._add_class_decorations(code)
        code, xml_entries = self._convert_execute_queries(code)
        code = self._inject_user_delegation(code)
        code = self._fix_throws(code)
        code = self._remove_trivial_try_catch(code)
        code = self._remove_throws_exception(code)
        code = self._cleanup_formatting(code)
        return code, self._build_mapper_xml(xml_entries)

    # ------------------------------------------------------------------ #
    #  내부 메서드                                                          #
    # ------------------------------------------------------------------ #

    def _apply_line_rules(self, code: str) -> str:
        for pattern, replacement in self._LINE_RULES:
            code = re.sub(pattern, replacement, code)
        return code

    def _add_class_decorations(self, code: str) -> str:
        """@Slf4j / @RequiredArgsConstructor / @Repository 추가 및 필드 삽입."""
        anns = '@Slf4j\n@RequiredArgsConstructor\n@Repository\n'
        code = re.sub(r'(public\s+class\s+)', anns + r'\1', code, count=1)
        fields = (
            '\n    private final CommonDao commonDao;'
            '\n    private final UxbDAO uxbDAO;\n'
        )
        code = re.sub(r'(public\s+class\s+\w+[^{]*\{)', r'\1' + fields, code, count=1)
        return code

    def _convert_execute_queries(self, code: str) -> tuple[str, list[dict]]:
        """PreparedStatement 패턴을 uxbDAO.select/update() 로 변환하고 SQL을 Mapper XML로 추출."""
        xml_entries: dict = {}
        method_query_count: dict[str, int] = {}

        prep_re = re.compile(
            r'(\w+)\s*=\s*conn\.prepareStatement\((\w+)\.toString\(\)\)\s*;'
        )

        offset = 0
        result_code = code

        for prep_match in prep_re.finditer(code):
            sb_var = prep_match.group(2)
            method_name = self._enclosing_method(code, prep_match.start())
            if not method_name:
                continue

            # executeUpdate vs executeQuery 판별
            after = code[prep_match.end():prep_match.end() + 800]
            is_update = bool(re.search(r'\bexecuteUpdate\(\)', after))

            idx = method_query_count.get(method_name, 0)
            method_query_count[method_name] = idx + 1
            mapper_id = method_name if idx == 0 else f"{method_name}{idx}"

            # SQL 추출 (prepareStatement 이전, 현재 메서드 범위만)
            before = code[:prep_match.start()]
            sql_parts, param_names = self._extract_sql_and_params(before, sb_var)

            if is_update:
                ordered_params = self._extract_update_params(code, prep_match.end())
                sql_xml = self._replace_positional_params(
                    ' '.join(sql_parts).strip(), ordered_params
                )
                xml_entries[mapper_id] = {
                    'id': mapper_id, 'sql': sql_xml,
                    'params': [k for k, _ in ordered_params], 'type': 'update',
                }
            else:
                ordered_params = []
                sql_xml = ' '.join(sql_parts).strip()
                xml_entries[mapper_id] = {
                    'id': mapper_id, 'sql': sql_xml,
                    'params': param_names, 'type': 'select',
                }

            # sb 선언부터 prepareStatement 줄까지를 java_call 로 교체
            adjusted_start = prep_match.start() + offset
            sb_decl_re = re.compile(
                rf'([ \t]*)(?:String\w*|StringBuilder|StringBuffer)\s+{re.escape(sb_var)}'
                rf'\s*=\s*new\s+\w+\(.*?\)\s*;',
                re.DOTALL
            )
            method_orig_start = self._find_method_start_pos(code, prep_match.start())
            method_to_prep = prep_match.start() - method_orig_start
            search_from = max(0, adjusted_start - method_to_prep - 200)
            sb_match = sb_decl_re.search(result_code, search_from)
            if sb_match and sb_match.start() < adjusted_start:
                # sb 선언의 들여쓰기를 기준으로 java_call 생성
                base = sb_match.group(1)
                inner = base + ('\t' if '\t' in base else '    ')

                if is_update:
                    lines = [f'{base}Map<String, Object> paramMap = new HashMap<>();']
                    for key, val in ordered_params:
                        lines.append(f'{inner}paramMap.put("{key}", {val});')
                    lines.append(f'{inner}uxbDAO.update("{self.namespace}.{mapper_id}", paramMap);')
                else:
                    lines = [f'{base}Map<String, Object> paramMap = new HashMap<>();']
                    for p in param_names:
                        lines.append(f'{inner}paramMap.put("{p}", {p});')
                    lines.append(
                        f'{inner}List<Map<String, Object>> listMap = '
                        f'uxbDAO.select("{self.namespace}.{mapper_id}", paramMap);'
                    )
                java_call = '\n'.join(lines)

                replace_start = sb_match.start()
                prep_line_end = result_code.index('\n', adjusted_start) + 1
                result_code = (
                    result_code[:replace_start] + java_call + '\n'
                    + result_code[prep_line_end:]
                )
                offset += len(java_call) + 1 - (prep_line_end - replace_start)

        # if 내부가 replacement 범위에 포함되어 } else { throw ... } 가 고아로 남는 경우 제거
        result_code = re.sub(
            r'\}\s*else\s*\{\s*throw\s+new\s+\w+\s*\(\s*"[^"]*"\s*\)\s*;\s*\}',
            '',
            result_code,
            flags=re.DOTALL,
        )

        # 잔여 execute 호출 및 ps.setXxx() 제거 (줄 단위로 매칭)
        result_code = re.sub(r'[ \t]*\w+\s*=\s*\w+\.executeQuery\(\)\s*;\n?', '', result_code)
        result_code = re.sub(r'[ \t]*\w+\.executeUpdate\(\)\s*;\n?', '', result_code)
        result_code = re.sub(
            r'[ \t]*\bps\d*\.set(?:Long|String|Int|Double|Timestamp|Object)\b[^\n]*;\n?',
            '', result_code
        )
        # 잔여 conn.prepareStatement() 호출 제거 (변환 실패한 케이스 정리)
        result_code = re.sub(r'[ \t]*\w+\s*=\s*conn\.prepareStatement\([^\n]+\)\s*;\n?', '', result_code)

        # while (rs.next()) → for (Map<String, Object> map : listMap)
        result_code = re.sub(
            r'while\s*\(\s*\w+\.next\(\)\s*\)',
            'for (Map<String, Object> map : listMap)',
            result_code
        )

        # if (rs.next()) 단건 조회 → if (listMap != null && !listMap.isEmpty()) + map 선언
        def _replace_if_rs_next(m: re.Match) -> str:
            indent = m.group(1)
            return (
                f'{indent}if (listMap != null && !listMap.isEmpty()) {{\n'
                f'{indent}    Map<String, Object> map = listMap.get(0);'
            )
        result_code = re.sub(
            r'([ \t]*)if\s*\(\s*\w+\.next\(\)\s*\)\s*\{',
            _replace_if_rs_next,
            result_code
        )

        # 빈 finally 블록 정리
        result_code = re.sub(
            r'\s*finally\s*\{\s*(?:try\s*\{)?\s*\}?\s*(?:catch\s*\([^)]+\)\s*\{[^}]*\})?\s*\}',
            '',
            result_code
        )

        return result_code, list(xml_entries.values())

    def _enclosing_method(self, code: str, pos: int) -> str:
        """pos 이전에서 가장 가까운 메서드 이름을 반환."""
        pattern = re.compile(r'\b(?:public|private|protected)\s+\S+\s+(\w+)\s*\(')
        name = ''
        for m in pattern.finditer(code[:pos]):
            name = m.group(1)
        return name

    def _extract_sql_and_params(self, code: str, sb_var: str) -> tuple[list[str], list[str]]:
        """sb.append() 호출에서 SQL 조각과 파라미터 이름을 추출.
        현재 메서드 범위로 스코프 제한 (마지막 sb 선언 이후만 검색).
        """
        sql_parts: list[str] = []
        param_names: list[str] = []

        # 마지막 sb 선언 위치 이후에서만 검색 (다른 메서드 sb와 혼용 방지)
        sb_decl_re = re.compile(
            rf'(?:StringBuilder|StringBuffer)\s+{re.escape(sb_var)}\b'
        )
        last_decl_pos = 0
        for m in sb_decl_re.finditer(code):
            last_decl_pos = m.start()

        # sb = new StringBuilder("initial SQL...") 생성자 초기값 추출
        init_re = re.compile(
            rf'(?:StringBuilder|StringBuffer)\s+{re.escape(sb_var)}\s*=\s*new\s+\w+\("([^"]*)"\)',
            re.DOTALL
        )
        init_match = init_re.search(code, last_decl_pos)
        if init_match:
            sql_parts.append(init_match.group(1))

        append_re = re.compile(
            rf'\b{re.escape(sb_var)}\.append\((.+?)\)\s*;',
            re.DOTALL
        )

        for m in append_re.finditer(code, last_decl_pos):
            arg = m.group(1).strip()

            # 순수 문자열 리터럴
            if re.match(r'^"[^"]*"$', arg):
                sql_parts.append(arg[1:-1])
                continue

            # "prefix" + param[.method()] + "suffix"
            concat = re.match(
                r'"([^"]*?)"\s*\+\s*([A-Za-z_][A-Za-z0-9_]*)(?:\.\w+\(\))?\s*\+\s*"([^"]*?)"',
                arg
            )
            if concat:
                sql_parts.append(concat.group(1))
                raw_param = concat.group(2)
                param_names.append(raw_param)
                sql_parts.append(f'#{{{raw_param}}}')
                sql_parts.append(concat.group(3))
                continue

            # "prefix" + param[.method()]  (suffix 없음)
            concat_no_suffix = re.match(
                r'"([^"]*?)"\s*\+\s*([A-Za-z_][A-Za-z0-9_]*)(?:\.\w+\(\))?$',
                arg
            )
            if concat_no_suffix:
                sql_parts.append(concat_no_suffix.group(1))
                raw_param = concat_no_suffix.group(2)
                param_names.append(raw_param)
                sql_parts.append(f'#{{{raw_param}}}')
                continue

            if not arg.startswith('"') and not arg.startswith("'"):
                sql_parts.append(f'/* {arg} */')

        return sql_parts, list(dict.fromkeys(param_names))

    def _extract_update_params(self, code: str, start: int) -> list[tuple[str, str]]:
        """ps.setXxx(pos, expr) 에서 순서대로 (key, value_expr) 쌍을 추출.
        pos는 숫자 또는 i++ 형태 모두 지원.
        """
        exec_m = re.search(r'\bexecuteUpdate\(\)', code[start:])
        end = start + exec_m.start() if exec_m else start + 1000

        set_line_re = re.compile(
            r'\bps\d*\.set(?:Long|String|Int|Double|Timestamp|Object)\s*\(\s*(\d+|i\+\+)\s*,\s*([^\n]+)\)',
        )
        fixed: dict[int, tuple[str, str]] = {}
        ordered: list[tuple[str, str]] = []

        for m in set_line_re.finditer(code, start, end):
            pos_str = m.group(1)
            expr = m.group(2).strip()
            kv = self._derive_param_key_value(expr)
            if pos_str == 'i++':
                ordered.append(kv)
            else:
                pos = int(pos_str)
                if pos not in fixed:
                    fixed[pos] = kv

        if fixed:
            return [fixed[k] for k in sorted(fixed.keys())]
        return ordered

    def _derive_param_key_value(self, expr: str) -> tuple[str, str]:
        """파라미터 표현식에서 (paramMap key, Java value expression) 쌍 도출.

        규칙:
        - 단순 파라미터(processFlag, invoNo 등) → (paramName, paramName)
        - VO/DTO getter(headVo.getCancel_date()) → (cancel_date, headVo.getCancel_date())
        - session userId → (_sessionUserId, userInfo.getUserId())
        """
        expr = expr.strip()

        # 1. session userId
        if 'getUserId' in expr or 'getUser_id' in expr:
            return ('_sessionUserId', 'userInfo.getUserId()')

        # 2. StringUtil.nvl(simpleVar, ...) — _LINE_RULES 가 Formatter.nullTrim(x) 변환한 결과
        m = re.match(r'StringUtil\.nvl\((\w+)\s*,', expr)
        if m:
            name = m.group(1)
            return (name, name)

        # 3. StringUtil.nvl(obj.getXxx(), ...) — VO getter inside nvl
        m = re.match(r'StringUtil\.nvl\((\w+)\.get(\w+)\(\)\s*,', expr)
        if m:
            obj, col = m.group(1), m.group(2)
            return (col[0].lower() + col[1:], f'{obj}.get{col}()')

        # 4. Formatter.nullTrim(obj.getXxx()) — VO getter with nullTrim
        m = re.match(r'Formatter\.nullTrim\((\w+)\.get(\w+)\(\)', expr)
        if m:
            obj, col = m.group(1), m.group(2)
            return (col[0].lower() + col[1:], f'{obj}.get{col}()')

        # 5. Formatter.nullTrim(simpleVar) — 미변환 잔여 케이스
        m = re.match(r'Formatter\.nullTrim\((\w+)\)', expr)
        if m:
            name = m.group(1)
            return (name, name)

        # 6. Formatter.nullXxx(obj.getXxx()) — VO getter with null wrapper
        m = re.match(r'Formatter\.\w+\((\w+)\.get(\w+)\(\)', expr)
        if m:
            obj, col = m.group(1), m.group(2)
            return (col[0].lower() + col[1:], f'{obj}.get{col}()')

        # 7. Formatter.nullXxx(simpleVar) — 단순 파라미터 with null wrapper
        m = re.match(r'Formatter\.\w+\((\w+)\)', expr)
        if m:
            name = m.group(1)
            return (name, name)

        # 8. obj.getXxx() — VO getter (래퍼 없음)
        m = re.match(r'(\w+)\.get(\w+)\(\)', expr)
        if m:
            obj, col = m.group(1), m.group(2)
            return (col[0].lower() + col[1:], f'{obj}.get{col}()')

        # 9. 단순 식별자 fallback
        clean = expr.rstrip(')')
        m = re.search(r'\b([a-z_]\w*)\s*$', clean)
        if m:
            name = m.group(1)
            return (name, name)

        name = re.sub(r'\W+', '_', expr)[:20]
        return (name, name)

    def _replace_positional_params(self, sql: str, params: list[tuple[str, str]]) -> str:
        """SQL의 ? 를 순서대로 #{paramName} 으로 치환."""
        for key, _ in params:
            sql = sql.replace('?', f'#{{{key}}}', 1)
        return sql

    def _find_method_start_pos(self, code: str, pos: int) -> int:
        """pos 이전에서 가장 가까운 메서드 선언 시작 위치 반환."""
        pattern = re.compile(r'\b(?:public|private|protected)\s+(?:(?:static|final|synchronized)\s+)*[\w<>\[\],\s]+\s+\w+\s*\(')
        last = 0
        for m in pattern.finditer(code[:pos]):
            last = m.start()
        return last

    def _find_block_end(self, code: str, open_pos: int) -> int:
        """open_pos에서 첫 { 를 찾아 매칭 } 위치 반환."""
        start = code.find('{', open_pos)
        if start == -1:
            return len(code)
        depth = 0
        for i, ch in enumerate(code[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return i
        return len(code)

    def _inject_user_delegation(self, code: str) -> str:
        """userInfo.getUserId() 사용 메서드에 UserDelegation userInfo 선언 자동 주입."""
        method_re = re.compile(
            r'\b(?:public|private|protected)\b[^{;]*\{',
            re.DOTALL
        )
        insertions: list[tuple[int, str]] = []
        for m in method_re.finditer(code):
            if re.search(r'\bclass\b', m.group()):
                continue
            body_start = m.end()
            body_end = self._find_block_end(code, m.start() + m.group().rfind('{'))
            body = code[body_start:body_end]
            if 'userInfo.getUserId()' in body and 'UserDelegation userInfo' not in body:
                line_start = code.rfind('\n', 0, body_start) + 1
                base_indent = re.match(r'[ \t]*', code[line_start:]).group()
                inner_indent = base_indent + '    '
                insertions.append((body_start, f'\n{inner_indent}UserDelegation userInfo = UserInfo.getUserInfo();'))
        for pos, text in reversed(insertions):
            code = code[:pos] + text + code[pos:]
        return code

    def _fix_throws(self, code: str) -> str:
        """throws Exception, Exception 같은 중복 제거."""
        return re.sub(r'\bthrows\s+Exception\s*,\s*Exception\b', 'throws Exception', code)

    def _remove_trivial_try_catch(self, code: str) -> str:
        """catch 바디가 throw new XxxException(e); 하나뿐인 try-catch를 제거하고 try 본문만 남김."""
        try_re = re.compile(r'^([ \t]*)try\s*\{', re.MULTILINE)
        replacements: list[tuple[int, int, str]] = []

        for m in try_re.finditer(code):
            indent = m.group(1)
            try_open_abs = code.index('{', m.start())
            try_close = self._find_block_end(code, try_open_abs)
            if try_close >= len(code):
                continue

            after = code[try_close + 1:]
            catch_m = re.match(r'\s*catch\s*\(\s*Exception\s+(\w+)\s*\)\s*\{', after)
            if not catch_m:
                continue

            catch_open_abs = try_close + 1 + after.index('{', catch_m.start())
            catch_close = self._find_block_end(code, catch_open_abs)
            if catch_close >= len(code):
                continue

            # 추가 catch / finally 가 있으면 건너뜀
            tail = code[catch_close + 1:].lstrip()
            if re.match(r'(catch|finally)\b', tail):
                continue

            # catch 바디가 단순 rethrow 하나뿐인지 확인
            catch_body = code[catch_open_abs + 1:catch_close].strip()
            if not re.match(r'^throw\s+new\s+\w+\s*\(\s*\w+\s*\)\s*;$', catch_body):
                continue

            # try 본문 추출 후 들여쓰기 한 단계 제거
            try_body = code[try_open_abs + 1:try_close]
            extra_indent = '\t'
            for line in try_body.splitlines():
                if line.strip():
                    ws = re.match(r'^(\s+)', line)
                    if ws and len(ws.group(1)) > len(indent):
                        extra_indent = ws.group(1)[len(indent):]
                    break

            de_indented = []
            for line in try_body.splitlines(keepends=True):
                if line.startswith(indent + extra_indent):
                    de_indented.append(indent + line[len(indent) + len(extra_indent):])
                else:
                    de_indented.append(line)
            replacements.append((m.start(), catch_close + 1, ''.join(de_indented)))

        for start, end, replacement in sorted(replacements, key=lambda x: x[0], reverse=True):
            code = code[:start] + replacement + code[end:]
        return code

    def _remove_throws_exception(self, code: str) -> str:
        """메서드 시그니처의 throws Exception 제거."""
        return re.sub(r'\)\s*throws\s+Exception\b', ')', code)

    def _cleanup_formatting(self, code: str) -> str:
        """빈 줄 정규화 및 기본 들여쓰기 정리."""
        # 공백·탭만 있는 줄 → 완전한 빈 줄로 정규화
        code = re.sub(r'^[ \t]+$', '', code, flags=re.MULTILINE)
        # 3개 이상 연속 빈 줄 → 1개 (반복 적용하여 체인 처리)
        while '\n\n\n' in code:
            code = code.replace('\n\n\n', '\n\n')
        # 여는 { 바로 뒤 빈 줄 제거
        code = re.sub(r'(\{)\n\n', r'\1\n', code)
        # 닫는 } 바로 앞 빈 줄 제거
        code = re.sub(r'\n\n(\s*\})', r'\n\1', code)
        # 파일 끝 정리
        code = code.rstrip() + '\n'
        return code

    def _format_sql(self, sql: str) -> str:
        """SQL 가독성 정리: 리터럴 \\n 제거, 과도한 공백 정규화, 8칸 들여쓰기 적용."""
        sql = sql.replace('\\n', '\n')
        lines = []
        for line in sql.splitlines():
            line = re.sub(r'\t+', ' ', line)
            line = re.sub(r' {2,}', ' ', line)
            line = line.strip()
            if line:
                lines.append(line)
        indent = '        '
        return '\n'.join(indent + line for line in lines)

    def _build_mapper_xml(self, entries: list[dict]) -> str:
        if not entries:
            return ''
        blocks = []
        for e in entries:
            is_update = e.get('type') == 'update'
            tag = 'update' if is_update else 'select'
            extra = '' if is_update else ' resultType="map" useCache="false"'
            formatted_sql = self._format_sql(e["sql"])
            blocks.append(
                f'    <{tag} id="{e["id"]}" parameterType="map"{extra} timeout="0">\n'
                f'        <![CDATA[\n'
                f'        /* {self.namespace}.{e["id"]} */\n'
                f'        ]]>\n'
                f'{formatted_sql}\n'
                f'    </{tag}>'
            )
        body = '\n\n'.join(blocks)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"\n'
            '    "http://mybatis.org/dtd/mybatis-3-mapper.dtd">\n'
            f'<mapper namespace="{self.namespace}">\n'
            f'{body}\n'
            '</mapper>'
        )


class EjbConverter:
    def __init__(self):
        self.rule_engine = RuleEngine()

    def _load_patterns(self) -> dict:
        if not PATTERNS_FILE.exists():
            raise FileNotFoundError(
                f"{PATTERNS_FILE} 파일이 없습니다. "
                "Claude Code 세션에서 샘플을 분석하여 패턴 파일을 먼저 생성하세요."
            )
        patterns = json.loads(PATTERNS_FILE.read_text(encoding="utf-8"))
        logger.info(f"패턴 로드: {PATTERNS_FILE}")
        return patterns

    def _is_dao_file(self, path: Path) -> bool:
        return path.stem.upper().endswith('DAO')

    def _mapper_name(self, stem: str) -> str:
        return re.sub(r'(?i)DAO$', '', stem) + 'Mapper.xml'

    def _read_source(self, path: Path) -> str:
        for enc in ('utf-8', 'cp949', 'euc-kr'):
            try:
                return path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        raise UnicodeDecodeError(f"인코딩 감지 실패: {path}")

    def convert_file(self, source_path: Path, patterns: dict) -> dict | str:
        """단일 파일 변환. DAO 파일은 {'java': ..., 'xml': ...} 반환."""
        code = self._read_source(source_path)
        code = self.rule_engine.apply(code, patterns)

        if self._is_dao_file(source_path):
            transformer = DaoTransformer(source_path.stem)
            java, xml = transformer.transform(code)
            return {'java': java, 'xml': xml}
        return code

    def convert_all(self) -> list[Path]:
        """input/ 폴더의 모든 .java 파일을 변환하여 output/ 에 저장."""
        patterns = self._load_patterns()

        java_files = sorted(INPUT_DIR.glob('*.java'))
        if not java_files:
            raise FileNotFoundError('input/ 폴더에 .java 파일이 없습니다.')

        OUTPUT_DIR.mkdir(exist_ok=True)
        converted: list[Path] = []

        for java_file in java_files:
            logger.info(f'변환 중: {java_file.name}')
            try:
                result = self.convert_file(java_file, patterns)

                if isinstance(result, dict):
                    out_java = OUTPUT_DIR / java_file.name
                    out_java.write_text(result['java'], encoding='utf-8')
                    converted.append(out_java)
                    logger.info(f'완료 (Java): {out_java}')

                    if result.get('xml'):
                        out_xml = OUTPUT_DIR / self._mapper_name(java_file.stem)
                        out_xml.write_text(result['xml'], encoding='utf-8')
                        converted.append(out_xml)
                        logger.info(f'완료 (Mapper XML): {out_xml}')
                else:
                    out_path = OUTPUT_DIR / java_file.name
                    out_path.write_text(result, encoding='utf-8')
                    converted.append(out_path)
                    logger.info(f'완료: {out_path}')

            except Exception as e:
                logger.error(f'실패 ({java_file.name}): {e}')

        return converted

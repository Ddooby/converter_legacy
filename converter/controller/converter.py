import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)


def _env_path(key: str, default: str) -> Path:
    return Path(os.getenv(key, default))


def _env_path_optional(key: str) -> Path | None:
    val = os.getenv(key, "").strip()
    return Path(val) if val else None


CTRL_INPUT_DIR    = _env_path("CTRL_INPUT_DIR",    "converter/controller/input")
CTRL_OUTPUT_DIR   = _env_path("CTRL_OUTPUT_DIR",   "converter/controller/output")
CTRL_PATTERNS_FILE = _env_path("CTRL_PATTERNS_FILE", "converter/controller/patterns/learned_patterns.json")

CTRL_EXTERNAL_GEN_YN = os.getenv("CTRL_EXTERNAL_GEN_YN", "false").strip().lower() == "true"
CTRL_EXTERNAL_BASE   = _env_path_optional("CTRL_EXTERNAL_BASE")

_VALID_MODES = {"overwrite", "skip", "backup"}
CTRL_OVERWRITE_MODE = os.getenv("CTRL_OVERWRITE_MODE", "overwrite").strip().lower()
if CTRL_OVERWRITE_MODE not in _VALID_MODES:
    logger.warning(f"CTRL_OVERWRITE_MODE='{CTRL_OVERWRITE_MODE}' 는 유효하지 않음. 'overwrite' 로 폴백.")
    CTRL_OVERWRITE_MODE = "overwrite"


def _read_source(path: Path) -> str:
    raw = path.read_bytes()
    try:
        import chardet
        enc = chardet.detect(raw)["encoding"] or "utf-8"
        try:
            return raw.decode(enc)
        except Exception:
            return raw.decode("cp949", errors="replace")
    except ImportError:
        # chardet 없을 때: utf-8 → cp949 → euc-kr 순으로 strict 시도
        for enc in ("utf-8", "cp949", "euc-kr"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("cp949", errors="replace")


def _safe_write(path: Path, content: str) -> bool:
    if path.exists():
        if CTRL_OVERWRITE_MODE == "skip":
            logger.warning(f"이미 존재 → 스킵: {path}")
            return False
        if CTRL_OVERWRITE_MODE == "backup":
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = path.with_name(f"{path.name}.bak.{ts}")
            path.rename(backup)
            logger.info(f"백업: {path.name} → {backup.name}")
    path.write_text(content, encoding="utf-8")
    return True


def _java_to_python_backref(s: str) -> str:
    """JSON 패턴의 $1 표기를 Python re.sub 용 \\1 으로 변환."""
    return re.sub(r'\$(\d+)', r'\\\1', s)


class RuleEngine:
    """patterns JSON의 치환 규칙을 코드에 적용."""

    def apply(self, code: str, patterns: dict) -> str:
        # 1. import 문자열 치환 (패키지 경로 변경 / 삭제)
        for rule in patterns.get("import_replacements", []):
            frm, to = rule.get("from", ""), rule.get("to", "")
            if frm:
                code = code.replace(frm, to)

        # 2. annotation 치환
        for rule in patterns.get("annotation_replacements", []):
            frm, to = rule.get("from", ""), rule.get("to", "")
            if frm:
                code = re.sub(re.escape(frm) + r'\b', to, code)

        # 3. 일반 텍스트 치환
        for rule in patterns.get("text_replacements", []):
            frm, to = rule.get("from", ""), rule.get("to", "")
            if frm:
                code = code.replace(frm, to)

        # 4. platform 코드 제거 (선언문 / 구문)
        platform = patterns.get("platform_code_removals", {})
        for stmt in platform.get("remove_statements", []):
            code = code.replace(stmt, "")
        for decl in platform.get("remove_declarations", []):
            code = code.replace(decl, "")
        for field in platform.get("remove_fields", []):
            lines = code.splitlines(keepends=True)
            code = "".join(
                line for line in lines
                if field not in line
            )

        # 5. getValueAsString 패턴 치환 → _apply_get_value_as_string 에서 분기 블록 스코프 내 적용
        #    전역 적용 시 헬퍼 메서드에도 dataRequest.getString() 이 주입되는 오염 문제 방지

        # 6. output 치환 (addDataset, addStr, out_vl 등)
        for rule in patterns.get("output_replacements", {}).get("rules", []):
            regex = rule.get("regex", "")
            to = _java_to_python_backref(rule.get("to", ""))
            if regex:
                code = re.sub(regex, to, code)

        # 7. DataSetManager 패턴 처리 (multiline)
        ds_patterns = patterns.get("datasetmanager_patterns", {})
        for key in ("convertResultDataSet", "convertResultDataSet_noArg"):
            p = ds_patterns.get(key, {})
            regex = p.get("regex", "")
            replacement = _java_to_python_backref(p.get("replacement", ""))
            if regex:
                code = re.sub(regex, replacement, code, flags=re.DOTALL)
        sep = ds_patterns.get("convertResultDataSet_separated", {})
        if sep.get("regex"):
            code = re.sub(sep["regex"], sep.get("replacement", ""), code)

        # 8. Dataset row 반복 패턴 치환
        row_iter = patterns.get("dataset_row_iteration_patterns", {})
        for key, val in row_iter.items():
            if key in ("description", "method_param"):
                continue
            from_regex = val.get("from_regex", "")
            to = _java_to_python_backref(val.get("to", ""))
            if from_regex:
                code = re.sub(from_regex, to, code)

        # 9. row status 패턴
        rs = patterns.get("row_status_pattern", {})
        if rs.get("from") and rs.get("to"):
            code = code.replace(rs["from"], rs["to"])
        if rs.get("copy_from") and rs.get("copy_to"):
            code = code.replace(rs["copy_from"], rs["copy_to"])

        # 10. import 추가 (중복 제외, package 선언 바로 뒤)
        for imp in patterns.get("import_additions", []):
            if imp not in code:
                code = re.sub(
                    r'(package\s+[\w.]+;\s*\n)',
                    r'\1' + imp + '\n',
                    code, count=1
                )

        return code


class ServletTransformer:
    """EJB Servlet → Spring Controller 변환 엔진."""

    def __init__(self, patterns: dict):
        self.patterns = patterns
        self.rule_engine = RuleEngine()

    # ------------------------------------------------------------------
    # 메인 변환 흐름
    # ------------------------------------------------------------------

    def transform(self, source: str, class_name: str) -> str:
        code = source

        # 1. EJB Home/Remote 패턴 제거 → service 호출로 변환
        code, service_fields = self._replace_ejb_home_remote(code)

        # 2. Logger 필드 제거 (@Slf4j 로 대체)
        code = re.sub(
            r'[ \t]*(?:public|private|protected)?\s*static\s+Logger\s+\w+\s*=\s*Logger\.getLogger\([^;]+\)\s*;\n?',
            '', code
        )

        # 3. serialVersionUID 제거
        code = re.sub(
            r'[ \t]*private\s+static\s+final\s+long\s+serialVersionUID\s*=[^;]+;\n?',
            '', code
        )

        # 4. execute() 내 functionGubun 분기 → @RequestMapping 메서드 생성
        code = self._convert_execute_to_request_mappings(code)

        # 5. 클래스 선언 변환 (Servlet → Controller, 어노테이션 + service 필드 추가)
        code = self._convert_class_declaration(code, class_name, service_fields)

        # 6. RuleEngine 규칙 일괄 적용 (import 치환, 플랫폼 코드 제거 등)
        code = self.rule_engine.apply(code, self.patterns)

        # 7. 패키지 경로 단일 레벨 정규화: rule_engine이 channel→controller 치환 후 실행
        code = self._normalize_package(code)

        # 8. service import 추가 + EJB 인터페이스 import 제거 (패키지 정규화 후 실행)
        code = self._add_service_imports(code, service_fields)
        code = self._remove_ejb_interface_imports(code)

        # 9. margeCollections Dataset → List<Map<String, Object>> 변환
        code = self._convert_marge_collections(code)

        # 10. 중복 캐스트 제거: (String) (String) → (String)
        code = re.sub(r'\(String\)\s*\(String\)', '(String)', code)

        # 11. 빈 줄 3개 이상 → 1개로 압축
        code = re.sub(r'\n{3,}', '\n\n', code)

        return code

    # ------------------------------------------------------------------
    # EJB Home/Remote 제거
    # ------------------------------------------------------------------

    def _replace_ejb_home_remote(self, code: str) -> tuple[str, list[tuple[str, str]]]:
        """EJB Home/Remote 패턴 제거. (code, [(ServiceClass, serviceVar), ...]) 반환."""
        lines = code.splitlines()
        collected: dict[str, str] = {}  # serviceVar → ServiceClass (중복 제거)
        while True:
            home_vars: dict[str, tuple[str, int]] = {}  # var_name → (home_type, line_idx)
            remote_vars: dict[str, tuple[str, int]] = {}
            call_lines: list[tuple] = []

            for idx, line in enumerate(lines):
                m = re.search(
                    r'(\w+Home)\s+(\w+)\s*=\s*\([^)]+\)\s*ServiceObjFactory\.getInstance\(\)\.lookUpHome\([^)]+\);',
                    line
                )
                if m:
                    home_vars[m.group(2)] = (m.group(1), idx)

            for idx, line in enumerate(lines):
                m = re.search(r'(\w+)\s+(\w+)\s*=\s*(?:\([^)]+\)\s*)?(\w+)\.create\(\);', line)
                if m:
                    remote_vars[m.group(2)] = (m.group(3), idx)

            for idx, line in enumerate(lines):
                m = re.search(r'(\w+)\s*=\s*(\w+)\.(\w+)\(([^;]*)\);', line)
                if m:
                    call_lines.append((idx, m.group(1), m.group(2), m.group(3), m.group(4)))
                else:
                    m2 = re.search(r'(\w+)\.(\w+)\(([^;]*)\);', line)
                    if m2:
                        call_lines.append((idx, None, m2.group(1), m2.group(2), m2.group(3)))

            to_remove: set[int] = set()
            to_replace: dict[int, str] = {}
            found = False

            for call in call_lines:
                call_idx, result_var, remote_var, method_name, args = call
                if remote_var in remote_vars:
                    home_var, remote_idx = remote_vars[remote_var]
                    if home_var in home_vars:
                        home_type, home_idx = home_vars[home_var]
                        service_var = self._home_type_to_service_var(home_type)
                        service_cls = self._home_type_to_service_class(home_type)
                        collected[service_var] = service_cls
                        to_remove.add(home_idx)
                        to_remove.add(remote_idx)
                        indent = re.match(r'(\s*)', lines[call_idx]).group(1)
                        if result_var:
                            to_replace[call_idx] = f"{indent}{result_var} = {service_var}.{method_name}({args});"
                        else:
                            to_replace[call_idx] = f"{indent}{service_var}.{method_name}({args});"
                        found = True

            if not found:
                break

            new_lines = []
            for idx, line in enumerate(lines):
                if idx in to_remove:
                    continue
                elif idx in to_replace:
                    new_lines.append(to_replace[idx])
                else:
                    new_lines.append(line)
            lines = new_lines

        service_fields = [(cls, var) for var, cls in sorted(collected.items())]
        return '\n'.join(lines), service_fields

    @staticmethod
    def _home_type_to_service_var(home_type: str) -> str:
        """ILubePriceHome → lubePriceService"""
        name = home_type
        if name.startswith('I'):
            name = name[1:]
        if name.endswith('Home'):
            name = name[:-4]
        return name[0].lower() + name[1:] + 'Service'

    @staticmethod
    def _home_type_to_service_class(home_type: str) -> str:
        """ILubePriceHome → LubePriceService"""
        name = home_type
        if name.startswith('I'):
            name = name[1:]
        if name.endswith('Home'):
            name = name[:-4]
        return name + 'Service'

    # ------------------------------------------------------------------
    # 패키지 정규화: channel.a.b → controller.a
    # ------------------------------------------------------------------

    def _normalize_package(self, code: str) -> str:
        def _shorten(m: re.Match) -> str:
            parts = m.group(1).split('.')
            # channel 뒤의 서브모듈 1단계만 유지
            if len(parts) > 0:
                return f"com.pan.som.controller.{parts[0]}"
            return "com.pan.som.controller"

        code = re.sub(
            r'com\.pan\.som\.controller\.(\w+(?:\.\w+)+)',
            _shorten,
            code
        )
        return code

    # ------------------------------------------------------------------
    # 클래스 선언 변환
    # ------------------------------------------------------------------

    def _convert_class_declaration(self, code: str, class_name: str,
                                    service_fields: list[tuple[str, str]]) -> str:
        controller_name = re.sub(r'Ser[lv]{2}et', 'Controller', class_name)

        # 클래스명 변경
        code = code.replace(class_name, controller_name)

        # extends GeneralServlet / GeneralSerlvet 제거 (오타 포함)
        code = re.sub(r'\s+extends\s+\w*Ser[lv]{2}et\b', '', code)
        code = re.sub(r'\s+extends\s+BaseController\b', '', code)

        # 클래스 선언 앞에 어노테이션 추가
        mapping = self._extract_request_mapping(controller_name)
        annotations = (
            f"@Controller\n"
            f"@Slf4j\n"
            f"@RequiredArgsConstructor\n"
            f"@RequestMapping(\"/{mapping}/*\")\n"
        )

        code = re.sub(
            r'(public\s+class\s+' + re.escape(controller_name) + r'\b)',
            annotations + r'\1',
            code
        )

        # 클래스 여는 중괄호 직후 service 필드 삽입
        if service_fields:
            fields_block = "\n".join(
                f"    private final {cls} {var};" for cls, var in service_fields
            )
            code = re.sub(
                r'(public\s+class\s+' + re.escape(controller_name) + r'[^{]*\{)',
                r'\1\n\n' + fields_block + '\n',
                code
            )

        return code

    def _extract_request_mapping(self, controller_name: str) -> str:
        name = controller_name.replace("Controller", "")
        # CamelCase 첫 글자 소문자
        if name:
            name = name[0].lower() + name[1:]
        return name

    @staticmethod
    def _remove_ejb_interface_imports(code: str) -> str:
        """변환 후 남은 EJB Home/Remote 인터페이스 import 제거 (I[대문자]로 시작하는 클래스)."""
        lines = code.splitlines(keepends=True)
        result = []
        for line in lines:
            m = re.match(r'\s*import\s+[\w.]+\.(I[A-Z]\w+)\s*;\s*\n?', line)
            if m:
                continue  # EJB 인터페이스 import 제거
            result.append(line)
        return ''.join(result)

    def _add_service_imports(self, code: str, service_fields: list[tuple[str, str]]) -> str:
        """패키지 정규화 후 service import를 controller 패키지 기준으로 추가."""
        if not service_fields:
            return code
        pkg_m = re.search(r'package\s+com\.pan\.som\.controller\.(\w+)', code)
        if not pkg_m:
            return code
        submodule = pkg_m.group(1)
        for service_cls, _ in service_fields:
            imp = f"import com.pan.som.service.{submodule}.{service_cls};"
            if imp not in code:
                code = re.sub(
                    r'(package\s+[\w.]+;\s*\n)',
                    r'\1' + imp + '\n',
                    code, count=1
                )
        return code

    # ------------------------------------------------------------------
    # execute() → @RequestMapping 메서드 변환
    # ------------------------------------------------------------------

    def _convert_execute_to_request_mappings(self, code: str) -> str:
        # execute() 메서드 전체 추출
        execute_body = self._extract_execute_body(code)
        if not execute_body:
            return code

        # execute() 에서 functionGubun 분기 파싱
        methods = self._parse_function_gubun_blocks(execute_body)
        if not methods:
            return code

        # execute() 메서드 전체 제거
        code = self._remove_execute_method(code)

        # 클래스 닫는 중괄호 앞에 메서드 삽입
        method_code = "\n".join(self._render_method(m) for m in methods)
        code = re.sub(r'(\n\})\s*$', f'\n{method_code}\n}}', code)

        return code

    def _extract_execute_body(self, code: str) -> str | None:
        m = re.search(
            r'(?:public|protected)\s+void\s+execute\s*\([^)]*\)[^{]*\{',
            code
        )
        if not m:
            return None
        start = m.end()
        depth = 1
        i = start
        while i < len(code) and depth > 0:
            if code[i] == '{':
                depth += 1
            elif code[i] == '}':
                depth -= 1
            i += 1
        return code[start:i - 1]

    def _remove_execute_method(self, code: str) -> str:
        m = re.search(
            r'\n?\s*(?:public|protected)\s+void\s+execute\s*\([^)]*\)[^{]*\{',
            code
        )
        if not m:
            return code
        start = m.start()
        body_start = m.end()
        depth = 1
        i = body_start
        while i < len(code) and depth > 0:
            if code[i] == '{':
                depth += 1
            elif code[i] == '}':
                depth -= 1
            i += 1
        return code[:start] + code[i:]

    def _parse_function_gubun_blocks(self, execute_body: str) -> list[dict]:
        """functionGubun/type 분기 블록을 파싱해 메서드 목록으로 반환."""
        pattern = re.compile(
            r'(?:"([^"]+)"\s*\.equals\s*\(\s*(?:functionGubun|type)\s*\)'
            r'|(?:functionGubun|type)\s*\.equals\s*\(\s*"([^"]+)"\s*\))',
            re.IGNORECASE
        )
        matches = list(pattern.finditer(execute_body))
        if not matches:
            return []

        methods = []
        for idx, match in enumerate(matches):
            gubun_value = match.group(1) or match.group(2)
            method_name = self._to_camel_case(gubun_value)
            block_start = match.end()

            # if/else if 블록 시작 찾기
            brace_pos = execute_body.find('{', block_start)
            if brace_pos == -1:
                continue

            depth = 1
            i = brace_pos + 1
            while i < len(execute_body) and depth > 0:
                if execute_body[i] == '{':
                    depth += 1
                elif execute_body[i] == '}':
                    depth -= 1
                i += 1
            block_body = execute_body[brace_pos + 1:i - 1]

            # try { ... } catch 제거 — 내용만 추출
            block_body = self._strip_try_catch(block_body)

            # getValueAsString → dataRequest.getString 변환 (분기 블록 스코프 내에서만 적용)
            block_body = self._apply_get_value_as_string(block_body)

            methods.append({
                "name": method_name,
                "url": gubun_value,
                "body": block_body.strip(),
            })

        return methods

    def _strip_try_catch(self, code: str) -> str:
        """try { body } catch/finally { ... } 에서 body만 추출."""
        m = re.match(r'\s*try\s*\{', code)
        if not m:
            return code
        body_start = m.end()
        depth = 1
        i = body_start
        while i < len(code) and depth > 0:
            if code[i] == '{':
                depth += 1
            elif code[i] == '}':
                depth -= 1
            i += 1
        return code[body_start:i - 1]

    def _apply_get_value_as_string(self, code: str) -> str:
        """getValueAsString → dataRequest.getString 변환 (블록 스코프 내 전용)."""
        for rule in self.patterns.get("getValueAsString_pattern", {}).get("rules", []):
            regex = rule.get("regex", "")
            replacement = _java_to_python_backref(rule.get("replacement", ""))
            if regex:
                code = re.sub(regex, replacement, code)
        return code

    def _render_method(self, method: dict) -> str:
        name = method["name"]
        url  = method["url"]
        body = method["body"]

        # body 들여쓰기 정규화 (4칸)
        indented_body = "\n".join(
            "        " + line if line.strip() else ""
            for line in body.splitlines()
        )

        return (
            f'    @RequestMapping("{url}.do")\n'
            f'    public void {name}(UxbDataRequest dataRequest, UxbDataResponse dataResponse) {{\n'
            f'{indented_body}\n'
            f'        dataResponse.success();\n'
            f'    }}\n'
        )

    @staticmethod
    def _to_camel_case(s: str) -> str:
        parts = re.split(r'[_\-]', s)
        if not parts:
            return s
        # ALL_CAPS 단어는 전체 소문자로, 그 외는 첫 글자만 소문자
        first = parts[0].lower() if parts[0].isupper() else parts[0][0].lower() + parts[0][1:]
        rest = ''.join(
            p.capitalize() if p.isupper() else p.capitalize()
            for p in parts[1:]
        )
        return first + rest

    # ------------------------------------------------------------------
    # margeCollections Dataset → List<Map<String, Object>> 변환
    # ------------------------------------------------------------------

    def _convert_marge_collections(self, code: str) -> str:
        """Dataset margeCollections → List<Map<String, Object>> margeCollections 로 치환."""
        sig_m = re.search(
            r'([ \t]*)(?:public|private|protected)\s+static\s+Dataset\s+margeCollections\s*\('
            r'[^)]*\)\s*(?:throws\s+\w+\s*)?\{',
            code
        )
        if not sig_m:
            return code

        indent = sig_m.group(1)
        body_start = sig_m.end()
        depth = 1
        i = body_start
        while i < len(code) and depth > 0:
            if code[i] == '{':
                depth += 1
            elif code[i] == '}':
                depth -= 1
            i += 1
        method_end = i

        # 호출부에서 DTO 타입 추론: margeCollections(x, XxxDTO.class.getFields(), y)
        dto_match = re.search(r'margeCollections\s*\([^,]+,\s*(\w+)\.class\.getFields\(\)', code)
        dto_type = dto_match.group(1) if dto_match else "Object"

        i4 = indent + "    "
        i8 = indent + "        "
        i12 = indent + "            "
        i16 = indent + "                "

        new_method = "\n".join([
            f"{indent}public static List<Map<String, Object>> margeCollections(",
            f"{i8}Collection rowPriority, Collection columnPriority) {{",
            f"{i4}List<Map<String, Object>> result = new ArrayList<>();",
            f"{i4}Map<String, Map<String, Object>> priceMap = new HashMap<>();",
            f"",
            f"{i4}for (Object obj : columnPriority) {{",
            f"{i8}{dto_type} lubePrc = ({dto_type}) obj;",
            f"{i8}if (lubePrc.getLube_prdt_code() != null) {{",
            f"{i12}String key = lubePrc.getLube_cmpny_code() + \"||\" + lubePrc.getLube_prdt_code();",
            f"{i12}priceMap.computeIfAbsent(key, k -> new LinkedHashMap<>())",
            f"{i16}.put(lubePrc.getPort_code(),",
            f"{i16}     lubePrc.getPort_prc() != null ? lubePrc.getPort_prc() : \"\");",
            f"{i8}}}",
            f"{i4}}}",
            f"",
            f"{i4}for (Object obj : rowPriority) {{",
            f"{i8}{dto_type} contract = ({dto_type}) obj;",
            f"{i8}Map<String, Object> row = new LinkedHashMap<>();",
            f"{i8}for (Field field : contract.getClass().getDeclaredFields()) {{",
            f"{i12}if (!\"defalutQry\".equals(field.getName())) {{",
            f"{i16}try {{",
            f"{i16}    field.setAccessible(true);",
            f"{i16}    row.put(field.getName(), field.get(contract));",
            f"{i16}}} catch (Exception ignored) {{}}",
            f"{i12}}}",
            f"{i8}}}",
            f"{i8}if (contract.getLube_cmpny_code() != null && contract.getLube_prdt_code() != null) {{",
            f"{i12}String key = contract.getLube_cmpny_code() + \"||\" + contract.getLube_prdt_code();",
            f"{i12}Map<String, Object> portPrices = priceMap.get(key);",
            f"{i12}if (portPrices != null) {{",
            f"{i16}row.putAll(portPrices);",
            f"{i12}}}",
            f"{i8}}}",
            f"{i8}result.add(row);",
            f"{i4}}}",
            f"",
            f"{i4}return result;",
            f"{indent}}}",
        ])

        code = code[:sig_m.start()] + new_method + code[method_end:]

        # getDataType 헬퍼 제거 (Dataset 전용, 더 이상 불필요)
        code = self._remove_method(code, "getDataType")

        # 호출부 치환: Dataset x = margeCollections(a, Xxx.class.getFields(), b)
        #             → List<Map<String, Object>> x = margeCollections(a, b)
        code = re.sub(
            r'\bDataset\s+(\w+)\s*=\s*margeCollections\s*\(\s*(\w+)\s*,\s*\w+\.class\.getFields\(\)\s*,\s*(\w+)\s*\)\s*;',
            r'List<Map<String, Object>> \1 = margeCollections(\2, \3);',
            code
        )

        # import 추가
        if "java.util.LinkedHashMap" not in code:
            code = re.sub(
                r'(package\s+[\w.]+;\s*\n)',
                r'\1import java.util.LinkedHashMap;\n',
                code, count=1
            )

        return code

    def _remove_method(self, code: str, method_name: str) -> str:
        """지정된 이름의 메서드를 코드에서 제거."""
        m = re.search(
            r'\n?[ \t]*(?:public|private|protected)\s+(?:static\s+)?'
            r'\w[\w<>, \[\]]*\s+' + re.escape(method_name) + r'\s*\([^)]*\)[^{]*\{',
            code
        )
        if not m:
            return code
        start = m.start()
        body_start = m.end()
        depth = 1
        i = body_start
        while i < len(code) and depth > 0:
            if code[i] == '{':
                depth += 1
            elif code[i] == '}':
                depth -= 1
            i += 1
        return code[:start] + code[i:]


class ServletConverter:
    """파일 I/O 조율 — input/ → output/ 변환."""

    def __init__(self):
        self.patterns = self._load_patterns()
        self.transformer = ServletTransformer(self.patterns)

    def _load_patterns(self) -> dict:
        if not CTRL_PATTERNS_FILE.exists():
            raise FileNotFoundError(f"패턴 파일 없음: {CTRL_PATTERNS_FILE}")
        with open(CTRL_PATTERNS_FILE, encoding="utf-8") as f:
            return json.load(f)

    def convert_all(self) -> list[Path]:
        if not CTRL_INPUT_DIR.exists():
            raise FileNotFoundError(f"입력 폴더 없음: {CTRL_INPUT_DIR}")
        CTRL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        converted: list[Path] = []
        for java_file in sorted(CTRL_INPUT_DIR.glob("*.java")):
            out_path = self._convert_file(java_file)
            if out_path:
                converted.append(out_path)
        return converted

    def _convert_file(self, src: Path) -> Path | None:
        source = _read_source(src)
        class_name = src.stem

        logger.info(f"변환 중: {src.name}")
        result = self.transformer.transform(source, class_name)

        out_name = re.sub(r'Ser[lv]{2}et', 'Controller', class_name) + ".java"
        out_path = CTRL_OUTPUT_DIR / out_name
        if not _safe_write(out_path, result):
            return None
        logger.info(f"  → {out_path}")

        if CTRL_EXTERNAL_GEN_YN and CTRL_EXTERNAL_BASE:
            ext_path = CTRL_EXTERNAL_BASE / out_name
            ext_path.parent.mkdir(parents=True, exist_ok=True)
            _safe_write(ext_path, result)
            logger.info(f"  → (외부) {ext_path}")

        return out_path

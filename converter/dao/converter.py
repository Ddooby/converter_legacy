import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)


def _env_path(key: str, default: str) -> Path:
    return Path(os.getenv(key, default))


def _env_path_optional(key: str) -> Path | None:
    val = os.getenv(key, "").strip()
    return Path(val) if val else None


INPUT_DIR = _env_path("INPUT_DIR", "converter/dao/input")
OUTPUT_DIR = _env_path("OUTPUT_DIR", "converter/dao/output")
PATTERNS_FILE = _env_path("PATTERNS_FILE", "converter/dao/patterns/learned_patterns.json")

# Panocean Git 프로젝트 경로 (output 파일 생성 시 프로젝트 폴더에도 같이 생성)
EXTERNAL_GEN_YN = os.getenv("EXTERNAL_GEN_YN", "true").strip().lower() == "true"
EXTERNAL_DAO_BASE = _env_path_optional("EXTERNAL_DAO_BASE")
EXTERNAL_MAPPER_BASE = _env_path_optional("EXTERNAL_MAPPER_BASE")

_VALID_MODES = {"overwrite", "skip", "backup"}
OVERWRITE_MODE = os.getenv("OVERWRITE_MODE", "overwrite").strip().lower()
if OVERWRITE_MODE not in _VALID_MODES:
    logger.warning(
        f"OVERWRITE_MODE='{OVERWRITE_MODE}' 는 유효하지 않음. 'overwrite' 로 폴백."
    )
    OVERWRITE_MODE = "overwrite"


def _safe_write(path: Path, content: str) -> bool:
    """OVERWRITE_MODE 에 따라 파일 저장. 저장하면 True, 스킵하면 False."""
    if path.exists():
        if OVERWRITE_MODE == "skip":
            logger.warning(f"이미 존재 → 스킵: {path}")
            return False
        if OVERWRITE_MODE == "backup":
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = path.with_name(f"{path.name}.bak.{ts}")
            path.rename(backup)
            logger.info(f"백업: {path.name} → {backup.name}")
    path.write_text(content, encoding="utf-8")
    return True


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
        # JavaDoc @param conn / @param userBean 라인 제거 (Spring 변환 시 두 파라미터 모두 사라짐)
        (r'[ \t]*\*[ \t]*@param[ \t]+(?:conn|connection|userBean)\b[^\n]*\n', ''),
        # RemoteException import 제거
        (r'import\s+java\.rmi\.RemoteException\s*;\n?', ''),
        # DbWrap 선언 제거 (접근제어자/static/final 등 modifier 도 함께 제거)
        (r'[ \t]*(?:(?:private|public|protected|static|final)\s+)*DbWrap\s+\w+\s*=\s*new\s+DbWrap\(\)\s*;\s*\n?', ''),
        # dbWrap / dbwrap (대소문자 무관) → commonDao
        (r'\bdb[Ww]rap\.getInt\b', 'commonDao.getInt'),
        (r'\bdb[Ww]rap\.getLong\b', 'commonDao.getLong'),
        (r'\bdb[Ww]rap\.getDouble\b', 'commonDao.getDouble'),
        (r'\bdb[Ww]rap\.getString\b', 'commonDao.getString'),
        (r'\bdb[Ww]rap\.getObject\b', 'commonDao.getObject'),
        (r'\bdb[Ww]rap\.getObjects\b', 'commonDao.getObjects'),
        (r'\bdb[Ww]rap\.getObjectCstmt\b', 'commonDao.getObjectCstmt'),
        (r'\bdb[Ww]rap\.updateQuery\b', 'commonDao.updateQuery'),
        (r'\bdb[Ww]rap\.isExist\b', 'commonDao.isExist'),
        # 메서드 호출에서 conn/connection 이 단독 인자인 경우 제거
        (r'\(\s*(?:conn|connection)\s*\)', '()'),
        # Logger 필드 선언 제거 (@Slf4j 로 대체)
        (r'private\s+\w*\s*Logger\s+\w+\s*=\s*Logger\.getLogger\([^;]+\)\s*;', ''),
        # StringBuffer → StringBuilder
        (r'\bStringBuffer\b', 'StringBuilder'),
        # PKGenerator 카멜케이스 정규화
        (r'\bPKGenerator\.', 'pkGenerator.'),
        # setObject/getObject/getObjects/updateQuery/isExist/getString: conn/connection 파라미터 제거
        (r'\b\w+\.setObject\((?:conn|connection),\s*', r'commonDao.setObject('),
        (r'\b\w+\.getObjects\((?:conn|connection),\s*', r'commonDao.getObjects('),
        (r'\b\w+\.getObject\((?:conn|connection),\s*', r'commonDao.getObject('),
        (r'\b\w+\.updateQuery\((?:conn|connection),\s*', r'commonDao.updateQuery('),
        (r'\b\w+\.isExist\((?:conn|connection),\s*', r'commonDao.isExist('),
        (r'\b\w+\.getString\((?:conn|connection),\s*', r'commonDao.getString('),
        # Connection <varname> 파라미터/인자 제거 (선언부 먼저, 이후 인자 변수)
        (r',\s*Connection\s+\w+\b', ''),
        (r'\bConnection\s+\w+\s*,\s*', ''),
        # 로컬 변수 선언 `Connection conn = null;` 통째로 제거 (`= null;` 잔여 방지)
        (r'[ \t]*\bConnection\s+\w+(\s*=\s*null)?\s*;\n?', ''),
        (r'\bConnection\s+\w+\b', ''),
        (r',\s*\b(?:conn|connection)\b(?=\s*[,)])', ''),
        (r'\b(?:conn|connection)\b\s*,\s*', ''),
        # UserBean userBean 파라미터/인자 제거
        (r',\s*UserBean\s+userBean\b', ''),
        (r'\bUserBean\s+userBean\s*,\s*', ''),
        (r',\s*\buserBean\b(?=\s*[,)])', ''),
        (r'\buserBean\b\s*,\s*', ''),
        # userBean 메서드 호출 → userInfo (특수 케이스 우선)
        (r'\buserBean\.getUser_id\s*\(', 'userInfo.getUserId('),
        (r'\buserBean\.getUser_name\s*\(', 'userInfo.getUserName('),
        # userBean. 잔여 → userInfo. (일반 치환)
        (r'\buserBean\.', 'userInfo.'),
        # STXException → UxbBizException (일반 치환)
        (r'\bSTXException\b', 'UxbBizException'),
        # RowStatus: Formatter.nullTrim(x.getStatus()).equals(...) → x.getStatus() == DataSetRowStatus.XXX
        (r'Formatter\.nullTrim\((\w+)\.getStatus\(\)\)\s*\.equals\s*\(\s*"insert"\s*\)', r'\1.getStatus() == DataSetRowStatus.INSERT'),
        (r'Formatter\.nullTrim\((\w+)\.getStatus\(\)\)\s*\.equals\s*\(\s*"update"\s*\)', r'\1.getStatus() == DataSetRowStatus.UPDATE'),
        (r'Formatter\.nullTrim\((\w+)\.getStatus\(\)\)\s*\.equals\s*\(\s*"delete"\s*\)', r'\1.getStatus() == DataSetRowStatus.DELETE'),
        # RowStatus: getStatus().equals(...) → DataSetRowStatus
        (r'\.getStatus\(\)\s*\.equals\s*\(\s*"insert"\s*\)', '.getRowStatus() == DataSetRowStatus.INSERT'),
        (r'\.getStatus\(\)\s*\.equals\s*\(\s*"update"\s*\)', '.getRowStatus() == DataSetRowStatus.UPDATE'),
        (r'\.getStatus\(\)\s*\.equals\s*\(\s*"delete"\s*\)', '.getRowStatus() == DataSetRowStatus.DELETE'),
        # CommonDao 로컬 인스턴스 생성 제거
        (r'[ \t]*CommonDao\s+\w+\s*=\s*new\s+CommonDao\(\)\s*;\n?', ''),
        # CommonFunction 로컬 인스턴스 생성 제거 (클래스 필드로 주입)
        (r'[ \t]*CommonFunction\s+\w+\s*=\s*new\s+CommonFunction\(\)\s*;\n?', ''),
        # CCDAttachFileInfo 로컬 인스턴스 생성 제거 (클래스 필드로 주입)
        (r'[ \t]*CCDAttachFileInfo\s+\w+\s*=\s*new\s+CCDAttachFileInfo\(\)\s*;\n?', ''),
        # 로컬 comDao.xxx / com.method() → commonDao.xxx (method call 패턴만, 패키지 경로 제외)
        (r'\bcomDao\.', 'commonDao.'),
        (r'\bcom\.([a-z]\w+)\(', r'commonDao.\1('),
        # 단독 defaultUpdate/defaultInsert/defaultDelete/defaultVoObjSysValue 호출 → commonDao.xxx
        # (메서드 선언부는 _prefix_common_dao_default_methods 에서 별도 처리)
        # this.defaultXxx → commonDao.defaultXxx (AS-IS에서 this.defaultInsert(conn,...) 패턴 처리 후 잔여)
        (r'\bthis\.(defaultUpdate|defaultInsert|defaultDelete|defaultVoObjSysValue)\b', r'commonDao.\1'),
        # conn/connection 트랜잭션 관리 구문 제거 (Spring @Transactional 로 대체)
        (r'[ \t]*\b(?:conn|connection)\s*\.\s*setAutoCommit\s*\([^;]*\)\s*;\n?', ''),
        (r'[ \t]*\b(?:conn|connection)\s*\.\s*commit\s*\(\s*\)\s*;\n?', ''),
        (r'[ \t]*\b(?:conn|connection)\s*\.\s*rollback\s*\(\s*\)\s*;\n?', ''),
        # Formatter.nullTrim(rs.getString("X")) 조합 우선 처리 → Formatter.nullTrim(String.valueOf(map.get("X")))
        (r'\bFormatter\.nullTrim\(\s*rs\w*\.getString\("(\w+)"\)\s*\)',
         r'Formatter.nullTrim(String.valueOf(map.get("\1")))'),
        # VO/DTO setter에서 rs.getString → Formatter.nullTrim(String.valueOf(map.get())) 우선 처리
        (r'(\.set\w+\(\s*)rs\w*\.getString\s*\(\s*"(\w+)"\s*\)(\s*\))',
         r'\1Formatter.nullTrim(String.valueOf(map.get("\2")))\3'),
        # Formatter.nullTrim 일반 (단순 인자)
        (r'\bFormatter\.nullTrim\((\w+)\)', r'StringUtil.nvl(\1, "")'),
        # Formatter.nullLong(obj.getXxx()) → StringUtil.nvl 래핑
        (r'\bFormatter\.nullLong\((\w+)\.get(\w+)\(\)\)',
         r'Formatter.nullLong(StringUtil.nvl(\1.get\2(), "0"))'),
        # ResultSet 컬럼 읽기 → Map 변환 (래핑 형태 우선 처리)
        # String.valueOf(rs.getDouble("COL")) → String.valueOf(map.get("COL")) (new Double 래핑용)
        (r'\bString\.valueOf\(\s*rs\w*\.getDouble\("(\w+)"\)\s*\)',
         r'String.valueOf(map.get("\1"))'),
        (r'\bString\.valueOf\(\s*rs\w*\.getLong\("(\w+)"\)\s*\)',
         r'String.valueOf(map.get("\1"))'),
        (r'new\s+Long\(\s*rs\w*\.getLong\("(\w+)"\)\s*\)',
         r'Formatter.nullLong(StringUtil.nvl(map.get("\1"), "0"))'),
        (r'new\s+Double\(\s*rs\w*\.getDouble\("(\w+)"\)\s*\)',
         r'Formatter.nullDouble(StringUtil.nvl(map.get("\1"), "0.0"))'),
        (r'\brs\w*\.getCharacterStream\("(\w+)"\)', r'new StringReader(String.valueOf(map.get("\1")))'),
        (r'\brs\w*\.getString\("(\w+)"\)', r'Formatter.nullTrim(String.valueOf(map.get("\1")))'),
        (r"\brs\w*\.getString\('(\w+)'\)", r'Formatter.nullTrim(String.valueOf(map.get("\1")))'),
        (r'\brs\w*\.getLong\("(\w+)"\)',
         r'StringUtil.toLong((String) map.get("\1"), 0L)'),
        (r'\brs\w*\.getDouble\("(\w+)"\)',
         r'Formatter.nullDouble(StringUtil.nvl(map.get("\1"), "0"))'),
        (r'\brs\w*\.getInt\("(\w+)"\)',
         r'StringUtil.toInt((String) map.get("\1"), 0)'),
        (r'\brs\w*\.getTimestamp\("(\w+)"\)',
         r'Formatter.parseToDate(map.get("\1"))'),
        # finally 블록 내 close() 제거 (ps/pstmt/rs 공통)
        # 중괄호 포함 형태: if (var != null) { var.close(); }
        (r'if\s*\(\s*rs\w*\s*!=\s*null\s*\)\s*\{\s*rs\w*\.close\(\)\s*;\s*\}', ''),
        (r'if\s*\(\s*ps\w*\s*!=\s*null\s*\)\s*\{\s*ps\w*\.close\(\)\s*;\s*\}', ''),
        # 중괄호 없는 형태: if (var != null) var.close();
        (r'if\s*\(\s*rs\w*\s*!=\s*null\s*\)\s*rs\w*\.close\(\)\s*;', ''),
        (r'if\s*\(\s*ps\w*\s*!=\s*null\s*\)\s*ps\w*\.close\(\)\s*;', ''),
        (r'\brs\w*\.close\(\)\s*;', ''),
        (r'\bps\w*\.close\(\)\s*;', ''),
        # PreparedStatement / ResultSet 선언 제거
        (r'\bPreparedStatement\s+\w+(\s*=\s*null)?\s*;', ''),
        (r'\bResultSet\s+\w+(\s*=\s*null)?\s*;', ''),
        # throw new Exception("ERR-...") → UxbBizException (문자열 코드 버전)
        (r'throw\s+new\s+Exception\s*\(\s*"([^"]+)"\s*\)',
         r'throw new UxbBizException("\1")'),
        # new Long / new Double 일반 fallback (위의 specific 패턴 처리 후 잔여분)
        (r'\bnew\s+Long\(', 'Long.valueOf('),
        (r'\bnew\s+Double\(', 'Double.valueOf('),
        
        # -----------------------------------------------------------------------
        # AMT/AMOUNT 컬럼 → BigDecimal 변환
        # new Double(rs.getDouble("ENTER_AMOUNT")) → Formatter.nullDouble(StringUtil.nvl(...)) 변환 후
        # AMT/AMOUNT 컬럼명인 경우 nullBigDecimal로 재변환
        (r'(?i)Formatter\.null(?:Double|Long)\(\s*StringUtil\.nvl\(\s*map\.get\("(\w*(?:amt|amount))"\)\s*,\s*"[^"]*"\s*\)\s*\)',
         r'Formatter.nullBigDecimal(StringUtil.nvl(map.get("\1"), "0"))'),
        # VO/DTO 의 defalutQry (오타 필드) → getDefaultQry() 메서드 호출
        (r'\b(\w+(?:VO|DTO))\.defalutQry\b', r'\1.getDefaultQry()'),
        # -----------------------------------------------------------------------
    ]

    # SQL 키워드 우측 정렬 prefix (6자 필드 기준)
    _SQL_KW_PREFIX: dict[str, str] = {
        'SELECT':   '',
        'FROM':     '  ',
        'WHERE':    ' ',
        'AND':      '   ',
        'OR':       '    ',
        'ON':       '    ',
        'SET':      '   ',
        'UPDATE':   '',
        'DELETE':   '',
        'INSERT':   '',
        'INTO':     '  ',
        'HAVING':   '',
        'UNION':    ' ',
        'ORDER':    ' ',
        'GROUP':    ' ',
        'VALUES':   '',
    }

    def __init__(self, class_name: str):
        self.class_name = class_name
        # DAO 뒤 숫자/언더스코어 suffix(_BACKUP, _1 등) 허용 — namespace 에는 suffix 보존
        m = re.match(r'(.+?)DAO(\d*)(_\w*)?$', class_name, re.IGNORECASE)
        if m:
            self.namespace = m.group(1) + (m.group(2) or '') + (m.group(3) or '')
        else:
            self.namespace = class_name

    def transform(self, code: str) -> tuple[str, str]:
        code = self._normalize_nonrs_resultset_vars(code)
        code = self._apply_line_rules(code)
        code = self._prefix_common_dao_default_methods(code)
        if 'StringReader' in code and 'import java.io.StringReader' not in code:
            code = re.sub(
                r'(package\s+[\w.]+;\s*\n)',
                r'\1import java.io.StringReader;\n',
                code, count=1
            )
        if 'DataSetRowStatus' in code and 'import kr.co.takeit.dataset.DataSetRowStatus' not in code:
            code = re.sub(
                r'(package\s+[\w.]+;\s*\n)',
                r'\1import kr.co.takeit.dataset.DataSetRowStatus;\n',
                code, count=1
            )
        # Timestamp 가 타입으로 사용되면 import 추가 (getTimestamp/setTimestamp 메서드 호출은 제외)
        if re.search(r'\bTimestamp\b', code) and 'import java.sql.Timestamp' not in code:
            code = re.sub(
                r'(package\s+[\w.]+;\s*\n)',
                r'\1import java.sql.Timestamp;\n',
                code, count=1
            )
        code = self._add_class_decorations(code)
        code, xml_entries = self._convert_execute_queries(code)
        code = self._replace_self_dao_refs(code)
        code = self._wrap_listmap_for_loops(code)
        code = self._resolve_nested_map_shadowing(code)
        code = self._inject_user_delegation(code)
        code = self._fix_throws(code)
        code = self._remove_trivial_try_catch(code)
        code = self._remove_throws_exception(code)
        code = self._remove_unused_imports(code)
        code = self._cleanup_formatting(code)
        return code, self._build_mapper_xml(xml_entries)

    # ------------------------------------------------------------------ #
    #  내부 메서드                                                          #
    # ------------------------------------------------------------------ #

    def _apply_line_rules(self, code: str) -> str:
        for pattern, replacement in self._LINE_RULES:
            code = re.sub(pattern, replacement, code)
        return code

    def _prefix_common_dao_default_methods(self, code: str) -> str:
        """defaultUpdate/Insert/Delete/VoObjSysValue 호출에 commonDao. 접두사 추가.
        메서드 선언부(`public void defaultUpdate(...)`)는 제외."""
        call_re = re.compile(
            r'(?<!\.)(?<!commonDao\.)(?<!\w)'
            r'(defaultUpdate|defaultInsert|defaultDelete|defaultVoObjSysValue)\b'
        )
        decl_re = re.compile(
            r'\b(?:public|private|protected)\b[^=;{}\n]*?'
            r'\b(?:defaultUpdate|defaultInsert|defaultDelete|defaultVoObjSysValue)\s*\('
        )
        out_lines = []
        for line in code.split('\n'):
            if decl_re.search(line):
                out_lines.append(line)
                continue
            out_lines.append(call_re.sub(r'commonDao.\1', line))
        return '\n'.join(out_lines)

    def _normalize_nonrs_resultset_vars(self, code: str) -> str:
        """`ResultSet tempRs ...;` 처럼 `rs` 로 시작하지 않는 ResultSet 변수의 호출을
        `rs` prefix 변수처럼 치환되도록 표준화한다.
        선언: `ResultSet (\\w+)` 중 `rs` 로 시작 안 하는 변수 → `rsXxx` 형태로 rename.
        같은 변수명이 다른 의미로 쓰일 수 있으므로 호출 패턴(.getString/getDouble/...
        .close/.next) 만 치환한다."""
        rs_vars = set(re.findall(r'\bResultSet\s+(\w+)\s*[=;]', code))
        target_methods = (
            'getString', 'getLong', 'getDouble', 'getInt', 'getTimestamp',
            'getCharacterStream', 'getObject', 'close', 'next',
        )
        for var in rs_vars:
            if var.startswith('rs') or var.startswith('Rs'):
                continue
            new_var = 'rs_' + var
            for mth in target_methods:
                code = re.sub(
                    rf'\b{re.escape(var)}\.{mth}\b', f'{new_var}.{mth}', code
                )
            # 선언/할당/null 체크도 동일 변수명으로 치환
            code = re.sub(
                rf'\bResultSet\s+{re.escape(var)}\b', f'ResultSet {new_var}', code
            )
            code = re.sub(
                rf'\b{re.escape(var)}\s*=\s*(?=\w+(?:\.\w+)?\.executeQuery)',
                f'{new_var} = ', code
            )
            code = re.sub(
                rf'\bif\s*\(\s*{re.escape(var)}\s*!=\s*null\s*\)',
                f'if ({new_var} != null)', code
            )
        return code

    def _resolve_nested_map_shadowing(self, code: str) -> str:
        """중첩 for (Map<String,Object> map : listMapN) 루프에서 inner map 변수 shadow 해소.

        depth N (0=outermost) 의 루프에 대해 N>=1 이면 `map` → `map{N+1}` 로 rename.
        선언부와 body 내 `\\bmap\\b` 참조를 모두 치환 (더 깊은 루프는 backward 처리로
        이미 renamed 되어 있어 정규식이 매치하지 않음)."""
        for_re = re.compile(r'for\s*\(\s*Map<String,\s*Object>\s+map\s*:\s*(\w+)\s*\)\s*\{')
        matches = list(for_re.finditer(code))
        if not matches:
            return code
        # body 범위 (start of `for`, body open `{` 다음, body 닫는 `}` 직전) 계산
        ranges: list[tuple[int, int, int]] = []
        for m in matches:
            body_start = m.end()
            d = 1
            j = body_start
            while j < len(code) and d > 0:
                if code[j] == '{':
                    d += 1
                elif code[j] == '}':
                    d -= 1
                j += 1
            ranges.append((m.start(), body_start, j - 1))
        # 각 루프의 nesting depth: 자기보다 바깥쪽 for-map 루프 개수
        depths: list[int] = []
        for i, (s, _, _) in enumerate(ranges):
            d = 0
            for j, (_, bs2, be2) in enumerate(ranges):
                if i != j and bs2 <= s < be2:
                    d += 1
            depths.append(d)
        # 가장 깊은 것부터 backward 처리 (offset 문제 회피)
        for i in range(len(matches) - 1, -1, -1):
            depth = depths[i]
            if depth == 0:
                continue
            new_var = f'map{depth + 1}'
            s, bs, be = ranges[i]
            old_decl = code[s:bs]
            new_decl = re.sub(r'\bmap\b', new_var, old_decl, count=1)
            body = code[bs:be]
            new_body = re.sub(r'\bmap\b', new_var, body)
            code = code[:s] + new_decl + new_body + code[be:]
        return code

    def _wrap_listmap_for_loops(self, code: str) -> str:
        """for (Map<String, Object> map : listMapXxx) 루프를 null 가드 if 블록으로 감쌈.

        이미 직전 줄에 null 체크가 있으면 건너뜀.
        """
        lines = code.splitlines(keepends=True)
        result: list[str] = []
        i = 0
        for_re = re.compile(
            r'^([ \t]*)for\s*\(\s*Map<String,\s*Object>\s+\w+\s*:\s*(\w+)\s*\)\s*\{'
        )
        while i < len(lines):
            line = lines[i]
            m = for_re.match(line)
            if m:
                indent = m.group(1)
                list_var = m.group(2)
                recent = [r.rstrip() for r in result[-5:] if r.strip()]
                if any(f'{list_var} != null' in r for r in recent):
                    result.append(line)
                    i += 1
                    continue
                # null 가드 삽입 + for 블록 전체 들여쓰기 한 단계 추가
                inner = indent + '    '
                result.append(f'{indent}if ({list_var} != null && !{list_var}.isEmpty()) {{\n')
                result.append(re.sub(r'^' + re.escape(indent), inner, line, count=1))
                i += 1
                depth = 1
                while i < len(lines) and depth > 0:
                    body = lines[i]
                    result.append(re.sub(r'^' + re.escape(indent), inner, body, count=1))
                    depth += body.count('{') - body.count('}')
                    i += 1
                result.append(f'{indent}}}\n')
                continue
            result.append(line)
            i += 1
        return ''.join(result)

    def _add_class_decorations(self, code: str) -> str:
        """@Slf4j / @RequiredArgsConstructor / @Repository 추가 및 필드 삽입."""
        # extends CommonDao 제거 (필드 주입 방식으로 전환)
        code = re.sub(r'\s+extends\s+CommonDao\b', '', code)
        anns = '@Slf4j\n@RequiredArgsConstructor\n@Repository\n'
        code = re.sub(r'(public\s+class\s+)', anns + r'\1', code, count=1)
        fields = (
            '\n    private final CommonDao commonDao;'
            '\n    private final UxbDAO uxbDAO;\n'
        )
        needs_pk = bool(re.search(r'\bpkGenerator\.', code))
        needs_cf = bool(re.search(r'\bcommonFunction\.', code))
        needs_attach = bool(re.search(r'\battachFileInfo\.', code))
        if needs_pk:
            fields += '    private final PKGenerator pkGenerator;\n'
        if needs_cf:
            fields += '    private final CommonFunction commonFunction;\n'
        if needs_attach:
            fields += '    private final CCDAttachFileInfo attachFileInfo;\n'
        # 메서드 내부 다른 DAO 클래스 로컬 선언 → 필드 주입
        dao_inject_re = re.compile(
            r'^[ \t]*(\w+DAO\d*)\s+(\w+)\s*=\s*new\s+\1\s*\(\s*\)\s*;\n?',
            re.MULTILINE
        )
        dao_injections: dict[str, str] = {}
        for _dm in dao_inject_re.finditer(code):
            cls, var = _dm.group(1), _dm.group(2)
            if cls != self.class_name:
                dao_injections[var] = cls
        if dao_injections:
            code = dao_inject_re.sub(
                lambda m: '' if m.group(1) != self.class_name else m.group(0),
                code
            )
            for var, cls in dao_injections.items():
                fields += f'    private final {cls} {var};\n'
        code = re.sub(r'(public\s+class\s+\w+[^{]*\{)', r'\1' + fields, code, count=1)
        # 필요한 import 추가 (package 선언 바로 뒤)
        if 'import com.pan.som.common.utility.CommonDao' not in code:
            code = re.sub(
                r'(package\s+[\w.]+;\s*\n)',
                r'\1import com.pan.som.common.utility.CommonDao;\n',
                code, count=1
            )
        if needs_pk and 'import com.pan.som.common.dao.PKGenerator' not in code:
            code = re.sub(
                r'(package\s+[\w.]+;\s*\n)',
                r'\1import com.pan.som.common.dao.PKGenerator;\n',
                code, count=1
            )
        if needs_cf and 'import com.pan.som.function.salesOpportunity.CommonFunction' not in code:
            code = re.sub(
                r'(package\s+[\w.]+;\s*\n)',
                r'\1import com.pan.som.function.salesOpportunity.CommonFunction;\n',
                code, count=1
            )
        if needs_attach and 'import com.pan.som.function.standardInfo.CCDAttachFileInfo' not in code:
            code = re.sub(
                r'(package\s+[\w.]+;\s*\n)',
                r'\1import com.pan.som.function.standardInfo.CCDAttachFileInfo;\n',
                code, count=1
            )
        return code

    def _replace_self_dao_refs(self, code: str) -> str:
        """같은 DAO 클래스 인스턴스 생성 후 메서드 호출을 this.xxx() 로 교체."""
        # XxxDAO varName = new XxxDAO(); 선언 제거
        decl_re = re.compile(
            rf'[ \t]*\b{re.escape(self.class_name)}\s+(\w+)\s*=\s*new\s+{re.escape(self.class_name)}\s*\(\s*\)\s*;\n?'
        )
        var_names: list[str] = []
        for m in decl_re.finditer(code):
            var_names.append(m.group(1))
        code = decl_re.sub('', code)
        # varName.methodCall( → this.methodCall( (패키지/import 경로의 .dao. 는 제외)
        for var in var_names:
            code = re.sub(rf'(?<!\.)\b{re.escape(var)}\.', 'this.', code)
        return code

    def _convert_execute_queries(self, code: str) -> tuple[str, list[dict]]:
        """PreparedStatement 패턴을 uxbDAO.select/update() 로 변환하고 SQL을 Mapper XML로 추출."""
        xml_entries: dict = {}
        method_query_count: dict[str, int] = {}
        # (method_name, rs_var) → list_var 매핑: prepareStatement→executeQuery 체인 추적
        self._rs_list_var_map: dict[tuple[str, str], str] = {}

        prep_re = re.compile(
            r'(\w+)\s*=\s*(?:conn|connection)\.prepareStatement\((\w+)\.toString\(\)\)\s*;'
        )

        # 메서드별 쿼리 수 사전 집계 (변수명 suffix 결정용) — 블록 주석 내부 제외
        method_total_count: dict[str, int] = {}
        for _pm in prep_re.finditer(code):
            if self._is_in_block_comment(code, _pm.start()):
                continue
            _mn = self._enclosing_method(code, _pm.start())
            if _mn:
                method_total_count[_mn] = method_total_count.get(_mn, 0) + 1

        offset = 0
        result_code = code

        for prep_match in prep_re.finditer(code):
            # 블록 주석(/* ... */) 내부 prepareStatement 는 건너뜀
            if self._is_in_block_comment(code, prep_match.start()):
                continue
            sb_var = prep_match.group(2)
            method_name = self._enclosing_method(code, prep_match.start())
            if not method_name:
                continue

            # executeUpdate vs executeQuery 판별 (호출 근접성으로 우선 판단)
            after = code[prep_match.end():prep_match.end() + 800]
            is_update = bool(re.search(r'\bexecuteUpdate\(\)', after))

            idx = method_query_count.get(method_name, 0)
            method_query_count[method_name] = idx + 1
            mapper_id = method_name if idx == 0 else f"{method_name}{idx}"

            total = method_total_count.get(method_name, 1)
            suffix = str(idx + 1) if total > 1 else ''
            param_var = f'paramMap{suffix}'
            list_var = f'listMap{suffix}'

            # rs_var → list_var 매핑: pstmt 재할당 전까지의 executeQuery() 호출에서 rs 변수 추출
            pstmt_var = prep_match.group(1)
            next_prep_re = re.compile(
                rf'\b{re.escape(pstmt_var)}\s*=\s*(?:conn|connection)\.prepareStatement\b'
            )
            next_prep_m = next_prep_re.search(code, prep_match.end())
            scope_end = next_prep_m.start() if next_prep_m else len(code)
            exec_m = re.search(
                rf'\b(\w+)\s*=\s*{re.escape(pstmt_var)}\.executeQuery\(\)',
                code[prep_match.end():scope_end]
            )
            if exec_m:
                self._rs_list_var_map[(method_name, exec_m.group(1))] = list_var

            # SQL 추출 (prepareStatement 이전, 현재 메서드 범위만)
            before = code[:prep_match.start()]
            sql_parts, param_pairs = self._extract_sql_and_params(before, sb_var)

            # SQL 본문 키워드로 타입 보강 (executeUpdate 호출이 멀리 있어도 보강)
            sql_type = self._detect_sql_type(' '.join(sql_parts))
            if sql_type != 'select':
                is_update = True
            elif is_update:
                sql_type = 'update'  # executeUpdate 호출은 있는데 첫 키워드 못 잡은 케이스

            # if/else 분기가 각각 완전한 SQL을 빌드하는지 감지
            split_result = self._detect_if_else_query_split(before, sb_var)

            if is_update:
                ordered_params = self._extract_update_params(code, prep_match.end())
                sql_xml = self._replace_positional_params(
                    ' '.join(sql_parts).strip(), ordered_params
                )
                xml_entries[mapper_id] = {
                    'id': mapper_id, 'sql': sql_xml,
                    'params': [k for k, _ in ordered_params], 'type': sql_type,
                }
            elif split_result:
                # if/else 분기별 XML 2개 생성
                java_cond, if_sql_parts, else_sql_parts, split_param_pairs = split_result
                else_mapper_id = f"{method_name}{idx + 1}"
                method_query_count[method_name] += 1  # 분기 엔트리 추가 카운트

                if_sql_xml = ' '.join(if_sql_parts).strip()
                else_sql_xml = ' '.join(else_sql_parts).strip()
                if_type = self._detect_sql_type(if_sql_xml)
                else_type = self._detect_sql_type(else_sql_xml)
                xml_entries[mapper_id] = {
                    'id': mapper_id, 'sql': if_sql_xml,
                    'params': [k for k, _ in split_param_pairs], 'type': if_type,
                }
                xml_entries[else_mapper_id] = {
                    'id': else_mapper_id, 'sql': else_sql_xml,
                    'params': [k for k, _ in split_param_pairs], 'type': else_type,
                }
            else:
                sql_xml = ' '.join(sql_parts).strip()
                # SQL 에 `?` 잔여 플레이스홀더가 있으면 ps.setXxx 에서 파라미터 추출해 #{} 치환
                ordered_params = []
                if '?' in sql_xml:
                    ordered_params = self._extract_update_params(code, prep_match.end())
                    if ordered_params:
                        sql_xml = self._replace_positional_params(sql_xml, ordered_params)
                # param_pairs (sb.append + 조건변수) + ordered_params (ps.setXxx) 병합 (key 중복 제거)
                merged_pairs: list[tuple[str, str]] = []
                seen_keys: set[str] = set()
                for k, v in param_pairs + ordered_params:
                    if k not in seen_keys:
                        seen_keys.add(k)
                        merged_pairs.append((k, v))
                ordered_params = merged_pairs
                xml_entries[mapper_id] = {
                    'id': mapper_id, 'sql': sql_xml,
                    'params': [k for k, _ in merged_pairs],
                    'type': 'select',
                }

            # sb 선언부터 prepareStatement 줄까지를 java_call 로 교체
            adjusted_start = prep_match.start() + offset
            # 타입 선언(StringBuffer sb = new StringBuffer()) 및 재할당(sb = new StringBuffer()) 모두 처리
            sb_decl_re = re.compile(
                rf'([ \t]*)(?:(?:String\w*|StringBuilder|StringBuffer)\s+)?{re.escape(sb_var)}'
                rf'\s*=\s*new\s+(?:StringBuffer|StringBuilder)\s*\([^)\n]*\)\s*;'
            )
            method_orig_start = self._find_method_start_pos(code, prep_match.start())
            method_to_prep = prep_match.start() - method_orig_start
            search_from = max(0, adjusted_start - method_to_prep - 200)
            # 메서드 경계를 넘지 않는 가장 마지막 sb 선언을 탐색
            # (search 대신 finditer 루프: 이전 메서드의 sb 를 잘못 참조하는 버그 방지)
            sb_match = None
            for _m in sb_decl_re.finditer(result_code, search_from):
                if _m.start() >= adjusted_start:
                    break
                between = result_code[_m.end():adjusted_start]
                if not re.search(r'\b(?:public|private|protected)\s+\S+\s+\w+\s*\(', between):
                    sb_match = _m
            if sb_match and sb_match.start() < adjusted_start:
                # sb 선언의 들여쓰기를 기준으로 java_call 생성
                base = sb_match.group(1)
                inner = base + ('\t' if '\t' in base else '    ')

                if split_result and not is_update:
                    # if/else 분기 SQL: sb init ~ prepareStatement 전체를 교체
                    java_cond, if_sql_parts, else_sql_parts, split_param_pairs = split_result
                    replace_start = sb_match.start()

                    lines = [f'{base}Map<String, Object> {param_var} = new HashMap<>();']
                    for key, val in split_param_pairs:
                        lines.append(f'{inner}{param_var}.put("{key}", {val});')
                    lines.append(f'{base}List<Map<String, Object>> {list_var} = new ArrayList<>();')
                    lines.append(f'{base}if ({java_cond}) {{')
                    lines.append(f'{inner}{list_var} = uxbDAO.select("{self.namespace}.{mapper_id}", {param_var});')
                    lines.append(f'{base}}} else {{')
                    lines.append(f'{inner}{list_var} = uxbDAO.select("{self.namespace}.{else_mapper_id}", {param_var});')
                    lines.append(f'{base}}}')
                    java_call = '\n'.join(lines)
                else:
                    # 교체 범위 전체에서 sb/log/conn 관련 줄만 제거하고 나머지 보존
                    range_text = result_code[sb_match.start():adjusted_start]
                    range_text = re.sub(r'/\*.*?\*/', '', range_text, flags=re.DOTALL)
                    preamble_parts = []
                    for _line in range_text.splitlines(keepends=True):
                        _s = _line.strip()
                        if not _s:
                            continue
                        # sb 선언 제거 (타입 선언 + 재할당 모두)
                        if re.match(rf'(?:(?:String(?:Buffer|Builder))\s+)?{re.escape(sb_var)}\s*=\s*new\s+(?:StringBuffer|StringBuilder)\s*\(', _s):
                            continue
                        # sb. 관련 (sb.append 등) 제거
                        if re.search(rf'\b{re.escape(sb_var)}\.', _s):
                            continue
                        # conn./connection. 관련 제거
                        if re.search(r'\b(?:conn|connection)\.', _s):
                            continue
                        # log. 제거
                        if re.match(r'log\.', _s):
                            continue
                        # 주석 라인 제거 (//, /*, *)
                        if re.match(r'(//|/\*|\*)', _s):
                            continue
                        preamble_parts.append(_line)
                    preamble = ''.join(preamble_parts)

                    if is_update:
                        call_method = self._java_call_for_type(sql_type)
                        lines = [f'{base}Map<String, Object> {param_var} = new HashMap<>();']
                        for key, val in ordered_params:
                            lines.append(f'{inner}{param_var}.put("{key}", {val});')
                        lines.append(f'{inner}uxbDAO.{call_method}("{self.namespace}.{mapper_id}", {param_var});')
                    else:
                        lines = [f'{base}Map<String, Object> {param_var} = new HashMap<>();']
                        effective_params = ordered_params if ordered_params else param_pairs
                        for key, val in effective_params:
                            lines.append(f'{inner}{param_var}.put("{key}", {val});')
                        lines.append(
                            f'{inner}List<Map<String, Object>> {list_var} = '
                            f'uxbDAO.select("{self.namespace}.{mapper_id}", {param_var});'
                        )
                    java_call = preamble + '\n'.join(lines)
                    replace_start = sb_match.start()
                prep_line_end = result_code.index('\n', adjusted_start) + 1
                result_code = (
                    result_code[:replace_start] + java_call + '\n'
                    + result_code[prep_line_end:]
                )
                offset += len(java_call) + 1 - (prep_line_end - replace_start)

            else:
                # sb 선언을 찾지 못한 경우 (else 분기 등): sb.append 위치를 기준으로 대체
                append_re_fb = re.compile(
                    rf'^([ \t]*){re.escape(sb_var)}\.append\(',
                    re.MULTILINE
                )
                first_append_fb = None
                for _am in append_re_fb.finditer(result_code, search_from, adjusted_start):
                    if first_append_fb is None:
                        first_append_fb = _am
                if first_append_fb is not None:
                    base = first_append_fb.group(1)
                    inner = base + ('\t' if '\t' in base else '    ')
                    replace_start = first_append_fb.start()
                    if is_update:
                        call_method = self._java_call_for_type(sql_type)
                        lines = [f'{base}Map<String, Object> {param_var} = new HashMap<>();']
                        for key, val in ordered_params:
                            lines.append(f'{inner}{param_var}.put("{key}", {val});')
                        lines.append(f'{inner}uxbDAO.{call_method}("{self.namespace}.{mapper_id}", {param_var});')
                    else:
                        lines = [f'{base}Map<String, Object> {param_var} = new HashMap<>();']
                        effective_params = ordered_params if ordered_params else param_pairs
                        for key, val in effective_params:
                            lines.append(f'{inner}{param_var}.put("{key}", {val});')
                        lines.append(
                            f'{inner}List<Map<String, Object>> {list_var} = '
                            f'uxbDAO.select("{self.namespace}.{mapper_id}", {param_var});'
                        )
                    java_call = '\n'.join(lines)
                    prep_line_end = result_code.index('\n', adjusted_start) + 1
                    result_code = (
                        result_code[:replace_start] + java_call + '\n'
                        + result_code[prep_line_end:]
                    )
                    offset += len(java_call) + 1 - (prep_line_end - replace_start)

        # if (cond) ps/pstmt.setXxx(i++, ...) 인라인 형태 통째 제거
        result_code = re.sub(
            r'[ \t]*if\s*\([^{]+?\)\s*ps\w*\.set(?:Long|String|Int|Double|Timestamp|Object)\b[^\n]*;\n?',
            '', result_code
        )
        # PreparedStatement 인덱스 카운터 (int i = 1;) 제거 — 루프 카운터(int i = 0;)는 유지
        result_code = re.sub(r'^[ \t]*\bint\s+i\s*=\s*1\s*;\n?', '', result_code, flags=re.MULTILINE)
        # sb.append 제거 후 남은 빈 if/else 블록 정리 — 중첩/연쇄 케이스 위해 수렴할 때까지 반복
        for _ in range(8):
            prev = result_code
            # 빈 if/else-if (뒤에 else/else-if 가 이어지지 않을 때만)
            result_code = re.sub(
                r'[ \t]*(?:else\s+)?if\b[^\n{]*\{\s*\}(?!\s*(?:else\s+if\b|else\s*\{))\s*\n?',
                '', result_code,
            )
            # 빈 else
            result_code = re.sub(r'[ \t]*else\s*\{\s*\}\s*\n?', '', result_code)
            # 빈 if {} else {empty body 가 또 다른 if-else 체인을 포함} 케이스: 내부 정리 후 남은 빈 if-else
            result_code = re.sub(
                r'[ \t]*if\b[^\n{]*\{\s*\}\s*else\s*\{\s*\}\s*\n?', '', result_code,
            )
            if result_code == prev:
                break

        # } else { throw ... } 패턴에서 else-throw 블록만 제거, 닫는 } 는 보존
        result_code = re.sub(
            r'(\})\s*else\s*\{\s*throw\s+new\s+\w+\s*\(\s*"[^"]*"\s*\)\s*;\s*\}',
            r'\1',
            result_code,
            flags=re.DOTALL,
        )

        # 리터럴 SQL prepareStatement 처리: conn.prepareStatement("SQL") → uxbDAO.select/update
        lit_prep_re = re.compile(
            r'^([ \t]*)(\w+)\s*=\s*(?:conn|connection)\.prepareStatement\("([^"]+)"\)\s*;$',
            re.MULTILINE
        )
        for lit_m in reversed(list(lit_prep_re.finditer(result_code))):
            if self._is_in_block_comment(result_code, lit_m.start()):
                continue
            base = lit_m.group(1)
            sql_literal = lit_m.group(3).strip()
            method_name = self._enclosing_method(result_code, lit_m.start())
            if not method_name:
                continue
            after_lit = result_code[lit_m.end():lit_m.end() + 600]
            is_update_lit = bool(re.search(r'\bexecuteUpdate\(\)', after_lit))
            sql_type_lit = self._detect_sql_type(sql_literal)
            if sql_type_lit != 'select':
                is_update_lit = True
            elif is_update_lit:
                sql_type_lit = 'update'
            idx = method_query_count.get(method_name, 0)
            method_query_count[method_name] = idx + 1
            mapper_id = method_name if idx == 0 else f"{method_name}{idx}"
            lit_params = self._extract_update_params(result_code, lit_m.end())
            sql_with_params = self._replace_positional_params(sql_literal, lit_params)
            xml_entries[mapper_id] = {
                'id': mapper_id, 'sql': sql_with_params,
                'params': [k for k, _ in lit_params],
                'type': sql_type_lit if is_update_lit else 'select',
            }
            inner = base + '    '
            total_m = method_total_count.get(method_name, 1)
            pv = f'paramMap{idx + 1}' if total_m > 1 else 'paramMap'
            lv = f'listMap{idx + 1}' if total_m > 1 else 'listMap'
            call_lines = [f'{base}Map<String, Object> {pv} = new HashMap<>();']
            for key, val in lit_params:
                call_lines.append(f'{inner}{pv}.put("{key}", {val});')
            if is_update_lit:
                call_method = self._java_call_for_type(sql_type_lit)
                call_lines.append(f'{inner}uxbDAO.{call_method}("{self.namespace}.{mapper_id}", {pv});')
            else:
                call_lines.append(
                    f'{inner}List<Map<String, Object>> {lv} = '
                    f'uxbDAO.select("{self.namespace}.{mapper_id}", {pv});'
                )
            java_call = '\n'.join(call_lines)
            prep_end = result_code.index('\n', lit_m.start()) + 1
            result_code = result_code[:lit_m.start()] + java_call + '\n' + result_code[prep_end:]

        # 잔여 execute 호출 및 ps.setXxx() 제거 (줄 단위로 매칭)
        result_code = re.sub(r'[ \t]*\w+\s*=\s*\w+\.executeQuery\(\)\s*;\n?', '', result_code)
        result_code = re.sub(r'[ \t]*\w+\.executeUpdate\(\)\s*;\n?', '', result_code)
        result_code = re.sub(
            r'[ \t]*\bps\w*\.set(?:Long|String|Int|Double|Timestamp|Object)\b[^\n]*;\n?',
            '', result_code
        )
        # 잔여 conn/connection.prepareStatement() 호출 제거 (변환 실패한 케이스 정리)
        result_code = re.sub(r'[ \t]*\w+\s*=\s*(?:conn|connection)\.prepareStatement\([^\n]+\)\s*;\n?', '', result_code)
        # SQL builder 변수 null 리셋 잔여 구문 제거 (sb = null;, sql = null; 등)
        result_code = re.sub(r'[ \t]*\b(?:sb|sql)\w*\s*=\s*null\s*;\n?', '', result_code)

        # ps.setXxx 제거 후 if 블록만 남은 블록 주석 정리 (/* \n if(cond){ \n }*/ 형태)
        result_code = re.sub(r'/\*\s*\n\s*if[^\n]*\n\s*\}\s*\*/', '', result_code)
        # 완전히 비거나 공백만 있는 블록 주석 제거
        result_code = re.sub(r'/\*\s*\*/', '', result_code)

        # while/if rs.next() 및 if (rs != null) { 를 listMapN 으로 교체
        result_code = self._fix_rs_patterns(result_code)

        # 빈 finally 블록 정리 (내용이 순수 공백만 남은 경우만 제거)
        result_code = re.sub(r'[ \t]*finally\s*\{\s*\}', '', result_code)

        # sb 선언이 제거된 후 남는 orphan log 라인 (.toString() 포함) 제거
        result_code = re.sub(r'[ \t]*log\.\w+\([^\n]*\.toString\(\)[^\n]*\);\n?', '', result_code)
        # 잔류 String sql = ... 선언 제거
        result_code = re.sub(r'[ \t]*String\s+sql\w*\s*=\s*[^\n]+;\n?', '', result_code)

        return result_code, list(xml_entries.values())

    def _detect_if_else_query_split(
        self, before: str, sb_var: str
    ) -> tuple[str, list[str], list[str], list[tuple[str, str]]] | None:
        """
        if/else 각 분기에서 sb.append() 로 독립적인 완전한 SQL을 빌드하는 패턴 감지.
        - 단일 선언 후 if/else append: sb=new...; if{ sb.append(many) } else{ sb.append(many) }
        - 분기별 재선언: if{ sb=new...; sb.append... } else{ sb=new...; sb.append... }
        (java_cond, if_sql_parts, else_sql_parts, param_pairs) 반환, 없으면 None.
        """
        sb_init_re = re.compile(
            rf'(?:(?:StringBuilder|StringBuffer)\s+)?{re.escape(sb_var)}\s*=\s*new\s+(?:StringBuffer|StringBuilder)\s*\('
        )
        inits = list(sb_init_re.finditer(before))
        if not inits:
            return None

        # 마지막 sb 초기화 이후 영역에서 } else { 탐색
        last_init_pos = inits[-1].start()
        after_init = before[last_init_pos:]

        # outer if-else 의 `}else{` 만 매칭 (중첩 `}else{` 는 brace depth 로 배제)
        # outer 의 닫는 `}` 직후 depth 는 0 이어야 함
        else_m = None
        for cand in re.finditer(r'\}\s*else\s*\{', after_init):
            depth = 0
            for i in range(cand.start() + 1):
                ch = after_init[i]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
            if depth == 0:
                else_m = cand
                break
        if else_m is None:
            return None

        # else if 가 있으면 3분기 → _find_multi_branch_choose 에서 처리
        if re.search(r'\}\s*else\s+if\s*\(', after_init[:else_m.start()]):
            return None

        # if-branch 영역과 else-branch 영역 모두에 sb.append() 가 있어야 함
        append_re_s = re.compile(rf'\b{re.escape(sb_var)}\.append\(')
        before_else = after_init[:else_m.start()]
        after_else = after_init[else_m.end():]
        if not append_re_s.search(before_else) or not append_re_s.search(after_else):
            return None

        # outer else-branch 의 닫는 `}` 이후에도 sb.append 가 있으면
        # 단일 쿼리가 if-else 뒤로 더 빌드되는 케이스 → split 포기
        else_brace_open = else_m.end() - 1
        bdepth = 0
        else_close_pos = -1
        for i in range(else_brace_open, len(after_init)):
            ch = after_init[i]
            if ch == '{':
                bdepth += 1
            elif ch == '}':
                bdepth -= 1
                if bdepth == 0:
                    else_close_pos = i
                    break
        if else_close_pos != -1 and append_re_s.search(after_init[else_close_pos + 1:]):
            return None

        # 조건부 WHERE 절 감지: if 블록 이전에 sb.append 가 있으면 단일 쿼리 → 분리 안 함
        first_if_m = re.search(r'\bif\s*\(', before_else)
        if first_if_m and append_re_s.search(before_else[:first_if_m.start()]):
            return None

        # if(condition) 추출: if-branch 의 첫 sb.append 직전에서 탐색
        first_append_m = append_re_s.search(before_else)
        text_to_first = before_else[:first_append_m.start()]
        java_cond = None
        for m in re.finditer(r'\bif\s*\((.+?)\)\s*\{', text_to_first, re.DOTALL):
            java_cond = m.group(1).strip()
        if java_cond is None:
            # 분기별 재선언 케이스: if(cond)가 마지막 init 이전에 있음
            for m in re.finditer(r'\bif\s*\((.+?)\)\s*\{', before[:last_init_pos], re.DOTALL):
                java_cond = m.group(1).strip()
        if java_cond is None:
            return None

        # if-branch SQL: last_init_pos ~ } else { 직전
        if_region = before[last_init_pos:last_init_pos + else_m.start()]
        # else-branch SQL: } else { 이후 ~ 끝
        else_region = before[last_init_pos + else_m.end():]

        if_sql_parts, if_param_pairs = self._extract_sql_and_params(if_region, sb_var)
        else_sql_parts, else_param_pairs = self._extract_sql_and_params(else_region, sb_var)

        if not if_sql_parts and not else_sql_parts:
            return None

        # 두 분기의 파라미터를 합치되 key 중복 제거
        seen_keys: set[str] = set()
        combined_pairs: list[tuple[str, str]] = []
        for k, v in if_param_pairs + else_param_pairs:
            if k not in seen_keys:
                seen_keys.add(k)
                combined_pairs.append((k, v))

        return java_cond, if_sql_parts, else_sql_parts, combined_pairs

    def _fix_rs_patterns(self, code: str) -> str:
        """while/if rs.next() 및 if (rs != null) { 를 매핑된 listMapN 변수로 교체."""
        list_decl_re = re.compile(r'\bList<Map<String, Object>>\s+(listMap\d*)\b')
        rs_map = getattr(self, '_rs_list_var_map', {})

        def nearest_list_var(snapshot: str, pos: int) -> str:
            best = 'listMap'
            for m in list_decl_re.finditer(snapshot):
                if m.start() < pos:
                    best = m.group(1)
                else:
                    break
            return best

        def lookup_list_var(snapshot: str, pos: int, rs_var: str) -> str:
            method_name = self._enclosing_method(snapshot, pos)
            if method_name and (method_name, rs_var) in rs_map:
                return rs_map[(method_name, rs_var)]
            return nearest_list_var(snapshot, pos)

        # 1. while (rs.next()) → for (Map<String, Object> map : listVarN)
        parts: list[str] = []
        last = 0
        for m in re.finditer(r'while\s*\(\s*(\w+)\.next\(\)\s*\)', code):
            lv = lookup_list_var(code, m.start(), m.group(1))
            parts.append(code[last:m.start()])
            parts.append(f'for (Map<String, Object> map : {lv})')
            last = m.end()
        parts.append(code[last:])
        code = ''.join(parts)

        # 2. if (rs.next()) { → if (listVarN != null && !listVarN.isEmpty()) { + map 선언
        parts = []
        last = 0
        for m in re.finditer(r'([ \t]*)if\s*\(\s*(\w+)\.next\(\)\s*\)\s*\{', code):
            lv = lookup_list_var(code, m.start(), m.group(2))
            indent = m.group(1)
            parts.append(code[last:m.start()])
            parts.append(
                f'{indent}if ({lv} != null && !{lv}.isEmpty()) {{\n'
                f'{indent}    Map<String, Object> map = {lv}.get(0);'
            )
            last = m.end()
        parts.append(code[last:])
        code = ''.join(parts)

        # 3. if (rs != null) { → if (listVarN != null && !listVarN.isEmpty()) {
        # 단, 블록 내에 for (Map<String, Object> map : ...) 가 있을 때만 변환
        parts = []
        last = 0
        for m in re.finditer(r'\bif\s*\(\s*(rs\w*)\s*!=\s*null\s*\)\s*\{', code):
            rest = code[m.end():]
            depth = 1
            block_end = len(rest)
            for ci, ch in enumerate(rest):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                if depth == 0:
                    block_end = ci
                    break
            block_content = rest[:block_end]
            if not re.search(r'for\s*\(\s*Map<String,\s*Object>', block_content):
                continue
            lv = lookup_list_var(code, m.start(), m.group(1))
            parts.append(code[last:m.start()])
            parts.append(f'if ({lv} != null && !{lv}.isEmpty()) {{')
            last = m.end()
        parts.append(code[last:])
        code = ''.join(parts)

        return code

    def _enclosing_method(self, code: str, pos: int) -> str:
        """pos 이전에서 가장 가까운 메서드 이름을 반환."""
        pattern = re.compile(r'\b(?:public|private|protected)\s+\S+\s+(\w+)\s*\(')
        name = ''
        for m in pattern.finditer(code[:pos]):
            name = m.group(1)
        return name

    def _java_condition_to_mybatis(self, java_cond: str) -> str:
        """Java if 조건식 → MyBatis <if test="..."> 조건식 변환."""
        cond = java_cond.strip()

        def decap(s: str) -> str:
            return s[0].lower() + s[1:] if s else s

        # 1. !"".equals(varName) → @kr.co.takeit.util.MybatisUtil@notEmpty( varName )
        cond = re.sub(
            r'!\s*""\s*\.equals\s*\(\s*(\w+)\s*\)',
            lambda m: f"@kr.co.takeit.util.MybatisUtil@notEmpty( {m.group(1)} )",
            cond,
        )
        # 1b. "".equals(varName) → @kr.co.takeit.util.MybatisUtil@empty( varName )
        cond = re.sub(
            r'""\s*\.equals\s*\(\s*(\w+)\s*\)',
            lambda m: f"@kr.co.takeit.util.MybatisUtil@empty( {m.group(1)} )",
            cond,
        )

        # 1c. !''.equals(dto.getXxx()) → @kr.co.takeit.util.MybatisUtil@notEmpty( xxx )
        cond = re.sub(
            r"!\s*''\s*\.equals\s*\(\s*(?:\w+\.)?get([A-Z]\w*)\s*\(\s*\)\s*\)",
            lambda m: f"@kr.co.takeit.util.MybatisUtil@notEmpty( {decap(m.group(1))} )",
            cond,
        )

        # 2. Formatter.nullTrim(...) 제거 (조건식 내)
        cond = re.sub(r'Formatter\.nullTrim\s*\(\s*(.+?)\s*\)', r'\1', cond)

        # 3. 'CONST'.equals(dto.getField()) → field == 'CONST'
        cond = re.sub(
            r"'([^']*)'\s*\.\s*equals\s*\(\s*(?:\w+\.)?get([A-Z]\w*)\s*\(\s*\)\s*\)",
            lambda m: f"{decap(m.group(2))} == '{m.group(1)}'",
            cond,
        )

        # 4. dto.getField().equals('CONST') → field == 'CONST'
        cond = re.sub(
            r"(?:\w+\.)?get([A-Z]\w*)\s*\(\s*\)\s*\.\s*equals\s*\(\s*'([^']*)'\s*\)",
            lambda m: f"{decap(m.group(1))} == '{m.group(2)}'",
            cond,
        )

        # 5. null != dto.getField() → field != null
        cond = re.sub(
            r"null\s*!=\s*(?:\w+\.)?get([A-Z]\w*)\s*\(\s*\)",
            lambda m: f"{decap(m.group(1))} != null",
            cond,
        )

        # 6. 숫자 != nullLong(getXxx()) → xxx != 0 and xxx != null
        cond = re.sub(
            r"(?:\b\w+\b|\d+)\s*!=\s*(?:Formatter\.)?nullLong\s*\(\s*(?:\w+\.)?get([A-Z]\w*)\s*\(\s*\)\s*\)",
            lambda m: f"{decap(m.group(1))} != 0 and {decap(m.group(1))} != null",
            cond,
        )

        # 6b. Formatter.nullLong(simpleVar) != 0 → simpleVar != 0
        cond = re.sub(
            r"(?:Formatter\.)?nullLong\s*\(\s*(\w+)\s*\)\s*!=\s*0",
            lambda m: f"{m.group(1)} != 0",
            cond,
        )

        # 7. obj.getXxx().longValue() 등 래퍼메서드 포함 비교
        cond = re.sub(
            r'(?:\w+\.)?get(\w+)\(\)\.\w+\(\)\s*(!=|==|>|<|>=|<=)\s*(\w+)',
            lambda m: f"{decap(m.group(1))} {m.group(2)} {m.group(3)}",
            cond,
        )

        # 8. obj.getXxx() 비교 (단순)
        cond = re.sub(
            r'(?:\w+\.)?get(\w+)\(\)\s*(!=|==|>|<|>=|<=)\s*(\S+)',
            lambda m: f"{decap(m.group(1))} {m.group(2)} {m.group(3)}",
            cond,
        )

        # 9. 잔여 getXxx() → 프로퍼티명
        cond = re.sub(
            r'(?:\w+\.)?get([A-Z]\w*)\s*\(\s*\)',
            lambda m: decap(m.group(1)),
            cond,
        )

        # 10. && → and, || → or
        cond = cond.replace('&&', 'and').replace('||', 'or')

        # 11. 남은 큰따옴표 문자열 리터럴 → 작은따옴표 (MyBatis <if test="..."> 속성 충돌 방지)
        cond = re.sub(r'"([^"]*)"', r"'\1'", cond)

        return cond.strip()

    def _find_block_end(self, code: str, open_brace_pos: int) -> int:
        """{ 로 시작하는 블록의 닫는 } 위치 반환."""
        depth = 0
        for i in range(open_brace_pos, len(code)):
            if code[i] == '{':
                depth += 1
            elif code[i] == '}':
                depth -= 1
                if depth == 0:
                    return i
        return -1

    def _find_multi_branch_choose(
        self, code: str, sb_var: str, search_from: int
    ) -> tuple[int, int, str, list[tuple[str, str]]] | None:
        """
        if { sb.appends } else if { sb.appends } else { sb.appends } 3분기 패턴 감지.
        Returns: (block_start, block_end, choose_xml, param_pairs) or None.
        """
        append_re_s = re.compile(rf'\b{re.escape(sb_var)}\.append\(')
        if_re = re.compile(r'\bif\s*\(')

        for if_m in if_re.finditer(code, search_from):
            pos = if_m.start()
            line_start = code.rfind('\n', 0, pos) + 1
            if '//' in code[line_start:pos]:
                continue

            # if ( cond ) 추출
            paren_start = code.index('(', pos)
            depth = 0
            cond_end = paren_start
            for i in range(paren_start, len(code)):
                if code[i] == '(':
                    depth += 1
                elif code[i] == ')':
                    depth -= 1
                    if depth == 0:
                        cond_end = i
                        break
            cond1 = code[paren_start + 1:cond_end].strip()

            brace1 = code.find('{', cond_end)
            if brace1 == -1:
                continue
            end1 = self._find_block_end(code, brace1)
            if end1 == -1:
                continue
            branch1_code = code[brace1 + 1:end1]

            # else if 체크
            rest1 = code[end1 + 1:]
            elif_m = re.match(r'\s*else\s+if\s*\(', rest1)
            if not elif_m:
                continue

            paren2_start = end1 + 1 + rest1.index('(', elif_m.start())
            depth = 0
            cond_end2 = paren2_start
            for i in range(paren2_start, len(code)):
                if code[i] == '(':
                    depth += 1
                elif code[i] == ')':
                    depth -= 1
                    if depth == 0:
                        cond_end2 = i
                        break
            cond2 = code[paren2_start + 1:cond_end2].strip()

            brace2 = code.find('{', cond_end2)
            if brace2 == -1:
                continue
            end2 = self._find_block_end(code, brace2)
            if end2 == -1:
                continue
            branch2_code = code[brace2 + 1:end2]

            # else 체크
            rest2 = code[end2 + 1:]
            else_m = re.match(r'\s*else\s*\{', rest2)
            if not else_m:
                continue

            brace3_abs = end2 + 1 + rest2.index('{', else_m.start())
            end3 = self._find_block_end(code, brace3_abs)
            if end3 == -1:
                continue
            branch3_code = code[brace3_abs + 1:end3]

            # 각 분기에 append가 있어야 함
            if not (append_re_s.search(branch1_code) and
                    append_re_s.search(branch2_code) and
                    append_re_s.search(branch3_code)):
                continue

            sql1, params1 = self._extract_sql_and_params(branch1_code, sb_var)
            sql2, params2 = self._extract_sql_and_params(branch2_code, sb_var)
            sql3, params3 = self._extract_sql_and_params(branch3_code, sb_var)

            mc1 = self._java_condition_to_mybatis(cond1)
            mc2 = self._java_condition_to_mybatis(cond2)

            choose_xml = (
                f'\n<choose>\n'
                f'    <when test="{mc1}">\n'
                f'        {" ".join(sql1).strip()}\n'
                f'    </when>\n'
                f'    <when test="{mc2}">\n'
                f'        {" ".join(sql2).strip()}\n'
                f'    </when>\n'
                f'    <otherwise>\n'
                f'        {" ".join(sql3).strip()}\n'
                f'    </otherwise>\n'
                f'</choose>'
            )

            seen: set[str] = set()
            combined: list[tuple[str, str]] = []
            for k, v in params1 + params2 + params3:
                if k not in seen:
                    seen.add(k)
                    combined.append((k, v))

            return (pos, end3 + 1, choose_xml, combined)

        return None

    def _is_in_block_comment(self, code: str, pos: int) -> bool:
        """pos 위치가 /* ... */ 블록 주석 내부인지 판별."""
        in_comment = False
        i = 0
        while i < pos:
            if not in_comment and code[i:i+2] == '/*':
                in_comment = True
                i += 2
            elif in_comment and code[i:i+2] == '*/':
                in_comment = False
                i += 2
            else:
                i += 1
        return in_comment

    def _parse_general_concat(self, arg: str) -> tuple[list[str], list[tuple[str, str]]] | None:
        """N-ary `"str" + var(.method())? + "str" + var + ...` 일반 파서.

        문자열 리터럴과 식별자(+ optional no-arg `.method()`)가 `+` 로 교차 연결된 형태만 처리.
        `Formatter.nullXxx(...)` 같이 인자가 있는 함수 호출이 포함되면 None 반환 → 호출자가 특수 패턴으로 폴백.
        다중 변수 연결을 무손실로 보존하기 위한 가드.
        """
        if not arg:
            return None
        frag_sql: list[str] = []
        frag_pairs: list[tuple[str, str]] = []
        pos = 0
        n = len(arg)
        expect_term = True

        while pos < n:
            while pos < n and arg[pos].isspace():
                pos += 1
            if pos >= n:
                break
            if expect_term:
                ch = arg[pos]
                if ch == '"':
                    end = arg.find('"', pos + 1)
                    if end == -1:
                        return None
                    frag_sql.append(arg[pos + 1:end])
                    pos = end + 1
                elif ch.isalpha() or ch == '_':
                    tok = re.match(r'[A-Za-z_]\w*(?:\.\w+\(\s*\))?', arg[pos:])
                    if not tok:
                        return None
                    token = tok.group(0)
                    bare = re.match(r'[A-Za-z_]\w*', token).group(0)
                    frag_sql.append(f'#{{{bare}}}')
                    frag_pairs.append((bare, token))
                    pos += len(token)
                else:
                    return None
                expect_term = False
            else:
                if arg[pos] != '+':
                    return None
                pos += 1
                expect_term = True

        if expect_term:
            return None

        # `'#{var}'` 형태의 양쪽 단일따옴표 제거 (MyBatis 바인딩은 quote 불필요)
        for i, frag in enumerate(frag_sql):
            if frag.startswith('#{') and frag.endswith('}'):
                if i > 0 and frag_sql[i - 1].endswith("'"):
                    frag_sql[i - 1] = frag_sql[i - 1][:-1]
                if i + 1 < len(frag_sql) and frag_sql[i + 1].startswith("'"):
                    frag_sql[i + 1] = frag_sql[i + 1][1:]
        return frag_sql, frag_pairs

    def _parse_append_arg(self, arg: str) -> tuple[list[str], list[tuple[str, str]]]:
        """sb.append() / StringBuffer 생성자 인자에서 (SQL fragments, param pairs) 추출."""
        frag_sql: list[str] = []
        frag_pairs: list[tuple[str, str]] = []

        if not arg:
            return frag_sql, frag_pairs

        if re.match(r'^"[^"]*"$', arg):
            frag_sql.append(arg[1:-1])
            return frag_sql, frag_pairs

        # N-ary "str"+var+"str"+var+... 다중 변수 손실 방지 (단일 변수 케이스도 포함)
        parsed = self._parse_general_concat(arg)
        if parsed is not None:
            g_sql, g_pairs = parsed
            frag_sql.extend(g_sql)
            frag_pairs.extend(g_pairs)
            return frag_sql, frag_pairs

        m = re.match(r'"([^"]*)"\s*\+\s*([A-Za-z_]\w*)(?:\.\w+\(\))?\s*\+\s*"([^"]*)"\s*$', arg)
        if m:
            prefix, var, suffix = m.group(1), m.group(2), m.group(3)
            frag_pairs.append((var, var))
            frag_sql.extend([prefix, f'#{{{var}}}', suffix])
            return frag_sql, frag_pairs

        m = re.match(r'"([^"]*)"\s*\+\s*([A-Za-z_]\w*)(?:\.\w+\(\))?\s*$', arg)
        if m:
            prefix, var = m.group(1), m.group(2)
            frag_pairs.append((var, var))
            frag_sql.extend([prefix, f'#{{{var}}}'])
            return frag_sql, frag_pairs

        # "prefix" + Formatter.nullXxx(WrapperType.valueOf(var)) + "suffix" (중첩 래퍼 호출)
        m = re.match(
            r'^"([^"]*)"\s*\+\s*(?:\w+\.)*\w+\(\s*(?:\w+\.)*\w+\(\s*([A-Za-z_]\w*)\s*\)\s*\)\s*(?:\+\s*"([^"]*)")?$',
            arg
        )
        if m:
            prefix, var = m.group(1), m.group(2)
            suffix = m.group(3) or ''
            prefix_clean = prefix.rstrip("'") if prefix.endswith("'") else prefix
            suffix_clean = suffix.lstrip("'") if suffix.startswith("'") else suffix
            frag_pairs.append((var, var))
            frag_sql.append(prefix_clean + f'#{{{var}}}' + suffix_clean)
            return frag_sql, frag_pairs

        # "prefix" + Formatter.nullXxx(varName) + "suffix" (메서드 호출 인자 포함)
        m = re.match(
            r'^"([^"]*)"\s*\+\s*(?:\w+\.)*\w+\(\s*([A-Za-z_]\w*)\s*\)\s*(?:\+\s*"([^"]*)")?$',
            arg
        )
        if m:
            prefix, var = m.group(1), m.group(2)
            suffix = m.group(3) or ''
            # SQL 문자열 바인딩용 surrounding single-quote 제거 (MyBatis #{} 사용)
            prefix_clean = prefix.rstrip("'") if prefix.endswith("'") else prefix
            suffix_clean = suffix.lstrip("'") if suffix.startswith("'") else suffix
            frag_pairs.append((var, var))
            frag_sql.append(prefix_clean + f'#{{{var}}}' + suffix_clean)
            return frag_sql, frag_pairs

        # 어떤 패턴도 매치 실패 → 원본 그대로 주석으로 보존 (조용한 손실 방지)
        frag_sql.append(f'/* UNPARSED_APPEND: {arg} */')
        return frag_sql, frag_pairs

    @staticmethod
    def _detect_sql_type(sql: str) -> str:
        """SQL 첫 키워드로 select/insert/update/delete 분류 (MERGE 는 update)."""
        head = re.sub(r'/\*.*?\*/', '', sql, flags=re.S).strip().upper()
        head = re.sub(r'<[^>]+>', '', head).strip()
        if re.match(r'^INSERT\b', head):
            return 'insert'
        if re.match(r'^DELETE\b', head):
            return 'delete'
        if re.match(r'^(UPDATE|MERGE)\b', head):
            return 'update'
        return 'select'

    @staticmethod
    def _java_call_for_type(sql_type: str) -> str:
        """xml_entries type → uxbDAO 메서드명 매핑."""
        return sql_type if sql_type in ('insert', 'update', 'delete') else 'select'

    def _extract_sql_and_params(self, code: str, sb_var: str) -> tuple[list[str], list[tuple[str, str]]]:
        """sb.append() 호출에서 SQL 조각과 (key, value) 파라미터 쌍 목록을 추출.
        if (cond) { sb.append(...) } 패턴은 <if test="..."> MyBatis 태그로 변환.
        """
        sql_parts: list[str] = []
        param_pairs: list[tuple[str, str]] = []

        # 타입 선언(StringBuilder sb = new StringBuilder()) 및 재할당(sb = new StringBuffer()) 모두 인식
        sb_decl_re = re.compile(
            rf'(?:(?:StringBuilder|StringBuffer)\s+)?{re.escape(sb_var)}\s*=\s*new\s+(?:StringBuffer|StringBuilder)\s*\('
        )
        # `tempQuery = new StringBuffer(tempQuery.toString().replaceAll(...))` 같은
        # self-reference 재할당은 *초기화* 가 아닌 *후처리* 이므로 last_decl_pos 후보에서 제외.
        # 동시에 replaceAll("TOKEN", var) 매핑은 placeholder_map 에 저장해 SQL 의 토큰을 ${var} 로 치환.
        last_decl_pos = 0
        placeholder_map: dict[str, str] = {}
        for m in sb_decl_re.finditer(code):
            stmt_end = code.find(';', m.end())
            stmt_arg = code[m.end():stmt_end] if stmt_end != -1 else code[m.end():]
            if f'{sb_var}.toString()' in stmt_arg:
                # replaceAll("PLACEHOLDER", varName) → ${varName} 치환 룰 등록
                for rm in re.finditer(
                    r'\.replaceAll\(\s*"([^"]+)"\s*,\s*(\w+)\s*\)', stmt_arg
                ):
                    placeholder_map[rm.group(1)] = rm.group(2)
                continue
            last_decl_pos = m.start()

        # 순수 문자열 리터럴로 초기화된 경우
        init_re = re.compile(
            rf'(?:(?:StringBuilder|StringBuffer)\s+)?{re.escape(sb_var)}\s*=\s*new\s+\w+\("([^"]*)"\)',
            re.DOTALL
        )
        init_match = init_re.search(code, last_decl_pos)
        if init_match:
            sql_parts.append(init_match.group(1))
        else:
            # 빈 생성자 또는 연결 문자열로 초기화: new StringBuffer() / new StringBuffer("PREFIX"+var)
            concat_init_re = re.compile(
                rf'(?:(?:StringBuilder|StringBuffer)\s+)?{re.escape(sb_var)}\s*=\s*new\s+\w+\(([^)]*)\)\s*;'
            )
            concat_m = concat_init_re.search(code, last_decl_pos)
            if concat_m:
                frags, pairs = self._parse_append_arg(concat_m.group(1).strip())
                sql_parts.extend(frags)
                param_pairs.extend(pairs)

        append_re = re.compile(
            rf'\b{re.escape(sb_var)}\.append\((.+?)\)\s*;',
            re.DOTALL
        )

        # 3분기 if/else if/else → <choose><when><when><otherwise> 변환 (다중 append 분기)
        multi_choose_info = self._find_multi_branch_choose(code, sb_var, last_decl_pos)
        multi_choose_start = -1
        multi_choose_end = -1
        multi_choose_xml = ''
        multi_choose_inserted = False
        if multi_choose_info:
            multi_choose_start, multi_choose_end, multi_choose_xml, multi_choose_params = multi_choose_info
            param_pairs.extend(multi_choose_params)

        # if { append } else { append } → <choose><when><otherwise> 변환
        if_else_re = re.compile(
            rf'if\s*\(([^{{;]+)\)\s*\{{\s*{re.escape(sb_var)}\.append\((.+?)\)\s*;\s*\}}\s*'
            rf'else\s*\{{\s*{re.escape(sb_var)}\.append\((.+?)\)\s*;\s*\}}',
            re.DOTALL
        )
        choose_when_pos: dict[int, tuple[str, str, str]] = {}
        choose_skip_pos: set[int] = set()

        for ie_m in if_else_re.finditer(code, last_decl_pos):
            # WHEN/OTHERWISE 본문에 brace 나 중첩 append 가 있으면 경계 잘못 잡힌 매치 (별도 if 블록 가로지름)
            a_body, b_body = ie_m.group(2), ie_m.group(3)
            if any(ch in a_body for ch in '{}') or f'{sb_var}.append' in a_body:
                continue
            if any(ch in b_body for ch in '{}') or f'{sb_var}.append' in b_body:
                continue
            cond = self._java_condition_to_mybatis(ie_m.group(1).strip())
            when_m = append_re.search(code, ie_m.start(), ie_m.end())
            if not when_m:
                continue
            oth_m = append_re.search(code, when_m.end(), ie_m.end())
            if not oth_m:
                continue
            when_frags, when_pairs = self._parse_append_arg(when_m.group(1).strip())
            oth_frags, oth_pairs = self._parse_append_arg(oth_m.group(1).strip())
            when_sql = ' '.join(when_frags).strip()
            oth_sql = ' '.join(oth_frags).strip()
            choose_when_pos[when_m.start()] = (cond, when_sql, oth_sql)
            choose_skip_pos.update({when_m.start(), oth_m.start()})
            param_pairs.extend(when_pairs + oth_pairs)

        # if (cond) { sb.append(...) } → <if test="..."> 변환 위한 위치 맵 (choose 제외)
        if_append_re = re.compile(
            rf'if\s*\(([^{{;]+)\)\s*\{{\s*{re.escape(sb_var)}\.append\((.+?)\)\s*;\s*\}}',
            re.DOTALL
        )
        cond_map: dict[int, str] = {}
        for im in if_append_re.finditer(code, last_decl_pos):
            inner = append_re.search(code, im.start(), im.end())
            if inner and inner.start() not in choose_skip_pos:
                cond_map[inner.start()] = self._java_condition_to_mybatis(im.group(1).strip())

        for m in append_re.finditer(code, last_decl_pos):
            pos = m.start()

            # // 라인 주석 내 sb.append는 제외
            line_start = code.rfind('\n', 0, pos) + 1
            if '//' in code[line_start:pos]:
                continue

            # 3분기 choose 블록 내부 append 처리
            if multi_choose_info and multi_choose_start <= pos < multi_choose_end:
                if not multi_choose_inserted:
                    sql_parts.append(multi_choose_xml)
                    multi_choose_inserted = True
                continue

            # choose/when/otherwise 처리 — XML 이스케이프는 _format_sql 에서 일괄 처리
            if pos in choose_when_pos:
                cond, when_sql, oth_sql = choose_when_pos[pos]
                sql_parts.append(
                    f'\n<choose>\n'
                    f'<when test="{cond}">\n'
                    f'    {when_sql}\n'
                    f'</when>\n'
                    f'<otherwise>\n'
                    f'    {oth_sql}\n'
                    f'</otherwise>\n'
                    f'</choose>\n'
                )
                continue
            if pos in choose_skip_pos:
                continue
            arg = m.group(1).strip()
            mybatis_cond = cond_map.get(m.start())

            frag_sql: list[str] = []
            frag_pairs: list[tuple[str, str]] = []

            # 순수 문자열 리터럴
            if re.match(r'^"[^"]*"$', arg):
                frag_sql.append(arg[1:-1])

            # N-ary "str"+var+"str"+var+... 다중 변수 연결 무손실 처리.
            # Formatter.nullXxx(...) 등 함수 호출 패턴은 None 반환 → 아래 특수 패턴들이 처리.
            elif (parsed := self._parse_general_concat(arg)) is not None:
                g_sql, g_pairs = parsed
                frag_sql.extend(g_sql)
                frag_pairs.extend(g_pairs)

            # "prefix" + Formatter.nullXxx(StringUtil.nvl(obj.getCol(), "...")) + "suffix"
            elif (m2 := re.match(
                r'"([^"]*)"\s*\+\s*Formatter\.\w+\(StringUtil\.nvl\((\w+)\.get(\w+)\(\)\s*,\s*"[^"]*"\s*\)\)\s*\+\s*"([^"]*)"',
                arg
            )):
                prefix, obj, col, suffix = m2.group(1).rstrip("'"), m2.group(2), m2.group(3), m2.group(4).lstrip("'")
                key = col[0].lower() + col[1:]
                frag_pairs.append((key, f'{obj}.get{col}()'))
                frag_sql.extend([prefix, f'#{{{key}}}', suffix])

            # "prefix" + Formatter.nullXxx(StringUtil.nvl(obj.getCol(), "..."))  (suffix 없음)
            elif (m2 := re.match(
                r'"([^"]*)"\s*\+\s*Formatter\.\w+\(StringUtil\.nvl\((\w+)\.get(\w+)\(\)\s*,\s*"[^"]*"\s*\)\)\s*$',
                arg
            )):
                prefix, obj, col = m2.group(1).rstrip("'"), m2.group(2), m2.group(3)
                key = col[0].lower() + col[1:]
                frag_pairs.append((key, f'{obj}.get{col}()'))
                frag_sql.extend([prefix, f'#{{{key}}}'])

            # "prefix" + Formatter.nullXxx(StringUtil.nvl(simpleVar, "...")) + "suffix"
            elif (m2 := re.match(
                r'"([^"]*)"\s*\+\s*Formatter\.\w+\(StringUtil\.nvl\((\w+)\s*,\s*"[^"]*"\s*\)\)\s*\+\s*"([^"]*)"',
                arg
            )):
                prefix, name, suffix = m2.group(1).rstrip("'"), m2.group(2), m2.group(3).lstrip("'")
                frag_pairs.append((name, name))
                frag_sql.extend([prefix, f'#{{{name}}}', suffix])

            # "prefix" + Formatter.nullXxx(StringUtil.nvl(simpleVar, "..."))  (suffix 없음)
            elif (m2 := re.match(
                r'"([^"]*)"\s*\+\s*Formatter\.\w+\(StringUtil\.nvl\((\w+)\s*,\s*"[^"]*"\s*\)\)\s*$',
                arg
            )):
                prefix, name = m2.group(1).rstrip("'"), m2.group(2)
                frag_pairs.append((name, name))
                frag_sql.extend([prefix, f'#{{{name}}}'])

            # "prefix" + param[.method()] + "suffix"
            elif (m2 := re.match(
                r'"([^"]*?)"\s*\+\s*([A-Za-z_][A-Za-z0-9_]*)(?:\.\w+\(\))?\s*\+\s*"([^"]*?)"',
                arg
            )):
                frag_sql.append(m2.group(1))
                raw_param = m2.group(2)
                frag_pairs.append((raw_param, raw_param))
                frag_sql.extend([f'#{{{raw_param}}}', m2.group(3)])

            # "prefix" + param[.method()]  (suffix 없음)
            elif (m2 := re.match(
                r'"([^"]*?)"\s*\+\s*([A-Za-z_][A-Za-z0-9_]*)(?:\.\w+\(\))?$',
                arg
            )):
                frag_sql.append(m2.group(1))
                raw_param = m2.group(2)
                frag_pairs.append((raw_param, raw_param))
                frag_sql.append(f'#{{{raw_param}}}')

            # "prefix" + Formatter.nullXxx(obj.getCol()) + "suffix"
            elif (m2 := re.match(
                r'"([^"]*)"\s*\+\s*Formatter\.\w+\((\w+)\.get(\w+)\(\)\)\s*\+\s*"([^"]*)"',
                arg
            )):
                prefix, obj, col, suffix = m2.group(1).rstrip("'"), m2.group(2), m2.group(3), m2.group(4).lstrip("'")
                key = col[0].lower() + col[1:]
                frag_pairs.append((key, f'{obj}.get{col}()'))
                frag_sql.extend([prefix, f'#{{{key}}}', suffix])

            # "prefix" + Formatter.nullXxx(obj.getCol())  (suffix 없음)
            elif (m2 := re.match(
                r'"([^"]*)"\s*\+\s*Formatter\.\w+\((\w+)\.get(\w+)\(\)\)\s*$',
                arg
            )):
                prefix, obj, col = m2.group(1).rstrip("'"), m2.group(2), m2.group(3)
                key = col[0].lower() + col[1:]
                frag_pairs.append((key, f'{obj}.get{col}()'))
                frag_sql.extend([prefix, f'#{{{key}}}'])

            # "prefix" + Formatter.nullXxx(simpleVar) + "suffix"
            elif (m2 := re.match(
                r'"([^"]*)"\s*\+\s*Formatter\.\w+\((\w+)\)\s*\+\s*"([^"]*)"',
                arg
            )):
                prefix, name, suffix = m2.group(1).rstrip("'"), m2.group(2), m2.group(3).lstrip("'")
                frag_pairs.append((name, name))
                frag_sql.extend([prefix, f'#{{{name}}}', suffix])

            # "prefix" + StringUtil.nvl(simpleVar, ...) + "suffix"  (_LINE_RULES Formatter.nullTrim 변환 결과)
            elif (m2 := re.match(
                r'"([^"]*)"\s*\+\s*StringUtil\.nvl\((\w+)\s*,', arg
            )):
                prefix = m2.group(1).rstrip("'")
                name = m2.group(2)
                # suffix: 닫힌 ) 이후의 나머지 + "..." 부분 추출
                rest_m = re.search(r'\)\s*\+\s*"([^"]*)"', arg[m2.end()-1:])
                suffix = rest_m.group(1).lstrip("'") if rest_m else ''
                frag_pairs.append((name, name))
                frag_sql.extend([prefix, f'#{{{name}}}', suffix])

            else:
                # 어떤 패턴도 매치 실패 → 원본 그대로 주석으로 보존 (조용한 손실 방지)
                frag_sql.append(f'/* UNPARSED_APPEND: {arg} */')

            # 조건부 append → <if> 태그 / 일반 append → 직접 병합
            # (XML 이스케이프는 _format_sql 에서 일괄 처리)
            if mybatis_cond is not None:
                sql_content = ' '.join(frag_sql).strip()
                if sql_content:
                    sql_parts.append(f'\n<if test="{mybatis_cond}">\n    {sql_content}\n</if>\n')
                param_pairs.extend(frag_pairs)
            else:
                sql_parts.extend(frag_sql)
                param_pairs.extend(frag_pairs)

        seen: dict[str, str] = {}
        for k, v in param_pairs:
            if k not in seen:
                seen[k] = v

        # if (!"".equals(var)) 조건에만 쓰이는 변수도 paramMap 에 추가 (MyBatis <if test> 평가 필요)
        cond_var_re = re.compile(r'!\s*""\s*\.equals\s*\(\s*(\w+)\s*\)')
        for cv_m in cond_var_re.finditer(code, last_decl_pos):
            var = cv_m.group(1)
            if var not in seen:
                seen[var] = var

        # placeholder token(예: #FIELD) → MyBatis 식별자 바인딩(${var}) 치환
        if placeholder_map:
            new_parts = []
            for p in sql_parts:
                for ph, var in placeholder_map.items():
                    p = p.replace(ph, f'${{{var}}}')
                new_parts.append(p)
            sql_parts = new_parts

        return sql_parts, list(seen.items())

    def _extract_update_params(self, code: str, start: int) -> list[tuple[str, str]]:
        """ps.setXxx / pstmt.setXxx(pos, expr) 에서 순서대로 (key, value_expr) 쌍을 추출.
        pos는 숫자, var++ / ++var 형태(임의 변수명) 모두 지원.
        """
        exec_m = re.search(r'\bexecute(?:Update|Query)\(\)', code[start:])
        end = start + exec_m.start() if exec_m else start + 500

        set_line_re = re.compile(
            r'\bps\w*\.set(?:Long|String|Int|Double|Timestamp|Object)\s*\(\s*(\+\+\w+|\w+\+\+|\d+)\s*,\s*([^\n]+)\)',
        )
        fixed: dict[int, tuple[str, str]] = {}
        ordered: list[tuple[str, str]] = []

        for m in set_line_re.finditer(code, start, end):
            pos_str = m.group(1)
            expr = m.group(2).strip()
            # 인라인 // 주석 제거 후, 주석으로 인해 혼입된 ); 잔여 제거
            expr = re.sub(r'\s*//[^\n]*', '', expr).strip()
            if expr.endswith(');'):
                expr = expr[:-2].strip()
            kv = self._derive_param_key_value(expr)
            if kv is None:
                continue
            if pos_str.endswith('++') or pos_str.startswith('++'):
                ordered.append(kv)
            else:
                pos = int(pos_str)
                if pos not in fixed:
                    fixed[pos] = kv

        if fixed:
            return [fixed[k] for k in sorted(fixed.keys())]
        return ordered

    def _derive_param_key_value(self, expr: str) -> tuple[str, str] | None:
        """파라미터 표현식에서 (paramMap key, Java value expression) 쌍 도출.

        규칙:
        - 단순 파라미터(processFlag, invoNo 등) → (paramName, paramName)
        - VO/DTO getter(headVo.getCancel_date()) → (cancel_date, headVo.getCancel_date())
        - session userId → (_sessionUserId, userInfo.getUserId())
        - 시스템 타임스탬프(new Date(System.currentTimeMillis())) → None (스킵)
        """
        expr = expr.strip()

        # 0. 시스템 타임스탬프 → 스킵 (SQL에서 SYSDATE 등으로 처리)
        if 'currentTimeMillis' in expr or 'System.currentTime' in expr:
            return None

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

        # 5.5. Long/Double/Integer.valueOf(x).longValue() 등 — 래퍼 언박싱 단순화
        m = re.match(r'(?:Long|Double|Integer|Float)\.valueOf\((\w+)\)\.\w+Value\(\)', expr)
        if m:
            name = m.group(1)
            return (name, name)

        # 6. Formatter.nullXxx((obj.getXxx())) — 추가 괄호 포함 VO getter with null wrapper
        m = re.match(r'Formatter\.\w+\(\s*\(?\s*(\w+)\.get(\w+)\(\)', expr)
        if m:
            obj, col = m.group(1), m.group(2)
            return (col[0].lower() + col[1:], f'{obj}.get{col}()')

        # 6.5. Formatter.nullXxx(StringUtil.nvl(obj.getXxx(), "...")) — LINE_RULES 변환 결과
        m = re.match(r'Formatter\.\w+\(StringUtil\.nvl\((\w+)\.get(\w+)\(\)', expr)
        if m:
            obj, col = m.group(1), m.group(2)
            return (col[0].lower() + col[1:], f'{obj}.get{col}()')

        # 6.6. Formatter.nullXxx(StringUtil.nvl(simpleVar, "...")) — LINE_RULES 변환 결과
        m = re.match(r'Formatter\.\w+\(StringUtil\.nvl\((\w+)\s*,', expr)
        if m:
            name = m.group(1)
            return (name, name)

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

        # 8.5. simpleVar.longValue()/intValue()/doubleValue() 등 — 래퍼 언박싱 단순화
        m = re.match(r'(\w+)\.(?:longValue|intValue|doubleValue|floatValue|shortValue|byteValue)\(\)', expr)
        if m:
            name = m.group(1)
            return (name, name)

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
        """userInfo.getUserId() 사용 메서드에 UserAdditionalDTO userInfo 선언 자동 주입."""
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
            if re.search(r'\buserInfo\b', body) and 'UserAdditionalDTO userInfo' not in body:
                line_start = code.rfind('\n', 0, body_start) + 1
                base_indent = re.match(r'[ \t]*', code[line_start:]).group()
                inner_indent = base_indent + '    '
                insertions.append((body_start, f'\n{inner_indent}UserAdditionalDTO userInfo = (UserAdditionalDTO) UserInfo.getUserInfo();'))
        for pos, text in reversed(insertions):
            code = code[:pos] + text + code[pos:]
        return code

    def _fix_throws(self, code: str) -> str:
        """throws Exception, Exception 같은 중복 제거."""
        return re.sub(r'\bthrows\s+Exception\s*,\s*\bException\b', 'throws Exception', code)

    def _remove_trivial_try_catch(self, code: str) -> str:
        """catch 바디가 throw new XxxException(e); 하나뿐인 try-catch를 제거하고 try 본문만 남김."""
        # 이중 catch 선처리:
        # catch(AnyType e){ throw e; } catch(Exception e){ throw new AnyType(e); }
        # → 첫 번째 단순 re-throw catch 제거 (두 번째 catch만 남겨 아래 로직에서 제거)
        code = re.sub(
            r'(?<=\})\s*catch\s*\(\s*\w+\s+(\w+)\s*\)\s*\{\s*throw\s+\1\s*;\s*\}(?=\s*catch\s*\(\s*Exception\b)',
            '',
            code,
            flags=re.DOTALL,
        )
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

            # 추가 catch 가 있으면 건너뜀 (finally 는 제거 범위에 포함)
            tail_str = code[catch_close + 1:]
            tail = tail_str.lstrip()
            if re.match(r'catch\b', tail):
                continue

            # catch 바디의 마지막 문장이 rethrow 이면 제거 대상
            # log.xxx()/e.printStackTrace() 제거 후 throw (new Xxx | e) 만 남으면 trivial
            catch_body = code[catch_open_abs + 1:catch_close].strip()
            catch_body_clean = re.sub(r'\blog\.\w+\s*\([^;]*\)\s*;\s*', '', catch_body)
            catch_body_clean = re.sub(r'\b\w+\.printStackTrace\s*\([^;]*\)\s*;\s*', '', catch_body_clean).strip()
            if not re.search(r'\bthrow\s+(?:new\s+\w+\b[^;]*|\w+)\s*;\s*$', catch_body_clean, re.DOTALL):
                continue

            # finally 블록이 있으면 제거 범위에 포함
            removal_end = catch_close + 1
            finally_m = re.match(r'\s*finally\s*\{', tail_str)
            if finally_m:
                finally_brace = catch_close + 1 + tail_str.index('{', finally_m.start())
                finally_close = self._find_block_end(code, finally_brace)
                if finally_close < len(code):
                    removal_end = finally_close + 1

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
            replacements.append((m.start(), removal_end, ''.join(de_indented)))

        # 중첩된 try-catch (finally 내부 등)는 외부 범위에 포함되므로 건너뜀
        sorted_reps = sorted(replacements, key=lambda x: x[0])
        filtered_reps: list[tuple[int, int, str]] = []
        covered_until = -1
        for start, end, replacement in sorted_reps:
            if start >= covered_until:
                filtered_reps.append((start, end, replacement))
                covered_until = max(covered_until, end)
        for start, end, replacement in sorted(filtered_reps, key=lambda x: x[0], reverse=True):
            code = code[:start] + replacement + code[end:]
        return code

    def _remove_throws_exception(self, code: str) -> str:
        """메서드 시그니처의 불필요한 throws 절 정리.

        - RemoteException: 무조건 제거
        - UxbBizException, Exception: 본문에 `throw` 문이 없을 때만 제거 (없으면 불필요)
        - 다른 예외(IOException 등)는 그대로 유지
        - throws 목록이 비면 'throws' 키워드도 함께 제거
        """
        REMOVE_ALWAYS = {'RemoteException', 'SQLException'}
        REMOVE_IF_NO_THROW = {'UxbBizException', 'Exception'}

        sig_re = re.compile(r'(\)\s*)throws\s+([\w\s,\.]+?)(\s*\{)')

        pieces: list[str] = []
        last_end = 0

        for m in sig_re.finditer(code):
            body_open = code.find('{', m.start(3))
            if body_open == -1:
                continue
            body_close = self._find_block_end(code, body_open)
            if body_close >= len(code):
                continue

            body = code[body_open + 1:body_close]
            has_throw_stmt = bool(re.search(r'\bthrow\s+', body))

            names = [n.strip() for n in m.group(2).split(',') if n.strip()]

            kept: list[str] = []
            for n in names:
                simple = n.rsplit('.', 1)[-1]
                if simple in REMOVE_ALWAYS:
                    continue
                if simple in REMOVE_IF_NO_THROW and not has_throw_stmt:
                    continue
                kept.append(n)

            if len(kept) == len(names):
                continue

            if kept:
                replacement = m.group(1) + 'throws ' + ', '.join(kept) + m.group(3)
            else:
                # throws 절 전체 제거 → ') {' 형태로 정규화
                replacement = ') {'

            pieces.append(code[last_end:m.start()])
            pieces.append(replacement)
            last_end = m.end()

        pieces.append(code[last_end:])
        return ''.join(pieces)

    def _remove_unused_imports(self, code: str) -> str:
        """미사용 import 자동 정리.

        - `import x.y.Z;` 형태에서 simple name `Z` 를 추출
        - 코드 본문(import 제외)에 `\\bZ\\b` 매치가 없으면 해당 import 제거
        - wildcard import (`import x.y.*;`) 는 유지
        """
        import_re = re.compile(
            r'^(import\s+(?:static\s+)?[\w.]+\.(\w+)\s*;\s*\n?)',
            re.MULTILINE,
        )
        imports = list(import_re.finditer(code))
        if not imports:
            return code
        body_no_imports = import_re.sub('', code)
        to_remove: list[tuple[int, int]] = []
        for m in imports:
            class_name = m.group(2)
            if class_name == '*':
                continue
            if not re.search(rf'\b{re.escape(class_name)}\b', body_no_imports):
                to_remove.append((m.start(), m.end()))
        for start, end in reversed(to_remove):
            code = code[:start] + code[end:]
        return code

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

    def _align_sql_keyword(self, stripped: str) -> str:
        """SQL 키워드를 6자 필드에 우측 정렬. 쉼표 시작 줄은 5칸 들여쓰기."""
        if stripped.startswith(','):
            return '     ' + stripped
        upper = stripped.upper()
        for kw, prefix in self._SQL_KW_PREFIX.items():
            if upper == kw or upper.startswith(kw + ' ') or upper.startswith(kw + '\t'):
                return prefix + stripped
        return stripped

    @staticmethod
    def _escape_sql_xml(s: str) -> str:
        """SQL 본문의 비교 연산자(>=, <=, >, <, <>)를 XML 엔티티로 이스케이프.

        MyBatis XML 파싱 오류 방지용. `&` 는 기존 엔티티(`&lt;`/`&gt;`/`&amp;`)를 보존하면서 처리.
        """
        # 기존 엔티티 보호 → `<`/`>` 이스케이프 → 보호 해제
        s = s.replace('&lt;', '\x00LT\x00').replace('&gt;', '\x00GT\x00').replace('&amp;', '\x00AMP\x00')
        s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        s = s.replace('\x00LT\x00', '&lt;').replace('\x00GT\x00', '&gt;').replace('\x00AMP\x00', '&amp;')
        return s

    def _format_sql(self, sql: str) -> str:
        """SQL 가독성 정리: 키워드 우측 정렬(6자 필드), \\n 제거, 공백 정규화.
        MyBatis <if>/<choose>/<when>/<otherwise> 태그는 base 들여쓰기,
        태그 내부 SQL은 한 단계 추가 들여쓰기.
        """
        sql = sql.replace('\\n', '\n')
        base = '        '   # 8 spaces
        inner = base + '    '  # 12 spaces (태그 내부 SQL)

        lines = []
        depth = 0  # 태그 내부 깊이 (SQL 들여쓰기용)

        for line in sql.splitlines():
            stripped = re.sub(r'\t+', ' ', line)
            stripped = re.sub(r' {2,}', ' ', stripped).strip()
            if not stripped:
                continue

            # 닫는 태그: depth 감소 후 base 출력 (뒤에 내용이 붙은 경우 분리)
            if re.match(r'</(if|when|otherwise)>', stripped):
                depth = max(0, depth - 1)
                tag_m = re.match(r'(</(if|when|otherwise)>)(.*)', stripped)
                lines.append(f'{base}{tag_m.group(1)}')
                rest = tag_m.group(3).strip()
                if rest:
                    lines.append(f'{base}{self._escape_sql_xml(self._align_sql_keyword(rest))}')
                continue

            # <choose> 닫는 태그: depth 변경 없음 (뒤에 내용이 붙은 경우 분리)
            if stripped.startswith('</choose>'):
                lines.append(f'{base}</choose>')
                rest = stripped[len('</choose>'):].strip()
                if rest:
                    lines.append(f'{base}{self._escape_sql_xml(self._align_sql_keyword(rest))}')
                continue

            # <choose> 여는 태그: depth 변경 없음 (내부는 <when>/<otherwise>)
            if re.match(r'<choose>', stripped):
                lines.append(f'{base}{stripped}')
                continue

            # <if>/<when>/<otherwise> 여는 태그: base 출력 후 depth 증가
            if re.match(r'<(if|when|otherwise)\b', stripped):
                lines.append(f'{base}{stripped}')
                if not stripped.endswith('/>'):
                    depth += 1
                continue

            # SQL 내용: 키워드 정렬 후 XML 비교연산자 이스케이프
            cur = inner if depth > 0 else base
            lines.append(f'{cur}{self._escape_sql_xml(self._align_sql_keyword(stripped))}')

        return '\n'.join(lines)

    def _build_mapper_xml(self, entries: list[dict]) -> str:
        if not entries:
            return (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"\n'
                '    "http://mybatis.org/dtd/mybatis-3-mapper.dtd">\n'
                f'<mapper namespace="{self.namespace}">\n'
                '</mapper>'
            )
        blocks = []
        for e in entries:
            sql_type = e.get('type', 'select')
            if sql_type in ('update', 'insert', 'delete'):
                tag = sql_type
                extra = ''
            else:
                tag = 'select'
                extra = ' resultType="map" useCache="false"'
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
        # DAO 뒤 숫자/언더스코어 suffix(_BACKUP, _1, _OLD 등) 변형도 DAO 파일로 인식
        return bool(re.search(r'(?i)DAO\d*(_\w*)?$', path.stem))

    def _mapper_name(self, stem: str) -> str:
        m = re.match(r'(.+?)DAO(\d*)(_\w*)?$', stem, re.IGNORECASE)
        if m:
            return m.group(1) + (m.group(2) or '') + (m.group(3) or '') + 'Mapper.xml'
        return stem + 'Mapper.xml'

    def _sub_path_after_dao(self, code: str) -> str | None:
        """변환된 package 선언에서 'dao' 세그먼트 이후 sub-path 추출.

        예: 'com.pan.som.dao.standardInfo' → 'standardInfo'
            'com.pan.som.dao' → ''
            package 없거나 'dao' 미포함 → None
        """
        m = re.search(r'package\s+([\w.]+)\s*;', code)
        if not m:
            return None
        parts = m.group(1).split('.')
        if 'dao' not in parts:
            return None
        sub = parts[parts.index('dao') + 1:]
        return '/'.join(sub)

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
                    java_code = result['java']
                    xml_code = result['xml']
                    mapper_name = self._mapper_name(java_file.stem)
                    sub = self._sub_path_after_dao(java_code)

                    out_java = OUTPUT_DIR / java_file.name
                    if _safe_write(out_java, java_code):
                        converted.append(out_java)
                        logger.info(f'완료 (Java): {out_java}')

                    out_xml = OUTPUT_DIR / mapper_name
                    if _safe_write(out_xml, xml_code):
                        converted.append(out_xml)
                        logger.info(f'완료 (Mapper XML): {out_xml}')

                    if EXTERNAL_GEN_YN:
                        if EXTERNAL_DAO_BASE and sub is not None:
                            ext_java = EXTERNAL_DAO_BASE / sub / java_file.name
                            ext_java.parent.mkdir(parents=True, exist_ok=True)
                            if _safe_write(ext_java, java_code):
                                converted.append(ext_java)
                                logger.info(f'완료 (외부 Java): {ext_java}')

                        if EXTERNAL_MAPPER_BASE and sub is not None:
                            ext_xml = EXTERNAL_MAPPER_BASE / sub / mapper_name
                            ext_xml.parent.mkdir(parents=True, exist_ok=True)
                            if _safe_write(ext_xml, xml_code):
                                converted.append(ext_xml)
                                logger.info(f'완료 (외부 Mapper XML): {ext_xml}')
                else:
                    out_path = OUTPUT_DIR / java_file.name
                    if _safe_write(out_path, result):
                        converted.append(out_path)
                        logger.info(f'완료: {out_path}')

                    if EXTERNAL_GEN_YN:    
                        sub = self._sub_path_after_dao(result)
                        if EXTERNAL_DAO_BASE and sub is not None:
                            ext_java = EXTERNAL_DAO_BASE / sub / java_file.name
                            ext_java.parent.mkdir(parents=True, exist_ok=True)
                            if _safe_write(ext_java, result):
                                converted.append(ext_java)
                                logger.info(f'완료 (외부 Java): {ext_java}')

            except Exception as e:
                logger.error(f'실패 ({java_file.name}): {e}')

        return converted
############# Servlet -> Controller 변환 (1차) #############
# EJB Home/Remote 관련 생성·메서드 호출을 → service 인스턴스 직접 호출 형태로 변환
# getDataset/getEntities/getEntity → Spring-스타일 객체 리스트/DTO 변환 구문으로 변경
# addDataset/addStr/out_vl/addParam 등 → dataResponse.addDataSet/addParam 등으로 일괄 변경
# getValueAsString → StringUtil.nvl(paramMap.get(xxx), "") 형태로 변환
# userBean 파라미터 자동 제거
# 내부 메서드(함수) 자동 인라인화
# execute() 본문 추출 및 try/catch 분리
# functionGubun, type 분기 파싱 → Controller 메서드화
import os
import re
from pathlib import Path
import chardet
from collections import defaultdict

def servlet_to_controller_and_service_converter():
    input_dir = Path(r"C:\take\file\input")
    output_dir_ctrl = Path(r"C:\take\file\output")
    output_dir_serv = Path(r"E:\panocean\panocean-v2\src\main\java\kr\co\panocean\service\standardInfo")

    def read_source(path: Path) -> str:
        raw = path.read_bytes()
        enc = chardet.detect(raw)["encoding"] or "cp949"
        try:
            return raw.decode(enc)
        except:
            return raw.decode("cp949", errors="replace")

    def replace_ejb_home_remote_service_recursive(code: str) -> str:
        lines = code.splitlines()
        while True:
            home_vars = {}
            remote_vars = {}
            call_lines = []
            for idx, line in enumerate(lines):
                m = re.search(r'(\w+Home)\s+(\w+)\s*=\s*\([^)]+\)\s*ServiceObjFactory\.getInstance\(\)\.lookUpHome\([^)]+\);', line)
                if m:
                    home_var = m.group(2)
                    home_vars[home_var] = idx
            for idx, line in enumerate(lines):
                m = re.search(r'(\w+)\s+(\w+)\s*=\s*\([^)]+\)\s*(\w+)\.create\(\);', line)
                if m:
                    remote_var = m.group(2)
                    home_var = m.group(3)
                    remote_vars[remote_var] = (home_var, idx)
            for idx, line in enumerate(lines):
                m = re.search(r'(\w+)\s*=\s*(\w+)\.(\w+)\((.*)\);', line)
                if m:
                    result_var, remote_var, method_name, args = m.group(1), m.group(2), m.group(3), m.group(4)
                    call_lines.append((idx, result_var, remote_var, method_name, args))
                else:
                    m2 = re.search(r'(\w+)\.(\w+)\((.*)\);', line)
                    if m2:
                        remote_var, method_name, args = m2.group(1), m2.group(2), m2.group(3)
                        call_lines.append((idx, None, remote_var, method_name, args))
            to_remove = set()
            to_replace = {}
            found = False
            for call in call_lines:
                call_idx, result_var, remote_var, method_name, args = call
                if remote_var in remote_vars:
                    home_var, remote_idx = remote_vars[remote_var]
                    if home_var in home_vars:
                        home_idx = home_vars[home_var]
                        to_remove.add(home_idx)
                        to_remove.add(remote_idx)
                        if result_var:
                            to_replace[call_idx] = f"{result_var} = service.{method_name}({args});"
                        else:
                            to_replace[call_idx] = f"service.{method_name}({args});"
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
        return '\n'.join(lines)

    def mask_string_literals(code):
        str_pat = re.compile(r'(["\'])(.*?)(\1)')
        str_list = []
        def replacer(m):
            idx = len(str_list)
            str_list.append(m.group(0))
            return f'__STR{idx}__'
        code2 = str_pat.sub(replacer, code)
        return code2, str_list

    def unmask_string_literals(code, str_list):
        for idx, s in enumerate(str_list):
            code = code.replace(f'__STR{idx}__', s)
        return code

    def extract_execute_body(src: str) -> str:
        m = re.search(r'\bvoid\s+execute\s*\([^)]*\)\s*(?:throws[^{]+)?\s*\{', src)
        if not m:
            return ""
        i, depth = m.end(), 1
        body_chars = []
        while i < len(src) and depth:
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
            if depth:
                body_chars.append(src[i])
            i += 1
        return "".join(body_chars)

    def extract_try_and_catch(body: str):
        m = re.search(r'try\s*\{', body)
        if not m:
            return "", ""
        i, depth = m.end(), 1
        try_chars = []
        while i < len(body) and depth:
            if body[i] == '{':
                depth += 1
            elif body[i] == '}':
                depth -= 1
            if depth:
                try_chars.append(body[i])
            i += 1
        catch_pat = re.compile(r'catch\s*\([^\)]*\)\s*\{((?:[^{}]|\{[^{}]*\})*)\}')
        catch_m = catch_pat.search(body, i)
        catch_body = catch_m.group(1) if catch_m else ""
        return "".join(try_chars), catch_body

    def extract_block(src: str, start_idx: int):
        brace_start = src.find("{", start_idx)
        if brace_start < 0:
            return "", 0
        depth = 1
        i = brace_start + 1
        while i < len(src) and depth:
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
            i += 1
        return src[brace_start+1:i-1], i - start_idx

    def remove_try_catch_blocks(code: str) -> str:
        def replacer(m):
            try_body = m.group(1)
            return try_body.strip()
        pattern = re.compile(
            r'try\s*\{((?:[^{}]|\{[^{}]*\})*)\}'
            r'(?:\s*catch\s*\([^\)]*\)\s*\{(?:[^{}]|\{[^{}]*\})*\})*'
            r'(?:\s*finally\s*\{(?:[^{}]|\{[^{}]*\})*\})?',
            re.DOTALL
        )
        prev = None
        while prev != code:
            prev = code
            code = pattern.sub(replacer, code)
        return code

    def replace_getValueAsString(code: str) -> str:
        return re.sub(
            r'\b\w+\.getValueAsString\s*\(\s*"([^"]+)"\s*\)',
            lambda m: f'dataRequest.getString("{m.group(1)}")',
            code
        )

    def extract_methods(src: str):
        method_pattern = re.compile(
            r'(public|private|protected)?\s+([\w<>]+)\s+(\w+)\s*\(([^)]*)\)\s*(?:throws[^{]*)?\{',
            re.MULTILINE
        )
        methods = {}
        for m in method_pattern.finditer(src):
            ret_type = m.group(2)
            name = m.group(3)
            params = m.group(4).strip()
            start = m.end()
            brace = 1
            i = start
            while i < len(src) and brace:
                if src[i] == '{': brace += 1
                elif src[i] == '}': brace -= 1
                i += 1
            body = src[start:i-1]
            body = remove_try_catch_blocks(body)
            body = replace_getValueAsString(body)
            methods[name] = {
                "ret_type": ret_type,
                "params": params,
                "body": body,
            }
        return methods

    def rename_internal_vars(method_body: str, method_name: str, call_seq: int, params: list, ret_var: str):
        code2, str_list = mask_string_literals(method_body)
        decl_pattern = re.compile(r'(\b\w[\w\d_<>]*\b)\s+(\w+)\s*=')
        decls = decl_pattern.findall(code2)
        param_set = set(params)
        rename_map = {}
        suffix = f"_{method_name}_{call_seq}"
        for typ, var in decls:
            if var not in param_set and (ret_var is None or var != ret_var):
                rename_map[var] = f"{var}{suffix}"
        if ret_var and ret_var not in param_set:
            rename_map[ret_var] = f"{ret_var}{suffix}"
        for old, new in sorted(rename_map.items(), key=lambda x: -len(x[0])):
            code2 = re.sub(rf'(?<![\.\>])\b{old}\b(?!\s*\()', new, code2)
        code2 = unmask_string_literals(code2, str_list)
        return code2, rename_map

    def inline_method_calls(code: str, methods: dict):
        call_seq_counter = defaultdict(int)
        declared_vars = set()
        cast_pattern = re.compile(
            r'(\w+)\s+(\w+)\s*=\s*\((\w+)\)\s*(\w+)\s*\(([^()]*)\)\s*;'
        )
        call_pattern = re.compile(
            r'(\w+)\s+(\w+)\s*=\s*(\w+)\s*\(([^()]*)\)\s*;'
        )
        assign_pattern = re.compile(
            r'(\w+)\s*=\s*(\w+)\s*\(([^;]*)\)\s*;'
        )

        def cast_call_replacer(m):
            ret_type, var_name, cast_type, call_name, call_args = m.groups()
            call_seq_counter[call_name] += 1
            call_seq = call_seq_counter[call_name]
            if call_name not in methods:
                return m.group(0)
            method = methods[call_name]
            method_ret_type = method["ret_type"]
            param_names = [p.strip().split()[-1] for p in method["params"].split(",") if p.strip()]
            arg_values = [a.strip() for a in call_args.split(",")] if call_args.strip() else []
            param_map = dict(zip(param_names, arg_values))
            method_body = method["body"]

            ret_var_match = re.search(r'return\s+([^\s;]+)\s*;', method_body)
            return_expr = ret_var_match.group(1) if ret_var_match else None

            method_body, rename_map = rename_internal_vars(method_body, call_name, call_seq, param_names, return_expr)

            for pname, pval in param_map.items():
                method_body = re.sub(rf'\b{pname}\b', pval, method_body)

            method_body = re.sub(r'return\s+[^\s;]+\s*;', '', method_body)
            assign_line = ""
            temp_var_decl = ""
            if return_expr:
                if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', return_expr):
                    ret_var_renamed = rename_map.get(return_expr, return_expr)
                    assign_line = f"{var_name} = ({cast_type}) {ret_var_renamed};"
                    if ret_var_renamed not in declared_vars:
                        temp_var_decl = f"{method_ret_type} {ret_var_renamed} = null;"
                        declared_vars.add(ret_var_renamed)
                else:
                    assign_line = f"{var_name} = ({cast_type}) {return_expr};"
            var_decl = ""
            if var_name not in declared_vars:
                var_decl = f"{ret_type} {var_name} = null;"
                declared_vars.add(var_name)

            if temp_var_decl:
                method_body = re.sub(rf'\b{method_ret_type}\s+{ret_var_renamed}\s*=\s*[^;]*;', '', method_body)

            lines = []
            if var_decl:
                lines.append(var_decl)
            if temp_var_decl:
                lines.append(temp_var_decl)
            if method_body.strip():
                lines.append(method_body.strip())
            if assign_line and assign_line.strip() != f"{var_name} = {var_name};":
                lines.append(assign_line)
            return "\n".join(lines)

        def call_replacer(m):
            ret_type, var_name, call_name, call_args = m.groups()
            call_seq_counter[call_name] += 1
            call_seq = call_seq_counter[call_name]
            if call_name not in methods:
                return m.group(0)
            method = methods[call_name]
            method_ret_type = method["ret_type"]
            param_names = [p.strip().split()[-1] for p in method["params"].split(",") if p.strip()]
            arg_values = [a.strip() for a in call_args.split(",")] if call_args.strip() else []
            param_map = dict(zip(param_names, arg_values))
            method_body = method["body"]

            ret_var_match = re.search(r'return\s+([^\s;]+)\s*;', method_body)
            return_expr = ret_var_match.group(1) if ret_var_match else None

            method_body, rename_map = rename_internal_vars(method_body, call_name, call_seq, param_names, return_expr)

            for pname, pval in param_map.items():
                method_body = re.sub(rf'\b{pname}\b', pval, method_body)

            method_body = re.sub(r'return\s+[^\s;]+\s*;', '', method_body)
            assign_line = ""
            temp_var_decl = ""
            if return_expr:
                if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', return_expr):
                    ret_var_renamed = rename_map.get(return_expr, return_expr)
                    assign_line = f"{var_name} = {ret_var_renamed};"
                    if ret_var_renamed not in declared_vars:
                        temp_var_decl = f"{method_ret_type} {ret_var_renamed} = null;"
                        declared_vars.add(ret_var_renamed)
                else:
                    assign_line = f"{var_name} = {return_expr};"
            var_decl = ""
            if var_name not in declared_vars:
                var_decl = f"{ret_type} {var_name} = null;"
                declared_vars.add(var_name)

            if temp_var_decl:
                method_body = re.sub(rf'\b{method_ret_type}\s+{ret_var_renamed}\s*=\s*[^;]*;', '', method_body)

            lines = []
            if var_decl:
                lines.append(var_decl)
            if temp_var_decl:
                lines.append(temp_var_decl)
            if method_body.strip():
                lines.append(method_body.strip())
            if assign_line and assign_line.strip() != f"{var_name} = {var_name};":
                lines.append(assign_line)
            return "\n".join(lines)

        def assign_replacer(m):
            var_name, call_name, call_args = m.groups()
            if call_name not in methods:
                return m.group(0)
            method = methods[call_name]
            method_ret_type = method["ret_type"]
            param_names = [p.strip().split()[-1] for p in method["params"].split(",") if p.strip()]
            arg_values = [a.strip() for a in call_args.split(",")] if call_args.strip() else []
            param_map = dict(zip(param_names, arg_values))
            method_body = method["body"]

            ret_var_match = re.search(r'return\s+([^\s;]+)\s*;', method_body)
            return_expr = ret_var_match.group(1) if ret_var_match else None

            method_body, rename_map = rename_internal_vars(method_body, call_name, 0, param_names, return_expr)

            for pname, pval in param_map.items():
                method_body = re.sub(rf'\b{pname}\b', pval, method_body)

            method_body = re.sub(r'return\s+[^\s;]+\s*;', '', method_body)
            assign_line = ""
            if return_expr:
                if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', return_expr):
                    ret_var_renamed = rename_map.get(return_expr, return_expr)
                    assign_line = f"{var_name} = {ret_var_renamed};"
                else:
                    assign_line = f"{var_name} = {return_expr};"

            lines = []
            if method_body.strip():
                lines.append(method_body.strip())
            if assign_line and assign_line.strip() != f"{var_name} = {var_name};":
                lines.append(assign_line)
            return "\n".join(lines)

        code = cast_pattern.sub(cast_call_replacer, code)
        code = call_pattern.sub(call_replacer, code)
        code = assign_pattern.sub(assign_replacer, code)
        return code

    def inline_method_calls_recursive(code: str, methods: dict) -> str:
        prev_code = None
        while prev_code != code:
            prev_code = code
            code = inline_method_calls(code, methods)
        return code

    # 이하 기존 변환 함수들은 그대로 두세요 (생략)

    # ... 나머지 변환 함수, generate_controller, generate_service 등 기존 소스 그대로 ...
    def replace_addDataset(code: str) -> str:
        return re.sub(
            r'\b(?!dataResponse\b)\w+\.addDataset\s*\(',
            'dataResponse.addDataSet(',
            code
        )

    def replace_addStr(code: str) -> str:
        return re.sub(
            r'\b(?!dataResponse\b)\w+\.addStr\s*\(',
            'dataResponse.addParam(',
            code
        )

    def replace_outvl_add(code: str) -> str:
        code = re.sub(r'\bout_vl\.addStr\s*\(', 'dataResponse.addParam(', code)
        code = re.sub(r'\bout_vl\.addParam\s*\(', 'dataResponse.addParam(', code)
        code = re.sub(r'\bout_vl\.addInt\s*\(', 'dataResponse.addParam(', code)
        code = re.sub(r'\bout_vl\.addDouble\s*\(', 'dataResponse.addParam(', code)
        code = re.sub(r'\bout_vl\.addLong\s*\(', 'dataResponse.addParam(', code)
        return code

    def replace_addErrorMessage(code: str) -> str:
        return re.sub(r'addErrorMessage\s*\(\s*out_vl\s*,', 'addErrorMessage(dataResponse,', code)

    def replace_getEntity_blocks(code: str) -> str:
        pattern = re.compile(
            r'Dataset\s+(\w+)\s*=\s*[\w\.]+getDataset\s*\(\s*"([^"]+)"\s*\)\s*;\s*'
            r'(?:\r?\n|\s)*'
            r'(\w+)\s+(\w+)\s*=\s*\(\s*\3\s*\)\s*dataSetManager\.getEntity\s*\(\s*\1\s*,\s*\3\.class\s*\)\s*;',
            re.DOTALL
        )
        def repl(m):
            ds_var = m.group(1)
            ds_name = m.group(2)
            dto_type = m.group(3)
            dto_var = m.group(4)
            return (
                f'List<{dto_type}> {ds_var} = dataRequest.getObjectList("{ds_name}", {dto_type}.class);\n'
                f'{dto_type} {dto_var} = null;\n'
                f'if({ds_var}.size() > 0) {{\n'
                f'    {dto_var} = {ds_var}.get(0);\n'
                f'}} else {{\n'
                f'    {dto_var} = new {dto_type}();\n'
                f'}}'
            )
        return pattern.sub(repl, code)

    def replace_getEntities_blocks(code: str) -> str:
        pattern = re.compile(
            r'Dataset\s+(\w+)\s*=\s*[\w\.]+getDataset\s*\(\s*"([^"]+)"\s*\)\s*;\s*'
            r'(?:\r?\n|\s)*'
            r'Collection\s+(\w+)\s*=\s*dataSetManager\.getEntities\s*\(\s*\1\s*,\s*(\w+)\.class\s*\)\s*;',
            re.DOTALL
        )
        def repl(m):
            ds_var = m.group(1)
            ds_name = m.group(2)
            col_var = m.group(3)
            dto_type = m.group(4)
            return (
                f'List<{dto_type}> {ds_var} = dataRequest.getDataSet("{ds_name}");\n'
                f'Collection {col_var} = {ds_var};'
            )
        return pattern.sub(repl, code)

    def remove_userBean_param(code: str) -> str:
        def param_replacer(match):
            before = match.group(1)
            params = match.group(2)
            param_list = [p.strip() for p in params.split(',')]
            param_list = [p for p in param_list if p != 'userBean']
            new_params = ', '.join(param_list) if any(param_list) else ''
            return f"{before}({new_params})"
        return re.sub(r'(\b\w+\s*)\(([^()]*)\)', param_replacer, code)

    def parse_functionGubun_blocks(body: str, methods: dict):
        blocks = []
        i, depth = 0, 0
        last_branch = None
        while i < len(body):
            ch = body[i]
            if ch == "{":
                depth += 1
                i += 1
                continue
            if ch == "}":
                depth -= 1
                i += 1
                continue
            if depth == 0:
                m_if = re.match(
                    r'if\s*\(\s*"([^"]+)"\s*\.equals\s*\(\s*(functionGubun|type)\s*\)\s*\)', 
                    body[i:], 
                    re.IGNORECASE
                )
                if m_if:
                    name = m_if.group(1)
                    code, jump = extract_block(body, i + m_if.end())
                    code = replace_getEntities_blocks(code.strip())
                    code = replace_addDataset(code)
                    code = replace_addStr(code)
                    code = replace_getValueAsString(code)
                    code = replace_getEntity_blocks(code)
                    code = inline_method_calls_recursive(code, methods)
                    code = remove_userBean_param(code)
                    code = replace_ejb_home_remote_service_recursive(code)
                    blocks.append((name, code))
                    last_branch = "if"
                    i += m_if.end() + jump
                    continue
                m_elif = re.match(
                    r'else\s+if\s*\(\s*"([^"]+)"\s*\.equals\s*\(\s*(functionGubun|type)\s*\)\s*\)', 
                    body[i:], 
                    re.IGNORECASE
                )
                if m_elif:
                    name = m_elif.group(1)
                    code, jump = extract_block(body, i + m_elif.end())
                    code = replace_getEntities_blocks(code.strip())
                    code = replace_addDataset(code)
                    code = replace_addStr(code)
                    code = replace_getValueAsString(code)
                    code = replace_getEntity_blocks(code)
                    code = inline_method_calls_recursive(code, methods)
                    code = remove_userBean_param(code)
                    code = replace_ejb_home_remote_service_recursive(code)
                    blocks.append((name, code))
                    last_branch = "else if"
                    i += m_elif.end() + jump
                    continue
                m_else = re.match(r'else\s*\{', body[i:], re.IGNORECASE)
                if m_else and last_branch in ("if", "else if"):
                    code, jump = extract_block(body, i + m_else.end() - 1)
                    code = replace_getEntities_blocks(code.strip())
                    code = replace_addDataset(code)
                    code = replace_addStr(code)
                    code = replace_getValueAsString(code)
                    code = replace_getEntity_blocks(code)
                    code = inline_method_calls_recursive(code, methods)
                    code = remove_userBean_param(code)
                    code = replace_ejb_home_remote_service_recursive(code)
                    blocks.append(("default", code))
                    i += m_else.end() + jump - 1
                    continue
            i += 1
        return blocks

    def generate_controller(src: str, filename: str) -> str:
        cls_match = re.search(r'public\s+class\s+(\w+)', src)
        cls = cls_match.group(1) if cls_match else "Unnamed"
        ctrl = cls.replace("Servlet", "Controller")
        serv = cls.replace("Servlet", "Service")
        base = filename.replace("Servlet.java", "")
        mapping = base[0].lower() + base[1:] if base else "default"
        methods = extract_methods(src)
        body = extract_execute_body(src)
        try:
            try_body, catch_body = extract_try_and_catch(body)
        except Exception:
            try_body, catch_body = "", ""
        # catch_body에도 치환 규칙 적용
        catch_body = replace_getEntities_blocks(catch_body)
        catch_body = replace_addDataset(catch_body)
        catch_body = replace_addStr(catch_body)
        catch_body = replace_outvl_add(catch_body)
        catch_body = replace_addErrorMessage(catch_body)
        catch_body = replace_getValueAsString(catch_body)
        catch_body = remove_userBean_param(catch_body)
        catch_body = replace_ejb_home_remote_service_recursive(catch_body)
        blocks = parse_functionGubun_blocks(try_body, methods)
        lines = [
            "package com.pan.som.controller.standardInfo;",
            "",
            "import org.springframework.beans.factory.annotation.Autowired;",
            "import org.springframework.stereotype.Controller;",
            "import com.pan.som.common.controller.BaseController;",
            "import com.pan.som.common.resourceBundle.MessageResources;",
            "import lombok.RequiredArgsConstructor;",
            "import lombok.extern.slf4j.Slf4j;",
            "import org.springframework.web.bind.annotation.RequestMapping;",
            "import kr.co.takeit.mvc.context.UxbDataRequest;",
            "import kr.co.takeit.mvc.context.UxbDataResponse;",
            "import com.pan.som.common.utility.Formatter;",
            "import org.slf4j.Logger;",
            "import org.slf4j.LoggerFactory;",
            "import java.util.Map;",
            "import java.util.Locale;",
            "import java.util.List;",
            "import java.util.*;",
            f"import com.pan.som.service.standardInfo.{serv};",
            "",
            "@Controller",
            f'@Slf4j',
            f'@RequiredArgsConstructor',
            f'@RequestMapping("/{mapping}/*")',
            f"public class {ctrl} " + "extends BaseController {",
            "",
            f"    private final {serv} service;",
            ""
        ]
        for name, code in blocks:
            lines.append(f'\t@RequestMapping("{name}.do")')
            lines.append(f"\tpublic void {name}(UxbDataRequest dataRequest, UxbDataResponse dataResponse) " + "{")
            lines.append("\t    Map<String, Object> paramMap = dataRequest.getParamMap();")
            lines.append("\t    try {")
            # try 블록에도 기존 치환 규칙 적용
            code = replace_getEntities_blocks(code)
            code = replace_addDataset(code)
            code = replace_addStr(code)
            code = replace_outvl_add(code)
            code = replace_addErrorMessage(code)
            code = replace_getValueAsString(code)
            code = remove_userBean_param(code)
            code = replace_ejb_home_remote_service_recursive(code)
            for ln in code.splitlines():
                lines.append("\t        " + ln)
            lines.append("\t    } catch (Exception e) {")
            for ln in catch_body.splitlines():
                lines.append("\t        " + ln)
            lines.append("\t    }")
            lines.append("\t    dataResponse.success();")
            lines.append("\t}")
            lines.append("")
        lines.append("}")
        return "\n".join(lines)

    def generate_service(filename: str):
        serv = filename.replace("Servlet.java", "Service").replace(".java", "")
        lines = [
            "package com.pan.som.service.standardInfo;",
            "",
            "import org.springframework.stereotype.Service;",
            "",
            "@Service",
            f"public class {serv} " + "{",
            "    // 비즈니스 로직 없이 빈 클래스",
            "}"
        ]
        return "\n".join(lines)

    output_dir_ctrl.mkdir(parents=True, exist_ok=True)
    output_dir_serv.mkdir(parents=True, exist_ok=True)
    for f in input_dir.glob("*.java"):
        src = read_source(f)
        if "execute" not in src:
            print(f"{f.name}: skipped")
            continue
        ctrl_code = generate_controller(src, f.name)
        serv_code = generate_service(f.name)
        out_ctrl = output_dir_ctrl / f.name.replace("Servlet.java", "Controller.java")
        out_serv = output_dir_serv / f.name.replace("Servlet.java", "Service.java")
        out_ctrl.write_text(ctrl_code, encoding="utf-8")
        out_serv.write_text(serv_code, encoding="utf-8")
        print(f"{f.name} → {out_ctrl.name}, {out_serv.name}")
    print("Controller/Service 변환 완료.")

if __name__ == "__main__":
    servlet_to_controller_and_service_converter()

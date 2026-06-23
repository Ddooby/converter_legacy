# converter_legacy

EJB(Enterprise Java Beans) 소스를 Spring Framework Java 소스로 자동 변환하는 Python 기반 컨버터.

Java 라고 썼지만 Python 으로 구현.
Claude Code 도 처음 사용해보면서 익숙해지는 것도 목표다.

- 변환 규칙은 `patterns/learned_patterns.json` 에 정의하며, Claude Code 세션에서 AS-IS / TO-BE 샘플을 분석해 갱신한다.
- 변환 실행 시 API 호출 없이 저장된 규칙과 내장 코드 로직만으로 처리한다.
- DAO 파일은 Java 변환본과 MyBatis Mapper XML 두 파일을 함께 생성한다.

---

## AS-IS

| 항목 | 내용 |
|------|------|
| 프레임워크 | EJB (Enterprise Java Beans), MiPlatform |
| DB | Oracle |
| WAS | JEUS 8 |
| JDK | OpenJDK 1.8 |
| 형상관리 | SVN / Git (프로젝트 수행 시에만) |

---

## TO-BE

| 항목 | 내용 |
|------|------|
| OS | Windows *(Nexacro Studio는 Windows 계열에서만 사용 가능)* |
| JDK | OpenJDK 17 |
| Spring Framework | 5.3.27 |
| WAS | Tomcat 9.0 |
| DB | Oracle |
| Nexacro SDK | 24.0.0.200 *(21버전 → 24버전: 21버전 async/await 오류로 업그레이드)* |
| IDE | IntelliJ, Nexacro Studio (Latest) |

> **Nexacro SDK 버전 변경 이유**
> 21버전에서 `async/await` 사용 시 오류가 발생하여 24버전으로 업그레이드.

---

## AS-IS vs TO-BE 비교

| 항목 | AS-IS | TO-BE |
|------|-------|-------|
| JDK | OpenJDK 1.8 | OpenJDK 17 |
| 프레임워크 | EJB + MiPlatform | Spring Framework 5.3.27 + Nexacro |
| WAS | JEUS 8 | Tomcat 9.0 |
| DB | Oracle | Oracle |
| IDE | - | IntelliJ + Nexacro Studio |

---

### EJB(Enterprise Java Beans) 개요

**Java Bean**이란 Java로 작성된 소프트웨어 컴포넌트를 말한다. Java는 프로그램 기본 단위가 클래스이고, Java Bean은 그 클래스들이 복합적으로 이루어진 구조다. Java Bean은 **데이터를 표현하는 것을 목적**으로 하는 자바 클래스로, 컴포넌트와 비슷한 의미로 사용된다.

**EJB**는 시스템을 구현하기 위한 **서버 측 컴포넌트 모델**이다.

- Application 업무 로직을 갖고 있는 서버 Application이다.
- 비즈니스 객체들을 관리하는 컨테이너 기술, 설정에 의한 트랜잭션 기술이 담겨있다.
- 2000년대 초반 Java 진영에서 표준으로 인정한 기술로 큰 인기를 얻었다.
- 복잡한 대규모 시스템의 **분산 객체 환경**을 쉽게 구현하기 위해 등장했다.

**EJB 구성 요소**

| 구성 요소 | 역할 |
|-----------|------|
| Enterprise Bean | 비즈니스 로직 구현 |
| Container | DB 처리, Transaction 처리 등 시스템 서비스 구현 |
| EJB Server | Enterprise Bean 및 Container 실행 환경 |
| Client Application | EJB 서비스를 호출하는 클라이언트 |

---

## 01. Java 파일 전환  (`converter/main.py`)
## 실행 방법

```bash
# 의존성 설치 (최초 1회)
pip install -r requirements.txt

# 변환 실행
# converter/dao/input/ 폴더에 변환할 .java 파일을 넣은 후 실행
python -m converter.dao.daoMain convert

# 패턴 파일 확인
python -m converter.dao.daoMain patterns
```

> 결과 파일은 `converter/dao/output/` 폴더에 생성됩니다.
> DAO 파일은 `XxxDAO.java` + `XxxMapper.xml` 두 파일이 함께 생성됩니다.

---

## `converter/converter.py` 핵심 변환 규칙 (AS-IS → TO-BE)

### 1. 클래스 구조

| AS-IS | TO-BE |
|-------|-------|
| `extends CommonDao` | 제거 → `private final CommonDao commonDao;` 필드 주입 |
| `Logger.getLogger(...)` 필드 선언 | 제거 → `@Slf4j` 어노테이션으로 대체 |
| 없음 | `@Slf4j` + `@RequiredArgsConstructor` + `@Repository` 자동 추가 |

### 2. DB 접근 방식 (가장 큰 변화)

| AS-IS | TO-BE |
|-------|-------|
| `StringBuffer sb = new StringBuffer()` + `sb.append(...)` | 제거 → SQL을 Mapper XML로 추출 |
| `conn.prepareStatement(sb.toString())` | 제거 |
| `rs.executeQuery()` | `uxbDAO.select("Namespace.methodId", paramMap)` |
| `executeUpdate()` | `uxbDAO.update("Namespace.methodId", paramMap)` |
| `ps.setString(i++, value)` | `paramMap.put("key", value)` |
| `while (rs.next()) { rs.getString("col") }` | `for (Map<String, Object> map : listMap)` + null 가드 자동 추가 |
| `rs.getString("col")` | `Formatter.nullTrim(String.valueOf(map.get("col")))` |
| `rs.getLong("col")` | `StringUtil.toLong((String) map.get("col"), 0L)` |
| `rs.getDouble("col")` | `StringUtil.toDouble((String) map.get("col"), 0.0)` |
| `finally { rs.close(); ps.close(); }` | 제거 |

### 3. 파라미터 제거

| AS-IS | TO-BE |
|-------|-------|
| 메서드 파라미터 `Connection conn` | 제거 (Spring `@Transactional`로 대체) |
| `conn.setAutoCommit()` / `commit()` / `rollback()` | 제거 |
| 메서드 파라미터 `UserBean userBean` | 제거 → 메서드 내부에서 `UserInfo.getUserInfo()` 사용 |
| `userBean.getUser_id()` | `userInfo.getUserId()` |

### 4. 유틸/예외 치환

| AS-IS | TO-BE |
|-------|-------|
| `DbWrap.getObject(conn, ...)` | `commonDao.getObject(...)` |
| `StringBuffer` | `StringBuilder` |
| `STXException` | `UxbBizException` |
| `Formatter.nullTrim(x)` | `StringUtil.nvl(x, "")` |
| `RowStatus.equals("insert")` | `DataSetRowStatus.INSERT` |

### 5. Mapper XML 자동 생성

- SQL을 Java에서 분리해 `{클래스명}Mapper.xml` 로 생성 (예: `OTCSADetailDAO` → `OTCSADetailMapper.xml`)
- 한 메서드에 쿼리가 여러 개면 `methodName`, `methodName1`, `methodName2` 순으로 ID 부여
- `if/else` 분기로 SQL이 달라지는 경우도 감지해 XML 2개로 분리

---

## 02. DAO 변환 대상  파일 추출 (`targetExtract/daoFile`)

2차 변환 작업 시, **Freezing Source(Business + Common 통합본)** 와 **1차 전환 프로젝트(Git)** 를 비교하여
**신규로 변환해야 할 DAO 파일 목록을 추출**하는 Python 스크립트입니다.

### 동작 요약
- `PATH_SOM` (SOM_Business) + `PATH_COMMON` (SOM_Common) 두 폴더의 `.java` 파일을 합집합으로 수집
- `PATH_GIT` (1차 전환 프로젝트) 폴더의 `.java` 파일과 비교
- **Freezing Source 에는 있지만 1차 전환에는 없는 파일** → 2차 변환 대상으로 간주
- **1차 전환에만 있는 파일**, **공통 파일** 도 참고용으로 함께 출력

### 실행 방법
IDE(VS Code 등)에서 열어 **`Ctrl + F5`** 로 실행하거나, 명령어로 직접 실행:

```bash
python converter/convertList.py
```

> 실행 전 스크립트 상단의 `PATH_SOM`, `PATH_COMMON`, `PATH_GIT` 경로를 환경에 맞게 수정해야 합니다.

### 결과물
- 콘솔에 비교 결과 요약 출력 (변환 대상 파일 수, 1차 전환 신규 파일 수, 공통 파일 수)
- **`dao_compare_result.txt`** 파일에 상세 결과 저장 (스크립트 실행 위치 기준)
  - `[Business+Common에 있고 Git 1차 전환에 없는 파일]` ← 실제 변환 대상 목록
  - `[Git 1차 전환에만 있는 파일]` ← 참고용 (Freezing Source에 없는 이상 파일)
  - `[공통 파일]` ← 양쪽 모두 존재하는 파일

---

## 03. DAO 변환 파일 검증 (`converter/validator.py`)

자동 변환된 **DAO + Mapper XML 쌍을 사용자가 가공한 뒤**, 코드 상 오류나 DAO ↔ XML 불일치를 잡아내는 검증 유틸입니다.
Claude API 호출 없이 정적 분석만으로 동작합니다.

### 검증 항목

| 분류 | 검증 내용 | 레벨 |
|------|-----------|------|
| 파일 쌍 | `XxxDAO.java` ↔ `XxxMapper.xml` 매칭 여부 | ERROR / WARN |
| XML 문법 | well-formed, 루트 `<mapper>`, `namespace` 속성, `id` 중복 | ERROR |
| Java 문법 | 중괄호 `{}` / 괄호 `()` 균형 (문자열·주석 제외) | ERROR |
| 네임스페이스 | XML `namespace` ↔ 클래스명에서 `DAO` 제거한 값 | WARN |
| **호출 ID** | DAO 의 `uxbDAO.select("NS.id", paramMap)` 가 XML 에 실존하는지 | ERROR |
| **호출 종류** | DAO 호출 `select`/`insert`/`update`/`delete` ↔ XML 태그 일치 | WARN |
| **파라미터 누락** | XML `#{key}` 인데 DAO `paramMap.put("key", ...)` 없음 | ERROR |
| **파라미터 미사용** | DAO 에서 put 했는데 XML 에서 사용 안 함 | WARN |
| 고립 ID | XML 에만 있고 DAO 에서 호출되지 않는 id | INFO |

> XML 파싱이 실패하면 교차검증은 자동 스킵되어 호출 ID 누락 알람으로 도배되지 않습니다 (XML 먼저 수정).

### 실행 방법

```bash
# 기본 (converter/dao/validate/ 폴더 검증)
python -m converter.dao.daoMain validate

# 검증 폴더 지정
python -m converter.dao.daoMain validate --dir converter/dao/output

# 결과 보고서 파일로 저장
python -m converter.dao.daoMain validate --dir converter/dao/validate --report converter/dao/validate/_validate_report.txt
```

`.env` 에 `VALIDATE_DIR=...` 를 두면 `--dir` 생략 가능.

### 결과물

- 콘솔에 Rich 테이블로 ERROR / WARN / INFO 목록 출력
- `--report` 지정 시 동일 내용을 텍스트 보고서로 저장
- 종료 시 매칭 페어 수와 레벨별 건수 요약

### 매칭 규칙

- DAO: 파일명이 `DAO.java` 로 끝나는 파일만 매핑 대상
- Mapper: `XxxDAO.java` ↔ `XxxMapper.xml` (`DAO` 제거 후 `Mapper.xml`)
- 매칭되지 않는 `*_BACKUP*.java` 등 백업 파일은 INFO 로 표시 후 제외

---

## 04. Servlet → Controller 변환 (`converter/controller/controllerMain.py`)

EJB Servlet 파일을 Spring MVC Controller 파일로 변환하는 스크립트입니다.
Claude API 호출 없이 저장된 패턴(`learned_patterns.json`)과 내장 규칙만으로 동작합니다.

### 폴더 구조

```
converter/controller/
├── input/         ← 변환할 Servlet.java 파일 배치
├── output/        ← 변환된 Controller.java 파일 생성
└── patterns/
    └── learned_patterns.json   ← 변환 패턴 캐시
```

### 실행 방법

```bash
# input/ 폴더에 변환할 *Servlet.java 파일을 넣은 후 실행
python -m converter.controller.controllerMain convert

# 패턴 파일 내용 확인
python -m converter.controller.controllerMain patterns
```

> 결과 파일은 `converter/controller/output/` 폴더에 생성됩니다.
> 파일명은 `XxxServlet.java` → `XxxController.java` 로 자동 변경됩니다.

### 환경변수 (`.env` 선택 설정)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `CTRL_INPUT_DIR` | `converter/controller/input` | 입력 폴더 경로 |
| `CTRL_OUTPUT_DIR` | `converter/controller/output` | 출력 폴더 경로 |
| `CTRL_PATTERNS_FILE` | `converter/controller/patterns/learned_patterns.json` | 패턴 파일 경로 |
| `CTRL_OVERWRITE_MODE` | `overwrite` | 출력 파일 중복 시 처리 (`overwrite` / `skip` / `backup`) |
| `CTRL_EXTERNAL_GEN_YN` | `false` | 외부 경로에 결과 생성 여부 |
| `CTRL_EXTERNAL_BASE` | (없음) | `CTRL_EXTERNAL_GEN_YN=true` 시 출력 기준 경로 |

---

## 05. BigDecimal 후처리 패치 (`converter/dao/patch.py`)

자동 변환 또는 수동 커스텀이 완료된 Java 파일에 **AMT/AMOUNT 컬럼 타입을 BigDecimal로 후처리** 적용하는 스크립트입니다.
Claude API 호출 없이 정규식 치환만으로 동작합니다.

### 적용 패턴

| AS-IS | TO-BE |
|-------|-------|
| `Formatter.nullDouble(StringUtil.nvl(map.get("*AMT"), ...))` | `Formatter.nullBigDecimal(StringUtil.nvl(map.get("*AMT"), "0"))` |
| `Formatter.nullLong(StringUtil.nvl(map.get("*AMOUNT"), ...))` | `Formatter.nullBigDecimal(StringUtil.nvl(map.get("*AMOUNT"), "0"))` |

- 컬럼명이 `AMT` 또는 `AMOUNT` 로 끝나는 경우에만 적용 (대소문자 무관)
- `nullDouble` / `nullLong` 모두 `nullBigDecimal` 로 변환

### 실행 방법

```bash
# 변경 대상 미리 확인 (파일 수정 없음)
python -m converter.dao.patch --dry-run

# 기본 실행 (validate/ → output/ 순으로 존재하는 폴더 자동 탐지)
python -m converter.dao.patch

# 폴더 직접 지정 (상대경로)
python -m converter.dao.patch --dir converter/dao/validate

# 다른 프로젝트 경로 직접 지정 (절대경로)
python -m converter.dao.patch --dir C:\Projects\MyApp\src\main\java\com\example\dao
```

`.env` 에 `PATCH_DIR` 을 지정하면 `--dir` 생략 가능합니다. 절대경로를 쓰면 이 컨버터 프로젝트 외부 경로도 대상으로 삼을 수 있습니다.

```dotenv
# .env
PATCH_DIR=C:\Projects\MyApp\src\main\java\com\example\dao
```

우선순위: `--dir` 인수 > `.env` 의 `PATCH_DIR` > 기본 폴더 자동 탐색

### 결과물

- 콘솔에 변경된 파일 목록과 건수 출력
- `--dry-run` 옵션 사용 시 실제 파일 수정 없이 대상 목록만 확인 가능
- 대상 폴더 내 `.java` 파일 전체를 재귀 탐색

> **참고:** `convert` 명령 실행 시에는 이 패턴이 자동 적용됩니다.
> `patch.py` 는 이미 변환·커스텀 완료된 파일에 소급 적용하는 용도입니다.

---

## 06. MiPlatform XFDL → Nexacro XFDL 변환 (`converter/nexacro/nexacroMain.py`)

1차 AI 변환된 XFDL 파일을 정제된 Nexacro XFDL로 자동 변환하는 스크립트입니다.
Claude API 호출 없이 저장된 패턴(`nexacro_convert_patterns.json`)과 내장 규칙만으로 동작합니다.

### 폴더 구조

```
converter/nexacro/
├── as-is/         ← 변환할 XFDL 파일 배치 (1차 AI변환본)
├── to-be/         ← 변환된 XFDL 파일 생성 (정제본)
├── output/        ← 테스트 출력용 임시 폴더
├── reference/     ← Java 변환 참고 소스 (패턴 추출 기준)
├── patterns/
│   └── nexacro_convert_patterns.json   ← 변환 패턴 정의
├── nexacroMain.py ← CLI 진입점
└── converter.py   ← 변환 엔진
```

### 실행 방법

```bash
# 기본 (as-is/ 폴더 전체 → to-be/ 폴더)
python -m converter.nexacro.nexacroMain

# 단일 파일 변환
python -m converter.nexacro.nexacroMain path/to/input.xfdl

# 단일 파일 변환 + 출력 경로 지정
python -m converter.nexacro.nexacroMain path/to/input.xfdl path/to/output.xfdl

# 폴더 단위 변환
python -m converter.nexacro.nexacroMain --dir path/to/input_dir path/to/output_dir
```

> 결과 파일은 기본적으로 `converter/nexacro/to-be/` 폴더에 생성됩니다.

### 환경변수 (`.env` 설정)

우선순위: `NEXACRO_BASE_DIR` > `NEXACRO_FILES` > `NEXACRO_INPUT_DIR` / `NEXACRO_OUTPUT_DIR`

| 변수 | 설명 |
|------|------|
| `NEXACRO_BASE_DIR` | 폴더 경로 → 하위 `*.xfdl` 전체 재귀 **in-place** 변환 |
| `NEXACRO_FILES` | **폴더 경로** → 하위 `*.xfdl` 전체 재귀 in-place 변환 |
| `NEXACRO_FILES` | **쉼표 구분 파일 경로** → 개별 파일 in-place 변환 |
| `NEXACRO_INPUT_DIR` | as-is 입력 폴더 (기본값: `converter/nexacro/as-is`) |
| `NEXACRO_OUTPUT_DIR` | to-be 출력 폴더 (기본값: `converter/nexacro/to-be`) |

**외부 프로젝트 폴더 변환 예시 (`.env`)**

```dotenv
# 특정 폴더 하위 *.xfdl 전체 in-place 변환
NEXACRO_FILES=C:\Projects\Panocean\nexacro\biz\salesOpportunity\report

# 개별 파일만 변환
# NEXACRO_FILES=converter/nexacro/as-is/FooForm.xfdl,converter/nexacro/as-is/BarForm.xfdl
```

```bash
python -m converter.nexacro.nexacroMain
```

### 변환 처리 순서 (converter.py `_convert_script`)

| 순서 | 처리 내용 |
|------|-----------|
| 1 | `fnAuthButtonControl` 전용 패턴 (경고 주석 포함 상태에서 매칭) |
| 2 | 경고 주석 제거 (`변수 확인 필요` 등) |
| 3 | `[AIChanger]` 마커 치환 (Script 내) |
| 4 | UXB INFO getBindDataset 마커 치환 |
| 5 | SVC_LOC URL 변환 (`com.pageCtx` + Servlet → REST URL) |
| 6 | Dataset getColumn 컬럼명 camelCase 변환 |
| 7 | Decimal 산술 변환 (`nexacro.round` 내 산술식 → Decimal 체인) |
| 8 | 텍스트 치환 (com.isEmpty / pThis → this 등) |
| 9 | 외부 JS 참조 주입 (`sa.*` / `so.*` / `ins.*` 감지 → `take.loadJs`) |
| 10 | async/await 변환 (`com.*` / `so.*` / `sa.*` / `ins.*` 호출 함수 전체 래핑) |

### 주요 변환 규칙 (Script 영역)

#### 텍스트 치환

| AS-IS | TO-BE |
|-------|-------|
| `pThis` | `this` |
| `com.isEmpty(pThis, x)` | `com.isEmpty(x)` |
| `.getRowCount()` | `.rowcount` |
| `== "insert"` / `!= "NORMAL"` | `Dataset.ROWTYPE_INSERT` / `Dataset.ROWTYPE_NORMAL` |
| `this.close(null)` | `com.fnClose(this)` |
| `gdsCCDUserMDS` | `gdsUserInfo` (컬럼명 camelCase 변환 포함) |
| 따옴표 없는 `Domain.msg~` | `"Domain.msg~"` (쌍따옴표 자동 감싸기) |
| UXB INFO getBindDataset 마커 | `com.getBindDataset(this, 컴포넌트)` |
| `[AIChanger]` 마커 (Script) | 실제 함수 호출 (`com.drawDetailGridBkColor` 등) |
| 경고 주석 (`변수 확인 필요` 등) | 제거 |

#### SVC_LOC URL 변환

`com.transaction()` 의 URL 인자에서 `com.pageCtx` 를 `functionGubun` 값 기반의 REST URL 로 변환.
`functionGubun` 이 URL 앞(이전 줄) 또는 URL 뒤(같은 transaction 호출 내 6번째 인자)에 있어도 감지.

| AS-IS | TO-BE |
|-------|-------|
| `"SVC_LOC::" + com.pageCtx + "/InternalTcOutServlet"` (functionGubun=onload) | `"SVC_LOC::internalTcOut/onload.do"` |
| `"SVC_LOC::" + com.pageCtx + "/SalesListServlet"` (functionGubun=ONLOAD_LIST) | `"SVC_LOC::salesList/ONLOAD_LIST.do"` |

변환 규칙: `XxxServlet` → `xxx` (camelCase) + `/functionGubun값.do`

#### Decimal 산술 변환

부동소수점 오차 방지 목적으로 산술 연산을 `nexacro.Decimal` 체인으로 변환.
변환 트리거는 아래 두 가지이며 재귀 하강 파서로 연산자 우선순위를 정확히 보존한다.

**트리거 1 — `nexacro.round()` 내 산술식**

| AS-IS | TO-BE |
|-------|-------|
| `nexacro.round((a - diff) * b + c)` | `nexacro.round(new nexacro.Decimal(take.nvl(a, 0)).sub(diff).mul(take.nvl(b, 0)).add(take.nvl(c, 0)))` |
| `nexacro.round(val - getCol1 - getCol2)` | `nexacro.round(new nexacro.Decimal(val).sub(take.nvl(getCol1, 0)).sub(take.nvl(getCol2, 0)))` |
| `nexacro.round(bal / (getCol1 - getCol2))` | `nexacro.round(new nexacro.Decimal(bal).div(new nexacro.Decimal(take.nvl(getCol1, 0)).sub(take.nvl(getCol2, 0))))` |

**트리거 2 — 금액 관련 변수 산술 대입문**

LHS 변수명 또는 RHS 피연산자 변수명에 아래 금액 키워드가 포함된 산술 대입문을 변환.

| 금액 키워드 | 예시 변수명 |
|------------|------------|
| `amt` / `amount` | `bal_amt`, `pl_amt`, `supply_amount` |
| `rate` | `exc_rate`, `vat_rate` |
| `vat` | `vat_amt`, `input_vat` |
| `cost` | `nav_cost`, `total_cost` |
| `fee` | `service_fee`, `base_fee` |

> 키워드 추가가 필요하면 `converter.py` 상단 `_FINANCIAL_KW_RE` 패턴에 `|키워드` 추가.

| AS-IS | TO-BE |
|-------|-------|
| `bal_amt = cb_bal_amt - al_bal_amt;` | `bal_amt = new nexacro.Decimal(cb_bal_amt).sub(al_bal_amt);` |
| `nav_cost = cb_nav_cost - al_nav_cost;` | `nav_cost = new nexacro.Decimal(cb_nav_cost).sub(al_nav_cost);` |
| `vat_amt = supply_amt * vat_rate;` | `vat_amt = new nexacro.Decimal(supply_amt).mul(vat_rate);` |

**공통 변환 규칙**

- `getColumn(...)` atom → `take.nvl(..., 0)` 자동 래핑
- 일반 변수 (`diff`, `balance` 등) → 래핑 없이 그대로 전달 (이미 Decimal이거나 number 모두 수용)
- 우변에 복잡한 식이 오는 경우 재귀적으로 Decimal 체인 생성
- 이미 `nexacro.Decimal` 이 포함된 식은 변환 스킵
- 비교/논리 연산자 포함 식 (`==`, `>`, `&&` 등) 스킵
- 파싱 실패 시 원본 유지 (예외 무시)

#### 외부 JS 참조 주입

스크립트 내 `sa.*` / `so.*` / `ins.*` 호출 감지 시, `//공통 라이브러리 호출` 주석 아래에 `take.loadJs` 라인 자동 삽입.
이미 삽입된 경우 중복 삽입하지 않음.

| 감지 패턴 | 삽입 내용 |
|-----------|-----------|
| `sa.*` 호출 | `take.loadJs(this, "saJsLoad_" + this.name, "/biz/commonJs/sa.js")` |
| `so.*` 호출 | `take.loadJs(this, "soJsLoad_" + this.name, "/biz/commonJs/so.js")` |
| `ins.*` 호출 | `take.loadJs(this, "insJsLoad_" + this.name, "/biz/commonJs/ins.js")` |

#### async/await 변환

`com.*` / `so.*` / `sa.*` / `ins.*` 직접 호출이 있는 함수 → `async` 대상으로 표시.
해당 함수를 호출하는 함수도 전파(propagation)되어 `async` 처리.

| 패턴 | 변환 내용 |
|------|-----------|
| `com.*` / `so.*` / `sa.*` / `ins.*` 직접 호출 함수 | `(async () => { ... }).call(this)` 로 감싸기 |
| 다른 async 함수에서 호출되는 함수 | `return (async () => { ... }).call(this)` |
| `com.*` 함수 호출 라인 | `await com.*()` 자동 추가 |
| `so.*` / `sa.*` / `ins.*` 함수 호출 라인 | `await so.*()` 등 자동 추가 |
| `this.fnXxx()` (async 전파된 함수) | `await this.fnXxx()` 자동 추가 |

**`return` 유무 기준**

async 래핑 시 `return` 을 붙이는지 여부는 **"다른 async 함수 안에서 호출되는가"** 로 결정된다.

```js
// return 없음 — 이벤트 핸들러나 최상위 진입 함수 (결과를 기다리는 호출자가 없음)
this.fnSearch = function() {
    (async () => {
        await com.transaction(...);
    }).call(this);
};

// return 있음 — 다른 async 함수에서 await this.fnIsUpdate() 로 호출됨
this.fnIsUpdate = function() {
    return (async () => {
        var bUpd = false;
        if (bUpd == false) bUpd = await com.isUpdateDataset(this["FSVoyageAnalMDS"]);
        return bUpd;
    }).call(this);
};
```

`return` 이 있으면 호출부에서 `await this.fnIsUpdate()` 로 결과값을 받을 수 있다.
`return` 이 없으면 호출부에서 `await` 해도 `undefined` 가 반환되고, async 작업 완료를 기다리지 않는다.

**`new Promise` 와의 차이**

| | async IIFE | `new Promise` |
|---|---|---|
| 내부에서 `await` 사용 | 가능 | 불가 |
| 주 용도 | `await` 기반 비동기 래핑 | 콜백 → Promise 변환 |
| 컨버터 생성 여부 | 생성함 | 생성하지 않음 |

`new Promise` 는 `setTimeout`, 이벤트 리스너 등 콜백 기반 API를 Promise 로 감쌀 때 사용하는 패턴으로,
이 컨버터에서는 생성하지 않는다.

### 주요 변환 규칙 (Layout Cell 영역)

| AS-IS | TO-BE |
|-------|-------|
| `cssclass="EXPR(...)"` | `cssclass="expr:(...)"` |
| `[AIChanger] drawDetailGridDisableColor` 마커 | `com.drawDetailGridDisableColor(...)` |
| `[AIChanger] drawDetailGridBkColor` 마커 | `com.drawDetailGridBkColor(...)` |
| `background="..."` 속성 | `cssclass="..."` 로 변환 또는 병합 |
| body 밴드 내 `displaytype="date"` 셀 | `calendardateformat="yyyy-MM-dd"` 자동 추가 |

### 패턴 파일 업데이트 방법

1. `converter/nexacro/as-is/` 에 변환할 XFDL 파일 배치
2. 수동으로 다듬은 정제본을 `converter/nexacro/to-be/` 에 동일 파일명으로 배치
3. AS-IS / TO-BE diff를 보고 `nexacro_convert_patterns.json` 갱신
4. `nexacroMain.py` 재실행으로 자동 변환 결과 검증

---
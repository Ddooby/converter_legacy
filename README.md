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

## 02. 변환 대상 DAO 파일 추출 (`targetExtract/daoFile`)

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

## 03. 변환 파일 검증 (`converter/validator.py`)

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

## 04. BigDecimal 후처리 패치 (`converter/dao/patch.py`)

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
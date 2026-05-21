# EJB → Spring Java Converter (with Claude)

## 프로젝트 개요

EJB(Enterprise Java Beans) 소스를 Spring Framework Java 소스로 자동 변환하는 Python 기반 컨버터.

- **패턴 학습** (`analyzer.py`): Claude API를 사용해 AS-IS / TO-BE 샘플 쌍에서 치환 규칙을 추출하고 JSON으로 저장 (일회성)
- **파일 변환** (`converter.py`): 저장된 패턴 JSON + 내장 변환 규칙으로 코드 변환 처리 (**API 호출 없음**)

### 기술 스택

| 항목 | 내용 |
|------|------|
| 언어 | Python 3.11+ |
| AI (패턴 학습 전용) | Claude API (claude-sonnet-4-6) |
| AS-IS | EJB + MiPlatform / Oracle / JEUS 8 / OpenJDK 1.8 |
| TO-BE | Spring Framework 5.3.27 + Nexacro / Oracle / Tomcat 9.0 / OpenJDK 17 |

---

## 폴더 구조

```
java_converter_with_claude/
├── CLAUDE.md                   # 이 파일
├── README.md
├── requirements.txt            # Python 의존성
├── .env.example                # 환경변수 템플릿
├── .env                        # 실제 환경변수 (git 제외)
│
├── convert/                    # 변환 관련 전체 모듈
│   ├── convertList.py          # 변환 대상 DAO 파일 추출 (Freezing Source vs Git 비교)
│   └── converter/              # 핵심 변환 로직 (Python 패키지)
│       ├── __init__.py
│       ├── convert.py          # CLI 진입점 (convert / validate / patterns 명령)
│       ├── converter.py        # 변환 실행기 (API 없음, 코드 규칙 기반)
│       ├── validate.py         # DAO ↔ Mapper XML 검증 유틸
│       ├── functionService/    # 변환 함수 서비스
│       ├── asisConverter/      # AS-IS 변환 참고 소스 (Java)
│       ├── input/              # 변환할 EJB 소스 파일 (사용자 입력)
│       ├── output/             # 변환된 Spring 소스 파일 (자동 생성)
│       │   ├── XxxDAO.java     # 변환된 Java 파일
│       │   └── XxxMapper.xml   # 생성된 Mapper XML (DAO 파일인 경우)
│       ├── validate/           # 검증 대상 파일 (사용자가 가공 후 배치)
│       ├── patterns/           # 학습된 변환 패턴 캐시 (JSON)
│       └── samples/            # 패턴 학습용 샘플 코드
│           ├── as_is/          # AS-IS EJB 원본 파일
│           └── to_be/          # TO-BE Spring 변환 파일
```

---

## 워크플로우

```
1. 샘플 준비
   convert/converter/samples/as_is/  ← AS-IS EJB 파일 배치
   convert/converter/samples/to_be/  ← TO-BE Spring 파일 배치 (같은 파일명)
                                        DAO 파일이면 XxxMapper.xml 도 함께 배치

2. 패턴 학습 (Claude API 호출 — 샘플 추가 시에만 실행)
   python -m convert.converter.convert learn

3. 변환 실행 (API 호출 없음)
   convert/converter/input/ ← 변환할 EJB 파일 배치
   python -m convert.converter.convert convert

4. 결과 확인
   convert/converter/output/ ← 변환된 Java + Mapper XML 파일 확인

5. 변환 파일 검증
   convert/converter/validate/ ← 가공한 파일 배치
   python -m convert.converter.convert validate
```

---

## 주요 변환 규칙 (EJB → Spring)

### 어노테이션 변환
| AS-IS (EJB) | TO-BE (Spring) |
|-------------|----------------|
| `@Stateless` | `@Service` |
| `@Stateful` | `@Service` + 상태 관리 |
| `@EJB` | `@Autowired` |
| `@PersistenceContext` | `@Autowired` (Repository) |
| `@TransactionAttribute` | `@Transactional` |
| `@Remote`, `@Local` | 제거 |

### 클래스 구조 변환
| AS-IS (EJB) | TO-BE (Spring) |
|-------------|----------------|
| SessionBean implements SessionBeanInterface | `@Service` 클래스 |
| Home Interface / Remote Interface | 제거 |
| JNDI Lookup | `@Autowired` DI |
| Container-Managed Transaction | `@Transactional` |

### 패키지/임포트 변환
| AS-IS | TO-BE |
|-------|-------|
| `javax.ejb.*` | `org.springframework.*` |
| `javax.naming.*` | 제거 |
| `com.tmax..*` (JEUS) | Spring 대응 클래스 |

### DAO 파일 변환 규칙

#### executeQuery → MyBatis
| AS-IS | TO-BE |
|-------|-------|
| `PreparedStatement` + `rs.executeQuery()` | `uxbDAO.select("Namespace.methodId", paramMap)` |
| SQL 문자열 연결 (`+ param.longValue() +`) | MyBatis 바인딩 (`#{paramName}`) |
| `while (rs.next()) { ... }` | `for (Map<String, Object> map : listMap) { ... }` |
| `rs.getString("col")` | `(String) map.get("col")` |
| `rs.getLong("col")` | `StringUtil.toLong((String) map.get("col"), 0L)` |
| `rs.getDouble("col")` | `StringUtil.toDouble((String) map.get("col"), 0.0)` |
| `finally { rs.close(); ps.close(); }` | 제거 |

#### 클래스/메서드 변환
| AS-IS | TO-BE |
|-------|-------|
| `DbWrap.setObject(conn, vo, sql, mode)` | `commonDao.setObject(vo, sql, mode)` |
| `DbWrap.getObject(conn, Class, sql)` | `commonDao.getObject(Class, sql)` |
| 메서드 파라미터 `Connection conn` | 제거 |
| 메서드 파라미터 `UserBean userBean` | 제거 → 메서드 내부에서 `UserInfo.getUserInfo()` 사용 |
| `STXException` | `Exception` |
| `new Timestamp(...)` | `new Date(...)` |
| `StringBuffer` | `StringBuilder` |
| `Formatter.nullTrim(x)` | `StringUtil.nvl(x, "")` |

#### Mapper XML 생성
- 파일명: `{클래스명에서 DAO 제거}Mapper.xml` (예: `OTCSADetailDAO` → `OTCSADetailMapper.xml`)
- namespace: 클래스명에서 DAO 제거 (예: `OTCSADetail`)
- 한 메서드 내 여러 쿼리: `methodName`, `methodName1`, `methodName2` 순으로 ID 부여

---

## 개발 가이드

### 환경 설정
```bash
pip install -r requirements.txt
cp .env.example .env
# .env 에 ANTHROPIC_API_KEY 입력 (패턴 학습 시에만 필요)
```

### Claude API 사용 원칙
- `analyzer.py` 전용 — 샘플에서 치환 규칙을 추출할 때만 호출
- 출력 형식: 코드가 직접 실행 가능한 `import_replacements` / `annotation_replacements` / `text_replacements` JSON
- 변환 규칙이 바뀌면 샘플을 추가하고 `python -m convert.converter.convert learn --relearn` 재실행
- `converter.py` 는 API를 **호출하지 않음** — 저장된 패턴 JSON + 내장 규칙만 사용

### 코드 스타일
- Python 타입 힌트 적극 사용
- 클래스 단위 모듈화
- 에러는 명시적으로 raise, 조용히 무시하지 않음
- 로그는 print 대신 `logging` 모듈 사용

---

## 샘플 파일 네이밍 규칙

샘플은 AS-IS / TO-BE 파일명을 **동일하게** 맞춰야 패턴 매핑이 가능하다.
DAO 파일인 경우 `to_be/` 에 Mapper XML도 함께 배치한다.

```
convert/converter/samples/
  as_is/
    UserService.java          # EJB 원본
    OTCSADetailDAO.java       # EJB DAO 원본
  to_be/
    UserService.java          # Spring 변환본 (같은 파일명)
    OTCSADetailDAO.java       # Spring DAO 변환본
    OTCSADetailMapper.xml     # MyBatis Mapper XML (DAO 파일 시 추가)
```

---

## 주의사항

- `.env` 파일은 절대 git에 커밋하지 않음 (`.gitignore` 처리)
- `ANTHROPIC_API_KEY` 는 반드시 `.env` 또는 환경변수로만 관리
- `output/` 폴더 내용은 git 추적 제외 권장
- 변환 결과는 반드시 사람이 검토 — 복잡한 비즈니스 로직은 수동 보완 필요

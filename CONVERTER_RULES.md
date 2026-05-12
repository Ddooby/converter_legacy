# Converter 변환 규칙 명세

`converter/converter.py` 기준 전체 변환 규칙 정리.  
변환은 **RuleEngine → DaoTransformer** 순서로 실행된다.

---

## 실행 순서 (transform 파이프라인)

```
1. RuleEngine.apply()          — patterns JSON 기반 import/annotation/text 치환
2. _apply_line_rules()         — 정규식 LINE_RULES 일괄 치환
3. _add_class_decorations()    — 클래스 어노테이션·필드 삽입
4. _convert_execute_queries()  — PreparedStatement → uxbDAO 변환 + Mapper XML 추출
5. _wrap_listmap_for_loops()   — for (Map : listMap) 루프에 null 가드 삽입
6. _inject_user_delegation()   — userInfo 사용 메서드에 UserDelegation 선언 주입
7. _fix_throws()               — throws Exception, Exception 중복 제거
8. _remove_trivial_try_catch() — rethrow 전용 try-catch 제거
9. _remove_throws_exception()  — 메서드 시그니처 throws Exception 제거
10. _cleanup_formatting()      — 빈 줄·들여쓰기 정규화
```

---

## 1. RuleEngine (patterns JSON)

`patterns/learned_patterns.json`을 읽어 아래 항목을 순서대로 적용한다.

| 키 | 처리 방식 |
|----|-----------|
| `import_replacements` | `from` → `to` 문자열 단순 치환 |
| `import_prefix_removals` | 해당 prefix로 시작하는 import 라인 전체 삭제 |
| `import_additions` | package 선언 바로 뒤에 중복 없이 import 삽입 |
| `annotation_replacements` | 정규식 단어 경계(`\b`) 기준 어노테이션 치환 |
| `text_replacements` | 일반 문자열 치환 |

---

## 2. LINE_RULES (정규식 치환, 순서 보장)

`_apply_line_rules()`에서 목록 순서대로 전체 코드에 적용.  
**순서가 우선순위**이므로 아래 표의 위에서 아래로 먼저 매칭된 규칙이 적용된다.

### 2-1. 선언 제거

| AS-IS | TO-BE | 비고 |
|-------|-------|------|
| `DbWrap dbw = new DbWrap();` | *(삭제)* | DbWrap 인스턴스 선언 |
| `private Logger log = Logger.getLogger(...);` | *(삭제)* | `@Slf4j`로 대체 |
| `PreparedStatement ps = null;` | *(삭제)* | — |
| `ResultSet rs = null;` | *(삭제)* | — |

### 2-2. 타입·클래스 변환

| AS-IS | TO-BE |
|-------|-------|
| `StringBuffer` | `StringBuilder` |
| `PKGenerator.` | `pkGenerator.` |
| `STXException` | `UxbBizException` |
| `new Long(` | `Long.valueOf(` |
| `new Double(` | `Double.valueOf(` |

### 2-3. DbWrap → commonDao 변환 (conn 파라미터 제거)

| AS-IS | TO-BE |
|-------|-------|
| `xxx.setObject(conn, ...)` | `commonDao.setObject(...)` |
| `xxx.getObjects(conn, ...)` | `commonDao.getObjects(...)` |
| `xxx.getObject(conn, ...)` | `commonDao.getObject(...)` |
| `xxx.updateQuery(conn, ...)` | `commonDao.updateQuery(...)` |
| `xxx.isExist(conn, ...)` | `commonDao.isExist(...)` |

### 2-4. 파라미터 제거

| 제거 대상 | 위치 |
|-----------|------|
| `Connection conn` | 메서드 파라미터 (앞·중간·끝 모두) |
| `UserBean userBean` | 메서드 파라미터 (앞·중간·끝 모두) |

### 2-5. userBean → userInfo

| AS-IS | TO-BE |
|-------|-------|
| `userBean.getUser_id()` | `userInfo.getUserId()` |
| `userBean.getUser_name()` | `userInfo.getUserName()` |
| `userBean.getXxx()` | `userInfo.getXxx()` (일반 치환) |

### 2-6. RowStatus 변환

| AS-IS | TO-BE |
|-------|-------|
| `.getStatus().equals("insert")` | `.getRowStatus() == DataSetRowStatus.INSERT` |
| `.getStatus().equals("update")` | `.getRowStatus() == DataSetRowStatus.UPDATE` |
| `.getStatus().equals("delete")` | `.getRowStatus() == DataSetRowStatus.DELETE` |

### 2-7. ResultSet 컬럼 읽기 → Map 변환 (우선순위 순)

| AS-IS | TO-BE | 비고 |
|-------|-------|------|
| `Formatter.nullTrim(rs.getString("COL"))` | `Formatter.nullTrim(String.valueOf(map.get("COL")))` | 우선 처리 |
| `.setXxx(rs.getString("COL"))` | `.setXxx(Formatter.nullTrim(String.valueOf(map.get("COL"))))` | VO/DTO setter 우선 |
| `new Long(rs.getLong("COL"))` | `Formatter.nullLong(StringUtil.nvl(map.get("COL"), "0"))` | 래핑 형태 우선 |
| `new Double(rs.getDouble("COL"))` | `Formatter.nullDouble(StringUtil.nvl(map.get("COL"), "0.0"))` | 래핑 형태 우선 |
| `rs.getString("COL")` | `map.get("COL")` | 일반 |
| `rs.getLong("COL")` | `StringUtil.toLong((String) map.get("COL"), 0L)` | — |
| `rs.getDouble("COL")` | `StringUtil.toDouble((String) map.get("COL"), 0.0)` | — |
| `rs.getInt("COL")` | `StringUtil.toInt((String) map.get("COL"), 0)` | — |
| `rs.getTimestamp("COL")` | `Formatter.parseToDate(map.get("COL"))` | — |

### 2-8. Formatter 변환

| AS-IS | TO-BE | 비고 |
|-------|-------|------|
| `Formatter.nullTrim(simpleVar)` | `StringUtil.nvl(simpleVar, "")` | 단순 인자 |
| `Formatter.nullLong(obj.getXxx())` | `Formatter.nullLong(StringUtil.nvl(obj.getXxx(), "0"))` | getter 래핑 |

### 2-9. close / 자원 해제 제거

| 제거 대상 |
|-----------|
| `if (rs != null) rs.close();` |
| `if (ps != null) ps.close();` |
| `rs.close();` |
| `ps.close();` |

### 2-10. 예외 변환

| AS-IS | TO-BE |
|-------|-------|
| `throw new Exception("ERR-xxx")` | `throw new UxbBizException("ERR-xxx")` |

---

## 3. 클래스 장식 (_add_class_decorations)

| 처리 내용 | 상세 |
|-----------|------|
| `extends CommonDao` 제거 | 필드 주입 방식으로 전환 |
| 어노테이션 삽입 | `@Slf4j`, `@RequiredArgsConstructor`, `@Repository` |
| 필드 삽입 (클래스 `{` 직후) | `private final CommonDao commonDao;` |
| | `private final UxbDAO uxbDAO;` |

---

## 4. PreparedStatement → uxbDAO 변환 (_convert_execute_queries)

`conn.prepareStatement(sb.toString())` 패턴을 감지하여 실행.

### 4-1. 변환 트리거

```java
ps = conn.prepareStatement(sb.toString());  // ← 이 패턴이 트리거
```

### 4-2. SQL 추출 (sb.append 분석)

sb 선언부터 prepareStatement 직전까지의 `sb.append(...)` 호출을 분석하여 SQL 문자열을 재구성한다.

**sb.append 인자 패턴별 처리:**

| 인자 형태 | 처리 결과 |
|-----------|-----------|
| `"순수 SQL 문자열"` | SQL에 직접 병합 |
| `"PREFIX" + obj.getXxx() + "SUFFIX"` | `#{xxx}` 바인딩 + paramMap 쌍 추출 |
| `"PREFIX" + Formatter.nullXxx(obj.getXxx()) + "SUFFIX"` | `#{xxx}` 바인딩 + paramMap 쌍 추출 |
| `"PREFIX" + Formatter.nullXxx(StringUtil.nvl(obj.getXxx(), "")) + "SUFFIX"` | `#{xxx}` 바인딩 + paramMap 쌍 추출 |
| `"PREFIX" + simpleVar + "SUFFIX"` | `#{simpleVar}` 바인딩 |
| 변수·표현식 (문자열 아님) | `/* expr */` 주석 처리 |

**조건부 append → MyBatis `<if>` 변환:**

```java
// AS-IS
if (!"".equals(dto.getVslCode())) {
    sb.append(" AND VSL_CODE = ?");
}

// TO-BE (Mapper XML)
<if test="vslCode != ''">
    AND VSL_CODE = #{vslCode}
</if>
```

### 4-3. 파라미터 추출 (_extract_update_params)

`ps.setXxx(i++, expr)` 또는 `ps.setXxx(1, expr)` 형태에서 (key, value) 쌍 추출.

**_derive_param_key_value 우선순위:**

| 순위 | 표현식 패턴 | 결과 key | 결과 value |
|------|-------------|----------|------------|
| 0 | `System.currentTimeMillis()` 포함 | *(스킵)* | *(스킵)* |
| 1 | `getUserId()` / `getUser_id()` 포함 | `_sessionUserId` | `userInfo.getUserId()` |
| 2 | `StringUtil.nvl(simpleVar, ...)` | `simpleVar` | `simpleVar` |
| 3 | `StringUtil.nvl(obj.getXxx(), ...)` | `xxx` | `obj.getXxx()` |
| 4 | `Formatter.nullTrim(obj.getXxx())` | `xxx` | `obj.getXxx()` |
| 5 | `Formatter.nullTrim(simpleVar)` | `simpleVar` | `simpleVar` |
| 5.5 | `Long/Double/Integer.valueOf(x).longValue()` 등 | `x` | `x` |
| 6 | `Formatter.nullXxx((obj.getXxx()))` (추가 괄호 포함) | `xxx` | `obj.getXxx()` |
| 6.5 | `Formatter.nullXxx(StringUtil.nvl(obj.getXxx(), ...))` | `xxx` | `obj.getXxx()` |
| 6.6 | `Formatter.nullXxx(StringUtil.nvl(simpleVar, ...))` | `simpleVar` | `simpleVar` |
| 7 | `Formatter.nullXxx(simpleVar)` | `simpleVar` | `simpleVar` |
| 8 | `obj.getXxx()` | `xxx` | `obj.getXxx()` |
| 9 | 단순 식별자 (fallback) | 마지막 식별자 | 마지막 식별자 |
| 10 | 해석 불가 (최종 fallback) | 비단어 → `_` 치환 후 20자 | 같음 |

### 4-4. Java 코드 생성

**SELECT (executeQuery):**
```java
Map<String, Object> paramMap = new HashMap<>();
paramMap.put("key", value);
List<Map<String, Object>> listMap = uxbDAO.select("Namespace.methodId", paramMap);
```

**UPDATE (executeUpdate):**
```java
Map<String, Object> paramMap = new HashMap<>();
paramMap.put("key", value);
uxbDAO.update("Namespace.methodId", paramMap);
```

### 4-5. 메서드 내 복수 쿼리 ID 부여

| 메서드 내 순서 | mapper id |
|----------------|-----------|
| 첫 번째 | `methodName` |
| 두 번째 | `methodName1` |
| 세 번째 | `methodName2` |

### 4-6. 변환 후 정리 (post-processing)

| 제거 대상 | 비고 |
|-----------|------|
| `if (cond) ps.setXxx(i++, ...)` 인라인 형태 | 조건부 setXxx 전체 제거 |
| `int i = 0;` / `int i = 1;` | PreparedStatement 인덱스 카운터 |
| 빈 `if { }` / `else if { }` 블록 | sb.append 제거 후 잔류 |
| `} else { throw new Xxx("..."); }` | else-throw 블록만 제거, `}` 보존 |
| `rs = ps.executeQuery();` | — |
| `ps.executeUpdate();` | — |
| `ps.setXxx(...)` 잔류분 | — |
| `ps = conn.prepareStatement(...)` 잔류분 | — |
| `/* \n if(cond) \n } */` 블록 주석 | setXxx 제거 후 잔류 |
| `/* */` 빈 블록 주석 | — |
| `while (rs.next())` | → `for (Map<String, Object> map : listMap)` |
| `if (rs.next()) {` | → `if (listMap != null && !listMap.isEmpty()) {` + `Map<String, Object> map = listMap.get(0);` |
| `finally { ... }` 빈 블록 | close() 제거 후 잔류 |
| `log.xxx(... .toString() ...)` | sb 선언 제거 후 orphan log 라인 |
| `String sql = ...;` | 잔류 sql 변수 선언 |

---

## 5. for-loop null 가드 삽입 (_wrap_listmap_for_loops)

`for (Map<String, Object> map : listVar)` 패턴을 감지하여 null 가드로 감싼다.  
직전 줄에 이미 null 체크가 있으면 건너뜀.

```java
// AS-IS
for (Map<String, Object> map : listMap) { ... }

// TO-BE
if (listMap != null && !listMap.isEmpty()) {
    for (Map<String, Object> map : listMap) { ... }
}
```

---

## 6. UserDelegation 주입 (_inject_user_delegation)

메서드 바디에 `userInfo.xxx` 사용이 있고 `UserDelegation userInfo` 선언이 없으면 메서드 첫 줄에 삽입.

```java
UserDelegation userInfo = UserInfo.getUserInfo();
```

---

## 7. throws 정리

| 단계 | 처리 내용 |
|------|-----------|
| `_fix_throws` | `throws Exception, Exception` → `throws Exception` |
| `_remove_throws_exception` | 메서드 시그니처의 `throws Exception` 전체 제거 |

---

## 8. try-catch 제거 (_remove_trivial_try_catch)

catch 바디의 **마지막 문장이 rethrow** (`throw new XxxException(...)`) 인 경우 try-catch를 제거하고 try 본문만 한 단계 de-indent하여 남긴다.  
finally 블록이 있으면 함께 제거한다.

**제거 대상:**
```java
try {
    // 비즈니스 로직
} catch (Exception e) {
    result = "ERR-0001";   // throw 전 도달 불가 코드는 허용
    throw new UxbBizException(e);  // 마지막이 rethrow → 제거
}
```

**보존 대상 (조건부 throw, return 포함):**
```java
} catch (Exception e) {
    if (someFlag) throw new UxbBizException(e);  // if-throw → 보존
}
} catch (Exception e) {
    return null;  // return → 보존
}
```

---

## 9. Java 조건식 → MyBatis `<if test="">` 변환 (_java_condition_to_mybatis)

`if (cond) { sb.append(...) }` 패턴의 조건식을 MyBatis test 속성으로 변환.  
아래 규칙을 순서대로 적용한다.

| 순서 | Java 조건식 패턴 | MyBatis test 결과 |
|------|-----------------|-------------------|
| 1 | `!"".equals(dto.getXxx())` | `xxx != ''` |
| 2 | `Formatter.nullTrim(expr)` | `expr` (래퍼 제거) |
| 3 | `'CONST'.equals(dto.getField())` | `field == 'CONST'` |
| 4 | `dto.getField().equals('CONST')` | `field == 'CONST'` |
| 5 | `null != dto.getField()` | `field != null` |
| 6 | `0 != nullLong(dto.getXxx())` | `xxx != 0 and xxx != null` |
| 7 | `dto.getXxx().longValue() == n` | `xxx == n` |
| 8 | `dto.getXxx() != value` | `xxx != value` |
| 9 | `dto.getXxx()` (잔여 getter) | `xxx` (프로퍼티명) |
| 10 | `&&` / `\|\|` | `and` / `or` |

---

## 10. Mapper XML 생성 (_build_mapper_xml)

**파일명:** `{ClassName에서 DAO 제거}Mapper.xml`  
예: `ODASendHeadDAO` → `ODASendHeadMapper.xml`

**namespace:** 클래스명에서 DAO 제거  
예: `ODASendHead`

**SELECT 태그:**
```xml
<select id="methodName" parameterType="map" resultType="map" useCache="false" timeout="0">
    <![CDATA[
    /* Namespace.methodName */
    ]]>
        SELECT ...
        FROM ...
        WHERE ...
        <if test="vslCode != ''">
            AND VSL_CODE = #{vslCode}
        </if>
</select>
```

**UPDATE 태그:**
```xml
<update id="methodName" parameterType="map" timeout="0">
    <![CDATA[
    /* Namespace.methodName */
    ]]>
        UPDATE ...
        SET ...
        WHERE ...
</update>
```

**SQL 포맷 규칙:**
- 리터럴 `\n` 제거
- 탭 → 단일 공백, 연속 공백 → 단일 공백
- 기본 들여쓰기: 8칸
- `<if>` 블록 내부: 12칸
- `<>` → `&lt;&gt;` 이스케이프

---

## 11. 포맷 정규화 (_cleanup_formatting)

| 처리 내용 |
|-----------|
| 공백·탭만 있는 줄 → 완전한 빈 줄 |
| 3개 이상 연속 빈 줄 → 1개 |
| `{` 바로 뒤 빈 줄 제거 |
| `}` 바로 앞 빈 줄 제거 |
| 파일 끝 빈 줄 1개로 정규화 |

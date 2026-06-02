// 파일명: DaoToMyBatisConverter.java

/*
 * Mapper.xml 생성용
 */

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * DAO -> Mapper Converter
 */
public class DaoToMyBatisConverter {

    // 1. AS-IS/TO-BE 루트 경로 설정 (필요에 맞게 수정)
//    private static final String ASIS_ROOT = "D:/panocean/20250729/som_workspace_utf8";
//    private static final String ASIS_ROOT = "D:/Take/panoean/as_is/som_workspace_urf8";
//    private static final String ASIS_ROOT   = "D:\\panocean\\20250729\\som_workspace_utf8\\SOM_Common\\CommonFnDaoSource\\com\\stx\\som\\business\\dao\\";
    private static final String ASIS_ROOT   = "C:/AdvDevEnv/som_workspace/";
    private static final String CREATE_ROOT = "D:/panocean/panocean-v2/src/main/resources/mappers/som";
    private static final String PARAMETER_TYPE_PATH = "D:/panocean/panocean-v2/src/main";

    // 2. 정규식 패턴 선언
    // 2.1. 메소드 시그니처

    /**
     * 수정된 메소드 시그니처 정규식.
     * 제네릭, 어레이, 와일드카드, 리턴 타입 구분자(‘.’)를 모두 허용하고
     * 파라미터 부분을 최소 매칭(non-greedy)으로 잡습니다.
     */
    private static final Pattern P_METHOD = Pattern.compile(
            // public 키워드 뒤에 반환형(식별자, 제네릭, 배열, 와일드카드, . 구분자)을 허용하고,
            // 메소드명과 파라미터 리스트를 최소 매칭으로 캡처한 후 '{'를 매칭
            "(public|private)\\s+([\\w\\.<>,\\s\\?\\[\\]]+)\\s+" +  // 반환형
                    "(\\w+)\\s*" +                             // 메소드명
                    "\\((.*?)\\)\\s*" +                        // 파라미터: 비탐욕(non-greedy) 매칭
                    "(?:throws\\s+[\\w\\.,\\s]+)?\\s*" +       // 선택적 throws 절
                    "\\{",                                     // 여는 중괄호
            Pattern.DOTALL
    );


    // 2.2. sb.append("..."); 단순 SQL 조각


    // ========== 정규식 패턴 선언 ==========
// 1) !''.equals(getXxx()) → xxx != ''
    private static final Pattern P_NOT_EMPTY_EQUALS = Pattern.compile(
            "!\\s*''\\s*\\.\\s*equals\\s*\\(\\s*(?:\\w+Dto|Vo?\\.)?get([A-Z]\\w*)\\s*\\(\\s*\\)\\s*\\)",
            Pattern.DOTALL
    );

    // 2) Formatter.nullTrim(...) → 내부 식별자
    private static final Pattern P_NULLTRIM = Pattern.compile(
            "Formatter\\.nullTrim\\s*\\(\\s*([^\\)]+?)\\s*\\)",
            Pattern.DOTALL
    );

    // 3) 'CONST'.equals(dto.getField()) → field == 'CONST'
    private static final Pattern P_LEFT_EQ = Pattern.compile(
            "'([^']*)'\\s*\\.\\s*equals\\s*\\(\\s*(?:\\w+Dto|Vo?\\.)?get([A-Z]\\w*)\\s*\\(\\s*\\)\\s*\\)",
            Pattern.DOTALL
    );

    // 4) dto.getField().equals('CONST') → field == 'CONST'
    private static final Pattern P_RIGHT_EQ = Pattern.compile(
            "(?:\\w+Dto?\\.)?get([A-Z]\\w*)\\s*\\(\\s*\\)\\s*\\.\\s*equals\\s*\\(\\s*'([^']*)'\\s*\\)",
            Pattern.DOTALL
    );

    // 3) 'CONST'.equals(dto.getField()) → field == 'CONST'
    private static final Pattern P_LEFT_EQ_DTO = Pattern.compile(
            "'([^']*)'\\s*\\.\\s*equals\\s*\\(\\s*(?:\\w+DTO|VO?\\.)?get([A-Z]\\w*)\\s*\\(\\s*\\)\\s*\\)",
            Pattern.DOTALL
    );

    // 4) dto.getField().equals('CONST') → field == 'CONST'
    private static final Pattern P_RIGHT_EQ_DTO = Pattern.compile(
            "(?:\\w+DTO|VO?\\.)?get([A-Z]\\w*)\\s*\\(\\s*\\)\\s*\\.\\s*equals\\s*\\(\\s*'([^']*)'\\s*\\)",
            Pattern.DOTALL
    );


    // 5) null != dto.getField() → field != null
    private static final Pattern P_NULL_NEQ = Pattern.compile(
            "null\\s*!=\\s*(?:\\w+Dto|Vo?\\.)?get([A-Z]\\w*)\\s*\\(\\s*\\)\\s*",
            Pattern.DOTALL
    );

    // 6) 숫자 또는 변수 != nullLong(getXxx()) → field != null
    private static final Pattern P_NULL_LONG = Pattern.compile(
            "(?:\\b\\w+\\b|\\d+)\\s*!=\\s*nullLong\\s*\\(\\s*(?:\\w+Dto|Vo?\\.)?get([A-Z]\\w*)\\s*\\(\\s*\\)\\s*\\)",
            Pattern.DOTALL
    );

    // 7) !invo_no == '' → invo_no != ''
    private static final Pattern P_NOT_EQUALS_EMPTY = Pattern.compile(
            "!\\s*(\\w+)\\s*==\\s*''",
            Pattern.DOTALL
    );

    // 8) 남은 getXxx() → 프로퍼티명
    private static final Pattern P_ANY_GETTER = Pattern.compile(
            "(?:\\w+Dto?\\.)?get([A-Z]\\w*)\\s*\\(\\s*\\)\\s*",
            Pattern.DOTALL
    );


    // 2.4. PreparedStatement 파라미터
    private static final Pattern P_PS_SET = Pattern.compile(
            "ps\\.set\\w+\\(\\s*i\\+\\+\\s*,\\s*([^\\)]+)\\)");

    // 2.5. Vector 파라미터
    private static final Pattern P_VEC_ADD = Pattern.compile(
            "vSqlParams\\.add\\(\\s*idx\\+\\+\\s*,\\s*([^\\)]+)\\)");

    // 2.6. String[] sqlParams = { ... };
    private static final Pattern P_ARR = Pattern.compile(
            "String\\[\\]\\s+\\w+\\s*=\\s*\\{([^}]*)\\}\\s*;");

    // if (조건) { … } 블록 전체를 캡처
    private static final Pattern P_IF_BLOCK = Pattern.compile(
            "if\\s*\\(\\s*([^\\)]+?)\\s*\\)\\s*\\{([^}]*?)\\}",
            Pattern.DOTALL
    );


    private static final Pattern P_EMPTY_NEQ = Pattern.compile(
            "!\\s*''\\.equals\\s*\\(([^)]+?)\\.get([A-Z]\\w*)\\s*\\(\\)\\)");

    // 제외할 필드명 목록 (확장)
    private static final Set<String> QONTAIN_QUERY = new HashSet<>(Arrays.asList(
            "select", "update", "insert", "where", "from"
    ));

    private static final Pattern P_NOT_EMPTY_TRIM_NULL_TRIM = Pattern.compile(
            "!\\s*Formatter\\.nullTrim\\s*\\(\\s*(?:\\w+\\.)?([A-Za-z_]\\w*)\\s*\\)\\s*\\.\\s*equals\\s*\\(\\s*''\\s*\\)",
            Pattern.DOTALL
    );


    private static final Pattern P_NOT_EMPTY_TRIM = Pattern.compile(
            "![A-Za-z_]\\w*\\s*\\)\\s*\\.\\s*equals\\s*\\(\\s*''\\s*\\)",
            Pattern.DOTALL
    );

    private static final Pattern P_SQL_APPEND = Pattern.compile(
            "(?:\\b|\\.)?append\\(\\s*\"([^\"]*?)\"\\s*\\)",
            Pattern.DOTALL
    );

    // 1) 정규식 패턴: #{ Formatter.nullLong(voyNo) }
    private static final Pattern P_NULLLONG_EXPR = Pattern.compile(
            "Formatter\\.nullLong\\s*\\(\\s*([^)]+?)\\s*\\)\\s*"
    );

    // "CONST".equals(variable) → variable == 'CONST'
    private static final Pattern P_CONST_EQUALS_VAR = Pattern.compile(
            "'([^']*)'\\s*\\.\\s*equals\\s*\\(\\s*(\\w+)\\s*\\)",
            Pattern.DOTALL
    );

    // 변수.equals('CONST') → 변수 == 'CONST'
    private static final Pattern P_VAR_EQUALS_CONST = Pattern.compile(
            "(\\b\\w+\\b)\\s*\\.\\s*equals\\s*\\(\\s*'([^']*)'\\s*\\)",
            Pattern.DOTALL
    );


    // CondBlock 클래스 정의 (필드만 추가)
    static class CondBlock {
        String test;
        List<String> sqlParts;
    }

    static class MethodSqlInfo {
        String strBuffNm;

        String preStateNm;
        int cnt;

    }


    private static List<String[]> getProjectNmList() {
        return Arrays.asList(

                /*                           2차 범위                                    */
                new String[]{"SOM_Business_OperSa", "ejbModule"},
                new String[]{"SOM_Business_OperSt", "ejbModule"},
                new String[]{"SOM_Business_SalesCb", "ejbModule"},
                new String[]{"SOM_Business_SalesDoc", "ejbModule"},
                new String[]{"SOM_Business_Edi", "ejbModule"},

                /*                           1차 범위                                    */
                new String[]{"SOM_Business_Basic", "ejbModule"},
                new String[]{"SOM_Business_Crm", "ejbModule"},
                new String[]{"SOM_Business_Sysm", "ejbModule"},
                new String[]{"SOM_Business_InsLeg", "ejbModule"},
                new String[]{"SOM_Common", "CommonFnDaoSource"}
        );
    }

//    private static boolean getIsDir(String fileNm) {
//        return ;
//    }


    public static void main(String[] args) throws IOException {
        // 변환 대상 프로젝트 목록 (폴더명, DAO 하위 디렉터리)
        List<String[]> modules = getProjectNmList();
        String createFilePath = CREATE_ROOT + File.separator ;
        for (String[] mod : modules) {
            Path srcDir = Paths.get(ASIS_ROOT, mod[0], mod[1]);
//            Path srcDir = Paths.get(ASIS_ROOT);
            if (!Files.isDirectory(srcDir)) {
                System.err.println("[SKIP] ASIS 경로 없음: " + srcDir);
                continue;
            }



            // TO-BE 경로: common/dao/business/standardInfo 등 구조 보존
            try (Stream<Path> files = Files.walk(srcDir)) {
                files.filter(p -> Files.isRegularFile(p)
                                && (p.getFileName().toString().contains("DAO") && p.getFileName().toString().endsWith("java"))
                                         //              && (
                                       // ( FileNm.OMISSION_DAO_PATH.stream().filter(file -> (file.startsWith(p.getFileName().toString().replace(".java", "")))).collect(Collectors.toSet()).size() > 0)
                                //)
                )
                        .forEach(dao -> processDao(dao, srcDir, Paths.get(createFilePath)));
            } catch(Exception e) {
                System.out.println("실패 :: [" + e.getMessage() + "]");
            }
        }        /* OBNBnkSplyOrderBook.bnkOrderBookInsert */
    }

    // DAO 파일별 처리
    private static void processDao(Path dao, Path srcDir, Path dstRoot) {
        try {
            String code = new String(Files.readAllBytes(dao), StandardCharsets.UTF_8);
            String className = dao.getFileName().toString().replace(".java", "");


            // ASIS 내 상대 경로 보존
            Path outDir = dstRoot.resolve(dao.getParent().getFileName());
            String mapperFile = className.replace("DAO", "") + "Mapper.xml";
            Path outFile = outDir.resolve(mapperFile);
            if(Files.exists(outFile)) {
                return;
            }
            String xml = convert(code, className, srcDir.toString(), String.valueOf(dao.getParent().getFileName()), outDir);
            if(!xml.contains("<select")
                    && !xml.contains("<update")
                    && !xml.contains("<insert")
                    && !xml.contains("<delete")
            ) {
                return;
            }
            Files.createDirectories(outDir);
            Files.write(outFile, xml.getBytes(StandardCharsets.UTF_8),
                    StandardOpenOption.CREATE,
                    StandardOpenOption.TRUNCATE_EXISTING);


            System.out.println("DAO Mapper 전환 :: [" + outFile + "]");
        } catch (Exception e) {
            System.err.println("[FAIL] " + dao + " : " + e.getMessage());
            e.printStackTrace();
        }
    }

    public static List<MethodSqlInfo> getMethodInfo(String body, String namespace, String method) {
        List<MethodSqlInfo> mList = new ArrayList<>();
        String[] lines = body.split("\n");


        Pattern p = Pattern.compile("(\\w+)\\s*=\\s*(\\w+)\\.prepareStatement\\s*\\(\\s*(\\w+)(?:\\.toString\\(\\))?\\s*\\)");



        String test = "";

        for (String line : lines) {
            test += line.trim() + "\n";
        }
        body = test;


        if (body.contains("prepareStatement")) {
            body = body.replaceAll(",\n", ",");
            lines = body.split("\n");
            for (String line : lines) {
                MethodSqlInfo mInfo = new MethodSqlInfo();
                Matcher m = p.matcher(line);
                if (m.find()) {

                    String preStateNm = m.group(1);
                    String strBuffNm = m.group(3);
                    int cnt = (int) mList.stream().filter(item -> item.strBuffNm.equals(strBuffNm)
                            && item.preStateNm.equals(preStateNm)).count();
                    mInfo.preStateNm = m.group(1);
                    mInfo.cnt = cnt;
                    mInfo.strBuffNm = m.group(3);

                    mList.add(mInfo);
                }
            }
        }


        return mList;
    }

    // 코드 → Mapper XML 변환
    public static String convert(String code, String namespace, String asisPath, String dirNm, Path outPath) throws IOException {
        StringBuilder xml = new StringBuilder();
        xml.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
                .append("<!DOCTYPE mapper PUBLIC \"-//mybatis.org//DTD Mapper 3.0//EN\"\n")
                .append("    \"http://mybatis.org/dtd/mybatis-3-mapper.dtd\">\n")
                .append("<mapper namespace=\"").append(namespace.replace("DAO", "")).append("\">\n\n");

        Matcher m = P_METHOD.matcher(code);
        List<String> mapperIdList = new ArrayList<>();
        int cnt = 0;
        String s = "";
        String[] lines = code.split("\n");
        for (String line : lines) {
            if (line.trim().startsWith("/") && (line.contains("{") || line.contains("}"))) {
                line = line.replace("{", "").replace("}", "");
            }
            s += line + "\n";
        }

        code = s;

        while (m.find()) {
            String method = m.group(3);
            String methodParam = m.group(4);

            int bodyStart = code.indexOf('{', m.end() - 1) + 1;
            int depth = 1, idx = bodyStart;
            boolean starComm = false;
            while (depth > 0 && idx < code.length()) {
                char c = code.charAt(idx++);
                if (c == '*') {
                    if (code.charAt(idx - 2) == '/') {
                        starComm = true;
                    }

                    if (code.charAt(idx) == '/') {
                        starComm = false;
                    }

                }
                if (starComm) continue;

                if (c == '{') depth++;
                else if (c == '}') depth--;
            }
            String body = code.substring(bodyStart, idx - 1);
            if (!body.contains("executeQuery") && !body.contains("executeUpdate"))
                continue;


            List<MethodSqlInfo> mList = getMethodInfo(body, namespace, method);

            AtomicInteger seq = new AtomicInteger();
            for (MethodSqlInfo mInfo : mList) {
                // 파라미터 수집
//                List<String> params = collectParams(body, method, mInfo);
                List<String> params = getCollectParams(body, method, mInfo);
                // SQL 추출
                List<String> sqls = collectSql(body, params, mInfo, asisPath, method, seq);


                if (sqls.isEmpty()) continue; // 빈 Mapper 스킵

                // CRUD 판단
                String op = detectOp(sqls, method);

                cnt = mapperIdList.stream().filter(item -> item.trim().equals(method.trim())).collect(Collectors.toList()).size();
                mapperIdList.add(method.trim());

                String id = method.substring(0, 1).toLowerCase() + method.substring(1) + (cnt > 0 ? cnt : "");
                String parameterType = getParamType(methodParam, method, outPath.toString(), namespace, asisPath, id);

                xml.append("    <").append(op)
                        .append(" id=\"").append(id).append("\"")
                        .append(" parameterType=\"").append(parameterType).append("\"")
                        .append(op.equals("select") ? " resultType=\"map\" useCache=\"false\" " : "");


                xml.append(" timeout=\"0\"");
                xml.append(">\n")
                        .append("        <![CDATA[\n")
                        .append("        /* ").append(namespace.replace("DAO", "")).append(".").append(method.substring(0,1).toLowerCase()).append(method.substring(1)).append((cnt > 0 ? cnt : "")).append(" */\n")
                        .append("        ]]>\n");

                if(mInfo.cnt > 0) {
                    xml.append("--TODO 확인 필요함... 쿼리가 두번..............................\n");
                }

                for (String line : sqls) {
                    xml.append("        ")
                            .append(line.replaceAll("&", "&amp;")
                                    .replaceAll("&amp;gt;", "&gt;")
                                    .replaceAll("&amp;lt;", "&lt;")
                                    .replace("\").append(\"", ""))
                            .append("\n");
                }
                xml.append("    </").append(op).append(">\n\n");
            }
        }

        xml.append("</mapper>");
        return xml.toString().replaceAll("\\\\n", "");
    }

    private static String getLineParam(String line, String ps, String method) {
        String rtnStr = "";
        try {
            line = line.replaceAll("\\.longValue\\(\\)", "")
                    .replaceAll("\\.doubleValue\\(\\)", "")
                    .replaceAll("\\.length", "");
            if (line.toUpperCase().contains("VO.") || line.toUpperCase().contains("DTO.")) {
                int startIdx = line.lastIndexOf(".");
                int endIdx = line.lastIndexOf("(");
                if (startIdx > endIdx) endIdx = line.lastIndexOf(")");

                line = line.substring(startIdx + 1, endIdx);
                line = line.replaceAll("get", "");


                rtnStr = line.substring(0, 1).toLowerCase() + line.substring(1);

            } else if (line.contains("Formatter")) {
                Pattern pFormatter = Pattern.compile(
                        "(" + ps + ")\\.set(?:String|Double|Long|Timestamp)\\s*\\(\\s*i\\+\\+\\s*,\\s*" +
                                "(?:Formatter\\.null(?:Trim|Long)\\s*\\(\\s*)?" +   // Formatter.nullTrim/Long( 생략 가능
                                "(?:new\\s+Long\\(\\s*)?" +                         // new Long( 생략 가능
                                "[\\w\\.]+?\\.get([A-Z][\\w]*)\\s*\\(\\s*\\)?" +    // .getXxx() 캡처 그룹1
                                "(?:\\.(doubleValue|longValue)\\(\\))?" +                       // .doubleValue() 생략
                                "\\s*\\)?\\s*\\)"
                );
                // 2) Formatter 패턴 우선 처리
                Matcher mf = pFormatter.matcher(line);
                while (mf.find()) {
                    String var = mf.group(2);
                    String name = var.substring(0, 1).toLowerCase() + var.substring(1);
                    rtnStr = name;
                }

                if (rtnStr.isEmpty()) {
                    String format = line.substring(line.indexOf("Formatter."));
                    format = format.substring(format.indexOf("(") + 1);
                    if (format.contains("VO") || format.contains("DT") || format.contains("Info.")) {
                        int startIdx = line.lastIndexOf(".");
                        int endIdx = line.lastIndexOf("(");
                        if (startIdx > endIdx) endIdx = line.lastIndexOf(")");

                        line = line.substring(startIdx + 1, endIdx);
                        line = line.replaceAll("get", "");
                        rtnStr = line.substring(0, 1).toLowerCase() + line.substring(1);
                    } else {
                        rtnStr = format.substring(0, format.indexOf(")"));
                    }
                }

            } else if (line.substring(line.indexOf(ps + ".")).contains(".")) {
                int startIdx = line.indexOf(",") + 1;
                int endIdx = line.lastIndexOf(".");

                if (line.contains("userBean")) {
                    line = line.substring(line.indexOf("userBean.get") + 12, line.lastIndexOf("("));
                    if (line.contains("_")) {
                        int idx = line.indexOf("_");
                        line = line.substring(0, idx) + line.substring(idx + 1, idx + 2).toUpperCase() + line.substring(idx + 2);
                    }
                    line = "_session" + line;
                    rtnStr = line;
                } else if (line.contains("parse")) {
                    rtnStr = line.substring(line.indexOf("parse"));
                    rtnStr = rtnStr.substring(rtnStr.indexOf("(") + 1, rtnStr.indexOf(")"));
                    if (rtnStr.contains(".")) {
                        rtnStr = rtnStr.split("\\.")[0];
                    }
                } else if (line.contains("DateUtil.getTimeStampString()")) {
                    rtnStr = "SYSDATE";
                } else if (startIdx < endIdx) {
                    rtnStr = line.substring(startIdx, endIdx).trim();
                } else {
                    rtnStr = line.substring(startIdx, line.lastIndexOf(")")).trim();
                }
            } else {
                rtnStr = line.trim();
            }
        } catch (Exception e) {
            System.err.println(method + " ::" + line);
        }
        return rtnStr;
    }

    private static List<String> getCollectParams(String body, String method, MethodSqlInfo mInfo) {
        List<String> list = new ArrayList<>();

        String[] lines = body.split("\n");

        String ps = mInfo.preStateNm;

        for (String line : lines) {
            String psLine = ps + ".set";
            if (line.contains(psLine)) {
                list.add(line.trim());
            }
        }

        List<String> rtnList = new ArrayList<>();

        for (String line : list) {
            String rtnStr = "";
            int idx = 0;

            if (line.contains("java.sql.Types.VARCHAR") || line.contains("0")) continue;
            if (line.contains("userBean")) {
                line = line.substring(line.indexOf("userBean.get") + 12, line.lastIndexOf("("));
                if (line.contains("_")) {
                    int idx2 = line.indexOf("_");
                    line = line.substring(0, idx2) + line.substring(idx2 + 1, idx2 + 2).toUpperCase() + line.substring(idx2 + 2);
                }
                line = "_session" + line;
                rtnList.add(line);
                continue;
            }

            // 아래 두개의 method는 for문으로 2번 반복해서 넣어주는 method임 직접 수정
            // openEffectInfoSAVE
            // openEffectFileSave
            // bunkerDetectiveDataStorageSave
            String test = "";
            try {
                test = line.split(",")[1].trim();
            } catch (Exception e) {
                System.out.println("line :: " + ps + ":: line :: " + line + ":: method :: " + method);
                e.printStackTrace();
            }
            if ((test.contains("+")) && !test.contains("++")) {
                int cnt = getLinePlus(test);
                if (cnt == 1) {
                    String[] splitStr = test.split("\\+");
                    String psSetStr = line.split(",")[0].trim();
                    String leftStr = psSetStr + "," + splitStr[0] + ");";
                    String rightStr = psSetStr + "," + splitStr[1].substring(0, splitStr[1].length() - 2) + ");";
                    String midStr = "} || #{";
                    if (rightStr.replaceAll("\"", "").trim().equals("%")) {
                        midStr = "} || ";
                    }
                    rtnStr = getLineParam(leftStr, ps, method) + midStr + getLineParam(rightStr, ps, method);
                } else {
                    int idxPlus = 0;
                    boolean isCode = true;

                    int paramIdx = 0;
                    String hardCode = "";
                    StringBuilder dynaCode = new StringBuilder();

                    while (idxPlus < test.length() - 2) {
                        char c = test.charAt(idxPlus++);
                        String str = c + "";

                        if (c == '+') {
                            if (isCode) {
                                isCode = false;
                            } else {
                                isCode = true;
                            }
                        }

                        if (!isCode) {
                            if (c == '+') {
                                if (paramIdx == 0) {
                                    str = " #{" + paramIdx + "} || ";
                                    paramIdx++;
                                } else {
                                    str = " || ";
                                }
                            }
                            if (c == '"') {
                                str = "'";
                            }
                            hardCode = hardCode + str;
                        } else {
                            if (c == ' ') continue;
                            if (c == '+') {
                                hardCode = hardCode + " || #{" + paramIdx + "}";
                                dynaCode.append(" ");
                                paramIdx++;
                            } else {
                                dynaCode.append(str);
                            }
                        }
                    }
                    String[] dynaList = dynaCode.toString().split(" ");
                    for (int i = 0; i < dynaList.length; i++) {
                        String code = dynaList[i];
                        String paramStr = getLineParam(line.split(",")[0].trim() + "," + code + ");", ps, method);


                        if (!paramStr.equals("SYSDATE") && !paramStr.equals("%")) {
                            if (i == 0) {
                                paramStr = paramStr + "}";
                            } else if (i == dynaList.length - 1) {
                                paramStr = "#{" + paramStr;
                            } else {
                                paramStr = "#{" + paramStr + "}";
                            }
                        }
                        hardCode = hardCode.replace("#{" + i + "}", paramStr);
                    }
                    rtnStr = hardCode;
                }
            } else {
                rtnStr = getLineParam(line, ps, method);
            }


            if (rtnStr.isEmpty()) continue;

            rtnList.add(rtnStr.replaceAll("\\(", "").replaceAll("\\)", "").replaceAll("Long", "").trim());
        }
        return rtnList;
    }

    private static String getParamTypePath(String paramNm, String method) {
        String rtnStr = paramNm;
        Path path = Paths.get(PARAMETER_TYPE_PATH);
        try (Stream<Path> files = Files.walk(path)) {
            List<Path> list = files.filter(p -> Files.isExecutable(p)
                    && p.getFileName().toString().startsWith(paramNm)).collect(Collectors.toList());

            if (!list.isEmpty()) {
                rtnStr = list.get(0).toString();
                rtnStr = rtnStr.substring(rtnStr.indexOf("com")).replaceAll("\\.java", "").replaceAll("\\\\", ".");
            }

        } catch (IOException e) {
            System.err.println(e.getMessage());
        }
        return rtnStr;
    }


    private static String getParamType(String methodParam, String method, String path, String fileNm, String asisPath, String id) throws IOException {
        String rtnStr = "map";

        String code = new String(
                Files.readAllBytes(Paths.get(PARAMETER_TYPE_PATH).resolve("java\\com\\pan\\som\\dao").resolve(Paths.get(path).getFileName()).resolve(fileNm + ".java")
                )
                , StandardCharsets.UTF_8);
        String[] lines = code.split("\n");
        String str = "";
        for (String line : lines) {
            if (line.contains("uxbDAO.") && line.contains(id)) {
                str = line.substring(line.lastIndexOf(",")+1).replace(");", "").trim();
                break;

            }
        }
//        System.out.println("methodParam :: " + methodParam + " - rtnStr :: " + rtnStr + " - str ::" + str);
        if (str.contains("Map") || str.contains("null")) {
            rtnStr = "map";
            methodParam = "";
        }

        if (methodParam.contains("DTO")) {
            int endIndex = methodParam.lastIndexOf("DTO") + 3;
            if (0 < endIndex) {
                String[] test = methodParam.substring(0, endIndex).replace("(", "").split(" ");

                List<String> dtoList = Arrays.stream(test)
                        .filter(s -> s.contains("DTO") && Character.isUpperCase(s.charAt(0)))
                        .collect(Collectors.toList());
                if (!dtoList.isEmpty()) {
                    if (dtoList.get(0).contains("\t")) {
                        rtnStr = dtoList.get(0).split("\t")[0];
                    } else if (dtoList.size() == 1) {
                        rtnStr = dtoList.get(0);
                    } else if (!"DTO".equals(dtoList.get(1))) {
                        rtnStr = dtoList.get(1);
                    }

                    if (!rtnStr.equals("map")) {
                        rtnStr = getParamTypePath(rtnStr, method);
                    }
                }
            }
        } else if (methodParam.contains("VO")) {
            int endIndex = methodParam.lastIndexOf("VO") + 2;
            if (0 < endIndex) {
                String[] test = methodParam.substring(0, endIndex).replace("(", "").split(",");

                List<String> voList = Arrays.stream(test)
                        .filter(s -> s.contains("VO") && Character.isUpperCase(s.charAt(0)))
                        .collect(Collectors.toList());
                if (!voList.isEmpty()) {
                    for (String voStr : voList) {
                        String paramType = voStr.replaceAll("\t", " ").split(" ")[0];
                        if (paramType.toUpperCase().contains("VO")) {
                            if (paramType.contains("\t")) {
                                rtnStr = paramType;
                            } else if (voList.size() == 1) {
                                rtnStr = paramType;
                            } else if (!"VO".equals(paramType)) {
                                rtnStr = paramType;

                            }
                        }
                    }

                    if (!rtnStr.equals("map")) {
                        rtnStr = getParamTypePath(rtnStr, method);
                    }
                }
            }
        }
        return rtnStr;
    }

    // 2) 치환 메서드
    public static String removeNullLong(String input) {
        Matcher m = P_NULLLONG_EXPR.matcher(input);
        StringBuffer sb = new StringBuffer();
        while (m.find()) {
            // 그룹1에 voyNo 등의 파라미터 이름이 들어옴
            String param = m.group(1).trim();

            m.appendReplacement(sb, param);
        }
        m.appendTail(sb);
        return sb.toString();
    }

    private static String applyNullLong(String cond) {
        Matcher m = P_NULL_LONG.matcher(cond);
        StringBuffer sb = new StringBuffer();
        while (m.find()) {
            String leftSide = m.group(1);     // "0" 또는 변수명
            String getterName = m.group(2);   // "Voy_no"
            String property = decap(getterName); // "voy_no"

            // 0이나 숫자 상수인 경우 프로퍼티명만 사용
            // 변수명인 경우 그대로 사용
            if (leftSide.matches("\\d+")) {
                // 숫자 상수 -> 프로퍼티만 사용
                m.appendReplacement(sb, property + " != " + leftSide + " and " + property + " != null");
            } else {
                // 변수명 -> 그대로 사용
                m.appendReplacement(sb, leftSide + " != null");
            }
        }
        m.appendTail(sb);
        return sb.toString();
    }

    /* 2. 변환 함수 (Java 8 호환) */
    private static String replaceNotEmptyEquals(String src) {
        Matcher m = P_NOT_EMPTY_TRIM.matcher(src);
        StringBuffer sb = new StringBuffer();
        while (m.find()) {
            String prop = m.group(1);               // 포착된 필드명(portCode)
            m.appendReplacement(sb, prop + " != ''");
        }
        m.appendTail(sb);
        return sb.toString();
    }

    // ========== 변환 메서드 ========== //
    private static String toMyBatisTest(String javaCond) {
        String cond = javaCond.trim();
        if (cond.contains("userBean")) {
            cond = cond.substring(cond.indexOf("userBean.get") + 12, cond.lastIndexOf("("));
            if (cond.contains("_")) {
                int idx = cond.indexOf("_");
                cond = cond.substring(0, idx) + cond.substring(idx + 1, idx + 2).toUpperCase() + cond.substring(idx + 2);
            }
            cond = "_session" + cond;
        }

        // 1) !''.equals(getXxx()) → xxx != ''
        cond = replaceAll(cond, P_NOT_EMPTY_EQUALS,
                m -> decap(m.group(1)) + " != ''");

        // 2) Formatter.nullTrim(...) 제거
        cond = P_NULLTRIM.matcher(cond).replaceAll("$1");

        // 3) 'CONST'.equals(dto.getField()) → field == 'CONST'
        cond = replaceAll(cond, P_LEFT_EQ,
                m -> decap(m.group(2)) + " == '" + m.group(1) + "'");
        cond = replaceAll(cond, P_LEFT_EQ_DTO,
                m -> decap(m.group(1)) + " == '" + m.group(2) + "'");

        // 4) dto.getField().equals('CONST') → field == 'CONST'
        cond = replaceAll(cond, P_RIGHT_EQ,
                m -> decap(m.group(1)) + " == '" + m.group(2) + "'");
        cond = replaceAll(cond, P_RIGHT_EQ_DTO,
                m -> decap(m.group(1)) + " == '" + m.group(2) + "'");

        // 5) variable.equals('CONST') → variable == 'CONST'
        cond = replaceAll(cond, P_VAR_EQUALS_CONST,
                m -> m.group(1) + " == '" + m.group(2) + "'");

        // 6) "CONST".equals(variable) → variable == 'CONST'
        cond = replaceAll(cond, P_CONST_EQUALS_VAR,
                m -> m.group(2) + " == '" + m.group(1) + "'");

        // 7) null != dto.getField() → field != null
        cond = replaceAll(cond, P_NULL_NEQ,
                m -> decap(m.group(1)) + " != null");

        // 8) 숫자/변수 != nullLong(getXxx()) → field != null
        cond = replaceAll(cond, P_NULL_LONG,
                m -> decap(m.group(1)) + " != null");

        // 9) !invo_no == '' → invo_no != ''
        cond = P_NOT_EQUALS_EMPTY.matcher(cond).replaceAll("$1 != ''");

        // 10) 남은 getXxx() → 프로퍼티명
        cond = replaceAll(cond, P_ANY_GETTER,
                m -> decap(m.group(1)));

        // 11) 잔여 객체접두사(dto.) 제거
//        cond = cond.replaceAll("\\b\\w+Dto\\.|\\b\\w+DTO\\.|\\b\\w+dto\\.|\\b\\w+Vo\\.|\\b\\w+VO\\.|\\b\\w+vo\\.", "");

        // 10) 논리연산자 치환
//        cond = cond.replace("&&", " and ")
//                .replace("||", " or ");

        return cond.replaceAll(".longValue\\(\\)", "").trim();
    }


// ========== 헬퍼 메서드 ========== //

    /**
     * 첫 글자 소문자 변환
     */
    private static String decap(String s) {
        return Character.toLowerCase(s.charAt(0)) + s.substring(1);
    }

    /**
     * Pattern + 람다 치환 *Java 8 호환*
     */
    private static String replaceAll(String src, Pattern p, Function<Matcher, String> repl) {
        Matcher m = p.matcher(src);
        StringBuffer sb = new StringBuffer();
        while (m.find()) {
            m.appendReplacement(sb, repl.apply(m));
        }
        m.appendTail(sb);
        return sb.toString();
    }


    private static List<String> selectFile(List<String> out, String code, String line, String asisPath) throws IOException {
        String dtoVoNm = "";

        if (line.toUpperCase().contains("VO")) {
            Pattern p = Pattern.compile("\\((\\w+VO)\\)\\s*defaultSelect");
            Matcher m = p.matcher(line);
            if (m.find()) {
                dtoVoNm = m.group(1);
            }
        } else if (line.toUpperCase().contains("DTO")) {
            Pattern p = Pattern.compile("\\((\\w+DTO)\\)\\s*defaultSelect");
            Matcher m = p.matcher(line);
            if (m.find()) {
                dtoVoNm = m.group(1);
            }
        }

        if (dtoVoNm.equals("")) {
            return out;
        }

        String[] lines = code.split("\n");

        String findImport = "";
        for (String lin : lines) {

            if (lin.contains(dtoVoNm) && lin.contains("import")) {
                findImport = lin;
                break;
            }
        }
        Path path = Paths.get(asisPath + File.separator + findImport.replace("import", "").trim().replaceAll("\\.", "\\\\"));

        String defaultQry = "";
        if (Files.isExecutable(Paths.get(path.toString()))) {
            String defaultCode = new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
            String[] defaultLines = defaultCode.split("\n");
            for (String defaultLine : defaultLines) {
                if (defaultLine.equals("defalut")) {
                    defaultQry = defaultLine.substring(defaultLine.indexOf("\""), defaultLine.lastIndexOf("\""));
                    break;
                }

            }
        }
        if (!defaultQry.equals("")) {
            out.add(0, defaultQry);
        }
        return out;
    }

    // SQL 추출·정제
    private static List<String> collectSql(String body, List<String> params, MethodSqlInfo methodSqlInfo, String asisPath, String method, AtomicInteger seq) throws IOException {
        String ps = methodSqlInfo.preStateNm;
        String sb = methodSqlInfo.strBuffNm;


        Pattern pSbSimple = Pattern.compile(
                "(" + sb + ")\\.append\\(\\s*\"([^\"]*?)\"\\s*\\);");

        Pattern pSbPlus = Pattern.compile(
                "(" + sb + ")\\.append\\(\\s*" +          // ➊ sb.append(
                        "(?:\"([^\"]*)\"\\s*\\+\\s*)?" +                  // ➋ 앞 문자열은 있을 수도 없음 (캡처 group 2)
                        "([a-zA-Z_]\\w*)\\.get([A-Z]\\w*)\\(\\)" +        // ➌ DTO.getXxx() (group 3: dto, group 4: getter)
                        "(?:\\s*\\+\\s*\"([^\"]*)\")?" +                  // ➍ 뒷 문자열도 있을 수도 없음 (캡처 group 5)
                        "\\s*\\)", Pattern.DOTALL
        );

//        if (method.contains("insertFirstAccLimit")) {
//            System.out.println(":::::: " + method + " :::::::");
//            System.out.println("ps :: " + ps);
//            System.out.println("sb :: " + sb);
//            System.out.println("methodSqlInfo.cnt :: " + methodSqlInfo.cnt);
//        }


        List<String> out = new ArrayList<>();
        if (body.contains("nrow++") || body.contains("++colRow") || body.contains("++col")) {
            return out;
        }

        String[] lines = body.split("\n");

        int idx = 0;
        int ifIdx = 0;
        boolean isStarAnno = false;
        boolean isSqlStart = false;
        boolean isPerQry = false;

        boolean isIf = false; // 이거 {}없는애들전용
        int idxIsIf = 0; // {} 이거 없는애들 전용

        String ifString = "";

        //        for(String line : lines ) {
        for (int j = 0; j < lines.length; j++) {

            String line = lines[j];


            if (line.contains("log.debug")) {
                continue;
            }

            if (line.contains("if(rs!=null)") || line.contains("rs.next()")) continue;

            if (isPerQry) {
                int startIdx = line.indexOf("(") + 1;
                int endIdx = line.lastIndexOf(")");
                if (line.lastIndexOf(")") != -1) {
                    isPerQry = false;
                }
            }

            if (line.contains("prepareStatement")) {
                int startIdx = line.indexOf("(") + 1;
                int endIdx = line.lastIndexOf(")");
                if (endIdx == -1) {
                    line = line.substring(startIdx, line.lastIndexOf("\""));
                    isPerQry = true;
                } else {
                    line = line.substring(startIdx, endIdx - 1);
                }
            }

            if (j == 0) {
                if (line.contains("if")) continue;
            }

            if (line.contains("System.out.print")) {
                line = line.replace("System.out.print", "--");
            }
            if (line.contains("log.")) {
                line = line.replace("log.", "--");
            }


            if (line.contains("append")) {
                if (!line.trim().substring(0, line.trim().indexOf(".")).replaceAll("\\.", "").equals(sb)) {
                    continue;
                }
            }

            Matcher simp = pSbSimple.matcher(line);
            Matcher plus = pSbPlus.matcher(line);

            if ((line.replaceAll(" ", "").contains("if(") || line.contains("else")) && !line.contains("{") && lines[j + 1].contains(sb)) {
                idxIsIf++;
                isIf = true;
            } else if ((line.contains("if") || line.contains("else"))) {

            } else {
                line = escapeXml(line);
            }

            line = removeNullLong(toMyBatisTest(line)).replaceAll("Formatter.nullTrim\\(", "");

            if (line.contains("catch") ) break;
            if (line.contains("SUC") || line.contains("close")) continue;

            if (line.contains("return") && line.contains("dbWrap")) {
                isSqlStart = true;
            }

            if (isStarAnno) {
                if (line.trim().indexOf("*/") == line.trim().length() - 2) {
                    isStarAnno = false;
                }
            } else {
                isStarAnno = line.trim().indexOf("/*") == 0;
            }


            boolean isAnno = line.trim().indexOf("//") == 0 || (isStarAnno);

            if (line.contains("?") && params.size() > idx) {
                if (!line.contains(sb)) continue;
                int strCont = line.indexOf("\"") + 1;
                int endCont = line.lastIndexOf("\"");

                if (strCont > endCont) continue;
                String sql = line.substring(strCont, endCont);
                if (sql.trim().equals("?")) {
                    out.add(sql);
                    continue;
                }
                String[] commaLine = sql.split(",");
                String[] questionLine = sql.split("\\?");

                if (commaLine.length > 0 && questionLine.length > 1) {
                    for (int k = 0; k < commaLine.length; k++) {
                        String comma = commaLine[k];
                        String str = escapeXml(cleanSql(comma));
                        if (str.isEmpty()) continue;
                        if (isAnno) {
                            out.add("--" + str);
                            continue;
                        }

                        if (comma.contains("?")) {
                            try {
                                String strParam = params.get(idx);
                                String bePercent = "";
                                String afterPercent = "";

                                if (strParam.contains("+") && strParam.contains("%")) {
                                    int plusIdx = strParam.indexOf("+");
                                    int percentidx = strParam.indexOf("%");
                                    if (percentidx < plusIdx) {
                                        strParam = strParam.substring(plusIdx + 1).trim();
                                        bePercent = "'%' || ";
                                    }
                                    plusIdx = strParam.indexOf("+");
                                    percentidx = strParam.indexOf("%");
                                    if (percentidx > plusIdx) {
                                        strParam = strParam.substring(0, plusIdx - 1).trim();
                                        afterPercent = " || '%'";
                                    }
                                }

                                if (strParam.contains(",")) {
                                    strParam = strParam.split(",")[0];
                                }

                                if (strParam.startsWith("\"") && strParam.endsWith("\"")) {
                                    strParam = strParam.replaceAll("\"", "'");
                                } else if (strParam.endsWith("SYSDATE") || strParam.endsWith("%")) {
                                    strParam = " #{" + strParam.replaceAll(",", "").trim().replaceAll("\\.longValue\\(", "")
                                            .replaceAll("Formatter\\.nullLong\\(", "")
                                            .replaceAll("Formatter\\.nullZero\\(", "");
                                } else if (!strParam.equals("null")) {
                                    strParam = " #{" + strParam.replaceAll(",", "").trim().replaceAll("\\.longValue\\(", "")
                                            .replaceAll("Formatter\\.nullLong\\(", "")
                                            .replaceAll("Formatter\\.nullZero\\(", "") + "}";
                                }

                                str = comma.trim().replace("?", bePercent + strParam + afterPercent);
                                if ((commaLine.length - 1) != k) {
                                    str += ",";
                                }
                            } catch (Exception e) {
                                str = comma.trim();
                            }

                            if (str.isEmpty()) {
                                str = ",";
                            }
                            idx++;
                        } else if ((commaLine.length - 1) != k) {
                            str = str + ",";
                        }
                        out.add(str);
                    }
                } else {
                    String str = escapeXml(cleanSql(sql.replace("?", "#{" + params.get(idx).replaceAll(",", "") + "}")));
                    if (isAnno) {
                        str = "--" + str;
                    }
                    out.add(escapeXml(str));
                    idx++;
                }
            } else if (plus.find()) {
                if (!line.contains(sb)) continue;
                String sbVar = plus.group(1);                         // StringBuilder 변수명 (sbAR, sbAP 등)
                String pre = plus.group(2).trim().replace("'", ""); // SQL 앞부분
                String dtoVar = plus.group(3);                        // DTO 변수명
                String getter = plus.group(4).trim();                 // getter 메서드명
                String post = plus.group(5);
                //.trim().replace("'", ""); // SQL 뒷부분

                // getter를 변수명으로 변환 (Head_cucry_code -> head_cucry_code)
                String var = Character.toLowerCase(getter.charAt(0)) + getter.substring(1);

                if (var.contains(".")) {
                    var = var.split("\\.")[1];
                }
                String combined;
                if (pre.isEmpty() && post.isEmpty()) {
                    combined = "#{" + var + "}";
                } else if (pre.isEmpty()) {
                    combined = "#{" + var + "}" + post;
                } else if (post == null) {
                    combined = pre + "#{" + var + "}";
                } else {
                    combined = pre + "#{" + var + "}" + post.replace("'", "");
                }


                combined = cleanSql(combined.replaceAll(",", ""));
                out.add((isAnno ? "--" : "") + escapeXml(combined));

            } else if (simp.find()) {
                if (!line.contains(sb)) continue;

                out.add((isAnno ? "--" : "") + escapeXml(cleanSqlNotTrim(simp.group(2))));
            } else if (line.contains("}") && ifIdx > 0) {
                if (
                        lines[j - 1].contains("close")) continue;
                String tapKey = "";
                for (int i = 0; i < ifIdx - 1; i++) {
                    tapKey += "\t";
                }
                out.add(tapKey + "</if>");
                if (line.contains("else")) {
                    if (line.contains("if")) {
                        ifString = line.substring(line.indexOf("(") + 1, line.lastIndexOf(")")).replaceAll("\"", "'");
                    } else {
                        if (ifString.contains("!")) {
                            ifString = ifString.replace("!", "=");
                        } else {
                            ifString = ifString.replaceAll("==", "!=");
                        }
                    }

                    out.add(tapKey + "<if test=\"" + toMyBatisTest(escapeXml(ifString.replaceAll(".intValue\\(\\)", "").replaceAll("&&", " and ").replaceAll("&", "&amp;").replaceAll("\\|\\|", " or "))) + "\">");
                } else {
                    ifIdx--;
                }
                continue;
            } else if ((line.contains("if("))) {
                if (out.isEmpty()) continue;
                if (lines[j + 1].contains("preparedStatement")) continue;

                if (!lines[j + 1].contains(sb) && (lines.length > (j + 2) && !lines[j + 2].contains(sb)))
                    continue;

                int strIf = line.indexOf("if(") + 3;
                int endIf = line.lastIndexOf(")");
                if (strIf > endIf || endIf == -1) continue;
                String tapKey = "";

                String ifContent = line.substring(strIf, endIf).replaceAll("\"", "'");
                ifString = ifContent;
                String ifStr = "<if test=\"" + escapeXml(toMyBatisTest(ifContent).replaceAll("&&", " and ").replaceAll("&", "&amp;").replaceAll("\\|\\|", " or ")) + "\">";
                for (int i = 0; i < ifIdx; i++) {
                    tapKey += "\t";
                }

                out.add(tapKey + ifStr);


                ifIdx++;
                continue;
            } else if (line.contains("if (")) {
                //!lines[j + 2].contains(methodSqlInfo.strBuffNm) || !lines[j + 1].contains(methodSqlInfo.strBuffNm) ||
                if (out.isEmpty()) continue;
                if (lines[j + 1].contains("preparedStatement")) continue;
                if (!lines[j + 1].contains(sb) && !lines[j + 2].contains(sb)) continue;
                int strIf = line.indexOf("if (") + 4;
                int endIf = line.lastIndexOf(")");
                if (strIf > endIf || endIf == -1) continue;


                String ifContent = line.substring(strIf, endIf).replaceAll("\"", "'")
                        .replaceAll("&&", " and ").replaceAll("\\|\\|", " or ");
                ifString = ifContent;
                String ifStr = "<if test=\"" + escapeXml(toMyBatisTest(ifContent).replaceAll("&&", " and ").replaceAll("&", "&amp;").replaceAll("\\|\\|", " or ")) + "\">";

                String tapKey = "";
                for (int i = 0; i < ifIdx; i++) {
                    tapKey += "\t";
                }
                ifIdx++;
                out.add(tapKey + ifStr);
                continue;
            } else if (line.contains("\"") && line.contains(methodSqlInfo.strBuffNm)) {
                int strCont = line.indexOf("\"") + 1;
                int endCont = line.lastIndexOf("\"");
                if (strCont > endCont) continue;
                String sql = line.substring(strCont, endCont);

                if (isAnno) {
                    sql = "--" + sql;
                }


                sql = removeNullLong(sql.trim())
                        .replaceAll("\\.toString\\(\\)", "")
                        .replaceAll("\\.longValue\\(\\)", "");


                if (sql.contains("+")) {
                    int plusCnt = countPlus(sql);

                    if (sql.contains("new Long")) {
                        sql = sql.replaceAll("new Long", "");
                    }

                    if (plusCnt % 2 == 0) {
                        int idxPlus = 0;
                        int idxSql = 0;
                        StringBuilder sqlStr = new StringBuilder();
                        boolean isCode = false;
                        StringBuilder param = new StringBuilder();
                        int paramIdx = 0;

                        while (idxPlus < sql.length()) {
                            char c = sql.charAt(idxPlus++);
                            String str = c + "";
                            if (c == '"') {
                                if (isCode) {
                                    isCode = false;
                                } else {
                                    isCode = true;
                                }
                            }
                            if (idxSql > 0 && (c == ' ' || c == '(' || c == ')')) {
                                continue;
                            }

                            if (!isCode && c == '+' && idxSql != 0) {
                                idxSql = 0;
                                param.append(" ");
                                str = "}";
                                isCode = true;
                            } else if (isCode && c == '+') {
                                idxSql++;
                                sqlStr.append("#{#").append(paramIdx).append("#");
                                paramIdx++;
                                isCode = false;
                                continue;
                            }
                            if (idxSql > 0) {
                                param.append(c);
                                continue;
                            }
                            sqlStr.append(str);
                        }

                        sql = sqlStr.toString().replaceAll("getTimeStamp2yyyyMMdd", "");
                        int i = 0;

                        for (String str : param.toString().split(" ")) {
                            if (str.contains("Formatter.")) {
                                if (str.contains("replace")) {
                                    str = str.split(",")[0];
                                }
                                str = str.replaceAll("Formatter\\.", "")
                                        .replaceAll("nullDouble", "")
                                        .replaceAll("nullTrim", "");
                            }

                            if (str.toUpperCase().contains("DTO.") || str.toUpperCase().contains("VO.")) {
                                str = str.split("\\.")[1];
                            }

                            sql = sql.replaceAll("#" + i + "#", str).replaceAll("getTimeStamp2yyyyMMdd", "");
                            i++;
                        }
                    } else if (sql.contains("\"") && plusCnt != 1) {
                        try {
                            int startidx = sql.indexOf("+");
                            int endidx = sql.lastIndexOf("+");

                            String startStr = sql.substring(0, startidx);
                            String midStr = "";
                            String endStr = sql.substring(endidx + 1);

                            String sqlLine = sql.substring(startidx + 1, endidx).trim().replaceAll("new Long", "");
                            int plusIdx = sqlLine.indexOf("+");
                            midStr = "#{" + sqlLine.substring(0, plusIdx - 1) + "} + #{" + sqlLine.substring(plusIdx + 1).trim() + "}";
                            startStr = startStr.replace("'\"", "").replace("\"", "");
                            endStr = endStr.replaceFirst("\"'", "").replaceFirst("\"", "");

                            sql = startStr + midStr + endStr;
                            sql = sql.replaceAll("'\"\\+", "#{").replaceAll("\\+\"'", "}");
                        } catch (Exception e) {
                            Arrays.stream(e.getStackTrace()).forEach(item -> System.out.println(item));
                        }
                    }

                    sql = sql.replace("'\"", "").replaceFirst("\"'", "").replace("\"", "");
                    sql = sql.replaceAll("'#\\{", "#{").replaceAll("}'", "}");

                    if (sql.contains("#{") && sql.contains("%'")) {
                        int s = sql.indexOf("}");
                        sql = sql.substring(0, s) + sql.substring(s).replaceAll("%'", " \\|\\| '%'");
                    }

                    if (sql.contains("#{") && sql.contains("'%")) {
                        int s = sql.indexOf("}");
                        sql = sql.substring(0, s).replaceAll("'%", " '%' \\|\\| ") + sql.substring(s);

                    }
                    if (isSqlStart) {
                        out.add(0, escapeXml(cleanSqlNotTrim(sql)));
                        isSqlStart = false;
                    } else {
                        out.add(escapeXml(cleanSqlNotTrim(sql)));
                    }
                }
            }
            if (idxIsIf > 0 && isIf && !line.contains("}") && ifIdx > 0) {
                if (lines[j - 1].contains("close")) continue;
                out.add("</if>");
                isIf = false;
                idxIsIf--;
                if (ifIdx > 0) {
                    ifIdx--;
                }
                continue;
            }

//                if (ifIdx > 0) {
//                    for (int i = 0; i < ifIdx; i++) {
//                        out.add("\t</if>");
//                    }
//                }
        }
        return out;
    }

    private static String getSessionInfoCh(String column) {
        if (column.contains("userBean")) {
            column = column.substring(column.indexOf("userBean.get") + 12, column.lastIndexOf("("));
            if (column.contains("_")) {
                int idx = column.indexOf("_");
                column = column.substring(0, idx) + column.substring(idx + 1, idx + 2).toUpperCase() + column.substring(idx + 2);
            }
            column = "_session" + column;
        }
        return column;
    }






    public static int getLinePlus(String line) {
        int count = 0;
        for (char c : line.toCharArray()) {
            if (c == '+') {
                count++;
            }
        }
        return count;
    }

    public static int countPlus(String line) {
        int count = 0;
        boolean isCode = false;
        for (char c : line.toCharArray()) {

            if (c == '"') {
                if (isCode) {
                    isCode = false;
                } else {
                    isCode = true;
                }
            }
            if (c == '+' && isCode) {
                count++;
            }
        }
        return count;
    }

    // SQL 문자열 정제
    private static String cleanSql(String s) {
        return s.replace("\\n", " ")
                .replace("\\r", " ")
                .replace("\\t", " ")
                .replaceAll("\\s+", " ")
                .trim();
    }

    // SQL 문자열 정제
    private static String cleanSqlNotTrim(String s) {
        return s.replace("\\n", " ");
    }

    private static String cleanSqlFormatReplace(String s) {
        String s1 = s.trim()
                .replaceAll(".*Formatter\\.replace\\(\\s*\"\"\\s*,\\s*\"\"\\s*\\);?", "")
                .replaceAll(".*?Formatter\\.replace\\(\\s*([^,]+)(?:,[^)]*)?\\)", "$1")
                .replaceAll("Formatter\\.replace\\(\\s*([^,]+?)(?:,.*)?\\)", "$1")
                .replaceAll("Formatter\\.replace\\(\\s*([^,\\s]+).*", "$1");  // 추가된 패턴

        return s1;
    }

    // XML 특수문자 이스케이프
    private static String escapeXml(String s) {
        return s
                .replace("<", "&lt;")
                .replace(">", "&gt;");
    }

    // CRUD 판단
    private static String detectOp(List<String> sqls, String method) {
        String line = sqls.get(0);
        String str = line.trim().toUpperCase();
        if(line.trim().contains(" ")) {
            str = line.trim().split(" ")[0].toUpperCase();
        }
        if(str.contains("SELECT")) {
            return "select";
        }else if(str.contains("INSERT")) {
            return "insert";
        }else if(str.contains("UPDATE") || str.contains("MERGE")) {
            return "update";
        }else if(str.contains("DELETE")) {
            return "delete";
        }
        return "select";
    }
}
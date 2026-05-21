
// 파일명: DaoToMyBatisConverter.java


import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * 주석 문제로 인한 메소드 잘림 현상 callback 전 backup
 */
public class DaoConverter {

    // 1. AS-IS/TO-BE 루트 경로 설정 (필요에 맞게 수정)
//    private static final String ASIS_ROOT   = "D:/panocean/20250729/som_workspace_utf8";
    private static final String ASIS_ROOT   = "C:/AdvDevEnv/som_workspace/";
    private static final String CREATE_ROOT = "D:/panocean/panocean-v2/src/main/java/com/pan/som/dao";
//
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





    // 찾을 메소드 명 목록 (확장)
    // 메서드 호출 탐색‧필터링용 Set CommonDAO
    private static final Set<String> TARGET_METHODS = new HashSet<>(Arrays.asList(
            "defaultVoObjSysValue",
            "defaultSelect",
            "defaultSearch",
            "defaultInsert",
            "defaultUpdate",
            "defaultDelete",
            "getMaxFieldSeq",
            "chkCodeMaster",
            "getMathDur",
            "inquiryMagam",
            "inquiryMagamNew",
            "cbMagam",
            "inquiryBackup",
            "inquiryBackupNew",
            "getUserGroupTeamTotis",
            "searchExchangeList",
            "ovaMailList",
            "scb_voyage_anal_ag_mail_newprcCall",
            "sqlExchangeRateDaily",
            "sqlExchangeRatePeriod",
            "searchPeriodicalList",
            "cbSummaryPeriodicalList",
            "cbSummaryPeriodicalSummary",
            "cbSummaryPeriodicalListRawData",
            "searchPeriodicalDifferenceList",
            "searchEisPeriodicalList",
            "inquiryMagamList",
            "inquiryMagamListNew",
            "inquiryCbMagamList",
            "inquiryCbMagamCommExp",
            "inquiryBackupList",
            "inquiryBackupListNew",
            "inquiryBackupSmryList",
            "inquiryBackupSmryListNew",
            "searchPeriodicalBgtList",
            "rawSql",
            "rawBgtSql",
            "teamMonthVslVoySql",
            "teamMonthVslVoyBgtSql",
            "teamVslVoySql",
            "teamVslVoyBgtSql",
            "teamVslSql",
            "teamMonthVslSql",
            "teamMonthTypeSql",
            "teamMonthSql",
            "teamTcTypeSql",
            "teamSql",
            "whereSql",
            "whereEisSql",
            "whereSqlBgt",
            "searchPeriodicalTotisList",
            "whereTotisSql",
            "rawTotisSql",
            "teamMonthVslVoyTotisSql",
            "teamVslVoyTotisSql",
            "teamVslTotisSql",
            "teamMonthVslTotisSql",
            "teamMonthTotisSql",
            "teamTcTypeTotisSql",
            "teamTotisSql",
            "cbCargoQtySearch",
            "giganSql",
            "giganSqlEis",
            "cbSql",
            "portSql",
            "getMultiData",
            "getCbDeleteList",
            "getModelCb",
            "getMaxFieldSeq2",
            "getCbVslVoyInfo",
            "getCbVslVoyInfo2",
            "fcmGlAccInfoList",
            "BBCFlagCheck",
            "courtAdmitNoCheck",
            "courtPayHoldAdmitNoCheck",
            "chkGenCostBudgetLimit",
            "courtAdmitBudgetLimitCheck",
            "getVoyageDivision",
            "TotiscbCargoQtySearch",
            "TotiscbSql",
            "TotisportSql",
            "onloadShortcutInquiry",
            "shortcutUpdate",
            "shortcutInsert",
            "batchHistoryInsert",
            "paraseValue",
            "searchPeriodicalDivList",
            "searchBunkerList",
            "searchReletList",
            "searchStatusList",
            "searchEisVslVoyCbSmryList",
            "vslVoyCbSmryRawSql",
            "teamVslVoyCBSmrySql",
            "whereVslVoyCBSmryEisSql",
            "tot_ActualDataExtractVslVoyTotRetrieve",
            "tot_ActualDataExtractVslVoyCorpRetrieve"
    ));




    static class MethodSqlInfo {

        String preStateNm;
        String strBuffNm;

        String dtoVoNm;

        String qryType;
        int cnt;

        String dbWrapNm;
    }


    private static List<String[]> getProjectNmList() {
        return Arrays.asList(
/*                           1차 범위                                    */
                new String[]{"SOM_Business_Basic", "ejbModule"},
                new String[]{"SOM_Business_Crm", "ejbModule"},
                new String[]{"SOM_Business_Sysm", "ejbModule"},
                new String[]{"SOM_Business_InsLeg", "ejbModule"},
                new String[]{"SOM_Common", "CommonFnDaoSource"},
/*                           2차 범위                                    */
                new String[]{"SOM_Business_OperSa", "ejbModule"},
                new String[]{"SOM_Business_OperSt", "ejbModule"},
                new String[]{"SOM_Business_SalesCb", "ejbModule"},
                new String[]{"SOM_Business_SalesDoc", "ejbModule"},
                new String[]{"SOM_Business_Edi", "ejbModule"}
        );
    }


    public static void main(String[] args) throws IOException {
        // 변환 대상 프로젝트 목록 (폴더명, DAO 하위 디렉터리)
        List<String[]> modules = getProjectNmList();
        String createFilePath = CREATE_ROOT + File.separator ;
        AtomicInteger projectCnt = new AtomicInteger();

        AtomicInteger i  = new AtomicInteger();
        AtomicInteger i2  = new AtomicInteger();

        for (String[] mod : modules) {
//        new String[]{"SOM_Common", "CommonFnDaoSource"}
            Path srcDir = Paths.get(ASIS_ROOT, mod[0], mod[1]);
//            Path srcDir = Paths.get(ASIS_ROOT, "SOM_Common", "CommonFnDaoSource");
//            if (!Files.isDirectory(srcDir)) {
//                System.err.println("[SKIP] ASIS 경로 없음: " + srcDir);
//                continue;
//            }


            // TO-BE 경로: common/dao/business/standardInfo 등 구조 보존
            try (Stream<Path> files = Files.walk(srcDir)) {
                files.filter(p -> (Files.isRegularFile(p)
                        && (p.getFileName().toString().contains(".java"))
                        && (p.getFileName().toString().toUpperCase().contains("DAO"))
//                        &&(p.getParent().getFileName().toString().contains("contract"))
//                                &&
//                                && (
//                                       ( FileNm.OMISSION_DAO_PATH.stream().filter(file -> (file.startsWith(p.getFileName().toString().replace(".java", "")))).collect(Collectors.toSet()).size() > 0)
//                                )
//
////                                )
                                )
//                                || p.getParent().getFileName().startsWith("invoice")
//                        && p.getFileName().toString().equals("CourtPermitAppDAO.java")
                        )

                        .forEach(dao -> {
                            projectCnt.getAndIncrement();
                            System.out.println(dao);
                            i2.incrementAndGet();
                            processDao(dao, srcDir, Paths.get(createFilePath), i);
                        });
            }
        }
        System.out.println("이미 전환 :: " + i + ":: 전체 파일 :: " + i2);
    }


    // DAO 파일별 처리
    private static void processDao(Path dao, Path srcDir, Path dstRoot, AtomicInteger i) {
        try {
            String code      = new String(Files.readAllBytes(dao), StandardCharsets.UTF_8);
            String className = dao.getFileName().toString().replace(".java","");


            // ASIS 내 상대 경로 보존
            Path outDir   = dstRoot.resolve(dao.getParent().getFileName());
            String xml    = convert(code, className, srcDir.toString(), outDir.toString());
            Files.createDirectories(outDir);

            String mapperFile = className + ".java";
            Path outFile = outDir.resolve(mapperFile);


            if(!Files.exists(outFile)) {
                Files.write(outFile, xml.getBytes(StandardCharsets.UTF_8),
                        StandardOpenOption.CREATE,
                        StandardOpenOption.TRUNCATE_EXISTING);

            }else {
                i.incrementAndGet();
            }


        } catch (Exception e) {
            System.err.println("[FAIL] " + dao + " : " + e.getMessage());
            Arrays.stream(e.getStackTrace()).forEach(item -> System.out.println(item));
        }
    }

    public static List<MethodSqlInfo> getMethodInfo (String body) {
        List<MethodSqlInfo> mList = new ArrayList<>();
        String[] lines = body.split("\n");

        Pattern p = Pattern.compile("(\\w+)\\s*=\\s*(\\w+)\\.prepareStatement\\s*\\(\\s*(\\w+)(?:\\.toString\\(\\))?\\s*\\)");
        for(String line : lines) {
            if(line.contains("prepareStatement")) {
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
    public static String convert(String code, String projectNm, String asisPath, String toPath) throws IOException {
        StringBuilder out = new StringBuilder();

        // 패키지 및 import
        out.append("package ").append(toPath.replace("D:\\panocean\\panocean-v2\\src\\main\\java\\","")
                .replace("\\",".")
                .replace("."+projectNm+".java", "")

        ).append(";\n\n");

        String[] lines = code.split("\n");

        StringBuilder topComment = null;
        boolean isTop = true;

        String s = "";
        for(String line : lines) {
            if(line.trim().startsWith("/") && (line.contains("{") || line.contains("}")) ) {
                line =  line.replace("{", "").replace("}", "");
            }
            s += line + "\n";
        }

        code = s;
        for(String line : lines) {

            if(line.contains("package")) {
                continue;
            }
            if(line.contains("import")) {
                if(line.contains("exception.STXException")) continue;
                out.append(line.replace("com.stx.som.common", "com.pan.som.common")).append("\n");
                isTop = false;
                continue;
            }

            if(line.contains(projectNm)) {break;}

            if(line.contains("class")) continue;
            if(line.contains("log")) continue;

            if(isTop) {
                out.append(line).append("\n");
            }else {
                if(topComment == null) topComment = new StringBuilder();
                topComment.append(line).append("\n");
            }
        }

        out.append("import java.util.*;\n")
                .append("import kr.co.takeit.util.StringUtil;\n")
                .append("import kr.co.takeit.exception.UxbBizException;\n")
                .append("import com.pan.som.common.utility.Formatter;\n")
                .append("import lombok.RequiredArgsConstructor;\n")
                .append("import lombok.extern.slf4j.Slf4j;\n")
                .append("import org.springframework.stereotype.Repository;\n")
                .append("import com.pan.som.common.utility.*;\n")
                .append("import org.springframework.beans.factory.annotation.Autowired;\n");
//                .append("import org.springframework.beans.factory.annotation.Autowired;\n")

        out.append("import kr.co.takeit.session.UserInfo;\n")
                .append("import kr.co.takeit.session.user.UserDelegation;\n")
                .append("import kr.co.takeit.dataset.DataSetRowStatus;\n")
                .append("import kr.co.takeit.dao.UxbDAO;\n\n");

        if (!Objects.isNull(topComment)) {
            out.append(topComment);
        }

        out.append("@Slf4j\n@RequiredArgsConstructor\n@Repository\n")
                .append("public class ").append(projectNm).append(" {\n")
//                .append("\tprivate final DbWrap dbWrap;\n")
                .append("\tprivate final CommonDao commonDao;\n")
                .append("\tprivate final UxbDAO uxbDAO;\n\n");
        Matcher m = P_METHOD.matcher(code);
        int i = 0;
        int methodStartIdx = code.indexOf("{");
        while (m.find()) {
            String methodFull = m.group();
            String method = m.group(3);

            String methodParam = m.group(4);

            boolean starComm = false;

            int bodyStart = code.indexOf('{', m.end()-1) + 1;
            int depth = 1, lastIdx = bodyStart;
            String[] line2 = code.substring(bodyStart).split("\n");
            for(String line : line2) {
                int idx = 0;
                while (depth > 0 && idx < line.length()) {
                    char c = line.charAt(idx++);
                    lastIdx++;

                    if (c == '*') {
                        if(!line.contains("//")) {
                            if (line.contains("/*")) {
                                starComm = true;
                            }

                            if (line.contains("*/")) {
                                starComm = false;
                            }
                        }
                    }
                    if (starComm && line.contains("//")) {
                        continue;
                    }

                    if (c == '{') {
                        depth++;
                    }
                    if (c == '}') {
                        depth--;
                    }
                }
            }

            String comment = "";
            String body = code.substring(bodyStart, lastIdx - 1)
                    .replaceAll("StringBuffer", "StringBuilder")
                    .replaceAll("dbWRAP", "dbWrap")
                    .replaceAll("dbwrap", "dbWrap");


            try {
                comment = code.substring(methodStartIdx + 1,  bodyStart - 1);

            } catch (Exception e) {
                System.err.println("dao :: " + projectNm + "  method :: " + m.group(2));
                System.err.println("methodStartIdx :: " + (methodStartIdx+1) + "::" + (bodyStart - 1));
                System.err.println("comment :: " + comment);
            }


            String[] comments = comment.split("\n");
            out.append("\n\n");
            for(String line : comments) {
                if(line.contains("Logger")) continue;
                if(line.contains("}")) continue;
                if(line.contains("{")) continue;
                if(line.contains("STXException")) continue;
                if (line.contains(");") || line.contains(";")) continue;
                if(line.contains("return") && line.contains(";")) continue;
                if(line.contains(method)) break;
                out.append(line).append("\n");
            }


            methodStartIdx = lastIdx;
            if(methodParam.indexOf(",") > 0) {
                String[] params = methodParam.split(",");
                String methodP = "";
                for(String param : params) {
                    if(param.contains("UserBean") || param.contains("Connection")) continue;

                    if(!methodP.isEmpty()) methodP += ", ";
                    methodP += param;
                }
                methodParam = methodP;
            }else if(methodParam.contains("UserBean") || methodParam.contains("Connection")){
                methodParam  = "";
            }
            out.append("\t");
            out.append(methodFull.substring(0, methodFull.indexOf("(") + 1));

            out.append(methodParam);
            out.append(")");
            if(body.contains("getField")) {
                out.append(" throws Exception");
            }
            out.append(" {\n");
            out.append("#{").append(i).append("}\n");
            out.append("\t}");

//            methodStartIdx = m.end();
            i++;
        }

        out.append("\n}");

        Matcher m2 = P_METHOD.matcher(code);
        String rtnStr = out.toString();
        i = 0;
        while (m2.find()) {
            String rtnType = m2.group(2);
            String method = m2.group(3);
            String methodParam = m2.group(4);

            int bodyStart = code.indexOf('{', m2.end()-1) + 1;
            int depth = 1, idx = bodyStart;
            boolean starComm = false;
            while (depth > 0 && idx < code.length()) {
                char c = code.charAt(idx++);
                if(c == '*') {
                    if(code.charAt(idx - 2) == '/') {
                        starComm = true;
                    }

                    if(code.charAt(idx) == '/') {
                        starComm = false;
                    }

                }
                if(starComm) continue;

                if (c == '{') depth++;
                else if (c == '}') depth--;
            }
            String body = code.substring(bodyStart, idx - 1)
                    .replaceAll("StringBuffer", "StringBuilder")
                    .replaceAll("dbWRAP", "dbWrap")
                    .replaceAll("dbwrap", "dbWrap")
                    .replaceAll("DbWrap\\.", "dbWrap.");


            List<MethodSqlInfo> mList = getMethodInfo(body);
            if(methodParam.indexOf(",") > 0) {
                String[] params = methodParam.split(",");
                String methodP = "";
                for(String param : params) {
                    if(param.contains("UserBean") || param.contains("Connection")) continue;

                    if(!methodP.isEmpty()) methodP += ", ";
                    methodP += param;
                }
                methodParam = methodP;
            }else if(methodParam.contains("UserBean") || methodParam.contains("Connection")){
                methodParam  = "";
            }

            String replaceStr = "";
            if(body.contains("userBean.")) {
                replaceStr += ("\n\t\tUserDelegation userInfo = UserInfo.getUserInfo();\n");
            }

//            if(body.contains("userBean.getUser_id()")) {
//                body = body.replaceAll("userBean.getUser_id\\(\\)", "userInfo.getUserId()");
//            }

            if(mList.isEmpty()  || body.contains("nrow++") || body.contains("++colRow") || body.contains("++col")) {
                if( body.contains("nrow++") || body.contains("++colRow") || body.contains("++col")) {
                    replaceStr += "// 직접 jdbc -> mapper로 전환\n";
                }

                replaceStr += getMethodString(body, mList,  method, projectNm, rtnType, methodParam);
            }else {

                replaceStr += collectCode(body, mList,  method, projectNm, rtnType, methodParam);
            }

            rtnStr = rtnStr.replace("#{" + i + "}", replaceStr);
            i++;
        }

        return rtnStr
                .replaceAll("userBean\\.", "userInfo.")
                .replaceAll("userBean," , "")
                .replaceAll("userBean ," , "")
                .replaceAll(", userBean" , "")
                .replaceAll(",userBean" , "")
                .replaceAll("new Long\\(dwt\\)", "dwt")
                .replaceAll("new Long", "")
                .replaceAll("new Double", "");

    }



    // 변수명 = Format.nullTrim(변수명); 패턴
    private static final Pattern P_NULLTRIM_ASSIGN = Pattern.compile(
            "\\b([A-Za-z_]\\w*)\\s*=\\s*Formatter\\.nullTrim\\(\\s*\\1\\s*\\)\\s*;?"
    );



    /**
     * 주어진 코드 라인이 "foo = Format.nullTrim(foo);" 형태인지 검사
     * @param line 코드 한 줄
     * @return 패턴에 매칭되면 true, 아니면 false
     */
    public static boolean isNullTrimAssignment(String line) {
        Matcher m = P_NULLTRIM_ASSIGN.matcher(line);
        return m.find();
    }
    private static final Pattern METHOD_CALL_PATTERN =
            Pattern.compile("\\b([a-zA-Z_][a-zA-Z0-9_]*)\\s*\\(");
    private static String getMethodString(String body, List<MethodSqlInfo> mList,  String method, String projectNm, String rtnType, String methodParam) {
        String[] lines = body.split("\n");
        StringBuilder out = new StringBuilder();
        boolean isCatch = rtnType.contains("String") || rtnType.contains("ArrayList");

        String qryType = "";
        boolean isCatchCon = false ;
        boolean isWhile = false;
        boolean isIf = false;


        int mapperCnt = 0;
        int cnt = 0;
        int catchDel = 0;

        String rtnNm ="";
        String dtoNm = "";
        String preStateNm = "";
        String nm = "";
        String resultSetNm = "";
        String rtnList = "listMap";


        for(int i = 0; i < lines.length; i++) {
            String line = lines[i].trim();
            String strTap = getTap(cnt);
            if (line.isEmpty()) {
                out.append("\n");
                continue;
            }
            if (line.contains("PKGenerator.")) {
                line = line.replace("PKGenerator", "pkGenerator");
            }
            if (line.contains("getStatus()") && (line.contains("\"insert\"") || line.contains("\"delete\"") || line.contains("\"update\"")) && line.contains("equals")) {
                line = line.replace("getStatus()", "getRowStatus()")
                        .replace(".equals(", " == ")
                        .replace("\"insert\")", "DataSetRowStatus.INSERT")
                        .replace("\"update\")", "DataSetRowStatus.UPDATE")
                        .replace("\"delete\")", "DataSetRowStatus.DELETE");
            }

            if(line.contains("DbWrap")) continue;
            if(line.contains("dbWrap")) line = line.replace("dbWrap", "commonDao");



            if(line.contains("if") && !line.contains("{") && !line.startsWith("/")) {

                String nextLine = lines[i + 1].trim();
                if(nextLine.contains(".setString")){
                    continue;
                }

                if(nextLine.contains("append")) {
                    String tap = strTap;
                    out.append(tap).append(line).append("\n");
                    out.append(tap).append("\t").append(nextLine).append("\n");
                    i++;
                    continue;
                }
            }

            if(line.startsWith("//")) {
                out.append(getTap(cnt)).append(line).append("\n");
                continue;
            }

            if(line.startsWith("System.out")) {
                out.append(getTap(cnt)).append(line).append("\n");
                continue;
            }

//            if(isNullTrimAssignment(line)) continue;


            qryType = detectQueryType(line, qryType);

            if(isCatchCon) {

                if ((line.contains("STXException") && !line.contains("\""))
                        || line.contains("printStackTrace")
                ) continue;

                if ((line.contains("STXException") && line.contains("\""))) {
                    line = line.replace("STXException", "UxbBizException");
                }
            }

            if(line.contains("userBean.getUser_id")) {
                line = line.replaceAll("userBean\\.getUser_id", "userInfo.getUserId");
            }

            if(line.startsWith("ResultSet")) {
                resultSetNm = line.split(" ")[1].trim();
                continue;
            }

            if(line.contains("catch")) {
                isCatchCon = true;

            }
            if(isCatchCon && line.contains("}")&& !line.contains("try") && !line.contains("catch")) {
                isCatchCon = false;
            }


            if(line.contains("PreparedStatement")) {
                preStateNm = line.split(" ")[1].trim();
                continue;
            }

            if((!preStateNm.isEmpty() && line.contains(preStateNm+".set")) && !line.contains("dbWrap")) {
                continue;
            }

            if(isResultSetNextIf(line)) {
                isWhile = true;
                isIf = true;

                out.append(strTap).append(getRsGetConverter(line.replace(resultSetNm+".next()", rtnList + "!= null && !"+rtnList+".isEmpty()"), resultSetNm).replace("map.", rtnList + ".get(0)."));
                cnt++;

                if(line.contains("}")) {
                    lineRsToList(out, line, resultSetNm, rtnList);
                    cnt--;
                }
                out.append("\n");

                continue;
            }

            if(line.contains("executeQuery") || line.contains("executeUpdate") ) {
                if(line.contains("=")) {
                    rtnList = "listMap"+(mapperCnt == 0 ? "" : mapperCnt);

                    nm = "List<Map<String, Object>> " + rtnList + " = ";
                }

                System.out.println("::::::method ::: " +  method);
                out.append(strTap).append(nm).append("uxbDAO.").append(qryType).append("(\"").append(projectNm.replace("DAO", ""))
                        .append(".").append(method).append("\", ").append(getParam(methodParam, cnt)).append(");\n");
                mapperCnt++;
                continue;
            }

            if(isWhile && line.contains(resultSetNm + ".get") && !line.contains("if(")) {

                line = getRsGetConverter(line, resultSetNm);
                if(isIf) {
                    line = line.replace("map.", rtnList+".get(0).");
                }
                // 정규식 패턴
//                String pattern = "\\b"+ resultSetNm +"\\.get\\w+\\(([^)]+)\\)";
//                String replacement = "map.get($1)";
//
//                // 변수 변환 타입
//                line = line.replaceAll(
//                        "(\\w+)\\.set(\\w+)\\(new (Boolean|Byte|Short|Integer|Long|Float|Double|Character)\\(rs\\.get\\w+\\(\"([^\"]+)\"\\)\\)\\);",
//                        "$1.set$2($3.valueOf(map.get(\"$4\")));"
//                );
//                line = line.replace(pattern, replacement);
            }

            if(line.contains("while") && line.contains(".next()") && line.contains(rtnNm)) {
                isWhile = true;
                out.append(strTap).append("for(Map<String, Object> map : "+ rtnList +") {\n");
                cnt++;
                continue;
            }

            if(line.contains("}") ) {
                cnt--;
            }
            strTap = getTap(cnt);
            if(isWhile && !line.contains("add(") && line.startsWith("ps")) {
                continue;
            }

            if(isWhile && line.contains("add(")) {
//                String outStr = line.substring(0, line.indexOf("(")+1) + dtoNm + ");";
//                if(dtoNm.isEmpty()) {
                out.append(strTap).append(line).append("\n");
//                }else {
//                    out.append(strTap).append(outStr.trim()).append("\n");
//                }

                continue;
            };

            if(line.contains("userBean.getUser_id")) {
                line = line.replaceAll("userBean\\.getUser_id", "userInfo.getUserId");
            }

//            if(line.contains("setSys_cre") || line.contains("setSys_upd")) continue;
            if(line.isEmpty() || line.contains("CommonDao")) continue;

            if(!isCatch) {

                if(catchDel > 0) {

                    if(line.contains("STXException") || line.contains("printStackTrace")) continue;

                    if(line.contains("{")) {
                        catchDel++;
                    }
                    if(line.contains("}") ) {
                        catchDel--;
                        if(catchDel == 0 && line.equals("}")) {

                            continue;
                        }
                    }
                    if(method.equals("approvedListSearch")) {
                        System.out.println("catchDel :: " + catchDel + " ::  " +line);
                    }
                    if(!line.contains("UCG") && !line.contains("ERR-") && !line.contains("FAIL") && (!line.contains("}") || catchDel >= 0)) {
                        continue;
                    }
                }
                if(line.replaceAll(" ", "").contains("try{") ) {
                    continue;
                }
                if(line.contains("catch")) {
                    catchDel++;
                    continue;
                }
                if(line.contains("finally") ) {
                    out.append(strTap).append("}\n");
                    continue;
                }

            }else {
                if(catchDel > 0) {

                    if(line.contains("STXException")){
                        out.append(strTap).append(line.replace("STXException", "UxbBizException"));
                    }
                    if( line.contains("printStackTrace")) continue;

                    if(line.contains("{")) {
                        catchDel++;
                    }
                    if(line.contains("}") ) {
                        catchDel--;
                    }

                    if(!line.contains("UCG") && !line.contains("FAIL") && (!line.contains("}") || catchDel > 0)) {
                        continue;
                    }
                }

                if(line.contains("catch")) {
                    catchDel++;
                }
                if(line.contains("finally") ) {

                    out.append(strTap).append("}\n");
                    continue;
                }
            }

            if(
//                    line.contains("log.") ||
                    line.contains("prepareStatement")
                            || line.contains("DbWrap")
                            || line.equals("PreparedStatement")) continue;

            // 공통 스킵 조건 체크
            if (shouldSkipLine(line, preStateNm) ) {
                continue;
            }

            line = getCommonMethod(line);


            line = line.replaceAll("connection", "conn")
                    .replaceAll("conn,", "")
                    .replaceAll("conn ,", "")
                    .replaceAll(", conn", "")
                    .replaceAll(",conn", "")
                    .replaceAll("conn", "")
                    .replaceAll("STXException", "UxbBizException")
            ;

            out.append(strTap).append(line).append("\n");
            if(line.contains("{")) {

                cnt++;
            }
        }
//        out.append("\t}");
        return out.toString();
    }

    private static String getCommonMethod(String line) {
        Matcher matcher = METHOD_CALL_PATTERN.matcher(line);

        while (matcher.find()) {
            String methodName = matcher.group(1);

            if (TARGET_METHODS.contains(methodName) ) {
                String methodCut = line.substring(0, line.indexOf(methodName));
                if(!methodCut.toLowerCase().endsWith("dao.")
                        && !methodCut.toLowerCase().endsWith("commonfunction.")
                        && !methodCut.toLowerCase().endsWith("com.")) {
                    if(methodCut.toLowerCase().endsWith("this.")) {
                        line = line.replace("this."+ methodName, "commonDao." + methodName);
                    }else {
                        line = line.replace(methodName, "commonDao." + methodName);
                    }
                }
            }
        }
        return line;
    }

    // SQL 추출·정제
    private static String collectCode(String body, List<MethodSqlInfo> mList, String method, String projectNm, String rtnType, String methodParam) throws IOException {
        String[] lines = body.split("\n");
        MethodSqlInfo mInfo = new MethodSqlInfo();
        StringBuilder out = new StringBuilder();

        if(mList.size() == 1) {
            mInfo = mList.get(0);
        }

        boolean isCatch = rtnType.contains("String") || rtnType.contains("ArrayList");
        boolean isWhile = false;
        boolean isCatchCon = false;
        boolean isList = false;
        boolean isIf = false;
        boolean isPerQry = false;


        int mapperCnt = 0;
        int cnt = 0;
        int catchDel = 0;
        String dtoNm = "";
        String preStateNm = "";

        String qryType = "";
        String nm = "";
        String rtnNm = "";

        String resultSetNm = "";

        String rtnList = "listMap";

        for(int i = 0; i < lines.length; i++) {
            String line = lines[i].trim();
            String strTap = getTap(cnt);
            if (line.isEmpty()) {
                out.append("\n");
                continue;
            }

            if (line.contains("PKGenerator.")) {
                line = line.replace("PKGenerator", "pkGenerator");
            }

            if (line.contains("getStatus()") && (line.contains("\"insert\"") || line.contains("\"delete\"") || line.contains("\"update\"")) && line.contains("equals")) {
                line = line.replace("getStatus()", "getRowStatus()")
                        .replace(".equals(", " == ")
                        .replace("\"insert\")", "DataSetRowStatus.INSERT")
                        .replace("\"update\")", "DataSetRowStatus.UPDATE")
                        .replace("\"delete\")", "DataSetRowStatus.DELETE");
            }


            if(cnt == 0 && line.trim().equals("}") && catchDel == 0) {
                continue;
            }

            if((line.contains("if") || line.contains("else"))) {
                String nextLine = lines[i + 1].trim();

                if(nextLine.contains(preStateNm+".set") ){
                    continue;
                }
            }

            if(line.startsWith("//")) {
                out.append(strTap).append(line).append("\n");
                continue;
            }
//            if(isNullTrimAssignment(line)) continue;

            if(line.startsWith("ResultSet")) {
                resultSetNm = line.split(" ")[1].trim();
                continue;
            }

            // 쿼리 타입 감지
            String detectedQuery = detectQueryType(line, qryType);
            if (detectedQuery != null) {
                qryType = detectedQuery;
            }

            if(isPerQry) {
                if(line.lastIndexOf(")") != -1) {
                    isPerQry = false;
                }
                continue;
            }

            if(line.contains("prepareStatement")) {
                int endIdx = line.lastIndexOf(")");
                if(endIdx == -1) {
                    isPerQry = true;
                }
                continue;
            }

            // PreparedStatement 변수명 추출
            if (line.contains("PreparedStatement")) {
                preStateNm = extractPreparedStatementName(line);
                continue;
            }


            if((!preStateNm.isEmpty() && line.contains(preStateNm+".set")) && !line.contains("dbWrap")) {
                if(line.contains(".get") && (line.toUpperCase().contains("DTO") || line.toUpperCase().contains("VO") || line.contains("Formatter"))
                        && (line.contains("setNull") ||
                        line.contains("setBoolean") ||
                        line.contains("setByte") ||
                        line.contains("setShort") ||
                        line.contains("setInt") ||
                        line.contains("setLong") ||
                        line.contains("setFloat") ||
                        line.contains("setDouble") ||
                        line.contains("setBigDecimal") ||
                        line.contains("setString") ||
                        line.contains("setBytes") ||
                        line.contains("setDate") ||
                        line.contains("setTime"))
                ) {
                    String re = "\\w+\\.set\\w+\\((\\w+\\+\\+|\\w+),\\s*(.*)\\)";
                    String lineStr = line.replaceAll(re, "$2");
//                    String t = lineStr.substring(lineStr.indexOf(".get"));
                    String dtoVo = "";
                    int lineIdx = 0;
                    int lineLength = lineStr.length();

                    while( lineIdx < lineLength) {
                        char c = lineStr.charAt(lineIdx++);
                        if(c == '.' ) {
                            if(!dtoVo.trim().equals("Formatter")) {
                                break;
                            }
                        }

                        if((c == '\n' || c== ' ') ) {
                            dtoVo = "";
                        }

                        dtoVo += c;
                    }

                    if(dtoVo.trim().startsWith("Formatter")) {
                        dtoVo = dtoVo.replace("Formatter.", "")
                                .replace("nullTrim(", "")
                                .replace("nullLong(", "")
                                .replace("(", "");

                    }
                    String paramNm = "";
                    try{
                        paramNm = lineStr.substring(lineStr.indexOf(".get")).replaceAll("\\)", "")
                                          .replaceAll(";", "")
                                          .replaceAll("\\(", "");
                    }catch (Exception e) {
                        System.out.println(":::: " + line + "::::: " +lineStr);
                        throw new IOException(e);
                    }

                    if(paramNm.substring(1).contains(".")) {
                        paramNm = paramNm.substring(0, 1)
                                + paramNm.substring(1).split("\\.")[0];
                    }




                    String s = dtoVo +  paramNm.replace("get", "set") + "(" + lineStr;

                    out.append(strTap).append(s.trim()).append("\n");
                }
                continue;
            }

            if(line.contains("userBean.getUser_id")) {
                line = line.replaceAll("userBean\\.getUser_id", "userInfo.getUserId");
            }

            if( line.isEmpty() || line.contains("CommonDao") || line.contains("new HashMap()")) continue;


            if(!isCatch) {
                if(line.contains("STXException") || line.contains("printStackTrace")) continue;
                if(catchDel > 0) {

                    if(line.contains("try")) {
                        if(line.contains("{")) {
                            catchDel++;
                        }
                        continue;
                    }

                    if(line.contains("catch")) {
                        if(line.contains("}")) {
                            catchDel--;

                        }
                        catchDel++;
                        continue;
                    }

                    if(line.contains("finally")) {
                        if(line.contains("}")) {
                            catchDel--;
                        }
                        catchDel++;
                        continue;
                    }
                    if(line.contains("{")) {
                        catchDel++;
                    }
                    if(line.contains("}")) {
                        catchDel--;
                    }
                    continue;
                }

                if(line.contains("try")) {
                    continue;
                }else if(line.contains("catch")){
                    catchDel++;
                    continue;
                }else if(line.contains("finally")) {
                    continue;
                }else if(catchDel > 0) {
                    if(line.contains("}")) {
                        catchDel--;
                        continue;
                    }
                }
            } else {
                if(catchDel > 0) {

                    if(line.contains("STXException") && line.contains("(e)")){

                        line = line.replace("(e)", "(e.getMessage())");

                        out.append(strTap).append(line.replace("STXException", "UxbBizException")).append("\n");
                        continue;
                    }
                    if( line.contains("printStackTrace")) continue;

                    if(line.contains("{")) {
                        catchDel++;
                    }

                    if(line.contains("}") ) {
                        catchDel--;
                    }

                    if(!line.contains("UCG") && !line.contains("FAIL") && (!line.contains("}") || catchDel > 0)) {
                        continue;
                    }
                }

                if(line.contains("catch")) {
                    catchDel++;
                }
                if(line.contains("finally") ) {

                    out.append(strTap).append("}\n");
                    continue;
                }
                if(isCatchCon) {
                    if(line.contains("STXException")
                            || line.contains("printStackTrace")
                    ) continue;

                }
                if(line.contains("catch")) {
                    isCatchCon = true;

                }
                if(isCatchCon && catchDel > 0 && line.contains("}") && !line.contains("try") && !line.contains("catch")) {
                    isCatchCon = false;
                    continue;
                }

            }

            if (line.equals("System.out")) {
                out.append(getTap(cnt)).append(line).append("\n");
                continue;
            }

            if (line.contains("PreparedStatement")
                    || line.replaceAll(" ", "").contains("if(rs!=null)") || line.replaceAll(" ", "").contains("rs.close();")
            ) {
                continue;
            }

            if(isIf && !line.contains("if(")) {
                line = getRsGetConverter(line, resultSetNm).replace("map.", rtnList+".get(0).");
            }

            if(!line.contains("append") && !line.contains("ResultSet") && !line.contains("if(")) {
                line = getRsGetConverter(line, resultSetNm);
            }



            if(line.contains("while") && line.contains(".next()") && line.contains(rtnNm)) {
                isWhile = true;
                out.append(strTap).append("for(Map<String, Object> map : "+ rtnList +") {\n");

                cnt++;
                continue;
            }

            if(line.contains("}") ) {
                cnt--;
            }
            strTap = getTap(cnt);

            if(isWhile && !line.contains("add(") && line.startsWith("ps")) {
                continue;
            }

            if(isWhile && line.contains("add(")) {
                out.append(strTap).append(line).append("\n");
                continue;
            }



            // ResultSet.next() if 문 처리
            if (isResultSetNextIf(line)) {
                isIf = true;

                line = line.replaceAll(" ", "");


                String substring = line.substring(line.indexOf("if(") + 3, line.indexOf(".next()"));
                if(!substring.equals(resultSetNm)) {
                    resultSetNm = substring;
                }

                out.append(strTap).append(getRsGetConverter(line.replace(resultSetNm+".next()", rtnList + " != null && !"+rtnList+".isEmpty()"), resultSetNm));

                cnt++;
                if(line.contains("}")) {
                    lineRsToList(out, line, resultSetNm, rtnList);
                    cnt--;
                }
                out.append("\n");

                continue;

            }

            if(line.contains("append")) {
                List<MethodSqlInfo> m = getListMethodInfo(mList, line);

                if(!m.isEmpty()) {
                    if(m.size() == 1) {
                        mInfo = m.get(0);
                    }
                    continue;
                }
            }


            if(line.contains("executeQuery") || line.contains("executeUpdate") ) {
                if(line.contains("=")) {
                    rtnNm = line.split("=")[0].trim();
                    if(rtnNm.contains(" ")) {
                        rtnNm = rtnNm.split(" ")[1].trim();
                    }
                    if(qryType.equals("select")) {
                        rtnList = "listMap"+(mapperCnt == 0 ? "" : mapperCnt);
                        nm = "List<Map<String, Object>> " + rtnList + " = ";

                    } else {
                        nm = rtnNm + " = ";
                    }
                }
                System.out.println("method :: " + method);
                StringBuilder sss = new StringBuilder();
                sss.append(strTap).append(nm).append("uxbDAO.").append(qryType).append("(\"").append(projectNm.replace("DAO", ""))
                        .append(".").append(method).append((mapperCnt == 0 ? "" : mapperCnt)).append("\", ").append(getParam(methodParam, cnt)).append(");\n");
                System.out.println(sss.toString());
                out.append(strTap).append(nm).append("uxbDAO.").append(qryType).append("(\"").append(projectNm.replace("DAO", ""))
                        .append(".").append(method).append((mapperCnt == 0 ? "" : mapperCnt)).append("\", ").append(getParam(methodParam, cnt)).append(");\n");
                mapperCnt++;
                continue;
            }


            if(isPreStateNm(mList, line)) {
                continue;
            }

            if(mInfo.preStateNm != null) {
                if(line.contains(mInfo.preStateNm)) {
                    continue;
                }
            }


            // 공통 스킵 조건 체크
            if (shouldSkipLine(line, preStateNm) ) {
                continue;
            }

            if(line.contains("new Double")) {
                line = line.replace("new Double", "Double.valueOf");
            }

            if(line.contains("new Long")) {
                line = line.replace("new Long", "Long.valueOf");
            }

            out.append(strTap).append(getCommonMethod(line).replaceAll("connection", "conn")
                    .replaceAll("conn,", "")
                    .replaceAll("conn ,", "")
                    .replaceAll(", conn", "")
                    .replaceAll("STXException", "UxbException")
                    .replaceAll("conn", "")
                    .replaceAll(",conn", "").trim()).append("\n");

            if(line.contains("{")) {
                cnt++;
            }

        }
        return out.toString();
    }


    private static String getRsGetConverter(String line, String resultSetNm) {
        if(!line.contains(".get")) {
            return line;
        }

        if(!line.contains(resultSetNm + ".")) {
            resultSetNm = "rs";
        }

        if(!line.contains(resultSetNm + ".")) {
            resultSetNm = "rs1";
        }



        // 정규식 패턴
        String pattern = "\\b"+resultSetNm+"\\.get\\w+\\(([^)]+)\\)";
        String replacement = "map.get($1)";
//        if(!test.contains(line)) {
//            replacement = "StringUtil.nvl(map.get($1))";
//        }
        line = line
                .replaceAll(
                        "\\b"+resultSetNm+"\\.getTimestamp\\(\"([^\"]+)\"\\)",
                        "Timestamp.valueOf(String.valueOf(map.get(\"$1\")))"
                )
//                .replaceAll(pattern, replacement)
                .replaceAll(
                        "\\b"+resultSetNm+"\\.get(\\w+)\\(\"([^\"]+)\"\\)",
                        "String.valueOf(map.get(\"$2\"))"
                )
                .replaceAll(
                        "\\bnew\\s+Long\\s*\\(\\s*map\\.get\\(\"([^\"]+)\"\\)\\s*\\)",
                        "Long.parseLong(String.valueOf(map.get(\"$1\")))"
                )
                // 2) Double 처리: new Double(map.get("키")) → Double.parseDouble(StringUtil.nvl(map.get("키"), \"0.0\"))
                .replaceAll(
                        "\\bnew\\s+Double\\s*\\(\\s*map\\.get\\(\"([^\"]+)\"\\)\\s*\\)",
                        "Double.parseDouble(String.valueOf(map.get(\"$1\")))"
                )
                // 3) Timestamp 처리: new Timestamp(map.get("키")) → Timestamp.valueOf(StringUtil.nvl(map.get("키"), \"1970-01-01 00:00:00\"))
                .replaceAll(
                        "\\bnew\\s+Timestamp\\s*\\(\\s*map\\.get\\(\"([^\"]+)\"\\)\\s*\\)",
                        "Timestamp.valueOf(String.valueOf(map.get(\"$1\")))"
                )
                // 4) String 처리 (나머지 map.get → StringUtil.nvl(map.get, \"\"))
                .replaceAll(
                        "\\bFormatter\\.nullTrim\\(String\\.valueOf\\(map\\.get\\(\"([^\"]+)\"\\)\\)\\)",
                        "StringUtil.nvl(map.get(\"$1\"), \"\")"
                )
                .replaceAll(
                        "\\bFormatter\\.nullLong\\(([^\"]+)\\)",
                        "Formatter.nullLong((String)$1)"
                )
                .replaceAll("new\\s+Long", "Long.parseLong");


        return line;
    }

    private static void lineRsToList(StringBuilder out, String line, String resultSetNm, String rtnList) {
        String ifStr = line.substring(line.indexOf("{") + 1, line.lastIndexOf("}") + 1);
        String chanStr = ""+rtnList + ".get(0).get(\"#{paramNm}\")";
        if(ifStr.contains(resultSetNm) && ifStr.contains("=")) {

            String typeNm = ifStr.split("=")[0].trim();
            String getType = ifStr.substring(ifStr.indexOf(".get") + 4, ifStr.lastIndexOf("("));
            String paramNm = chanStr.replace("#{paramNm}", ifStr.substring(ifStr.indexOf("\"")+1, ifStr.lastIndexOf("\"")));

            switch (getType) {
                case "String" :
                    chanStr = "String.valueOf(" + paramNm + ")";
                    break;
                case "Int" :
                    chanStr = "Integer.parseInt(String.valueOf(" + paramNm + "))";
                    break;
                case "Double" :
                    chanStr = "Double.parseDouble(String.valueOf(" + paramNm + "))";
                    break;
                case "Long" :
                    chanStr = "Long.parseLong(String.valueOf(" + paramNm + "))";
                    break;
                case "Timestamp" :
                    chanStr = "Timestamp.valueOf(String.valueOf(" + paramNm + "))";
                    break;
                default:
            }
            chanStr = " " + typeNm + " = " + chanStr + "; }";
        }
        out.append(chanStr);
    }

    private static List<MethodSqlInfo> getListMethodInfo(List<MethodSqlInfo> mList, String line) {
        return mList.stream().filter(item -> line.contains(item.strBuffNm)).collect(Collectors.toList());
    }

    private static boolean isPreStateNm(List<MethodSqlInfo> mList, String line) {
        return mList.stream().filter(item -> line.startsWith(item.preStateNm)).count() > 0;
    }

    private static String getParam(String param, int cnt) {
        String[] params = param.replaceAll("\t", " ").trim().split(",");
        List<String> paramList = Arrays.stream(params)
                .filter(item -> item.contains("DTO") || item.contains("VO"))
                .collect(Collectors.toList());
        StringBuilder rtnParam = new StringBuilder();

        if(paramList.size() > 1) {
//            setParam = paramList.get(0).split(" ")[1];
            rtnParam = new StringBuilder(paramList.get(1).split(" ")[1]);
        } else if(paramList.size() == 1) {
            rtnParam = new StringBuilder(paramList.get(0).split(" ")[1]);
        } else {
            for(String paramInfo : params) {
                if(paramInfo.trim().isEmpty()) break;

                String paramNm = paramInfo.replaceAll("\t", " ").trim().split(" ")[1].trim().replace("," , "");

                if(param.toString().isEmpty()) {
                    rtnParam.append(paramNm.trim());
                }else {
                    rtnParam.append(" ").append(paramNm.trim());
                }
            }
        }

        if(!param.contains("DTO") && !param.contains("VO")) {
            rtnParam = new StringBuilder("new HashMap<String, Object>() {{\n");
            String[] mParams = param.split(" ");
            for(int i = 0; i < mParams.length; i++) {
                String mParam = mParams[i];
//            for(String mParam: param.split(" ")) {
                mParam = mParam.replace(",", "");
                if(mParam.contains("String") || mParam.contains("int") || mParam.contains("Long") || mParam.contains("Timestamp")
                        ||mParam.contains("Collection") || mParam.equals("long")) continue;
                if(mParam.isEmpty()) continue;

                rtnParam.append(getTap(cnt)).append("\tput(\"").append(mParam).append("\", ").append(mParam).append(");\n");
            }
            rtnParam.append(getTap(cnt)).append("}}");
        }
        return rtnParam.toString();
    }

    private static String getTap(int cnt) {
        StringBuilder rtnTap = new StringBuilder("\t\t");
        for(int i = 0; i < cnt; i++) {
            rtnTap.append("\t");
        }
        return rtnTap.toString();
    }

    /**
     * 스킵해야 하는 기본 라인들을 체크
     */
    private static boolean shouldSkipBasicLine(String line) {
//        if (isNullTrimAssignment(line)) return true;
//        if (line.contains("setSys_cre") || line.contains("setSys_upd")) return true;
        if (line.isEmpty() || line.contains("CommonDao")) return true;
        if (line.contains("printStackTrace")) return true;
//        if (line.contains("log.")) return true;

        return false;
    }

    /**
     * 예외처리 관련 키워드들을 체크
     */
    private static boolean isExceptionHandling(String line) {
        return line.contains("catch") ||
                line.contains("finally") ||
                line.contains("try");
    }

    /**
     * SQL 실행 관련 라인인지 체크
     */
    private static boolean isSqlExecution(String line) {
        return line.contains("executeQuery") ||
                line.contains("executeUpdate") ||
                line.contains("PreparedStatement");
    }



    /**
     * 쿼리 타입을 감지하고 설정
     */
    private static String detectQueryType(String line, String qryType) {
        String lineLow = line.toLowerCase();

        if ((lineLow.contains("select") && line.contains("append")) || (lineLow.contains("select") && lineLow.contains("from"))) {
            return "select";
        } else if (lineLow.contains("update") && line.contains("append")) {
            return "update";
        } else if (lineLow.contains("insert") && line.contains("append")) {
            return "insert";
        } else if (lineLow.contains("delete") && line.contains("append")) {
            return "delete";
        }

        return qryType; // 쿼리 타입 없음
    }

    /**
     * PreparedStatement 변수명을 추출
     */
    private static String extractPreparedStatementName(String line) {
        if (line.contains("PreparedStatement")) {
            String[] parts = line.split(" ");
            if (parts.length > 1) {
                return parts[1].trim();
            }
        }
        return "";
    }

    /**
     * PreparedStatement 관련 라인인지 체크 (set 메서드 호출)
     */
    private static boolean isPreparedStatementSetter(String line, String preStateNm) {
        return !preStateNm.isEmpty() &&
                line.contains(preStateNm + ".set") &&
                !line.contains("dbWrap");
    }

    /**
     * ResultSet.next() 관련 if 문인지 체크
     */
    private static boolean isResultSetNextIf(String line) {
        return line.contains(".next()") && line.contains("if");
    }

    /**
     * 종합적으로 라인을 스킵해야 하는지 판단
     */
    private static boolean shouldSkipLine(String line, String preStateNm) {
        // 기본 스킵 조건들
        if (shouldSkipBasicLine(line)) {
            return true;
        }

        // PreparedStatement setter 라인
        if (isPreparedStatementSetter(line, preStateNm)) {
            return true;
        }

        // close() 메서드 호출
        if (line.contains("close()")) {
            return true;
        }

        // prepareStatement 호출
        if (line.contains("prepareStatement")) {
            return true;
        }

        return false;
    }

}
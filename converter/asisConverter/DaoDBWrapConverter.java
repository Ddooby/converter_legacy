

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class DaoDBWrapConverter {

    // 1. AS-IS/TO-BE 루트 경로 설정 (필요에 맞게 수정)
    private static final String ASIS_ROOT   = "D:/panocean/som_workspace_test";
    private static final String CREATE_ROOT = "D:/panocean/panocean/src/main/java/kr/co/panocean/dao";

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
            "public\\s+([\\w\\.<>,\\s\\?\\[\\]]+)\\s+" +  // 반환형
                    "(\\w+)\\s*" +                             // 메소드명
                    "\\((.*?)\\)\\s*" +                        // 파라미터: 비탐욕(non-greedy) 매칭
                    "(?:throws\\s+[\\w\\.,\\s]+)?\\s*" +       // 선택적 throws 절
                    "\\{",                                     // 여는 중괄호
            Pattern.DOTALL
    );


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
                new String[]{"SOM_Business_Basic", "ejbModule"},
                new String[]{"SOM_Business_Crm", "ejbModule"},
                new String[]{"SOM_Business_Sysm", "ejbModule"},
                new String[]{"SOM_Business_InsLeg", "ejbModule"},
                new String[]{"SOM_Common", "CommonFnDaoSource"}
        );
    }


    public static void main(String[] args) throws IOException {
        // 변환 대상 프로젝트 목록 (폴더명, DAO 하위 디렉터리)
        List<String[]> modules = getProjectNmList();
        String createFilePath = CREATE_ROOT + File.separator ;
        for (String[] mod : modules) {
            Path srcDir = Paths.get(ASIS_ROOT, mod[0], mod[1]);
            if (!Files.isDirectory(srcDir)) {
                System.err.println("[SKIP] ASIS 경로 없음: " + srcDir);
                continue;
            }

            // TO-BE 경로: common/dao/business/standardInfo 등 구조 보존
            try (Stream<Path> files = Files.walk(srcDir)) {
                files.filter(p -> Files.isRegularFile(p)
                                && (p.getFileName().toString().endsWith("DAO.java")|| p.getFileName().toString().endsWith("DAO2.java") ))
                        .forEach(dao -> {processDao(dao, srcDir, Paths.get(createFilePath));
                        });
            }
        }
    }

    // DAO 파일별 처리
    private static void processDao(Path dao, Path srcDir, Path dstRoot) {
        try {
            String code      = new String(Files.readAllBytes(dao), StandardCharsets.UTF_8);
            String className = dao.getFileName().toString().replace(".java","");


            // ASIS 내 상대 경로 보존
            Path outDir   = dstRoot.resolve(dao.getParent().getFileName());
            String xml    = convert(code, className, srcDir.toString(), outDir.toString());
            Files.createDirectories(outDir);

            String mapperFile = className + ".java";
            Path outFile = outDir.resolve(mapperFile);
            Files.write(outFile, xml.getBytes(StandardCharsets.UTF_8),
                    StandardOpenOption.CREATE,
                    StandardOpenOption.TRUNCATE_EXISTING);

        } catch (Exception e) {

            System.err.println("[FAIL] " + dao + " : " + e.getMessage());
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
        out.append("package ").append(toPath.replace("D:\\panocean\\panocean\\src\\main\\java\\","")
                .replace("\\",".")
                .replace("."+projectNm+".java", "")

        ).append(";\n\n");

        String[] lines = code.split("\n");
        for(String line : lines) {
            if(line.contains("package")) {
                continue;
            }
            if(line.contains("import")) {
                if(line.contains("exception.STXException")) continue;
                out.append(line.replace("com.stx.som.common", "kr.co.panocean.common")).append("\n");
            }

            if(line.contains(projectNm)) {
                break;
            }
        }

        out.append("import java.util.*;\n")
                .append("import kr.co.takeit.exception.TakeBizException;\n")
                .append("import kr.co.panocean.common.utility.Formatter;\n")
                .append("import lombok.RequiredArgsConstructor;\n")
                .append("import lombok.extern.slf4j.Slf4j;\n")
                .append("import org.springframework.stereotype.Repository;\n")
                .append("import kr.co.panocean.common.utility.*;\n")
                .append("import org.springframework.beans.factory.annotation.Autowired;\n")
                .append("import org.springframework.beans.factory.annotation.Autowired;\n")
                .append("import kr.co.takeit.dao.TakeDAO;\n\n")

                .append("@Slf4j\n@RequiredArgsConstructor\n@Repository\n")
                .append("public class ").append(projectNm).append(" {\n")
                .append("\tprivate final DbWrap dbWrap;\n")
                .append("\tprivate final CommonDao commonDao;\n")
                .append("\tprivate final TakeDAO takeDAO;\n\n");
        Matcher m = P_METHOD.matcher(code);
        while (m.find()) {
            String methodFull = m.group();
            String rtnType = m.group(1);
            String method = m.group(2);
            String methodParam = m.group(3);


            int bodyStart = code.indexOf('{', m.end()-1) + 1;
            int depth = 1, idx = bodyStart;
            while (depth > 0 && idx < code.length()) {
                char c = code.charAt(idx++);
                if (c == '{') depth++;
                else if (c == '}') depth--;
            }
            String body = code.substring(bodyStart, idx - 1)
                    .replaceAll("StringBuffer", "StringBuilder")
                    .replaceAll("dbWRAP", "dbWrap")
                    .replaceAll("dbwrap", "dbWrap");

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
            out.append("\n\n\t");
            out.append(methodFull.substring(0, methodFull.indexOf("(") + 1));

            out.append(methodParam);
            out.append(")");
            if(body.contains("dbWrap.getObjects") || body.contains("dbWrap.setObject")) {

                out.append(" throws Exception");
            }
            out.append(" {");

            List<MethodSqlInfo> mList = getMethodInfo(body);

            if(body.contains("dbWrap")) {
                getMethodString(body, mList, out, method, projectNm, rtnType, methodParam);
            }
        }
        out.append("\n}");

        return out.toString()
                .replaceAll("userBean.", "userInfo.")
                .replaceAll("userBean," , "")
                .replaceAll("userBean ," , "")
                .replaceAll(", userBean" , "")
                .replaceAll(",userBean" , "")
                .replaceAll("userBean", "");
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

    private static void getMethodString(String body, List<MethodSqlInfo> mList, StringBuilder out, String method, String projectNm, String rtnType, String methodParam) {
        String[] lines = body.split("\n");
        MethodSqlInfo mInfo = new MethodSqlInfo();

        boolean isCatch = rtnType.contains("String");

        String resultTypd = "";
        String qryType = "";
        boolean isCatchCon = false ;

        String rtnNm ="";
        int cnt = 0;
        int catchDel = 0;
        String dtoNm = "";
        String preStateNm = "";

        String nm = "";

        for(String line : lines) {
            if(isNullTrimAssignment(line.trim())) continue;
            String lineLow = line.toLowerCase();

            if(lineLow.contains("select") && line.contains("append"))
                qryType = "select";

            if(lineLow.contains("update") && line.contains("append"))
                qryType = "update";

            if(lineLow.contains("insert") && line.contains("append"))
                qryType = "insert";

            if(lineLow.contains("delete") && line.contains("append"))
                qryType = "delete";

            if(isCatchCon) {

                if(line.contains("STXException")
                        || line.contains("printStackTrace")
                ) continue;

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

            if(line.contains(".next()") && line.contains("if")) {

//                out.append(getTap(cnt)).append("for(").append("Map<String, Object>").append(" ").append("map").append(" : ").append("list) {\n");
                out.append(getTap(cnt)).append("if(!listS.isEmpty())");
                if(line.contains("{")) {
                    out.append(" {");
                }
                out.append("\n");
                continue;
            }

            if(line.contains("executeQuery") || line.contains("executeUpdate")) {

                Pattern p = Pattern.compile("new\\s+([\\w\\.\\$]*(DTO|VO))\\s*\\(", Pattern.MULTILINE);
                String dtoCode = body.substring(body.indexOf(line));
                Matcher matcher = p.matcher(dtoCode.substring(0, dtoCode.indexOf("}")));
                while(matcher.find()) {
                    resultTypd = matcher.group(1);  // 찾은 DTO 이름
                }

                if(line.contains("=")) {
                    rtnNm = line.split("=")[0].trim();
                    if(!resultTypd.isEmpty()){


                    }
                    try {
                        dtoNm = resultTypd.substring(0,1).toLowerCase() + resultTypd.substring(1);
                        nm = "List<" + resultTypd + "> "+dtoNm+"List = ";
                    }catch (Exception e) {
                        nm = "List<Map<String, Object>> listS = ";
                    }
                }


                out.append(getTap(cnt)).append(nm).append("takeDAO.").append(qryType).append("(\"").append(projectNm.replace("DAO", ""))
                        .append(".").append(method).append("\", ").append(getParam(methodParam)).append(");\n");
                continue;
            }



            if(line.contains("setSys_cre") || line.contains("setSys_upd")) continue;
            if(line.isEmpty() || line.contains("CommonDao")) continue;

            if(!isCatch) {

                if(catchDel > 0) {

                    if(line.contains("STXException") || line.contains("printStackTrace")) continue;

                    if(line.contains("{")) {
                        catchDel++;
                    }
                    if(line.contains("}") ) {
                        catchDel--;
                    }

                    if(!line.contains("UCG") && !line.contains("FAIL") && (!line.contains("}") || catchDel >= 0)) {
                        continue;
                    }
                }
                if(line.contains("try") ) {
                    continue;
                }
                if(line.contains("catch")) {
                    catchDel++;
                    continue;
                }
                if(line.contains("finally") ) {

                    out.append(getTap(cnt)).append("}\n");
                    continue;
                }
            }else {
                if(catchDel > 0) {

                    if(line.contains("STXException") || line.contains("printStackTrace")) continue;

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

                    out.append(getTap(cnt)).append("}\n");
                    continue;
                }
            }

            if( line.contains("log.")
                    || line.contains("prepareStatement")
                    || line.contains("DbWrap")
                    || line.equals("PreparedStatement")) continue;
            if(line.contains("}")) {
                cnt--;
            }
            line = line.replaceAll("connection", "conn")
                    .replaceAll("conn,", "")
                    .replaceAll("conn ,", "")
                    .replaceAll(", conn", "")
                    .replaceAll(",conn", "")
                    .replaceAll("conn", "")
                    .replaceAll("STXException", "TakeBizException")
            ;

            out.append(getTap(cnt)).append(line.trim()).append("\n");
            if(line.contains("{")) {
                cnt++;
            }
        }
        out.append("\t}");
    }


    private static String getParam(String param) {
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
            for(String mParam: param.split(" ")) {
                mParam = mParam.replace(",", "");
                if(mParam.contains("String") || mParam.contains("int") || mParam.contains("Long") || mParam.contains("Timestamp")
                ||mParam.contains("Collection")) continue;
                if(mParam.isEmpty()) continue;
                rtnParam.append("\t\t\tput(\"").append(mParam).append("\", ").append(mParam).append(");\n");
            }
            rtnParam.append("\t\t}}");

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

    // CRUD 판단
    private static String detectOp(String body, String sb) {
        String[] lines = body.split("\n");
        for(String line : lines) {
            if(!line.contains(sb + "append")) continue;
            line = line.toLowerCase().replaceAll(" ","");
            if (line.contains("insert") && line.contains(sb))
                return "insert";
            if (line.contains("delete") && line.contains(sb))
                return "delete";
            if (line.contains("update") && line.contains(sb))
                return "update";
        }
        return "select";
    }
}
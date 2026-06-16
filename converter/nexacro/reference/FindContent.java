

import netscape.javascript.JSObject;

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

public class FindContent {

    // 1. AS-IS/TO-BE 루트 경로 설정 (필요에 맞게 수정)
//    private static final String ASIS_ROOT   = "D:/panocean/20250729/som_workspace_utf8";
    private static final String ASIS_ROOT = "C:/AdvDevEnv/som_workspace/SOM_XInternet/";
//    private static final String CREATE_ROOT = "D:/TAKE/panoean/panocean/nexacro/biz/";
//    private static final String CREATE_ROOT = "D:/panocean/sombas/sombas/nexacro/biz/";
    private static final String CREATE_ROOT = "D:/panocean/somfin/nexacro/";
//    private static final String CREATE_ROOT = "D:/panocean/panocean-v2/nexacro/";

    private static final boolean All_SYS = false;
    private static final boolean TEST_SYS = true;


    public static void main(String[] args) throws IOException {
        // 변환 대상 프로젝트 목록 (폴더명, DAO 하위 디렉터리)

        Path srcDir = Paths.get(CREATE_ROOT);
        Path srcAsDir = Paths.get(ASIS_ROOT);
        AtomicInteger projectCnt = new AtomicInteger();

        AtomicInteger i = new AtomicInteger();
        AtomicInteger i2 = new AtomicInteger();
        AtomicInteger i3 = new AtomicInteger();

        try (Stream<Path> files = Files.walk(srcDir)) {
            files.filter(p -> (Files.isRegularFile(p)
                                      // && (p.getFileName().toString().contains(".xfdl"))
                                       && (
//                            p.getFileName().toString().contains("com.js")
//                    || p.getFileName().toString().contains("common_oz.js")
//                            FileNm.TEST_FILE.startsWith(p.getFileName().toString().replace(".xml", ""))
                    p.getFileName().toString().equals("com.js")
                       // (FileNm.MY_CRM_PATH.stream().filter(file -> (file.equals(p.getFileName().toString().replace(".xfdl", "")))).collect(Collectors.toSet()).size() > 0)
//
//                    || (FileNm.COMMON_FILE_NM.stream().filter(file -> (
//                                    file.startsWith(p.getFileName().toString().replace(".xml", ""))
//                                )
//                            ).collect(Collectors.toSet()).size() > 0)
            ))).forEach(xfdl -> {
                projectCnt.getAndIncrement();
                i2.incrementAndGet();
                processXfdl(xfdl, i, i3);
            });
        }
        System.out.println("전체 파일 :: " + i2 + " ::  없는 파일 :: " + i + " ::: " + i3);
    }

    private static List<String> getFuncList(String ozCode, String fileNm) {
        Pattern p = Pattern.compile(fileNm + "\\.(\\w+)\\s*=\\s*function\\s*\\(");
        Matcher m = p.matcher(ozCode);
        List<String> list = new ArrayList<>();
        int i = 0;
        while (m.find()) {
            String func = m.group(1).replace("_", "").toLowerCase();
            if(!func.isEmpty()) {
                i++;
                if(!fileNm.contains("common") && !func.startsWith("fn")){
                    func = "fn" + func;
                }
                list.add(func);

            }
        }
        System.out.println(fileNm + " :: " + i);
        return list;
    }

    private List<String> xfdlList = new ArrayList<>();
    private static void processXfdl(Path xfdl, AtomicInteger i, AtomicInteger i3) {
        try {
            Path tobePath = xfdl;

            if(!Files.exists(tobePath)) {
                i.incrementAndGet();
                return;
            }
            String codeTobe = new String(Files.readAllBytes(tobePath), StandardCharsets.UTF_8);
            String fileNm = xfdl.getFileName().toString().replace(".xfdl", "");
            Path outDir = tobePath.getParent();
            String xml = "";

            getComJsFunc(codeTobe);

            //공통 버튼이 제대로 선언이 되어있는지 확인. - 정확하지 않음..
            //getCommBtn(codeTobe, tobePath);

            //사용자 함수의 async가 잘 넣어져 있는지 확인.
            //getUserFuncAsync(codeTobe, fileNm);

            //파일 라인 수
            //getCharCount(codeTobe, fileNm);

            //주석처리된 arrayButtonFullID 찾기
            //formAuthBtnScript(codeTobe, fileNm);
            //cssclass 잘못되어 있는 [&quot;|']*(#(?:[0-9A-Fa-f]{6}){1,2}|red|blue)[&quot;|']* 찾는 메소드
//            getCssclassHexAndColor(codeTobe, fileNm, i3);

            //없는 스크립트 함수 호출 찾기
//            findNoneFunc(codeTobe, xfdl.toString());

            //findMessageError(codeTobe, fileNm);

            // 버튼 밖에 있는거 찾기
            //formOutComponent(codeTobe, fileNm);

            //Import 버튼
            //xml = importBtnConvert(codeTobe, fileNm);

            //중복 함수 찾기
//            duplicationFuncFind(codeTobe, fileNm);

            //비교 연산자여야 하는데 대입 연산자 찾기
//            comparisonOperator(codeTobe, fileNm);

            //기능 버튼 권한 이벤트 찾기
            //fnAuthButtonControlFind(codeTobe, fileNm);

            //기능 버튼 enable하는 스크립트 찾기
            //getBtnEnableScript(codeTobe, fileNm);

//            if(codeTobe.contains("com.fnAuthButtonControl")){
//                System.out.println("fileNm :: " + fileNm);
//            }

//            xml = closeToComFnClose(codeTobe, fileNm);

            Files.createDirectories(outDir);

            Path outFile = outDir.resolve(fileNm);

            if(!xml.isEmpty()) {
                Files.write(outFile, xml.getBytes(StandardCharsets.UTF_8),
                        StandardOpenOption.CREATE,
                        StandardOpenOption.TRUNCATE_EXISTING);
            }
        } catch (Exception e) {
            System.err.println("[FAIL] " + xfdl + " : " + e.getMessage());
            Arrays.stream(e.getStackTrace()).forEach(item -> System.out.println(item));
        }
    }

    private static void getComJsFunc(String codeTobe) throws IOException {
        String asIsOzCode = new String(Files.readAllBytes(Paths.get("C:\\AdvDevEnv\\som_workspace\\SOM_XInternet\\commonJS\\common_oz.js")), StandardCharsets.UTF_8);
        Path comOz = Paths.get(CREATE_ROOT + "_extlib_"+ File.separator + "Som" + File.separator + "common_oz.js");
        String ozCode = new String(Files.readAllBytes(comOz), StandardCharsets.UTF_8);


        String[] ozLines = ozCode.split("\n");
        String[] comLines = codeTobe.split("\n");
        String[] lines = asIsOzCode.split("\n");
        Pattern p = Pattern.compile("^var\\s*(G_\\w+)");
        Pattern pp = Pattern.compile("^function\\s*(\\w+)");
        List<String> asisList = new ArrayList<>();
        for(String line : lines) {
            Matcher m = p.matcher(line);
            if(m.find()) {
                asisList.add(m.group(1));
                continue;
            }
            Matcher mm = pp.matcher(line);
            if(mm.find()) {
                asisList.add(mm.group(1));
            }
        }

        //asisList.forEach(e-> System.out.println(e));
        System.out.println("###################################### " + asisList.size());


        List<String> comList = new ArrayList<>();
        List<String> comOzList = new ArrayList<>();

        for(String line : comLines) {
            for(String item : asisList) {
                Pattern pCom = Pattern.compile("^com\\.("+item+")\\s*=\\s+");

                Pattern pCom2 = Pattern.compile("^com\\.(fn"+item+")\\s*=\\s+");
                Matcher mCom2 = pCom2.matcher(line);
                Matcher mCom = pCom.matcher(line);
                if (mCom.find()) {
                    comList.add(mCom.group(1));
                }else if(mCom2.find()) {
                    comList.add(mCom2.group(1).replace("fn", ""));
                }
            }
        }
        System.out.println("::" + comList.size());
        comList.forEach(e-> System.out.println(e));

        for(String line : ozLines) {
            for(String item : asisList) {
                Pattern pOz = Pattern.compile("^common_oz\\.("+item+")\\s*=\\s+");
                Matcher mOz = pOz.matcher(line);
                Pattern pOz2 = Pattern.compile("^common_oz\\.(fn"+item+")\\s*=\\s+");
                Matcher mOz2 = pOz2.matcher(line);
                if (mOz.find()) {
                    comOzList.add(mOz.group(1));
                }else if(mOz2.find()) {
                    comOzList.add(mOz2.group(1));
                }
            }
        }
        System.out.println("::" + comOzList.size());
        comOzList.forEach(e-> System.out.println(e));

        System.out.println("########################################");
        int i = 0;
        for(String item : comList) {
            for(String item2 : comOzList) {
                if(item.contains(item2) || ("fn" + item).contains(item2)) {
                    System.out.println(item + " :: " + item2);
                    i++;
                    break;
                }
            }
        }
        System.out.println("i :: " + i);

//        for(String line : comLines) {
//            Matcher mCom = pCom.matcher(line);
//            while (mCom.find()) {
//                if ((comOzList.stream().anyMatch(e -> e.contains(mCom.group(1))))) {
//                    String func = mCom.group(1);
//                    Pattern pOz2 = Pattern.compile("(common_oz\\."+func+")\\s*=\\s+");
//                    Matcher mOz2 = pOz2.matcher(ozCode);
//                    if(mOz2.find()) {
//
//                    }else {
//                        if (func.startsWith("OZ")) {
//                            func = "fn" + func;
//                        }
//                    }
//                    comList.add(func.trim());
//                }
//            }
//        }
//        comList.stream().forEach(e-> {
//            Pattern pOz2 = Pattern.compile("(common_oz\\."+e+")\\s*=\\s+");
//            Matcher mOz2 = pOz2.matcher(ozCode);
//
//            if (mOz2.find()) {
//                System.out.println(mOz2.group(1));
//            }else {
//                System.out.println("XXXXXXXXXXXXXXXX :: "+e);
//            }
//
//        });
//        if(1==1 ) return;
//        List<String> list = new ArrayList<>();
//        comOzList.forEach(e->{
//            comList.stream().filter(e::contains).forEach(c -> {
//                list.add(e);
//            });
//        });
//
//        list.stream().forEach(e->{
//            System.out.println(":: " + e);
//        });
    }

    private static void getCommBtn(String codeTobe, Path filePath) throws IOException {
        String[] btnStrs = new String[]{"INQUIRY", "NEW", "SAVE", "APPROVE", "DETAIL", "EXPORT"};

        String fileNm = filePath.getFileName().toString().replace(".xfdl", ".xml");
        String path = filePath.toString().replace(CREATE_ROOT.replace("/","\\"), "").replace("/", "_");

        String[] paths = path.split("\\\\");
        String ppath = "";

        for(String ps : paths) {
            if(ps.contains(".xfdl")) continue;
            if(!ppath.isEmpty()
                       && !ppath.contains("_")
            ){
                ppath += "_";
            }
            if(ps.equals("accoun")) {
                ps = "account";
            }
            ppath += ps;
        }

        Path asisPath = Path.of(ASIS_ROOT + ppath + File.separator + fileNm);
        if(!Files.exists(asisPath)) {
            return;
        }

        String codeAsis = new String(Files.readAllBytes(asisPath), StandardCharsets.UTF_8);
        //<Button Height="13" Id="btn_calendar3" ImageID="btn_calendar" Left="1041" OnClick="btn_calendar3_OnClick" TabOrder="36" TabStop="FALSE" Text="Button7" Top="42" Width="16"></Button>
        Pattern p = Pattern.compile("<Button\\s*[^>]*Id=\"(\\w+)\"[^>]*Text=\"(\\w+)\"");
        Matcher m = p.matcher(codeAsis);
        List<String> btnList = new ArrayList<>();
        while(m.find()) {
            String id = m.group(1);
            String text = m.group(2).trim().toUpperCase();
            for(String str : btnStrs) {
                if(str.equals(text)){
                    switch (text){
                        case "INQUIRY" :
                            btnList.add("this.fnSearch");
                            break;
                        case "NEW" :
                            btnList.add("this.fnAdd");
                            break;
                        case "SAVE" :
                            btnList.add("this.fnSave");
                            break;
                        case "APPROVE" :
                            btnList.add("this.fnApprove");
                            break;
                        case "DETAIL" :
                            btnList.add("this.fnDetail");
                            break;
                        case "EXPORT" :
                            btnList.add("this.fnExcel");
                            break;
                        default:
                            break;
                    }
                }
            }
        }
        //"INQUIRY", "NEW", "SAVE", "APPROVE", "DETAIL", "EXPORT"
        for(String btnType : btnList) {
           if(!codeTobe.contains(btnType)) {
               if(!fileNm.isEmpty()) {
                   System.out.println("############ ::"  + fileNm);
                   fileNm = "";
               }
               System.out.println("btnType :: " + btnType);
           }
        }

        //<Button ButtonStyle="TRUE" Height="20" Id="btn_inquiry"
    }

    private static void getUserFuncAsync(String codeTobe, String fileNm) {
        String[] lines = codeTobe.split("\n");
        Pattern p = Pattern.compile("this\\.(\\w+)\\s*=\\s*function\\(([^)]*)\\)\\s*");
        List<String> listFunc = new ArrayList<>();

        boolean isFunc = false;

        String funcNm = "";
        for(String line : lines) {
            Matcher m = p.matcher(line);
            if(m.find()) {
                String func = m.group(1);
                if(!m.group(2).trim().contains(":nexacro")) {
                    funcNm = func;
                    isFunc = true;
                    continue;
                }
            }

            if(isFunc && !funcNm.isEmpty()
                       && !funcNm.toLowerCase().contains("callback")
                       && !funcNm.contains("fnInit")
                       && !funcNm.contains("fnSearch")
                       && !funcNm.contains("fnSave")
                       && !funcNm.contains("fnExcel")
                       && !funcNm.contains("fnClose")
                       && !funcNm.contains("fnPrint")
                       && !funcNm.contains("fnAdd")
                       && !funcNm.contains("fnDel")
            ) {
                if(line.contains("(async ()")) {
                    listFunc.add(funcNm);
                    funcNm = "";
                    isFunc = false;
                }
            }
        }

        if(!listFunc.isEmpty()) System.out.println("######## :: " + fileNm);
        for(String funcNms : listFunc) {
            System.out.println("------- [" + funcNms+"]");

        }
    }

    private static void getCharCount(String codeTobe, String fileNm) {
        int i = 0;
        int lineCnt = 0;
        int scriptStart = codeTobe.indexOf("<Script ");
        String[] lines = codeTobe.substring(scriptStart).split("\n");
        for(String line : lines) {

            if(line.trim().isEmpty()) continue;
            lineCnt++;
            for(var j = 0; j < line.length(); j++) {
                char c = line.charAt(j);
                if(c == ' ') {
                    continue;
                }
                i++;
            }
        }
        System.out.println("File Name :: " + fileNm + " :: line :: " + lineCnt+ "\nCount :: " + i);
    }

    private static void findMessageError(String codeTobe, String fileNm) {
        String[] lines = codeTobe.split("\n");
        for(int i = 0; i < lines.length; i++) {
            String line = lines[i].trim();
            if(line.startsWith("//")
                          || line.startsWith("/*")) continue;
            if((line.contains("com.replace") && line.contains("@")) || line.contains("com.replace(com.replace")) {
                if(!fileNm.isEmpty()) {
                    System.out.println("-" + fileNm);
                    fileNm = "";
                }
                System.out.println(line);
            }

        }
    }

    private static void findNoneFunc(String codeTobe, String fileNm) {
        Pattern funcP = Pattern.compile("(this\\.\\w+)\\s*=\\s*(:?async\\s*)?function\\s*\\(");
        List<String> list = new ArrayList<>();

        String[] lines = codeTobe.split("\n");
        for(int i = 0; i < lines.length; i++) {
            String line = lines[i].trim();
            Matcher funcM = funcP.matcher(line);
            while (funcM.find()) {
                String funcNm = funcM.group(1);

                list.add(funcNm);
            }
        }
        Pattern p = Pattern.compile("(this\\.\\w+)\\s*\\(");

        for(int i = 0; i < lines.length; i++) {
            String line = lines[i].trim();
            Matcher m = p.matcher(line);
            while(m.find()) {
                String s = m.group(1);
                if(s.toLowerCase().endsWith("callback")
                           || s.contains("titletext")
                           || s.contains("close")
                           || s.contains("setTimer")
                           || s.contains("killTimer")
                           || s.contains("getFocus")
                           || line.startsWith("//")
                           || line.startsWith("/*")
                           || line.contains("isValidObject")
                           || line.contains("getOwnerFrame")
                           || line.contains("setWaitCursor")
                           || line.contains("set_scrolltype")
                           || line.contains("CreateDataObject")
                           || line.contains("reload")
                           || line.contains("addChild")
                ) {
                    continue;
                }
                List<String> findList = list.stream().filter(e -> e.equals(s)).toList();
                if(!findList.isEmpty()) {
                   continue;
                }
                if(!fileNm.isEmpty()) {
                    System.out.println("========================= ::" + fileNm);
                    fileNm = "";
                }
                System.out.println(line + " :: " +s);
            }
        }
    }

    private static void getCssclassHexAndColor(String codeTobe, String fileNm, AtomicInteger i3) {
        Pattern p = Pattern.compile("[&quot;|']+(#(?:[0-9A-Fa-f]{6}){1,2}|red|blue|default)[&quot;|']+");
        Pattern p2 = Pattern.compile("return\\s*[\"|']+(#(?:[0-9A-Fa-f]{6}){1,2}|red|blue|default)[\"|']+");
        String[] lines = codeTobe.split("\n");
        boolean isScript = false;
        for(int i = 0; i < lines.length; i++) {
            String line = lines[i].trim();
            if(line.contains("<Script type=\"xscript5.1\">")) {
                isScript = true;
            }
            if(line.contains("<Cell")) {
                Matcher m = p.matcher(line);
                if(m.find()) {
                    if(!fileNm.isEmpty()) {
                        System.out.println("========================= ::" + fileNm);
                        fileNm = "";
                        i3.incrementAndGet();
                    }
                    System.out.println(line);
                }
            }else if(isScript && !line.contains("<Format")){
                Matcher m = p2.matcher(line);
                if(m.find()) {
                    if(!fileNm.isEmpty()) {
                        System.out.println("========================= ::" + fileNm);
                        fileNm = "";
                        i3.incrementAndGet();
                    }
                    System.out.println(line);
                }
            }

        }
    }

    private static void formAuthBtnScript(String codeTobe, String fileNm) {
        String[] lines = codeTobe.split("\n");
        for(String line : lines) {
            line = line.trim();
            if(line.contains("com.fnAuthButtonControl") && line.startsWith("//")) {
                if(!fileNm.isEmpty()) {
                    System.out.println("=========================== >> " + fileNm);
                    fileNm = "";
                }
                System.out.println(line);
            }
        }
    }

    private static void formOutComponent(String codeTobe, String fileNm) {
        if(!codeTobe.contains("right=")) return;

        Pattern formP = Pattern.compile("<Form.*width=\"(\\w+)\"");
        Pattern p = Pattern.compile(" right=\"(\\w+)\"");
        Pattern pL = Pattern.compile(" left=\"(\\w+)\"");
        int width = 0;


        String[] lines = codeTobe.split("\n");
        for(String line : lines) {
            if(line.contains("<Script")) {
                return;
            }
            if(line.contains("<Form")) {
                Matcher formM = formP.matcher(codeTobe);
                if(formM.find()) {
                    width = Integer.parseInt(formM.group(1));
                }
            }else {
                if(line.contains("right=\"0\"")) continue;
                Matcher m = p.matcher(line);
                while (m.find()) {
                    int right = Integer.parseInt(m.group(1));
                    if (right >= 0) {
                        continue;
                    }
                    if (!fileNm.isEmpty()) {
                        System.out.println("============================================ :: " + fileNm);
                        fileNm = "";
                    }
                    System.out.println(line);
                    continue;
                }
                Matcher mL = pL.matcher(line);
                while (mL.find()) {
                    int right = Integer.parseInt(mL.group(1));
                    if (right <= width) {
                        continue;
                    }
                    if (!fileNm.isEmpty()) {
                        System.out.println("============================================ :: " + fileNm);
                        fileNm = "";
                    }
                    System.out.println(line);
                    continue;
                }
            }

        }
    }

    private static String closeToComFnClose(String codeTobe, String fileNm) {
        StringBuilder sb = new StringBuilder();
        String[] lines = codeTobe.split("\n");
        if(!codeTobe.contains("this.close")) return "";

        for(int i = 0; i < lines.length; i++){
            String line = lines[i];


        }

        return sb.toString();
    }

    private static void getBtnEnableScript(String codeTobe, String fileNm) {
        String[] lines = codeTobe.split("\n");
        Pattern p = Pattern.compile("\\s*this\\.(\\w+)\\.");
        for(int i = 0; i < lines.length; i++) {
            String line = lines[i];
            Matcher m = p.matcher(line.trim());
            if(m.find()) {
                String btnNm = m.group(1);
                if(btnNm.equals("parent") || btnNm.contains("objExport") || btnNm.contains("form") || btnNm.contains("opener")) continue;
                if(!codeTobe.contains("id=\""+btnNm+"\"")){
                    if(!fileNm.isEmpty()) {
                        System.out.println("+====================================================+");
                        System.out.println("fileNm :: >>." + fileNm);
                        fileNm = "";
                    }
                    System.out.println("\t\t" + line);
                }
            }
        }
    }

    private static void fnAuthButtonControlFind(String codeTobe, String fileNm) {
        String[] lines = codeTobe.split("\n");
        if(!codeTobe.contains("com.fnAuthButtonControl")) return;
        boolean isFile = true;
        for(int i = 0; i < lines.length; i++) {
            String line = lines[i].trim();
            if(line.contains("com.fnAuthButtonControl") && line.substring(0,2).equals("//")){
//              if(line.contains("functionGubun")){
                  if(!fileNm.isEmpty()) {
                      System.out.println("fileNm :: " + fileNm);
                      fileNm = "";
                  }
                System.out.println(line);
            }
        }
    }

    private static void comparisonOperator(String codeTobe, String fileNm) {
        String[] lines = codeTobe.split("\n");
        Pattern p = Pattern.compile("text=\"([^\"]*)\"");
        boolean isCss = codeTobe.contains("com.drawGridDisableColor");
        boolean isFile = true;
        for(int i = 0; i < lines.length; i++) {
            String line = lines[i];
            if (line.trim().startsWith("//")) {
                continue;
            }

           if(line.contains("<Cell") && ( line.contains("cssclass=") || line.contains("drawDetailGridBkColor")) && isCss) {
               if(isFile) {
                   isFile = false;
                   System.out.println(fileNm);
               }
               System.out.println("\t" + line);

           }
        }
    }

    //중복 함수 찾기

    private static void duplicationFuncFind(String codeTobe, String fileNm) {
        String[] lines = codeTobe.split("\n");
        Pattern p = Pattern.compile("(this\\.\\w+)\\s*=\\s*function\\(");
        List<String> listFunc = new ArrayList<>();
        for(int i = 0; i < lines.length; i++) {
            String line = lines[i];
            if(line.trim().startsWith("//")){
                continue;
            }
            Matcher m = p.matcher(line);
            if(m.find()) {
                String funcNm = m.group(1);
                listFunc.add(funcNm);
            }

//            if (i != (lines.length - 1)) {
//                rtn.append("\n");
//            }
        }
        Set<String> seen = new HashSet<>();
        List<String> duplicates = listFunc.stream()
                                             .filter(s -> !seen.add(s))   // 이미 나온 적 있으면 true
                                             .collect(Collectors.toList());
        if(!duplicates.isEmpty() && duplicates.size() > 0) {
            System.out.println("================"+fileNm);
            for(String funcNm : duplicates) {
                System.out.println(funcNm);
            }
        }
    }

    //import 버튼
    private static String importBtnConvert(String codeTobe, String fileNm) {
        StringBuilder rtn = new StringBuilder();
        String[] lines = codeTobe.split("\n");
        for(int i = 0; i < lines.length; i++) {
            String line = lines[i];
            if(line.contains("<Button") && line.toUpperCase().contains("TEXT=\"IMPORT\"")) {
                if(line.contains("ico_upload") && line.contains("btn_ol_darkgray") && line.contains("btn_text")) {
                    rtn.append(line);
                    rtn.append("\n");
                    continue;
                }
                System.out.println(fileNm+"=====================================");
//                if(!line.contains("ico_upload")) {
//                    System.out.println(fileNm);
//                    return "";
//                }
                System.out.println("AS :: " + line);
                if(line.contains("cssclass")) {
                    line = line.replaceAll(" cssclass=\"([^\"]*)\"", " cssclass=\"btn_ol_darkgray,btn_text,ico_upload\"");
                }else {
                    line = line.replace("/>", " cssclass=\"btn_ol_darkgray,btn_text,ico_upload\"/>");
                }
                line = line.replaceAll("width=\"\\w+\"", "width=\"85\"");
                System.out.println("TO :: " + line);
            }
            rtn.append(line);
            rtn.append("\n");
//            if (i != (lines.length - 1)) {
//                rtn.append("\n");
//            }
        }
        return rtn.toString();
    }

}
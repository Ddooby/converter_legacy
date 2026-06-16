

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

public class FindComAsync {

    // 1. AS-IS/TO-BE 루트 경로 설정 (필요에 맞게 수정)
//    private static final String ASIS_ROOT   = "D:/panocean/20250729/som_workspace_utf8";
    //private static final String CREATE_ROOT = "D:/TAKE/panoean/panocean/nexacro/biz/";
    private static final String CREATE_ROOT = "D:/panocean/panocean-v2/nexacro/biz/";
//    private static final String CREATE_ROOT = "D:/panocean/somfin/nexacro/biz";
    private static final boolean All_SYS = false;
    private static final boolean TEST_SYS = true;


    public static void main(String[] args) throws IOException {
        // 변환 대상 프로젝트 목록 (폴더명, DAO 하위 디렉터리)

        GetComAsyncList getComAsyncList = new GetComAsyncList();
        List<String> comList = getComAsyncList.getComList();

        // TO-BE 경로: common/dao/business/standardInfo 등 구조 보존
        try (Stream<Path> files = Files.walk(Path.of(CREATE_ROOT))) {
            files.filter(p -> (Files.isRegularFile(p)
                        && (p.getFileName().toString().contains(".xfdl"))
                        && p.getFileName().toString().equals("pagingForm.xfdl")
                           //&& p.getFileName().toString().equals("OceanRouteFeeInvoiceDetailForm.xfdl")
//                            FileNm.TEST_FILE.startsWith(p.getFileName().toString().replace(".xml", ""))
//                            && FileNm.MY_CRM_PATH.stream().filter(file -> (file.startsWith(p.getFileName().toString().replace(".xfdl", "")))).collect(Collectors.toSet()).size() > 0
                )
            ).forEach(xfdl -> {
                processXfdl(xfdl, comList);
            });
        }
    }

    private static void processXfdl(Path xfdl, List<String> comList) {
        try {
            String code = new String(Files.readAllBytes(xfdl), StandardCharsets.UTF_8);
            String fileNm = xfdl.getFileName().toString();

            String xfdlCode = console(code,  comList, fileNm);

            Files.write(xfdl, xfdlCode.getBytes(StandardCharsets.UTF_8),
                    StandardOpenOption.CREATE,
                    StandardOpenOption.TRUNCATE_EXISTING);
        } catch (Exception e) {
            System.err.println("[FAIL] " + xfdl + " : " + e.getMessage());
            Arrays.stream(e.getStackTrace()).forEach(item -> System.out.println(item));
        }
    }

    private static String console(String code, List<String> comList, String fileNm) {
        String[] lines = code.split("\n");
        StringBuilder rtn = new StringBuilder();

        for(int i = 0; i < lines.length; i++) {
            String line = lines[i];


            Pattern p = Pattern.compile("(com\\.\\w+)");
            Matcher m = p.matcher(line);
            while(m.find()) {
                String com = m.group(1);
                List<String> findCom = comList.stream().filter(e -> com.equals(e)).collect(Collectors.toList());
                if(!findCom.isEmpty() && !line.contains("await")) {
                    if(com.equals("com.fnMessageOpenForm")) {
//                        if(line.contains("com.fnMessageOpenForm")
//                                && !line.contains("\"Q\"")
//                                && !line.contains("\"C\"")
//                                && !line.contains("\"Y\"")
//                                   && !line.contains("'Q'")
//                                   && !line.contains("'C'")
//                                   && !line.contains("'Y'")
//                        ) {
//                            continue;
//                        }
                    }

                    if(!line.trim().startsWith(com) && !line.trim().startsWith("//")){
                        if(!fileNm.isEmpty()) {
                            System.out.println("===========================================");
                            System.out.println(fileNm);
                            fileNm = "";
                        }
                        line = line.replace(com, "await " + com);
                        System.out.println("\t##  :: " + line);
                    }
                }
            }
            Pattern p2 = Pattern.compile("(Domain\\.\\w+.\\w+.\\w+)");
            Matcher m2 = p2.matcher(line);
            while (m2.find()) {
                String s = m2.group(1);
                if(!line.contains("\""+s + "\"")){
                    if(!fileNm.isEmpty()) {
//                        System.out.println("===========================================");
//                        System.out.println(fileNm);
                        fileNm = "";
                    }
//                    System.out.println("###"+line);
                }
            }

            if(line.trim().startsWith("com.fnAuthButtonControl")) {
                System.out.println("===========================================");
                System.out.println(fileNm);
                line = "//" + line;
            }

            rtn.append(line);
            if(lines.length-1 != i)
                rtn.append("\n");

        }
        return rtn.toString();
    }
}
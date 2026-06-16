// 파일명: DaoToMyBatisConverter.java


import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class NexacroComJSFindConverter {

    //private static final String CREATE_ROOT = "D:/Take/panoean/panocean/nexacro/biz";
    private static final String CREATE_ROOT = "D:/panocean/panocean-v2/nexacro/biz";


    public static void main(String[] args) throws IOException {
        // 변환 대상 프로젝트 목록 (폴더명, DAO 하위 디렉터리)
//        List<String[]> modules = getProjectNmList();
        String createFilePath = CREATE_ROOT + File.separator ;
//        for (String[] mod : modules) {
        AtomicInteger i  = new AtomicInteger();
        AtomicInteger i2 = new AtomicInteger();
        AtomicInteger i3 = new AtomicInteger();
        // TO-BE 경로: common/dao/business/standardInfo 등 구조 보존
        try (Stream<Path> files = Files.walk(Paths.get(createFilePath))) {
            files.filter(p -> Files.isRegularFile(p)
                    && p.getFileName().toString().endsWith(".xfdl")
                    && (    //p.getFileName().toString().contains("PortChargeTramperNewForm")
                                    FileNm.MY_PATH.stream().filter(file -> (
                                                file.startsWith(p.getFileName().toString().replace(".xfdl", ""))
                                        )
                                    ).collect(Collectors.toSet()).size() > 0

//                            && (p.getFileName().toString().endsWith("DAO.java")
//                            || (p.getFileName().toString().endsWith(".java") && p.getFileName().toString().toUpperCase().contains("DAO"))
//                    || p.getFileName().toString().endsWith("DTO.java")
//                    || p.getFileName().toString().endsWith("VO.java")
                    )
                    )
                    .forEach(dao -> {
                        processDao(dao, Paths.get(createFilePath), i, i2, i3);
                    });
        } catch (Exception e) {
            System.out.println(e.getMessage());
        }
        System.out.println("file :: "+i3+"\nfunction :: " + i + "\ncom :: " + i2);
//        }
    }

    // DAO 파일별 처리
    private static void processDao(Path dao, Path srcDir, AtomicInteger i, AtomicInteger i2, AtomicInteger i3) {
        try {
            String code      = new String(Files.readAllBytes(dao), StandardCharsets.UTF_8);
            String className = dao.getFileName().toString().replace(".xfdl","");

                        // ASIS 내 상대 경로 보존
//            String xml    =
            convert(code, className, i, i2, i3);


//            String mapperFile = className + ".java";
//            Path outFile = outDir.resolve(mapperFile);
//            Files.write(dao, xml.getBytes(StandardCharsets.UTF_8),
//                    StandardOpenOption.CREATE,
//                    StandardOpenOption.TRUNCATE_EXISTING);

            //Files.delete(dao);

//            Files.write(outDir, xml.getBytes(StandardCharsets.UTF_8),
//            StandardOpenOption.CREATE,
//            StandardOpenOption.TRUNCATE_EXISTING);
//
//            Files.delete(dao);



        } catch (Exception e) {
            System.err.println("[FAIL] " + dao + " : " + e.getMessage());
            Arrays.stream(e.getStackTrace()).forEach(item -> System.out.println(item));
        }
    }


    public static void convert(String code, String classNam,AtomicInteger i, AtomicInteger i2, AtomicInteger i3) {
        String[] lines = code.split("\n");

        Pattern p1 = Pattern.compile("\\s+(com\\.\\w+)");
        Matcher mm = p1.matcher(code);
        if(mm.find()) {
            i3.incrementAndGet();
        }

        Pattern p3 = Pattern.compile("\\s*this\\.(ed|me)_(\\w+)\\.value\\s*=\\s*\"\"");
        Matcher m3 = p3.matcher(code);

        while (m3.find()) {
            System.out.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! " + m3.group());
        }

        if(code.contains("com.")) {
            System.out.println("===============================================================");
            System.out.println(classNam);
            String function = "";
            for(String line : lines) {
                //Pattern p = Pattern.compile("\\s*this\\.\\w+\s*=\\s*(?:async)?\\s*function\\([^)]*\\)");
                Pattern p = Pattern.compile("\\s*this\\.(\\w+)\s*=\\s*(?:async)?\\s*function\\([^)]*\\)");
                Matcher m = p.matcher(line);

                while (m.find()) {
                    function = m.group(0);
                }

                Matcher m1 = p1.matcher(line);
                while(m1.find()){
                    String com = m1.group(0).trim();

                    if(com.equals("com.fnClose")
                               || com.equals("com.replace")
                               || com.equals("com.isEmpty")
                               || com.equals("com.setGridPositionXY")
                               || com.equals("com.length")
                               || com.equals("com.drawDetailGridBkColor")
                               || com.equals("com.somToday")
                               || com.equals("com.fnAuthButtonControl")
                               || com.equals("com.substr")
                               || com.equals("com.drawGridDisableColor")
                               || com.equals("com.isUpdateDataset")
                               || com.equals("com.G_OzDel")
                               || com.equals("com.OZVwMaker")
                               || com.equals("com.OZFormParamSet")
                               || com.equals("com.G_OzSplit")
                               || com.startsWith("//")
                    ) {
                        continue;
                    }


                    if(!function.isEmpty()) {
                        i.incrementAndGet();
                        System.out.println("    ## function::" + function);
                        function = "";
                    }
                    i2.incrementAndGet();
                    System.out.println("        com ::" + m1.group(0));
                }
            }
        }
    }

    public static String rTrim(String s) {
        return s.replaceAll("\\s+$", "");
    }

    public static String match(String line, Pattern pattern) {
        Matcher m = pattern.matcher(line);
        String rtnStr = "";
        while(m.find()) {
            m.group(0);
            rtnStr = m.group(1);
        }
        return rtnStr;
    }

    public static List<String> match2(String line, Pattern pattern) {
        Matcher m = pattern.matcher(line);

        List<String> l = new ArrayList<>();
        while(m.find()) {
            String rtnStr = m.group(1);
            String rtnStr2 = m.group(2);
            l.add(rtnStr);
            l.add(rtnStr2);
        }
        return l;
    }
}
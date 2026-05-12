// 파일명: DaoToMyBatisConverter.java


import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ParamMapConverter {

    // 1. AS-IS/TO-BE 루트 경로 설정 (필요에 맞게 수정)
//    private static final String ASIS_ROOT   = "D:/panocean/panocean-v2/src/main/java/com/pan/som/dao";
//    private static final String CREATE_ROOT = "D:/panocean/panocean-v2/src/main/java/kr/co/panocean/dao";
//    private static final String CREATE_ROOT = "D:/Take/panoean/panocean/src/main/java/kr/co/panocean/dao";

    private static final String CREATE_ROOT = "D:/panocean/panocean-v2/src/main/java/com/pan/som/dao";

    public static void main(String[] args) throws IOException {
        // 변환 대상 프로젝트 목록 (폴더명, DAO 하위 디렉터리)
        String createFilePath = CREATE_ROOT + File.separator;
        Path srcDir = Paths.get(createFilePath);

        // TO-BE 경로: common/dao/business/standardInfo 등 구조 보존
        try (Stream<Path> files = Files.walk(srcDir)) {
            files.filter(p -> (Files.isRegularFile(p)
                            && (p.getFileName().toString().toUpperCase().contains("DAO")
                                && p.getFileName().toString().endsWith(".java")
                    ))
//                                || p.getParent().getFileName().startsWith("invoice")
//                        && p.getFileName().toString().equals("CourtPermitAppDAO.java")
            ).forEach(dao -> {
                processDao(dao, srcDir, Paths.get(createFilePath));
            });
        } catch (Exception e) {
            System.out.println(e.getMessage());
        }

    }

    // DAO 파일별 처리
    private static void processDao(Path dao, Path srcDir, Path dstRoot) {
        try {
            String code = new String(Files.readAllBytes(dao), StandardCharsets.UTF_8);
            String className = dao.getFileName().toString().replace(".java", "");
            if (!code.contains("new HashMap") && !code.contains("listMap")) return;

            // ASIS 내 상대 경로 보존
            Path outDir = dao;

            Pattern p = Pattern.compile("\\s+put\\(\"\\w+\"\\s*,\\s*[^)]*\\);");
            Matcher m = p.matcher(code);
            if(m.find()) {
                String xml = convert(code, className, srcDir.toString(), outDir.toString());
                Files.createDirectories(outDir.getParent());

                Files.write(outDir, xml.getBytes(StandardCharsets.UTF_8),
                        StandardOpenOption.CREATE,
                        StandardOpenOption.TRUNCATE_EXISTING);
                System.out.println("전환 완료[ " + outDir.toString() + "]");
            }
//
//            Files.delete(dao);

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


    public static String convert(String code, String classNam, String srcDir, String outDir) {
        String[] lines = code.split("\n");
        StringBuilder out = new StringBuilder();
        boolean isParam = false;
        boolean isFor = false;
        String uxbMap = "";
        int publicIdx = 0;
        int putCnt = 0;
        String strParamNm = "";
        String tap = "";
        int endIf = 0;

        for (int i = 0; i < lines.length; i++) {
            String line = lines[i];

            if ((line.contains("public ") || line.contains("private ")) && line.contains("(")) {
                publicIdx = 0;
                putCnt = 0;
                if (lines[i + 1].trim().isEmpty()) {
                    out.append(line).append("\n");
                    i++;
                    continue;
                }
            }

            if (isFor) {
                if (endIf == 0 && line.contains("}")) {
                    isFor = false;
                    out.append("\t").append(line).append("\n");
                } else {
                    if (line.contains("{")) {
                        endIf++;
                    }

                    if (line.contains("}")) {
                        endIf--;
                    }
                }
            }

            if (line.contains("for") && line.contains("map") && line.contains("Map<String") && line.contains("listMap")) {
                if (!lines[i - 1].contains("listMap") && !lines[i - 1].contains("!= null")) {
                    isFor = true;
                    String listMapNm = line.substring(line.indexOf(":") + 1, line.indexOf(")")).trim();
                    out.append("        ").append("if(").append(listMapNm).append(" != null && !").append(listMapNm).append(".isEmpty()) {\n");
                }
            }


            if (line.contains("uxbDAO") && line.contains("new HashMap")) {
                tap = "";
                if (publicIdx == 0) {
                    strParamNm = "paramMap";
                } else {
                    strParamNm = "paramMap" + publicIdx;
                }
                publicIdx++;

                uxbMap = line.split("\",")[0] + "\", " + strParamNm + ");";
                isParam = true;
            }

            if (isParam) {
                if (line.contains("}});")) {
                    isParam = false;
                    if (putCnt == 0) {
                        uxbMap = uxbMap.replace(strParamNm, "null");
                    }
                    out.append("\n").append(uxbMap).append("\n");
                } else if (line.contains("put")) {
                    if (tap.isEmpty()) {
                        int k = 0;
                        while (k < uxbMap.length()) {
                            char c = uxbMap.charAt(k);
                            if (c != ' ' && c != '\t') {
                                break;
                            }
                            k++;
                        }
                        tap = uxbMap.substring(0, k);
                        out.append("\n").append(tap).append("Map<String, Object> ").append(strParamNm).append(" = new HashMap<>();\n");
                    }
                    out.append(tap).append(strParamNm).append(".").append(line.trim()).append("\n");
                    putCnt++;
                }
            } else {
                out.append(getForTap(endIf, isFor)).append(line).append("\n");
            }
        }
        return out.toString();
    }

    public static String getForTap(int cnt, boolean isFor) {
        StringBuilder tap = new StringBuilder();
        for (int i = 0; i < cnt; i++) {
            tap.append("\t");
        }
        if (isFor) {
            tap.append("\t");
        }
        return tap.toString();
    }
}
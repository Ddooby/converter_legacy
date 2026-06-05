package kr.co.generate;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.*;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

/**
 * Controller URL 소문자로 변경
 * ※ 2번까지 수정하고 마지막에 돌려야함
 */
public class ServletConverter04 {

    public static void main(String[] args) throws IOException {
        // 하드코딩 된 입력/출력 폴더 경로
        String inputRootStr = "C:\\take\\panocean\\src\\main\\java\\kr\\co\\panocean\\controller\\insLeg";
        String outputRootStr = "C:\\take\\panocean\\src\\main\\java\\kr\\co\\panocean\\controller\\insLeg";

        Path inputRoot = Paths.get(inputRootStr);
        Path outputRoot = Paths.get(outputRootStr);

        if (!Files.isDirectory(inputRoot)) {
            System.err.println("Input root path is not a directory: " + inputRootStr);
            System.exit(1);
        }
        if (!Files.exists(outputRoot)) {
            Files.createDirectories(outputRoot);
        }

        System.out.println("Start processing...");
        try (Stream<Path> files = Files.walk(inputRoot)) {
            files.filter(path -> path.toString().endsWith(".java"))
                    .filter(path -> path.getFileName().toString().contains("Controller"))
                    .forEach(javaFilePath -> processJavaFile(javaFilePath, inputRoot, outputRoot));
        }
        System.out.println("Processing completed.");
    }

    private static void processJavaFile(Path javaFilePath, Path inputRoot, Path outputRoot) {
        try {
            String code = new String(Files.readAllBytes(javaFilePath), StandardCharsets.UTF_8);
            CompilationUnit cu = StaticJavaParser.parse(code);
            boolean modified = false;

            List<MethodDeclaration> methods = cu.findAll(MethodDeclaration.class);
            for (MethodDeclaration method : methods) {
                // 메서드명 카멜케이스 변환
                String oldMethodName = method.getNameAsString();
                String newMethodName = toCamelCaseIfNeeded(oldMethodName);
                if (!oldMethodName.equals(newMethodName)) {
                    method.setName(newMethodName);
                    modified = true;
                }

                // @RequestMapping 어노테이션 URL 변환
                List<AnnotationExpr> annotations = method.getAnnotations();
                for (AnnotationExpr anno : annotations) {
                    if ("RequestMapping".equals(anno.getNameAsString())) {
                        Optional<String> optUrl = extractRequestMappingValue(anno);
                        if (optUrl.isPresent()) {
                            String oldUrl = optUrl.get();
                            String newUrl = convertUrlToCamelCase(oldUrl);
                            if (!oldUrl.equals(newUrl)) {
                                replaceRequestMappingValue(anno, newUrl);
                                modified = true;
                            }
                        }
                    }
                }
            }

            // 출력 경로 설정 (원본 기준 상대 경로 유지)
            Path relativePath = inputRoot.relativize(javaFilePath);
            Path outputFilePath = outputRoot.resolve(relativePath);

            if (!Files.exists(outputFilePath.getParent())) {
                Files.createDirectories(outputFilePath.getParent());
            }

            // 변경되지 않아도 모든 파일을 출력 폴더에 저장 (필요시 변경 가능)
            Files.write(outputFilePath, cu.toString().getBytes(StandardCharsets.UTF_8));

            System.out.println("Processed and saved: " + outputFilePath);

        } catch (Exception e) {
            // 오류 시 스택트레이스 대신 파일명만 출력
            System.err.println("Error processing file: " + javaFilePath.toString());
            // 필요시 아래 줄 주석 해제하여 상세 에러메세지 출력 가능
            // System.err.println("Error message: " + e.getMessage());
        }
    }

    private static boolean isCamelCase(String s) {
        if (s == null || s.isEmpty()) return false;
        if (s.contains("_") || s.contains("-")) return false;
        if (!Character.isLowerCase(s.charAt(0))) return false;

        for (int i = 1; i < s.length(); i++) {
            if (Character.isUpperCase(s.charAt(i))) {
                return true;
            }
        }
        return false;
    }

    // 카멜케이스가 아니면 변환 (스네이크케이스 → camelCase, 단어 없는 경우 소문자 변환)
    private static String toCamelCaseIfNeeded(String str) {
        if (str == null || str.isEmpty()) return str;

        if (isCamelCase(str)) {
            return str;
        }

        String[] parts = str.split("[_-]");
        if (parts.length == 1) {
            return str.toLowerCase();
        }

        StringBuilder sb = new StringBuilder();
        sb.append(parts[0].toLowerCase());

        for (int i = 1; i < parts.length; i++) {
            String p = parts[i].toLowerCase();
            if (p.length() > 0) {
                sb.append(Character.toUpperCase(p.charAt(0)));
                if (p.length() > 1) {
                    sb.append(p.substring(1));
                }
            }
        }
        return sb.toString();
    }

    // @RequestMapping 애노테이션 내 URL 문자열 추출
    private static Optional<String> extractRequestMappingValue(AnnotationExpr annotation) {
        if (annotation instanceof SingleMemberAnnotationExpr) {
            SingleMemberAnnotationExpr sma = (SingleMemberAnnotationExpr) annotation;
            if (sma.getMemberValue() instanceof StringLiteralExpr) {
                return Optional.of(((StringLiteralExpr) sma.getMemberValue()).getValue());
            }
        } else if (annotation instanceof NormalAnnotationExpr) {
            NormalAnnotationExpr na = (NormalAnnotationExpr) annotation;
            for (MemberValuePair pair : na.getPairs()) {
                if ("value".equals(pair.getNameAsString()) && pair.getValue() instanceof StringLiteralExpr) {
                    return Optional.of(((StringLiteralExpr) pair.getValue()).getValue());
                }
            }
        }
        return Optional.empty();
    }

    // @RequestMapping 애노테이션 내 URL 문자열 변경
    private static void replaceRequestMappingValue(AnnotationExpr annotation, String newValue) {
        if (annotation instanceof SingleMemberAnnotationExpr) {
            ((SingleMemberAnnotationExpr) annotation).setMemberValue(new StringLiteralExpr(newValue));
        } else if (annotation instanceof NormalAnnotationExpr) {
            NormalAnnotationExpr na = (NormalAnnotationExpr) annotation;
            for (MemberValuePair pair : na.getPairs()) {
                if ("value".equals(pair.getNameAsString())) {
                    pair.setValue(new StringLiteralExpr(newValue));
                    return;
                }
            }
            na.addPair("value", new StringLiteralExpr(newValue));
        }
    }

    // URL을 경로 별로 나누어 각 부분을 camelCase로 변환 (확장자 유지)
    private static String convertUrlToCamelCase(String url) {
        if (url == null || url.isEmpty()) return url;

        String ext = "";
        String body = url;

        int idx = url.lastIndexOf('.');
        if (idx != -1) {
            body = url.substring(0, idx);
            ext = url.substring(idx);
        }

        String[] parts = body.split("/");
        for (int i = 0; i < parts.length; i++) {
            parts[i] = toCamelCaseIfNeeded(parts[i]);
        }

        return String.join("/", parts) + ext;
    }
}
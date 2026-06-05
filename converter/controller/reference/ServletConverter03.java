package kr.co.generate;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.ImportDeclaration;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.MethodCallExpr;

import java.io.File;
import java.io.FileInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;

/**
 * 빈껍데기 Service 클래스 생성
 */
public class ServletConverter03 {

    private static final String INPUT_DIR = "C:/take/file/output3"; //변환된 controller파일
    private static final String OUTPUT_DIR = "C:/take/panocean/src/main/java/kr/co/panocean/service/bunkerSupply/";
    private static final Set<String> JAVA_LANG = new HashSet<>(Arrays.asList(
            "String", "Integer", "Long", "Boolean", "Double", "Float", "Character", "Short", "Byte", "Void", "Object"
    ));

    public static void main(String[] args) throws Exception {
        File inputDir = new File(INPUT_DIR);
        File[] files = inputDir.listFiles((dir, name) -> name.endsWith("Controller.java"));
        if (files == null || files.length == 0) {
            System.err.println("❌ No controller files found in " + INPUT_DIR);
            return;
        }

        for (File file : files) {
            convert(file);
        }
    }

    private static void convert(File controllerFile) throws Exception {

        CompilationUnit cu;
        try (FileInputStream fis = new FileInputStream(controllerFile)) {
            JavaParser parser = new JavaParser();
            ParseResult<CompilationUnit> result = parser.parse(fis);
            if (result.getResult() == null) {
                System.err.println("❌ Failed to parse " + controllerFile.getName());
                return;
            }
            cu = result.getResult().get();
        }

        String controllerName = controllerFile.getName().replace(".java", "");
        String baseName = controllerName.replace("Controller", "");
        String serviceClassName = baseName + "Service";

        Set<String> importSet = new TreeSet<>();
        Map<String, String> methodMap = new LinkedHashMap<>();

        Map<String, String> localTypeImportCache = extractImports(cu);

        List<MethodDeclaration> methods = cu.findAll(MethodDeclaration.class);

        for (MethodDeclaration method : methods) {
            method.findAll(MethodCallExpr.class).forEach(call -> {
                if (call.getScope().isPresent() && call.getScope().get().isNameExpr()) {
                    String serviceRef = call.getScope().get().asNameExpr().getNameAsString().toLowerCase();
                    if (serviceRef.contains("service")) {
                        String methodName = call.getNameAsString();
                        List<String> paramDecls = new ArrayList<>();
                        Set<String> usedNames = new HashSet<>();
                        int index = 1;

                        for (Expression arg : call.getArguments()) {
                            String[] resolved = inferParam(arg, method, usedNames, index++);
                            String typeName = resolved[0];
                            String shortType = getSimpleTypeName(typeName);

                            if (!JAVA_LANG.contains(shortType)) {
                                if (localTypeImportCache.containsKey(shortType)) {
                                    importSet.add(localTypeImportCache.get(shortType));
                                } else if (shortType.contains(".")) {
                                    importSet.add(typeName);
                                } else if (shortType.endsWith("DTO") || shortType.endsWith("VO")) {
                                    importSet.add("com.pan.som.common.dto." + shortType);
                                }
                            }

                            paramDecls.add(shortType + " " + resolved[1]);
                            usedNames.add(resolved[1]);
                        }

                        String returnType = inferReturnType(call, localTypeImportCache);
                        String shortType = getSimpleTypeName(returnType);
                        if (!JAVA_LANG.contains(shortType)) {
                            if (localTypeImportCache.containsKey(shortType)) importSet.add(localTypeImportCache.get(shortType));
                            else if (shortType.contains(".")) importSet.add(returnType);
                            else if (shortType.endsWith("DTO") || shortType.endsWith("VO")) {
                                importSet.add("com.pan.som.common.dto." + shortType);
                            }
                        }

                        String key = methodName + "#" + String.join(",", paramDecls);
                        String signature = "public " + returnType + " " + methodName + "("
                                + String.join(", ", paramDecls) + ") {\n"
                                + "        // TODO: Implement\n"
                                + (returnType.equals("void") ? "" : "        return null;\n")
                                + "    }\n";

                        methodMap.putIfAbsent(key, signature);
                    }
                }
            });
        }

        // ✅ 항상 포함할 Import
        importSet.add("org.springframework.stereotype.Service");
        importSet.add("lombok.extern.slf4j.Slf4j");
        importSet.add("java.util.Collection");
        importSet.add("java.util.HashMap");

        // ✅ 최종 파일 생성
        StringBuilder source = new StringBuilder();
        source.append("package com.pan.som.service.bunkerSupply;\n\n");
        for (String imp : importSet) source.append("import ").append(imp).append(";\n");

        source.append("\n@Service\n");
        source.append("@Slf4j\n");
        source.append("public class ").append(serviceClassName).append(" {\n\n");

        for (String m : methodMap.values()) {
            source.append("    ").append(m).append("\n");
        }

        source.append("}\n");

        Files.createDirectories(Paths.get(OUTPUT_DIR));
        Path outputPath = Paths.get(OUTPUT_DIR, serviceClassName + ".java");
        Files.write(outputPath, source.toString().getBytes());
        System.out.println("✅ " + outputPath + " 생성됨");
    }

    private static String[] inferParam(Expression expr, MethodDeclaration contextMethod, Set<String> usedNames, int idx) {
        String paramType = "Object";
        String paramName = "param" + idx;

        if (expr.isNameExpr()) {
            String varName = expr.asNameExpr().getNameAsString();
            for (Parameter param : contextMethod.getParameters()) {
                if (param.getNameAsString().equals(varName)) {
                    paramType = param.getTypeAsString();
                    paramName = varName;
                    break;
                }
            }

            List<VariableDeclarator> vars = contextMethod.findAll(VariableDeclarator.class);
            for (VariableDeclarator var : vars) {
                if (var.getNameAsString().equals(varName)) {
                    paramType = var.getTypeAsString();
                    paramName = varName;
                    break;
                }
            }

            if (usedNames.contains(paramName)) paramName = "param" + idx;
            return new String[]{paramType, paramName};
        }

        if (expr.isStringLiteralExpr()) return new String[]{"String", "value" + idx};
        if (expr.isIntegerLiteralExpr()) return new String[]{"int", "value" + idx};
        if (expr.isBooleanLiteralExpr()) return new String[]{"boolean", "value" + idx};

        return new String[]{paramType, paramName};
    }

    private static String inferReturnType(MethodCallExpr call, Map<String, String> importMap) {
        Optional<Node> parent = call.getParentNode();
        if (parent.isPresent() && parent.get() instanceof VariableDeclarator) {
            return ((VariableDeclarator) parent.get()).getTypeAsString();
        }
        String methodName = call.getNameAsString().toLowerCase();
        if (methodName.contains("search")) return "Collection";
        if (methodName.contains("onload")) return "HashMap";
        if (methodName.contains("account")) return "HashMap";
        if (methodName.contains("mail")) return "String";
        if (methodName.contains("list")) return "Collection";
        return "Collection";
    }

    private static String getSimpleTypeName(String fullType) {
        if (fullType == null) return "Object";
        int idx = fullType.lastIndexOf(".");
        return (idx == -1) ? fullType : fullType.substring(idx + 1);
    }

    private static Map<String, String> extractImports(CompilationUnit cu) {
        Map<String, String> result = new HashMap<>();
        if (cu.getImports() != null) {
            for (ImportDeclaration imp : cu.getImports()) {
                String impStr = imp.getNameAsString();
                if (impStr.endsWith(".*")) continue;
                String[] tokens = impStr.split("\\.");
                result.put(tokens[tokens.length - 1], impStr);
            }
        }
        return result;
    }
}

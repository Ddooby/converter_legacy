package kr.co.generate;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.*;
import com.github.javaparser.ast.stmt.ExpressionStmt;
import com.github.javaparser.ast.stmt.Statement;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/**
 * ############# Servlet -> Controller 변환 (2차) #############
 * EJB Home/Remote 제거 → service 호출로 변경
 * ※ 안 되는 경우 있음. 그런 경우 1차 파일 이용하여 수정
 */
public class ServletConverter02 {
    public static void main(String[] args) throws Exception {
        String inputDir = "C:/take/file/output";
        String outputDir = "C:/take/file/output2";
        //String outputDir = "C:/take/panocean/src/main/java/kr/co/panocean/controller/bunkerDetective/";

        File folder = new File(inputDir);
        for (File file : Objects.requireNonNull(folder.listFiles((d, name) -> name.endsWith(".java")))) {
            CompilationUnit cu = new JavaParser().parse(file).getResult().orElse(null);
            if (cu == null) continue;

            for (MethodDeclaration method : cu.findAll(MethodDeclaration.class)) {
                Set<String> homeVars = new HashSet<>();
                Set<String> remoteVars = new HashSet<>();
                Set<String> remoteCandidates = new HashSet<>();
                Set<String> deleteVars = new HashSet<>();
                Set<Statement> toRemove = new HashSet<>();

                // 1. Home 객체 추적: lookUpHome을 통해 생성된 모든 변수명 수집
                for (VariableDeclarationExpr v : method.findAll(VariableDeclarationExpr.class)) {
                    for (VariableDeclarator var : v.getVariables()) {
                        if (var.getInitializer().isPresent()) {
                            Expression init = var.getInitializer().get();
                            if (init.isCastExpr()) init = init.asCastExpr().getExpression();
                            if (init.isMethodCallExpr()) {
                                MethodCallExpr mc = init.asMethodCallExpr();
                                if (mc.getNameAsString().equals("lookUpHome") &&
                                        mc.getScope().isPresent() &&
                                        mc.getScope().get().isMethodCallExpr() &&
                                        mc.getScope().get().asMethodCallExpr().getNameAsString().equals("getInstance")) {
                                    homeVars.add(var.getNameAsString());
                                    deleteVars.add(var.getNameAsString());
                                }
                            }
                        }
                    }
                }

                // 2. Remote 후보: 선언만 있는 변수도 후보로 등록 (타입명과 무관하게 모든 변수)
                for (VariableDeclarationExpr v : method.findAll(VariableDeclarationExpr.class)) {
                    for (VariableDeclarator var : v.getVariables()) {
                        remoteCandidates.add(var.getNameAsString());
                    }
                }

                // 3. Remote 객체 반복 추적 (선언/대입 분리, 복사, 여러 번 대입 모두)
                boolean changed;
                do {
                    changed = false;
                    List<ExpressionStmt> stmts = method.findAll(ExpressionStmt.class);
                    for (ExpressionStmt stmt : stmts) {
                        // 선언+대입
                        if (stmt.getExpression().isVariableDeclarationExpr()) {
                            VariableDeclarationExpr v = stmt.getExpression().asVariableDeclarationExpr();
                            for (VariableDeclarator var : v.getVariables()) {
                                if (var.getInitializer().isPresent()) {
                                    Expression init = var.getInitializer().get();
                                    if (init.isCastExpr()) init = init.asCastExpr().getExpression();
                                    // HomeVar.create()
                                    if (init.isMethodCallExpr()) {
                                        MethodCallExpr mc = init.asMethodCallExpr();
                                        if (mc.getNameAsString().equals("create") && mc.getScope().isPresent()) {
                                            String homeVar = mc.getScope().get().toString();
                                            if (homeVars.contains(homeVar)) {
                                                if (remoteVars.add(var.getNameAsString())) changed = true;
                                                deleteVars.add(var.getNameAsString());
                                            }
                                        }
                                    }
                                    // Remote→Remote 대입
                                    else if (init.isNameExpr() && remoteVars.contains(init.toString())) {
                                        if (remoteVars.add(var.getNameAsString())) changed = true;
                                        deleteVars.add(var.getNameAsString());
                                    }
                                }
                            }
                        }
                        // 대입문
                        else if (stmt.getExpression().isAssignExpr()) {
                            AssignExpr assign = stmt.getExpression().asAssignExpr();
                            String targetVar = assign.getTarget().toString();
                            Expression value = assign.getValue();
                            if (value.isCastExpr()) value = value.asCastExpr().getExpression();
                            // HomeVar.create()
                            if (value.isMethodCallExpr()) {
                                MethodCallExpr mc = value.asMethodCallExpr();
                                if (mc.getNameAsString().equals("create") && mc.getScope().isPresent()) {
                                    String homeVar = mc.getScope().get().toString();
                                    if (homeVars.contains(homeVar)) {
                                        if (remoteVars.add(targetVar)) changed = true;
                                        deleteVars.add(targetVar);
                                    }
                                }
                            }
                            // Remote→Remote 대입
                            else if (value.isNameExpr() && remoteVars.contains(value.toString())) {
                                if (remoteVars.add(targetVar)) changed = true;
                                deleteVars.add(targetVar);
                            }
                        }
                    }
                } while (changed);

                // 4. Remote/Home 변수의 선언만 있는 줄도 삭제 후보에 추가
                for (VariableDeclarationExpr v : method.findAll(VariableDeclarationExpr.class)) {
                    for (VariableDeclarator var : v.getVariables()) {
                        if (remoteVars.contains(var.getNameAsString()) || homeVars.contains(var.getNameAsString())) {
                            deleteVars.add(var.getNameAsString());
                        }
                    }
                }

                // 5. 비즈니스 호출 치환 (remoteVar.메서드() → service.메서드())
                for (MethodCallExpr mc : method.findAll(MethodCallExpr.class)) {
                    if (mc.getScope().isPresent()) {
                        Expression scope = mc.getScope().get();
                        if (remoteVars.contains(scope.toString())) {
                            mc.setScope(new NameExpr("service"));
                        }
                    }
                }

                // 6. Home/Remote 선언문 및 대입문 삭제 (deleteVars에 포함된 변수명 줄 전체)
                for (ExpressionStmt stmt : method.findAll(ExpressionStmt.class)) {
                    boolean remove = false;
                    // 선언문
                    if (stmt.getExpression().isVariableDeclarationExpr()) {
                        VariableDeclarationExpr v = stmt.getExpression().asVariableDeclarationExpr();
                        for (VariableDeclarator var : v.getVariables()) {
                            if (deleteVars.contains(var.getNameAsString())) {
                                remove = true;
                            }
                        }
                    }
                    // 대입문
                    else if (stmt.getExpression().isAssignExpr()) {
                        AssignExpr assign = stmt.getExpression().asAssignExpr();
                        if (deleteVars.contains(assign.getTarget().toString())) {
                            remove = true;
                        }
                    }
                    if (remove) toRemove.add(stmt);
                }
                for (Statement stmt : toRemove) {
                    stmt.remove();
                }
            }

            // 저장 위치: outputDir에 동일 파일명으로 저장
            File outFile = new File(outputDir, file.getName());
            Files.write(Paths.get(outFile.getAbsolutePath()), cu.toString().getBytes(StandardCharsets.UTF_8));
            System.out.println(file.getName() + " 변환 완료 → " + outFile.getAbsolutePath());
        }
        System.out.println("EJB 패턴 변환(커스텀 AST 완전판) 완료.");
    }
}
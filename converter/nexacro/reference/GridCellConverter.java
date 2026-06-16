

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

public class GridCellConverter {

	// 1. AS-IS/TO-BE 루트 경로 설정 (필요에 맞게 수정)
	private static final String ASIS_ROOT = "C:/AdvDevEnv/som_workspace/SOM_XInternet/";
	//private static final String CREATE_ROOT = "D:/panocean/somcrm/nexacro/biz/";
	private static final String CREATE_ROOT = "C:/Projects/somlawsvn/nexacro/biz/";


	private static final boolean All_SYS = false;
	private static final boolean TEST_SYS = true;


	public static void main(String[] args) throws IOException {
		// 변환 대상 프로젝트 목록 (폴더명, DAO 하위 디렉터리)

		Path srcDir = Paths.get(ASIS_ROOT);
		AtomicInteger projectCnt = new AtomicInteger();

		AtomicInteger i = new AtomicInteger();
		AtomicInteger i2 = new AtomicInteger();
		AtomicInteger i3 = new AtomicInteger();


		// TO-BE 경로: common/dao/business/standardInfo 등 구조 보존
		try (Stream<Path> files = Files.walk(srcDir)) {
			files.filter(p -> (Files.isRegularFile(p)
					                   && (p.getFileName().toString().contains(".xml"))
					                   && (
							(FileNm.ALL_LAW_FULL_PATH.stream().filter(file -> (
											p.toString().contains(file)
									)
							).collect(Collectors.toSet()).size() > 0)
					))
			).forEach(xfdl -> {
				projectCnt.getAndIncrement();
				i2.incrementAndGet();
				processXfdl(xfdl, i, i3);
			});
		}
		System.out.println("전체 파일 :: " + i2 + " ::  없는 파일 :: " + i + " ::: " + i3);
	}

	private static Path getToBePath(Path asisPath) {
		String asisStr = asisPath.getParent().toString().replace(ASIS_ROOT.replace("/", "\\"), CREATE_ROOT);
		String fileNm = asisPath.getFileName().toString().replace("xml", "xfdl");
		String asisParent = asisPath.getParent().getFileName().toString();
		if (asisParent.contains("standardInfo_trsact_codeManagement")) {
			asisStr = (asisPath.getParent().getParent().toString() + File.separator).replace(ASIS_ROOT.replace("/", "\\") + File.separator, CREATE_ROOT).replace("_", "/")
					          + "standardInfo/trsact_codeManagement";
			System.out.println(":: " + (asisPath.getParent().getParent().toString() + File.separator).replace(ASIS_ROOT.replace("/", "\\"), CREATE_ROOT));
		} else {
			asisStr = asisStr.replace("_", "/");
		}

		if (fileNm.equals("trsactCodeListForm.xfdl")) {
			asisStr = "D:/panocean/sombas/sombas/nexacro/biz/standardInfo/trsact_codeManagement";
		}
		return Paths.get(asisStr + File.separator + fileNm);
	}

	private static void processXfdl(Path xfdl, AtomicInteger i, AtomicInteger i3) {
		try {
			Path tobePath = getToBePath(xfdl);

			if (!Files.exists(tobePath)) {
				System.out.println("tobePath :: " + tobePath);
				i.incrementAndGet();
				return;
			}
//            if(1==1){
//                return;
//            }


			String codeAsis = new String(Files.readAllBytes(xfdl), StandardCharsets.UTF_8);
			String codeTobe = new String(Files.readAllBytes(tobePath), StandardCharsets.UTF_8);
			if (!codeTobe.contains("<Grid")) return;
			String fileNm = xfdl.getFileName().toString().replace(".xml", "");
			Path outDir = tobePath.getParent();
			String xml = "";

			if (isGridCss(codeAsis)) {
				i3.incrementAndGet();
				xml = convertGrid(codeTobe, codeAsis, fileNm);
				if (All_SYS)
					System.out.println(xfdl);
			} else {
				xml = convert(codeTobe, codeAsis);
				if (All_SYS)
					System.out.println(":xxxxxxx:" + xfdl);
			}

			//왜 파일이 같은데 왜
			if (xml.length() == codeTobe.length() || xml.length() == (codeTobe.length() - 1)) {
				return;
			}

			Files.createDirectories(outDir);

			Path outFile = outDir.resolve(fileNm + ".xfdl");

			Files.write(outFile, xml.getBytes(StandardCharsets.UTF_8),
					StandardOpenOption.CREATE,
					StandardOpenOption.TRUNCATE_EXISTING);
		} catch (Exception e) {
			System.err.println("[FAIL] " + xfdl + " : " + e.getMessage());
			Arrays.stream(e.getStackTrace()).forEach(item -> System.out.println(item));
		}
	}

	private static String convert(String codeTobe, String codeAsis) {
		StringBuilder rtn = new StringBuilder();
		String[] lines = codeTobe.split("\n");
		for (int i = 0; i < lines.length; i++) {
			String line = lines[i];
			line = commonConvert(line);
			rtn.append(line);
			rtn.append("\n");
//            if (i != (lines.length - 1)) {
//                rtn.append("\n");
//            }
		}
		return rtn.toString();
	}

	private static boolean isGridCss(String code) {
		String[] lines = code.split("\n");
		for (String line : lines) {
			line = line.trim();
			if (line.equals("g_drawGridDisableColor();")
					    || line.startsWith("g_drawGridDisableColor_forGrid(")
					    || line.equals("g_drawGridDisableColor_forTab();")) {
				return true;
			}
		}
		return false;
	}

	private static String convertGrid(String code, String asisCode, String fileNm) {
		String[] lines = code.split("\n");
		String[] lineAs = asisCode.split("\n");
		List<Map<String, String>> gridList = new ArrayList<>();
		List<String[]> gridList2 = new ArrayList<>();

		Pattern p = Pattern.compile("\\s*<Grid.*BindDataset=\"(\\w+)\".*Id\\=\"(\\w+)\".*Style=\"(\\w+)\"");
		Matcher m = p.matcher(asisCode);
//<Grid\s+.*bindDataset="(\w+)".*\s+id="(\w+)"
		while (m.find()) {
			String bind = m.group(1);
			String id = m.group(2);
			String style = m.group(3);
			gridList.add(new HashMap<String, String>() {{
				put(id, style);
			}});
			gridList2.add(new String[]{bind, id, style});
		}


		List<Map<String, String>> uniqueList = gridList.stream()
				                                       .distinct() // Map 자체가 equals/hashCode 기반으로 중복 제거
				                                       .collect(Collectors.toList());

		List<String[]> uniqueList2 = gridList2.stream()
				                             .collect(Collectors.collectingAndThen(
						                             Collectors.toCollection(() -> new TreeSet<>(Comparator.comparing(arr -> Arrays.toString(arr)))),
						                             ArrayList::new
				                             ));

		List<String> gridCssFun = new ArrayList<>();
		for (String line : lineAs) {
			line = line.trim();
			if (!line.isEmpty()) {
				if (line.startsWith("//")) continue;
			}
			if (line.startsWith("g_drawGridDisableColor()")) {
				gridCssFun.add("\tcom.drawGridDisableColor(this);");
				continue;
			}
			if (line.startsWith("g_drawGridDisableColor_forGrid(")) {
				line = line.replace("g_drawGridDisableColor_forGrid(", "com.drawGridDisableColorForGrid(this.");
				gridCssFun.add("\t" + line);
				continue;
			}
			if (line.startsWith("g_drawGridDisableColor_forTab()")) {
				line = line.replace("g_drawGridDisableColor_forTab()", "com.drawGridDisableColorForTab(this)");
				gridCssFun.add("\t" + line);
			}
		}
		boolean isCssFun = !gridCssFun.isEmpty();
		for (int i = 0; i < lines.length; i++) {
			String line = lines[i].trim();
			for (String cssFun : gridCssFun) {
				if (line.equals(cssFun)) {
					gridCssFun.remove(cssFun);
				}
			}
		}

		if (code.contains("<Tab ")) {
			System.out.println(fileNm);
		}

		StringBuilder rtn = new StringBuilder();
		for (int i = 0; i < lines.length; i++) {
			String line = lines[i];

			if (line.contains("this.fnInit =")) {
				if (isCssFun) {
					rtn.append(line).append("\n");
					if (lines[i + 1].trim().equals("{")) {
						rtn.append(lines[i + 1]).append("\n");
						i++;
					}
					for (String cssFun : gridCssFun) {
						if (cssFun != null) {
							if (!rtn.toString().contains(cssFun)) {
								rtn.append(cssFun).append("\n");
							}
						}
						if (All_SYS)
							System.out.println("cssFun :: " + cssFun);
					}
					continue;
				}
			}
			if (line.contains("<Grid")) {
				for (int j = 0; j < uniqueList2.size(); j++) {
					String[] arrStr = uniqueList2.get(j);
					//for(Map<String, String> map : uniqueList) {
					String bind = arrStr[0];
					String id = arrStr[1];
					String style = arrStr[2];
					if (line.contains("\"" + bind + "\"") && line.contains("\"" + id + "\"")) {
						if (line.contains("cssclass=")) {
							line = line.replace("cssclass=\"", "cssclass=\"" + style + "+&quot;,&quot;+");
						} else {
							line = line.replace("\">", "\" cssclass=\"" + style + "\">");
						}
						if (All_SYS)
							System.out.println("[" + style + "]gridCss :: " + line);
						break;
					} else if (!code.contains("\"" + id + "\"")) {
						if (line.contains("cssclass=")) {
							line = line.replace("cssclass=\"", "cssclass=\"" + style + "+&quot;,&quot;+");
						} else {
							line = line.replace("\">", "\" cssclass=\"" + style + "\">");
						}
					}


				}
			}
			line = commonConvert(line);
			rtn.append(line);
			rtn.append("\n");
//            if(i != lines.length-1) {
//            }
		}
		return rtn.toString();
	}

	public static String commonConvert(String line) {
		if (!line.contains("<Cell")) return line;

		Pattern cssClass = Pattern.compile("\\s*<Cell.*background=\"([^\"]*)\"");
		Pattern colorClass = Pattern.compile("\\s*<Cell.* color=\"([^\"]*)\"");

		//drawDetailGridBkColor drawDetailGridDisableColor
		line = line.replace("EXPR", "expr:");
		if (line.contains("expr:(/*[AIChanger] com.drawDetailGridBkColor") || line.contains("expr:(/*[AIChanger] com.drawDetailGridDisableColor")) {
			line = line.replace("/*[AIChanger] ", "")
					       .replace(" 사용 불가 background expr로 처리 필요*/ //", "")
					       .replace(" 사용 불가 cssclass expr로 처리 필요*/ //", "");
			line = cssclassConvert(line, cssClass, " background");
			line = cssclassConvert(line, colorClass, " color");
			if (All_SYS)
				System.out.println("line::" + line);

//            if(line.contains("cssclass")) {
//                Matcher m = p.matcher(line);
//                String css = "";
//                while (m.find()) {
//                    css = m.group(1);
//                    if(!css.isEmpty())
//                        line = line.replace(css, "#1");
//                }
//
//                if(!css.isEmpty()) {
//                    if(css.contains("expr:")) {
//                        Matcher cm = cssClass.matcher(line);
//                        while (cm.find()) {
//                            String bac = cm.group(1);
//                            line = line.replace("background=\"" + bac + "\"", "");
//                            if(bac.startsWith("expr:")) bac = bac.replace("expr:", "");
//                            css += "," + bac;
//                            line = line.replace("#1", css);
//                        }
//                    }else {
//                        Matcher cm = cssClass.matcher(line);
//                        while (cm.find()) {
//                            String bac = cm.group(1);
//                            line = line.replace("#1", bac);
//                        }
//                    }
//                }
//            }else {
//                line = line.replace("background", "cssclass");
//            }
//            System.out.println("line :: " + line);
		} else if (line.contains(" color=\"")) {
			line = cssclassConvert(line, colorClass, " color");
		} else if (line.contains(" background=\"")) {
			line = cssclassConvert(line, cssClass, " background");
		}
//        if(line.contains(" color=\"")) {
//            Matcher coM = colorClass.matcher(line);
//            while(coM.find()) {
//                String color = coM.group(1);
//                line = line.replace(" color=\"" + color + "\"", "");
//                if(color.contains("expr:")) {
//
//                }else {
//
//                }
//            }
//        }
		return line;
	}

	public static String cssclassConvert(String line, Pattern findP, String property) {
		if (line.contains("cssclass")) {
			Pattern p = Pattern.compile("\\s*<Cell.*cssclass=\"([^\"]*)\"");
			Matcher m = p.matcher(line);
			String css = "";
			while (m.find()) {
				css = m.group(1);
				if (!css.isEmpty())
					line = line.replace(css, "#1");
			}

			if (!css.isEmpty()) {
				String bac = "";
				if (css.contains("expr:")) {
					Matcher cm = findP.matcher(line);
////왜 background가 안되냐
					while (cm.find()) {
						bac = cm.group(1);
						line = line.replace(property + "=\"" + bac + "\"", " ");
						if (bac.startsWith("expr:")) bac = bac.replace("expr:", "");
						css += "+&quot;,&quot;+" + bac;
						line = line.replace("#1", css);
					}
				} else {
					Matcher cm = findP.matcher(line);
					while (cm.find()) {
						bac = cm.group(1);
						line = line.replace("#1", bac);
					}
				}
				if (bac.isEmpty()) {
					line = line.replace("#1", css);
				}
			}
		} else {
			line = line.replace(property, " cssclass");
		}

		if (line.contains(" color=\"")) {
			line = line.replace("#000000", "").replace("#e40000", "cellredFC");
		}
		return line;
	}
}